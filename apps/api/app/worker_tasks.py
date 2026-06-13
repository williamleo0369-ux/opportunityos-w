from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.celery_app import celery_app
from app.schemas import SearchRequest, SearchTask
from app.services.database_store import (
    load_task_payload,
    persist_pipeline_result,
    upsert_task_payload,
)
from app.services.pipeline import run_pipeline


class SearchTaskCancelled(Exception):
    pass


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def load_task(task_id: str) -> SearchTask:
    payload = load_task_payload(task_id)
    if payload is None:
        raise RuntimeError(f"Search task {task_id} does not exist")
    return SearchTask.model_validate(payload)


def save_task(task: SearchTask) -> None:
    upsert_task_payload(task.model_dump(mode="json"))


def update_task(
    task_id: str,
    *,
    status: str,
    progress: int,
    current_step: str,
    error_message: str | None = None,
) -> SearchTask:
    task = load_task(task_id)
    if task.status == "cancelled":
        raise SearchTaskCancelled()
    task.status = status  # type: ignore[assignment]
    task.progress = max(0, min(100, progress))
    task.current_step = current_step  # type: ignore[assignment]
    task.error_message = error_message
    task.updated_at = utc_now()
    save_task(task)
    return task


def mark_terminal_failure(task_id: str, error_message: str) -> None:
    payload = load_task_payload(task_id)
    if payload is None:
        return
    task = SearchTask.model_validate(payload)
    if task.status == "cancelled":
        return
    now = utc_now()
    task.status = "failed"
    task.current_step = "failed"
    task.progress = 100
    task.error_message = error_message[:500]
    task.finished_at = now
    task.updated_at = now
    save_task(task)


@celery_app.task(name="opportunity_os.run_search")
def run_search_task(
    request_payload: dict[str, Any],
    task_id: str,
    user_id: str,
) -> dict[str, str | None]:
    request = SearchRequest.model_validate(request_payload)
    initial_task = load_task(task_id)

    def progress_callback(step: str, progress: int) -> None:
        update_task(
            task_id,
            status=step,
            current_step=step,
            progress=progress,
        )

    try:
        if initial_task.status == "cancelled":
            raise SearchTaskCancelled()
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
        latest = load_task(task_id)
        if latest.status == "cancelled":
            raise SearchTaskCancelled()
        task.created_at = initial_task.created_at
        task.started_at = initial_task.started_at
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
        return {
            "task_id": task.id,
            "status": task.status,
            "opportunity_id": opportunity.id,
            "report_id": report.id,
        }
    except SearchTaskCancelled:
        return {
            "task_id": task_id,
            "status": "cancelled",
            "opportunity_id": None,
            "report_id": None,
        }
    except Exception as exc:
        mark_terminal_failure(task_id, str(exc))
        raise
