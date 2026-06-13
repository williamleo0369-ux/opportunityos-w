from __future__ import annotations

import os
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from time import perf_counter
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

from fastapi import Cookie, Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.schemas import (
    AdminLlmSettingsRequest,
    AdminUserRecord,
    AdminUserUpdate,
    Competitor,
    ApiLog,
    AuthResponse,
    InnovationIdea,
    LoginRequest,
    Opportunity,
    OpportunityDetail,
    PainPoint,
    Patent,
    Report,
    ReportRequest,
    RegisterRequest,
    SaveRequest,
    SearchRequest,
    SearchResponse,
    SearchTask,
    SourceCredentialRequest,
    SourceHealthSchedulerRequest,
    SupplyChainItem,
    TrendData,
    User,
    UserUsage,
)
from app.services.persistence import build_state_payload, load_state, save_state, store_status
from app.services.database_store import (
    DuplicateUserError,
    QuotaExceededError,
    append_api_log,
    create_user_payload,
    delete_saved_payload,
    load_api_logs,
    load_saved_payloads,
    load_task_payload,
    load_task_payloads,
    load_user_payload,
    load_user_payload_by_email,
    load_user_payloads,
    persist_pipeline_result,
    replace_source_health_history,
    reserve_search_task,
    upsert_report_payload,
    upsert_saved_payload,
    upsert_task_payload,
    upsert_user_payload,
    user_usage,
)
from app.services.auth import (
    DUMMY_PASSWORD_HASH,
    SESSION_TTL_DAYS,
    create_session_token,
    hash_password,
    verify_password,
    verify_session_token,
)
from app.services.data_export import data_export_json, data_export_zip, export_timestamp
from app.services.exporters import (
    docx_bytes,
    download_content_disposition,
    markdown_bytes,
    pdf_bytes,
    safe_filename,
    xlsx_bytes,
)
from app.services.data_quality import build_data_quality
from app.services.health_scheduler import SourceHealthScheduler
from app.services.pipeline import build_report, run_pipeline
from app.services.real_sources import probe_1688_supply_status
from app.services.source_credentials import (
    CredentialDecryptionError,
    clear_1688_cookie,
    load_1688_cookie,
    load_1688_metadata,
    save_1688_cookie,
)
from app.services.source_health import get_source_health
from app.services.system_settings import (
    clear_llm_settings,
    llm_settings_status,
    save_llm_settings,
)
from app.services.ai_agent import test_llm_connection

app = FastAPI(title="OpportunityOS API", version="0.1.0")

CORS_ORIGINS = [
    item.strip()
    for item in os.getenv(
        "OPPORTUNITY_OS_CORS_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000",
    ).split(",")
    if item.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

state = load_state()
state_lock = threading.RLock()
SEARCH_WORKER_COUNT = int(os.getenv("OPPORTUNITY_OS_SEARCH_WORKERS", "2"))
TASK_QUEUE_MODE = os.getenv("OPPORTUNITY_OS_TASK_QUEUE", "local").strip().lower()
if TASK_QUEUE_MODE not in {"local", "celery"}:
    TASK_QUEUE_MODE = "local"
REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0").strip()
search_executor = ThreadPoolExecutor(max_workers=SEARCH_WORKER_COUNT) if TASK_QUEUE_MODE == "local" else None
tasks: dict[str, SearchTask] = state["tasks"]
opportunities: dict[str, Opportunity] = state["opportunities"]
trends: dict[str, list[TrendData]] = state["trends"]
patents: dict[str, list[Patent]] = state["patents"]
competitors: dict[str, list[Competitor]] = state["competitors"]
pain_points: dict[str, list[PainPoint]] = state["pain_points"]
supply_chain: dict[str, list[SupplyChainItem]] = state["supply_chain"]
innovation_ideas: dict[str, list[InnovationIdea]] = state["innovation_ideas"]
reports: dict[str, Report] = state["reports"]
saved: dict[str, dict[str, str | None]] = state["saved"]
source_health_history: list[dict[str, object]] = state["source_health_history"]
source_health_scheduler = SourceHealthScheduler()
TERMINAL_SEARCH_STATUSES = {"completed", "failed", "cancelled"}
active_search_tasks: dict[str, dict[str, str]] = {}
SESSION_COOKIE = "opportunity_os_session"
DEFAULT_SEARCH_QUOTA = int(os.getenv("OPPORTUNITY_OS_DEFAULT_SEARCH_QUOTA_DAILY", "20"))
DEFAULT_REPORT_QUOTA = int(os.getenv("OPPORTUNITY_OS_DEFAULT_REPORT_QUOTA_MONTHLY", "100"))
BOOTSTRAP_ADMIN_USERNAME = os.getenv("OPPORTUNITY_OS_BOOTSTRAP_ADMIN_USERNAME", "admin").strip() or "admin"
BOOTSTRAP_ADMIN_PASSWORD = os.getenv("OPPORTUNITY_OS_BOOTSTRAP_ADMIN_PASSWORD", "admin1212").strip() or "admin1212"
BOOTSTRAP_ADMIN_EMAIL = (
    os.getenv("OPPORTUNITY_OS_BOOTSTRAP_ADMIN_EMAIL", "admin@opportunityos.local").strip().lower()
    or "admin@opportunityos.local"
)


class SearchTaskCancelled(Exception):
    pass


def persist() -> None:
    with state_lock:
        save_state(
            tasks=tasks,
            opportunities=opportunities,
            trends=trends,
            patents=patents,
            competitors=competitors,
            pain_points=pain_points,
            supply_chain=supply_chain,
            innovation_ideas=innovation_ideas,
            reports=reports,
            saved=saved,
            source_health_history=source_health_history,
        )


def sync_state_from_database() -> None:
    next_state = load_state()
    with state_lock:
        for target, source in [
            (tasks, next_state["tasks"]),
            (opportunities, next_state["opportunities"]),
            (trends, next_state["trends"]),
            (patents, next_state["patents"]),
            (competitors, next_state["competitors"]),
            (pain_points, next_state["pain_points"]),
            (supply_chain, next_state["supply_chain"]),
            (innovation_ideas, next_state["innovation_ideas"]),
            (reports, next_state["reports"]),
            (saved, next_state["saved"]),
        ]:
            target.clear()
            target.update(source)
        source_health_history[:] = next_state["source_health_history"]


def safe_broker_url() -> str:
    parts = urlsplit(REDIS_URL)
    hostname = parts.hostname or ""
    port = f":{parts.port}" if parts.port else ""
    username = f"{parts.username}@" if parts.username else ""
    return urlunsplit((parts.scheme, f"{username}{hostname}{port}", parts.path, parts.query, parts.fragment))


def celery_worker_count() -> int:
    if TASK_QUEUE_MODE != "celery":
        return SEARCH_WORKER_COUNT
    try:
        from app.celery_app import celery_app

        replies = celery_app.control.inspect(timeout=0.5).ping() or {}
        return len(replies)
    except Exception:
        return 0


@app.middleware("http")
async def refresh_distributed_state(request: Request, call_next):
    started_at = perf_counter()
    if TASK_QUEUE_MODE == "celery" and request.url.path.startswith("/api/"):
        sync_state_from_database()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    finally:
        if request.url.path.startswith("/api/"):
            session = verify_session_token(request.cookies.get(SESSION_COOKIE, ""))
            user_id = str(session["sub"]) if session else None
            try:
                append_api_log(
                    {
                        "id": str(uuid4()),
                        "user_id": user_id,
                        "endpoint": request.url.path,
                        "method": request.method,
                        "status_code": status_code,
                        "request_body": {
                            "query": dict(request.query_params),
                            "body_logging": "omitted_to_protect_credentials",
                        },
                        "response_time_ms": round((perf_counter() - started_at) * 1000),
                        "created_at": utc_now().isoformat(),
                    }
                )
            except Exception:
                pass


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def public_user(payload: dict[str, object]) -> User:
    return User.model_validate(payload)


def load_user_payload_by_login(identifier: str) -> dict[str, object] | None:
    normalized = identifier.strip().lower()
    if not normalized:
        return None
    payload = load_user_payload_by_email(normalized)
    if payload:
        return payload
    for account in load_user_payloads():
        if str(account.get("username", "")).strip().lower() == normalized:
            return account
    return None


def ensure_bootstrap_admin() -> None:
    now = utc_now().isoformat()
    payload = load_user_payload_by_login(BOOTSTRAP_ADMIN_USERNAME)
    if payload is None:
        payload = load_user_payload_by_email(BOOTSTRAP_ADMIN_EMAIL)
    if payload is None:
        payload = {
            "id": str(uuid4()),
            "created_at": now,
        }
    payload.update(
        {
            "email": BOOTSTRAP_ADMIN_EMAIL,
            "password_hash": hash_password(BOOTSTRAP_ADMIN_PASSWORD),
            "username": BOOTSTRAP_ADMIN_USERNAME,
            "avatar_url": payload.get("avatar_url"),
            "plan": "pro",
            "role": "admin",
            "is_active": True,
            "search_quota_daily": DEFAULT_SEARCH_QUOTA,
            "report_quota_monthly": DEFAULT_REPORT_QUOTA,
            "updated_at": now,
        }
    )
    upsert_user_payload(payload)


def usage_for_user(user: User) -> UserUsage:
    usage = user_usage(user.id)
    return UserUsage(
        searches_today=usage["searches_today"],
        reports_this_month=usage["reports_this_month"],
        search_remaining=max(0, user.search_quota_daily - usage["searches_today"]),
        report_remaining=max(0, user.report_quota_monthly - usage["reports_this_month"]),
    )


def set_session_cookie(response: Response, user_id: str) -> None:
    secure_cookie = os.getenv("OPPORTUNITY_OS_SECURE_COOKIES", "").lower() in {"1", "true", "yes"}
    same_site = os.getenv("OPPORTUNITY_OS_COOKIE_SAMESITE", "lax").strip().lower()
    if same_site not in {"lax", "strict", "none"}:
        same_site = "lax"
    if same_site == "none" and not secure_cookie:
        same_site = "lax"
    response.set_cookie(
        key=SESSION_COOKIE,
        value=create_session_token(user_id),
        max_age=SESSION_TTL_DAYS * 86400,
        httponly=True,
        samesite=same_site,  # type: ignore[arg-type]
        secure=secure_cookie,
        path="/",
    )


def current_user(
    session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> User:
    if not session_token:
        raise HTTPException(status_code=401, detail="请先登录")
    session = verify_session_token(session_token)
    if not session:
        raise HTTPException(status_code=401, detail="会话已失效，请重新登录")
    payload = load_user_payload(str(session["sub"]))
    if payload is None:
        raise HTTPException(status_code=401, detail="账户不存在")
    user = public_user(payload)
    if not user.is_active:
        raise HTTPException(status_code=403, detail="账户已停用，请联系管理员")
    return user


def require_admin(user: User = Depends(current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="仅管理员可访问")
    return user


def require_task_owner(task_id: str, user: User) -> SearchTask:
    task = tasks.get(task_id)
    if task is None or task.user_id != user.id:
        raise HTTPException(status_code=404, detail="Search task not found")
    return task


def require_opportunity_owner(opportunity_id: str, user: User) -> Opportunity:
    opportunity = opportunities.get(opportunity_id)
    if opportunity is None or opportunity.user_id != user.id:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    return opportunity


def require_report_owner(report_id: str, user: User) -> Report:
    report = reports.get(report_id)
    if report is None or report.user_id != user.id:
        raise HTTPException(status_code=404, detail="Report not found")
    return report


def current_state_payload(user_id: str) -> dict[str, object]:
    with state_lock:
        user_tasks = {key: value for key, value in tasks.items() if value.user_id == user_id}
        user_opportunities = {
            key: value for key, value in opportunities.items() if value.user_id == user_id
        }
        opportunity_ids = set(user_opportunities)
        user_reports = {key: value for key, value in reports.items() if value.user_id == user_id}
        return build_state_payload(
            tasks=user_tasks,
            opportunities=user_opportunities,
            trends={key: value for key, value in trends.items() if key in opportunity_ids},
            patents={key: value for key, value in patents.items() if key in opportunity_ids},
            competitors={key: value for key, value in competitors.items() if key in opportunity_ids},
            pain_points={key: value for key, value in pain_points.items() if key in opportunity_ids},
            supply_chain={key: value for key, value in supply_chain.items() if key in opportunity_ids},
            innovation_ideas={key: value for key, value in innovation_ideas.items() if key in opportunity_ids},
            reports=user_reports,
            saved={
                f"{user_id}:{key}": value
                for key, value in load_saved_payloads(user_id).items()
            },
            source_health_history=[],
        )


def update_search_task(task_id: str, *, status: str, progress: int, current_step: str, error_message: str | None = None) -> None:
    with state_lock:
        task = tasks.get(task_id)
        if task is None:
            return
        task.status = status  # type: ignore[assignment]
        task.progress = max(0, min(100, progress))
        task.current_step = current_step  # type: ignore[assignment]
        task.error_message = error_message
        task.updated_at = utc_now()
        if status in TERMINAL_SEARCH_STATUSES:
            task.finished_at = task.updated_at
        payload = task.model_dump(mode="json")
    upsert_task_payload(payload)


def mark_active_search_task(task_id: str, **updates: str) -> None:
    with state_lock:
        current = active_search_tasks.get(task_id, {})
        active_search_tasks[task_id] = {**current, **updates}


def search_queue_status(user_id: str | None = None) -> dict[str, object]:
    if TASK_QUEUE_MODE == "celery":
        stored_tasks = [
            SearchTask.model_validate(payload)
            for payload in load_task_payloads().values()
            if user_id is None or payload.get("user_id") == user_id
        ]
        active_rows = [
            {
                "id": task.id,
                "keyword": task.keyword,
                "state": "queued" if task.status == "pending" else "running",
                "queued_at": task.created_at.isoformat(),
                "started_at": task.started_at.isoformat() if task.status != "pending" else None,
            }
            for task in stored_tasks
            if task.status not in TERMINAL_SEARCH_STATUSES
        ]
        observed_worker_count = celery_worker_count()
        recently_running = any(
            task.status != "pending"
            and (utc_now() - task.updated_at).total_seconds() < 300
            for task in stored_tasks
            if task.status not in TERMINAL_SEARCH_STATUSES
        )
        worker_count = max(observed_worker_count, 1 if recently_running else 0)
        return {
            "mode": "celery",
            "broker_url": safe_broker_url(),
            "worker_count": worker_count,
            "active_count": len(active_rows),
            "queued_count": sum(1 for item in active_rows if item["state"] == "queued"),
            "running_count": sum(1 for item in active_rows if item["state"] == "running"),
            "stale_non_terminal_count": sum(
                1
                for task in stored_tasks
                if task.status not in TERMINAL_SEARCH_STATUSES
                and worker_count == 0
                and (utc_now() - task.updated_at).total_seconds() >= 300
            ),
            "active_tasks": active_rows,
        }

    with state_lock:
        active_rows = [
            {
                "id": task_id,
                "keyword": item.get("keyword", ""),
                "state": item.get("state", "queued"),
                "queued_at": item.get("queued_at"),
                "started_at": item.get("started_at"),
            }
            for task_id, item in active_search_tasks.items()
        ]
        stale_rows = [
            task
            for task in tasks.values()
            if task.status not in TERMINAL_SEARCH_STATUSES
            and task.id not in active_search_tasks
            and (user_id is None or task.user_id == user_id)
        ]
        if user_id is not None:
            allowed_ids = {task.id for task in tasks.values() if task.user_id == user_id}
            active_rows = [row for row in active_rows if row["id"] in allowed_ids]
    return {
        "mode": "local",
        "broker_url": None,
        "worker_count": SEARCH_WORKER_COUNT,
        "active_count": len(active_rows),
        "queued_count": sum(1 for item in active_rows if item["state"] == "queued"),
        "running_count": sum(1 for item in active_rows if item["state"] == "running"),
        "stale_non_terminal_count": len(stale_rows),
        "active_tasks": active_rows,
    }


def recover_interrupted_search_tasks() -> int:
    now = utc_now()
    changed = 0
    with state_lock:
        for task in tasks.values():
            if task.status in TERMINAL_SEARCH_STATUSES:
                continue
            task.status = "failed"
            task.current_step = "failed"
            task.progress = 100
            task.finished_at = now
            task.updated_at = now
            task.error_message = "API 进程重启前后台搜索未完成，任务已标记为失败，可点击重试重新进入队列。"
            changed += 1
    if changed:
        persist()
    return changed


def search_task_is_cancelled(task_id: str) -> bool:
    if TASK_QUEUE_MODE == "celery":
        payload = load_task_payload(task_id)
        return bool(payload and payload.get("status") == "cancelled")
    with state_lock:
        return tasks.get(task_id).status == "cancelled" if task_id in tasks else False


def enqueue_search_task(
    request: SearchRequest,
    user_id: str,
    *,
    quota_user: User | None = None,
) -> SearchResponse:
    task_id = str(uuid4())
    created_at = utc_now()
    task = SearchTask(
        id=task_id,
        user_id=user_id,
        keyword=request.keyword,
        industry=request.industry,
        target_market=request.target_market,
        language=request.language,
        status="pending",
        progress=1,
        current_step="pending",
        started_at=created_at,
        finished_at=None,
        created_at=created_at,
        updated_at=created_at,
    )
    with state_lock:
        tasks[task.id] = task
        if TASK_QUEUE_MODE == "local":
            active_search_tasks[task.id] = {
                "keyword": request.keyword,
                "state": "queued",
                "queued_at": created_at.isoformat(),
            }
    try:
        if quota_user:
            reserve_search_task(
                task.model_dump(mode="json"),
                user_id=user_id,
                search_quota_daily=quota_user.search_quota_daily,
                report_quota_monthly=quota_user.report_quota_monthly,
            )
        else:
            upsert_task_payload(task.model_dump(mode="json"))
    except QuotaExceededError as exc:
        with state_lock:
            tasks.pop(task.id, None)
            active_search_tasks.pop(task.id, None)
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    if TASK_QUEUE_MODE == "celery":
        try:
            from app.worker_tasks import run_search_task as celery_run_search_task

            celery_run_search_task.apply_async(
                args=[request.model_dump(mode="json"), task.id, user_id],
                task_id=task.id,
            )
        except Exception as exc:
            update_search_task(
                task.id,
                status="failed",
                current_step="failed",
                progress=100,
                error_message=f"Unable to enqueue Redis task: {exc}",
            )
            raise HTTPException(status_code=503, detail="Search queue is unavailable") from exc
    elif search_executor is not None:
        search_executor.submit(run_search_task, request, task.id)
    return SearchResponse(task_id=task.id, status=task.status, opportunity_id=None)


def run_search_task(request: SearchRequest, task_id: str) -> None:
    def progress_callback(step: str, progress: int) -> None:
        if search_task_is_cancelled(task_id):
            raise SearchTaskCancelled()
        update_search_task(task_id, status=step, current_step=step, progress=progress)

    try:
        mark_active_search_task(task_id, state="running", started_at=utc_now().isoformat())
        if search_task_is_cancelled(task_id):
            raise SearchTaskCancelled()
        with state_lock:
            queued_task = tasks.get(task_id)
            if queued_task is None:
                raise RuntimeError("Queued search task no longer exists")
            user_id = queued_task.user_id
        (
            task,
            opportunity,
            trend_rows,
            patent_rows,
            competitor_rows,
            pain_rows,
            supply_rows,
            idea_rows,
            report,
        ) = run_pipeline(
            request,
            task_id,
            user_id=user_id,
            progress_callback=progress_callback,
        )
        if search_task_is_cancelled(task_id):
            raise SearchTaskCancelled()
        with state_lock:
            tasks[task.id] = task
            opportunities[opportunity.id] = opportunity
            trends[opportunity.id] = trend_rows
            patents[opportunity.id] = patent_rows
            competitors[opportunity.id] = competitor_rows
            pain_points[opportunity.id] = pain_rows
            supply_chain[opportunity.id] = supply_rows
            innovation_ideas[opportunity.id] = idea_rows
            reports[report.id] = report
        persist_pipeline_result(
            task=task.model_dump(mode="json"),
            opportunity=opportunity.model_dump(mode="json"),
            trends=[row.model_dump(mode="json") for row in trend_rows],
            patents=[row.model_dump(mode="json") for row in patent_rows],
            competitors=[row.model_dump(mode="json") for row in competitor_rows],
            pain_points=[row.model_dump(mode="json") for row in pain_rows],
            supply_chain=[row.model_dump(mode="json") for row in supply_rows],
            innovation_ideas=[row.model_dump(mode="json") for row in idea_rows],
            report=report.model_dump(mode="json"),
        )
    except SearchTaskCancelled:
        update_search_task(task_id, status="cancelled", current_step="cancelled", progress=100, error_message=None)
    except Exception as exc:
        update_search_task(task_id, status="failed", current_step="failed", progress=100, error_message=str(exc)[:500])
    finally:
        with state_lock:
            active_search_tasks.pop(task_id, None)


def record_source_health_snapshot(snapshot: dict[str, object], triggered_by: str = "manual") -> dict[str, object]:
    recorded = {**snapshot, "triggered_by": triggered_by}
    source_health_history.insert(0, recorded)
    del source_health_history[30:]
    replace_source_health_history(source_health_history)
    return recorded


def run_source_health_check(triggered_by: str) -> dict[str, object]:
    health = get_source_health(refresh=True)
    return record_source_health_snapshot(health, triggered_by=triggered_by)


def _credential_metadata(status: dict[str, object]) -> dict[str, object]:
    return {
        "status": status.get("status"),
        "available": bool(status.get("available")),
        "reason": status.get("reason"),
        "url": status.get("url"),
        "checked_at": utc_now().isoformat(),
    }


def account_1688_status(
    user_id: str,
    *,
    refresh: bool = False,
) -> tuple[dict[str, object], str]:
    metadata = load_1688_metadata(user_id)
    if metadata is not None:
        try:
            cookie = load_1688_cookie(user_id)
        except CredentialDecryptionError as exc:
            return {
                "available": False,
                "status": "encryption_error",
                "reason": str(exc),
                "url": None,
            }, "account"
        if not refresh:
            return metadata, "account"
        status = probe_1688_supply_status("pet water fountain", cookie=cookie)
        save_1688_cookie(user_id, cookie, _credential_metadata(status))
        return status, "account"
    source = "environment" if os.getenv("OPPORTUNITY_OS_1688_COOKIE", "").strip() else "none"
    return probe_1688_supply_status("pet water fountain"), source


def credential_1688_status(
    user_id: str,
    status: dict[str, object] | None = None,
    source: str | None = None,
) -> dict[str, object]:
    if status is None or source is None:
        status, source = account_1688_status(user_id)
    return {
        "source": source,
        "configured": source != "none",
        "available": bool(status.get("available")),
        "status": status.get("status"),
        "reason": status.get("reason"),
        "url": status.get("url"),
        "checked_at": status.get("checked_at"),
    }


def source_health_for_user(
    user_id: str,
    *,
    refresh: bool,
    base_health: dict[str, object] | None = None,
) -> dict[str, object]:
    base = base_health or get_source_health(refresh=refresh)
    health = {
        **base,
        "sources": [dict(item) for item in base["sources"]],
    }
    started_at = perf_counter()
    status_1688, source = account_1688_status(user_id, refresh=refresh)
    replacement = {
        "key": "1688",
        "label": "1688 Search HTML",
        "category": "supply",
        "status": status_1688.get("status", "missing_session"),
        "available": bool(status_1688.get("available")),
        "reason": status_1688.get("reason", ""),
        "latency_ms": round((perf_counter() - started_at) * 1000),
        "checked_at": utc_now().isoformat(),
        "credential_source": source,
    }
    health["sources"] = [
        replacement if item.get("key") == "1688" else item
        for item in health["sources"]
    ]
    sources = health["sources"]
    health["summary"] = {
        "ok": sum(1 for item in sources if item["status"] in {"ok", "configured"}),
        "guarded": sum(
            1
            for item in sources
            if item["status"] in {"guarded", "missing_session", "missing_credentials", "encryption_error"}
        ),
        "error": sum(1 for item in sources if item["status"] == "error"),
        "empty": sum(1 for item in sources if item["status"] in {"empty", "reachable_empty"}),
        "not_checked": sum(1 for item in sources if item["status"] == "not_checked"),
    }
    return health


source_health_scheduler.configure(lambda: run_source_health_check("scheduler"))


@app.on_event("startup")
def maybe_start_source_health_scheduler() -> None:
    ensure_bootstrap_admin()
    if TASK_QUEUE_MODE == "local":
        recover_interrupted_search_tasks()
    raw_interval = os.getenv("OPPORTUNITY_OS_SOURCE_HEALTH_INTERVAL_SECONDS", "").strip()
    if not raw_interval:
        return
    try:
        interval_seconds = int(raw_interval)
    except ValueError:
        return
    if interval_seconds >= 60:
        source_health_scheduler.start(interval_seconds=interval_seconds, run_immediately=False)


@app.on_event("shutdown")
def stop_source_health_scheduler() -> None:
    source_health_scheduler.stop()
    if search_executor is not None:
        search_executor.shutdown(wait=False, cancel_futures=False)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/auth/register", response_model=AuthResponse)
def register(request: RegisterRequest, response: Response) -> AuthResponse:
    if load_user_payload_by_email(request.email):
        raise HTTPException(status_code=409, detail="该邮箱已注册")
    now = utc_now()
    payload: dict[str, object] = {
        "id": str(uuid4()),
        "email": request.email.strip().lower(),
        "password_hash": hash_password(request.password),
        "username": request.username,
        "avatar_url": None,
        "plan": "starter",
        "role": (
            "admin"
            if request.email.strip().lower()
            in {
                item.strip().lower()
                for item in os.getenv("OPPORTUNITY_OS_ADMIN_EMAILS", "").split(",")
                if item.strip()
            }
            else "user"
        ),
        "is_active": True,
        "search_quota_daily": DEFAULT_SEARCH_QUOTA,
        "report_quota_monthly": DEFAULT_REPORT_QUOTA,
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
    }
    try:
        create_user_payload(payload)
        sync_state_from_database()
    except DuplicateUserError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    user = public_user(payload)
    set_session_cookie(response, user.id)
    return AuthResponse(user=user, usage=usage_for_user(user))


@app.post("/api/auth/login", response_model=AuthResponse)
def login(request: LoginRequest, response: Response) -> AuthResponse:
    payload = load_user_payload_by_login(request.email)
    password_hash = str(payload.get("password_hash", "")) if payload else DUMMY_PASSWORD_HASH
    password_valid = verify_password(request.password, password_hash)
    if payload is None or not password_valid:
        raise HTTPException(status_code=401, detail="账号或密码不正确")
    user = public_user(payload)
    if not user.is_active:
        raise HTTPException(status_code=403, detail="账户已停用，请联系管理员")
    set_session_cookie(response, user.id)
    return AuthResponse(user=user, usage=usage_for_user(user))


@app.post("/api/auth/logout")
def logout(response: Response) -> dict[str, str]:
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"status": "signed_out"}


@app.get("/api/auth/me", response_model=AuthResponse)
def get_me(user: User = Depends(current_user)) -> AuthResponse:
    return AuthResponse(user=user, usage=usage_for_user(user))


@app.get("/api/admin/users", response_model=list[AdminUserRecord])
def admin_list_users(admin: User = Depends(require_admin)) -> list[AdminUserRecord]:
    del admin
    records: list[AdminUserRecord] = []
    for payload in load_user_payloads():
        account = public_user(payload)
        account_tasks = [item for item in tasks.values() if item.user_id == account.id]
        account_reports = [item for item in reports.values() if item.user_id == account.id]
        latest_activity = load_api_logs(account.id, 1)
        records.append(
            AdminUserRecord(
                user=account,
                usage=usage_for_user(account),
                task_count=len(account_tasks),
                report_count=len(account_reports),
                last_active_at=latest_activity[0].get("created_at") if latest_activity else None,
            )
        )
    records.sort(key=lambda item: item.user.created_at, reverse=True)
    return records


@app.patch("/api/admin/users/{user_id}", response_model=AdminUserRecord)
def admin_update_user(
    user_id: str,
    request: AdminUserUpdate,
    admin: User = Depends(require_admin),
) -> AdminUserRecord:
    payload = load_user_payload(user_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    changes = request.model_dump(exclude_none=True)
    if user_id == admin.id and (
        changes.get("role") == "user" or changes.get("is_active") is False
    ):
        raise HTTPException(status_code=400, detail="不能停用或取消自己的管理员权限")
    payload.update(changes)
    payload["updated_at"] = utc_now().isoformat()
    upsert_user_payload(payload)
    account = public_user(payload)
    account_tasks = [item for item in tasks.values() if item.user_id == account.id]
    account_reports = [item for item in reports.values() if item.user_id == account.id]
    latest_activity = load_api_logs(account.id, 1)
    return AdminUserRecord(
        user=account,
        usage=usage_for_user(account),
        task_count=len(account_tasks),
        report_count=len(account_reports),
        last_active_at=latest_activity[0].get("created_at") if latest_activity else None,
    )


@app.get("/api/admin/settings/llm")
def admin_get_llm_settings(admin: User = Depends(require_admin)) -> dict[str, object]:
    del admin
    return llm_settings_status()


@app.put("/api/admin/settings/llm")
def admin_save_llm_settings(
    request: AdminLlmSettingsRequest,
    admin: User = Depends(require_admin),
) -> dict[str, object]:
    del admin
    try:
        return save_llm_settings(request.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/api/admin/settings/llm")
def admin_clear_llm_settings(admin: User = Depends(require_admin)) -> dict[str, object]:
    del admin
    return clear_llm_settings()


@app.post("/api/admin/settings/llm/test")
def admin_test_llm_settings(admin: User = Depends(require_admin)) -> dict[str, object]:
    del admin
    return test_llm_connection()


@app.get("/api/api-logs", response_model=list[ApiLog])
def list_api_activity(
    limit: int = Query(default=20, ge=1, le=100),
    user: User = Depends(current_user),
) -> list[ApiLog]:
    return [ApiLog.model_validate(item) for item in load_api_logs(user.id, limit)]


@app.get("/api/system/status")
def system_status(user: User = Depends(current_user)) -> dict[str, object]:
    source_health = source_health_for_user(user.id, refresh=False)
    source_map = {item["key"]: item for item in source_health["sources"]}
    ai_status = source_map["llm_agent"]
    status_1688 = source_map["1688"]
    enabled_sources = [
        "Google Suggest",
        "Amazon Suggest",
        "Wikimedia Pageviews/Search",
        "Google Patents",
        "Amazon Search HTML",
        "Amazon Product Page Reviews",
        "Reddit Search RSS",
        "Alibaba.com Search HTML",
        "EC21 B2B Market",
    ]
    guarded_sources = []
    pending_sources = ["LLM agent orchestration"]
    mode = "real_sources_with_multi_agent" if ai_status.get("available") else "real_sources_with_rule_fallback"
    if ai_status.get("available"):
        enabled_sources.append(f"Multi-Agent ({ai_status.get('provider')})")
        pending_sources = []
    else:
        guarded_sources.append(
            {
                "source": "LLM Agent",
                "status": ai_status.get("status", "missing_credentials"),
                "reason": ai_status.get("reason", "LLM provider is not configured."),
            }
        )
    if status_1688.get("available"):
        enabled_sources.append("1688 Search HTML")
    else:
        credential_source = str(status_1688.get("credential_source", "none"))
        guarded_sources.append(
            {
                "source": "1688 Search",
                "status": status_1688.get("status", "guarded"),
                "reason": status_1688.get("reason", "1688 is not available in the current runtime."),
            }
        )
        pending_sources.insert(
            0,
            "1688 session/cookie integration"
            if credential_source == "none"
            else "1688 session validation or collector compatibility",
        )
    user_opportunity_ids = {
        item.id for item in opportunities.values() if item.user_id == user.id
    }
    account_counts = {
        "tasks": sum(1 for item in tasks.values() if item.user_id == user.id),
        "opportunities": len(user_opportunity_ids),
        "reports": sum(1 for item in reports.values() if item.user_id == user.id),
        "saved": len(load_saved_payloads(user.id)),
        "patents": sum(len(patents.get(item_id, [])) for item_id in user_opportunity_ids),
        "competitors": sum(len(competitors.get(item_id, [])) for item_id in user_opportunity_ids),
        "pain_points": sum(len(pain_points.get(item_id, [])) for item_id in user_opportunity_ids),
        "suppliers": sum(len(supply_chain.get(item_id, [])) for item_id in user_opportunity_ids),
    }
    storage = store_status()
    storage["counts"] = account_counts
    return {
        "status": "ok",
        "storage": storage,
        "counts": {
            "tasks": account_counts["tasks"],
            "opportunities": account_counts["opportunities"],
            "reports": account_counts["reports"],
            "saved": account_counts["saved"],
            "source_health_checks": len(source_health_history),
        },
        "account": AuthResponse(user=user, usage=usage_for_user(user)).model_dump(mode="json"),
        "export_formats": ["markdown", "pdf", "excel", "word"],
        "data_export_formats": ["json", "zip"],
        "source_credentials": {
            "1688": credential_1688_status(
                user.id,
                status_1688,
                str(status_1688.get("credential_source", "none")),
            ),
        },
        "search_queue": search_queue_status(user.id),
        "pipeline": {
            "mode": mode,
            "enabled_sources": enabled_sources,
            "guarded_sources": guarded_sources,
            "pending_sources": pending_sources,
            "source_health": source_health,
            "source_health_scheduler": source_health_scheduler.status(),
        },
    }


@app.get("/api/source-health")
def source_health(refresh: bool = False, user: User = Depends(current_user)) -> dict[str, object]:
    base_health = get_source_health(refresh=refresh)
    if refresh:
        record_source_health_snapshot(base_health, triggered_by="manual")
    return source_health_for_user(user.id, refresh=refresh, base_health=base_health)


@app.get("/api/source-health/history")
def list_source_health_history(
    page_size: int = Query(default=10, ge=1, le=30),
    _user: User = Depends(current_user),
) -> list[dict[str, object]]:
    return source_health_history[:page_size]


@app.get("/api/source-health/scheduler")
def get_source_health_scheduler(_user: User = Depends(current_user)) -> dict[str, object]:
    return source_health_scheduler.status()


@app.post("/api/source-health/scheduler")
def start_source_health_scheduler(
    request: SourceHealthSchedulerRequest,
    _user: User = Depends(current_user),
) -> dict[str, object]:
    try:
        return source_health_scheduler.start(
            interval_seconds=request.interval_seconds,
            run_immediately=request.run_immediately,
        )
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/api/source-health/scheduler")
def stop_source_health_scheduler_endpoint(_user: User = Depends(current_user)) -> dict[str, object]:
    return source_health_scheduler.stop()


@app.post("/api/source-health/scheduler/run")
def run_source_health_scheduler_once(_user: User = Depends(current_user)) -> dict[str, object]:
    try:
        return source_health_scheduler.run_once()
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/data/export")
def export_data(
    format: str = "zip",
    user: User = Depends(current_user),
) -> Response:
    payload = current_state_payload(user.id)
    timestamp = export_timestamp()
    if format == "json":
        return Response(
            content=data_export_json(payload),
            media_type="application/json; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="opportunity-os-data-{timestamp}.json"'},
        )
    if format == "zip":
        return Response(
            content=data_export_zip(
                payload,
                {key: value for key, value in reports.items() if value.user_id == user.id},
            ),
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="opportunity-os-data-{timestamp}.zip"'},
        )
    raise HTTPException(status_code=400, detail="Unsupported export format")


@app.get("/api/source-credentials/1688")
def get_1688_credentials(user: User = Depends(current_user)) -> dict[str, object]:
    return credential_1688_status(user.id)


@app.post("/api/source-credentials/1688")
def set_1688_credentials(
    request: SourceCredentialRequest,
    user: User = Depends(current_user),
) -> dict[str, object]:
    status = probe_1688_supply_status("pet water fountain", cookie=request.cookie)
    save_1688_cookie(
        user.id,
        request.cookie,
        _credential_metadata(status),
    )
    return credential_1688_status(user.id, status, "account")


@app.delete("/api/source-credentials/1688")
def clear_1688_credentials(user: User = Depends(current_user)) -> dict[str, object]:
    clear_1688_cookie(user.id)
    return credential_1688_status(user.id)


@app.post("/api/search", response_model=SearchResponse)
def create_search(
    request: SearchRequest,
    user: User = Depends(current_user),
) -> SearchResponse:
    return enqueue_search_task(request, user_id=user.id, quota_user=user)


@app.get("/api/search-queue/status")
def get_search_queue_status(user: User = Depends(current_user)) -> dict[str, object]:
    return search_queue_status(user.id)


@app.get("/api/search/{task_id}", response_model=SearchTask)
def get_search(task_id: str, user: User = Depends(current_user)) -> SearchTask:
    return require_task_owner(task_id, user)


@app.post("/api/search/{task_id}/cancel", response_model=SearchTask)
def cancel_search(task_id: str, user: User = Depends(current_user)) -> SearchTask:
    with state_lock:
        task = require_task_owner(task_id, user)
        if task.status in TERMINAL_SEARCH_STATUSES:
            return task
        task.status = "cancelled"
        task.current_step = "cancelled"
        task.progress = 100
        task.finished_at = utc_now()
        task.updated_at = utc_now()
        payload = task.model_dump(mode="json")
    upsert_task_payload(payload)
    if TASK_QUEUE_MODE == "celery":
        try:
            from app.celery_app import celery_app

            celery_app.control.revoke(task_id, terminate=False)
        except Exception:
            pass
    return task


@app.post("/api/search/{task_id}/retry", response_model=SearchResponse)
def retry_search(task_id: str, user: User = Depends(current_user)) -> SearchResponse:
    with state_lock:
        task = require_task_owner(task_id, user)
        request = SearchRequest(
            keyword=task.keyword,
            industry=task.industry,
            target_market=task.target_market,
            language=task.language,
        )
    return enqueue_search_task(request, user_id=user.id, quota_user=user)


@app.get("/api/search-tasks", response_model=list[SearchTask])
def list_search_tasks(
    status: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user: User = Depends(current_user),
) -> list[SearchTask]:
    rows = [row for row in tasks.values() if row.user_id == user.id]
    if status:
        rows = [row for row in rows if row.status == status]
    rows.sort(key=lambda item: item.created_at, reverse=True)
    start = (page - 1) * page_size
    return rows[start : start + page_size]


@app.get("/api/opportunities", response_model=list[Opportunity])
def list_opportunities(
    keyword: str | None = None,
    industry: str | None = None,
    min_score: int | None = Query(default=None, ge=0, le=100),
    recommendation_level: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user: User = Depends(current_user),
) -> list[Opportunity]:
    rows = [row for row in opportunities.values() if row.user_id == user.id]
    if keyword:
        rows = [row for row in rows if keyword.lower() in row.product_name.lower()]
    if industry:
        rows = [row for row in rows if industry.lower() in row.product_category.lower()]
    if min_score is not None:
        rows = [row for row in rows if row.opportunity_score >= min_score]
    if recommendation_level:
        rows = [row for row in rows if row.recommendation_level == recommendation_level]
    rows.sort(key=lambda item: item.created_at, reverse=True)
    start = (page - 1) * page_size
    return rows[start : start + page_size]


def patent_summary(opportunity_id: str) -> dict[str, int | str]:
    rows = patents.get(opportunity_id, [])
    active = sum(1 for item in rows if item.legal_status == "active")
    expired = sum(1 for item in rows if item.legal_status == "expired")
    expiring = sum(1 for item in rows if item.legal_status == "expiring_soon")
    high_risk = sum(1 for item in rows if item.risk_level == "high")
    risk_level = "high" if high_risk >= 3 else "medium" if active >= 3 else "low"
    return {
        "total": len(rows),
        "active": active,
        "expired": expired,
        "expiring_soon": expiring,
        "high_risk": high_risk,
        "risk_level": risk_level,
    }


def competitor_summary(opportunity_id: str) -> dict[str, float | int | str]:
    rows = competitors.get(opportunity_id, [])
    if not rows:
        return {
            "count": 0,
            "price_min": 0,
            "price_max": 0,
            "average_rating": 0,
            "review_total": 0,
            "competition_level": "unknown",
        }
    prices = [item.price for item in rows if item.price > 0]
    reviews = [item.review_count for item in rows]
    return {
        "count": len(rows),
        "price_min": min(prices) if prices else 0,
        "price_max": max(prices) if prices else 0,
        "average_rating": round(sum(item.rating for item in rows) / len(rows), 1),
        "review_total": sum(reviews),
        "competition_level": "high" if sum(reviews) > 40000 else "medium",
    }


@app.get("/api/opportunities/{opportunity_id}", response_model=OpportunityDetail)
def get_opportunity(
    opportunity_id: str,
    user: User = Depends(current_user),
) -> OpportunityDetail:
    opportunity = require_opportunity_owner(opportunity_id, user)
    report = next((item for item in reports.values() if item.opportunity_id == opportunity_id), None)
    trend_rows = trends.get(opportunity_id, [])
    patent_rows = patents.get(opportunity_id, [])
    competitor_rows = competitors.get(opportunity_id, [])
    pain_rows = pain_points.get(opportunity_id, [])
    supply_rows = supply_chain.get(opportunity_id, [])
    idea_rows = innovation_ideas.get(opportunity_id, [])
    return OpportunityDetail(
        opportunity=opportunity,
        trend_data=trend_rows,
        patents=patent_rows,
        competitors=competitor_rows,
        patent_summary=patent_summary(opportunity_id),
        competitor_summary=competitor_summary(opportunity_id),
        pain_points=pain_rows,
        supply_chain=supply_rows,
        innovation_ideas=idea_rows,
        data_quality=build_data_quality(
            trend_rows=trend_rows,
            patents=patent_rows,
            competitors=competitor_rows,
            pain_points=pain_rows,
            supply_chain=supply_rows,
            innovation_ideas=idea_rows,
            agent_result=report.agent_run if report else None,
        ),
        agent_run=report.agent_run if report else {},
        report_status=report.status if report else "missing",
        report_id=report.id if report else "",
    )


@app.get("/api/opportunities/{opportunity_id}/trends", response_model=list[TrendData])
def get_trends(
    opportunity_id: str,
    user: User = Depends(current_user),
) -> list[TrendData]:
    require_opportunity_owner(opportunity_id, user)
    return trends.get(opportunity_id, [])


@app.get("/api/opportunities/{opportunity_id}/patents")
def get_patents(
    opportunity_id: str,
    user: User = Depends(current_user),
) -> dict[str, object]:
    require_opportunity_owner(opportunity_id, user)
    return {"patents": patents.get(opportunity_id, []), "patent_summary": patent_summary(opportunity_id)}


@app.get("/api/patents/{patent_id}", response_model=Patent)
def get_patent(patent_id: str, user: User = Depends(current_user)) -> Patent:
    owned_ids = {item.id for item in opportunities.values() if item.user_id == user.id}
    for opportunity_id, rows in patents.items():
        if opportunity_id not in owned_ids:
            continue
        for item in rows:
            if item.id == patent_id:
                return item
    raise HTTPException(status_code=404, detail="Patent not found")


@app.get("/api/opportunities/{opportunity_id}/competitors")
def get_competitors(
    opportunity_id: str,
    user: User = Depends(current_user),
) -> dict[str, object]:
    require_opportunity_owner(opportunity_id, user)
    return {"competitor_list": competitors.get(opportunity_id, []), **competitor_summary(opportunity_id)}


@app.get("/api/opportunities/{opportunity_id}/pain-points")
def get_pain_points(
    opportunity_id: str,
    user: User = Depends(current_user),
) -> dict[str, object]:
    require_opportunity_owner(opportunity_id, user)
    rows = pain_points.get(opportunity_id, [])
    return {"top_pain_points": rows, "example_reviews": [review for row in rows for review in row.example_reviews[:1]], "ai_summary": rows[0].ai_summary if rows else ""}


@app.get("/api/opportunities/{opportunity_id}/supply-chain")
def get_supply_chain(
    opportunity_id: str,
    user: User = Depends(current_user),
) -> dict[str, object]:
    require_opportunity_owner(opportunity_id, user)
    rows = supply_chain.get(opportunity_id, [])
    prices = [item.unit_price_min for item in rows] + [item.unit_price_max for item in rows]
    moqs = [item.moq for item in rows]
    return {
        "items": rows,
        "supplier_count": len(rows),
        "price_range": [min(prices), max(prices)] if prices else [],
        "moq_range": [min(moqs), max(moqs)] if moqs else [],
        "main_locations": sorted({item.location for item in rows}),
        "maturity_score": round(sum(item.production_maturity_score for item in rows) / len(rows)) if rows else 0,
    }


@app.get("/api/opportunities/{opportunity_id}/innovation-ideas", response_model=list[InnovationIdea])
def get_innovation_ideas(
    opportunity_id: str,
    user: User = Depends(current_user),
) -> list[InnovationIdea]:
    require_opportunity_owner(opportunity_id, user)
    return innovation_ideas.get(opportunity_id, [])


def rebuild_report_for_opportunity(opportunity: Opportunity, existing: Report | None = None) -> Report:
    task = tasks[opportunity.search_task_id]
    trend_rows = trends.get(opportunity.id, [])
    patent_rows = patents.get(opportunity.id, [])
    competitor_rows = competitors.get(opportunity.id, [])
    pain_rows = pain_points.get(opportunity.id, [])
    supply_rows = supply_chain.get(opportunity.id, [])
    idea_rows = innovation_ideas.get(opportunity.id, [])
    if not trend_rows or not pain_rows or not idea_rows:
        raise HTTPException(status_code=400, detail="Opportunity evidence is incomplete; rerun the search task before regenerating the report.")
    report = build_report(
        task,
        opportunity,
        trend_rows[0],
        patent_rows,
        competitor_rows,
        pain_rows,
        supply_rows,
        idea_rows,
    )
    if existing:
        report.id = existing.id
        report.created_at = existing.created_at
        report.agent_run = existing.agent_run
    reports[report.id] = report
    upsert_report_payload(report.model_dump(mode="json"))
    return report


@app.post("/api/reports/generate")
def generate_report(
    request: ReportRequest,
    user: User = Depends(current_user),
) -> dict[str, str]:
    opportunity = require_opportunity_owner(request.opportunity_id, user)
    existing = next((item for item in reports.values() if item.opportunity_id == opportunity.id), None)
    if existing and not request.force and existing.data_quality_summary:
        return {"report_id": existing.id, "status": existing.status}
    if not existing and usage_for_user(user).report_remaining <= 0:
        raise HTTPException(status_code=429, detail="本月报告额度已用完")
    report = rebuild_report_for_opportunity(opportunity, existing=existing)
    return {"report_id": report.id, "status": report.status}


@app.post("/api/reports/{report_id}/refresh", response_model=Report)
def refresh_report(
    report_id: str,
    user: User = Depends(current_user),
) -> Report:
    existing = require_report_owner(report_id, user)
    opportunity = require_opportunity_owner(existing.opportunity_id, user)
    return rebuild_report_for_opportunity(opportunity, existing=existing)


@app.get("/api/reports", response_model=list[Report])
def list_reports(user: User = Depends(current_user)) -> list[Report]:
    return sorted(
        (item for item in reports.values() if item.user_id == user.id),
        key=lambda item: item.created_at,
        reverse=True,
    )


@app.get("/api/reports/{report_id}", response_model=Report)
def get_report(report_id: str, user: User = Depends(current_user)) -> Report:
    return require_report_owner(report_id, user)


@app.get("/api/reports/{report_id}/download")
def download_report(
    report_id: str,
    format: str = "markdown",
    user: User = Depends(current_user),
) -> Response:
    report = require_report_owner(report_id, user)
    if format not in {"markdown", "pdf", "excel", "word"}:
        raise HTTPException(status_code=400, detail="Unsupported format")
    exporters = {
        "markdown": (markdown_bytes, "text/markdown; charset=utf-8", "md"),
        "pdf": (pdf_bytes, "application/pdf", "pdf"),
        "excel": (xlsx_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "xlsx"),
        "word": (docx_bytes, "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "docx"),
    }
    exporter, media_type, extension = exporters[format]
    filename = safe_filename(report.report_title, extension)
    return Response(
        content=exporter(report),
        media_type=media_type,
        headers={"Content-Disposition": download_content_disposition(filename)},
    )


@app.post("/api/opportunities/{opportunity_id}/save")
def save_opportunity(
    opportunity_id: str,
    request: SaveRequest | None = None,
    user: User = Depends(current_user),
) -> dict[str, str]:
    require_opportunity_owner(opportunity_id, user)
    now = utc_now().isoformat()
    payload = {
        "user_id": user.id,
        "opportunity_id": opportunity_id,
        "note": request.note if request else None,
        "created_at": now,
    }
    saved[f"{user.id}:{opportunity_id}"] = payload
    upsert_saved_payload(user.id, opportunity_id, payload)
    return {"status": "saved", "opportunity_id": opportunity_id}


@app.delete("/api/opportunities/{opportunity_id}/save")
def unsave_opportunity(
    opportunity_id: str,
    user: User = Depends(current_user),
) -> dict[str, str]:
    require_opportunity_owner(opportunity_id, user)
    saved.pop(f"{user.id}:{opportunity_id}", None)
    delete_saved_payload(user.id, opportunity_id)
    return {"status": "removed", "opportunity_id": opportunity_id}


@app.get("/api/saved-opportunities", response_model=list[Opportunity])
def list_saved_opportunities(user: User = Depends(current_user)) -> list[Opportunity]:
    user_saved = load_saved_payloads(user.id)
    return [
        opportunities[item_id]
        for item_id in user_saved
        if item_id in opportunities and opportunities[item_id].user_id == user.id
    ]
    append_api_log,
    load_api_logs,
