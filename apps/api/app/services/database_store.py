from __future__ import annotations

import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import urlsplit, urlunsplit


DEFAULT_DATABASE_PATH = Path.home() / ".opportunity-os" / "opportunity-os.db"
DATABASE_ENV_KEYS = ("OPPORTUNITY_OS_DATABASE_URL", "DATABASE_URL")


def _normalize_database_url(value: str) -> str:
    if value.startswith("postgres://"):
        return f"postgresql://{value.removeprefix('postgres://')}"
    return value


def _is_supported_database_url(value: str) -> bool:
    return value.startswith(("sqlite:///", "postgresql://", "postgres://"))


def _resolve_database_url() -> str:
    for key in DATABASE_ENV_KEYS:
        value = os.getenv(key, "").strip()
        if _is_supported_database_url(value):
            return _normalize_database_url(value)

    configured_values = [os.getenv(key, "").strip() for key in DATABASE_ENV_KEYS if os.getenv(key, "").strip()]
    if configured_values:
        return configured_values[0]
    return f"sqlite:///{DEFAULT_DATABASE_PATH}"


DATABASE_URL = _resolve_database_url()
_INITIALIZE_LOCK = threading.RLock()
_DATABASE_INITIALIZED = False

MODEL_TABLES = {
    "tasks": "search_tasks",
    "opportunities": "opportunities",
    "reports": "reports",
}

LIST_TABLES = {
    "trends": "trend_data",
    "patents": "patents",
    "competitors": "competitors",
    "pain_points": "pain_points",
    "supply_chain": "supply_chain",
    "innovation_ideas": "innovation_ideas",
}


class QuotaExceededError(RuntimeError):
    pass


class DuplicateUserError(RuntimeError):
    pass


def database_backend() -> str:
    if DATABASE_URL.startswith("sqlite:///"):
        return "sqlite"
    if DATABASE_URL.startswith(("postgresql://", "postgres://")):
        return "postgresql"
    raise RuntimeError("OPPORTUNITY_OS_DATABASE_URL must use sqlite:/// or postgresql://")


def sqlite_path() -> Path:
    if database_backend() != "sqlite":
        raise RuntimeError("SQLite path requested for a non-SQLite database")
    raw_path = DATABASE_URL.removeprefix("sqlite:///")
    return Path(f"/{raw_path.lstrip('/')}" if raw_path.startswith("/") else raw_path).expanduser()


def safe_database_url() -> str:
    if database_backend() == "sqlite":
        return f"sqlite:///{sqlite_path()}"
    parts = urlsplit(DATABASE_URL)
    hostname = parts.hostname or ""
    port = f":{parts.port}" if parts.port else ""
    username = f"{parts.username}@" if parts.username else ""
    return urlunsplit((parts.scheme, f"{username}{hostname}{port}", parts.path, parts.query, parts.fragment))


@contextmanager
def connect() -> Iterator[Any]:
    backend = database_backend()
    if backend == "sqlite":
        path = sqlite_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(path, timeout=30)
        connection.execute("PRAGMA busy_timeout=30000")
        try:
            connection.execute("PRAGMA journal_mode=WAL")
        except sqlite3.OperationalError as exc:
            if "locked" not in str(exc).lower():
                connection.close()
                raise
        connection.execute("PRAGMA foreign_keys=ON")
    else:
        try:
            import psycopg
        except ImportError as exc:
            raise RuntimeError(
                "PostgreSQL storage requires psycopg. Install API requirements before starting the server."
            ) from exc
        connection = psycopg.connect(DATABASE_URL)
    try:
        yield connection
    finally:
        connection.close()


def _placeholder() -> str:
    return "?" if database_backend() == "sqlite" else "%s"


def _json_payload(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False)


def _upsert_payload(
    cursor: Any,
    *,
    table: str,
    key_column: str,
    key: str,
    payload: dict[str, Any],
) -> None:
    placeholder = _placeholder()
    cursor.execute(
        f"INSERT INTO {table} ({key_column}, payload) "
        f"VALUES ({placeholder}, {placeholder}) "
        f"ON CONFLICT ({key_column}) DO UPDATE SET payload = EXCLUDED.payload",
        (key, _json_payload(payload)),
    )


def initialize_database() -> None:
    global _DATABASE_INITIALIZED
    with _INITIALIZE_LOCK:
        if _DATABASE_INITIALIZED:
            return
        _initialize_database_locked()
        _DATABASE_INITIALIZED = True


def _initialize_database_locked() -> None:
    schema = [
        """
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            email TEXT NOT NULL UNIQUE,
            payload TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS search_tasks (
            id TEXT PRIMARY KEY,
            payload TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS opportunities (
            id TEXT PRIMARY KEY,
            payload TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS reports (
            id TEXT PRIMARY KEY,
            payload TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS trend_data (
            id TEXT PRIMARY KEY,
            opportunity_id TEXT NOT NULL,
            payload TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS patents (
            id TEXT PRIMARY KEY,
            opportunity_id TEXT NOT NULL,
            payload TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS competitors (
            id TEXT PRIMARY KEY,
            opportunity_id TEXT NOT NULL,
            payload TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS pain_points (
            id TEXT PRIMARY KEY,
            opportunity_id TEXT NOT NULL,
            payload TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS supply_chain (
            id TEXT PRIMARY KEY,
            opportunity_id TEXT NOT NULL,
            payload TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS innovation_ideas (
            id TEXT PRIMARY KEY,
            opportunity_id TEXT NOT NULL,
            payload TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS saved_opportunities (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            opportunity_id TEXT NOT NULL,
            payload TEXT NOT NULL,
            UNIQUE(user_id, opportunity_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS api_logs (
            id TEXT PRIMARY KEY,
            user_id TEXT,
            endpoint TEXT NOT NULL,
            method TEXT NOT NULL,
            status_code INTEGER NOT NULL,
            response_time_ms INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            payload TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS source_credentials (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            source TEXT NOT NULL,
            encrypted_secret TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            payload TEXT NOT NULL,
            UNIQUE(user_id, source)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS agent_runs (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            task_id TEXT NOT NULL,
            opportunity_id TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            payload TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS system_settings (
            key TEXT PRIMARY KEY,
            encrypted_secret TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            payload TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS source_health_history (
            position INTEGER PRIMARY KEY,
            payload TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS store_metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_trend_opportunity ON trend_data(opportunity_id)",
        "CREATE INDEX IF NOT EXISTS idx_patents_opportunity ON patents(opportunity_id)",
        "CREATE INDEX IF NOT EXISTS idx_competitors_opportunity ON competitors(opportunity_id)",
        "CREATE INDEX IF NOT EXISTS idx_pain_points_opportunity ON pain_points(opportunity_id)",
        "CREATE INDEX IF NOT EXISTS idx_supply_chain_opportunity ON supply_chain(opportunity_id)",
        "CREATE INDEX IF NOT EXISTS idx_innovation_ideas_opportunity ON innovation_ideas(opportunity_id)",
        "CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)",
        "CREATE INDEX IF NOT EXISTS idx_api_logs_user ON api_logs(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_source_credentials_user ON source_credentials(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_agent_runs_user ON agent_runs(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_agent_runs_opportunity ON agent_runs(opportunity_id)",
    ]
    with connect() as connection:
        for statement in schema:
            try:
                connection.execute(statement)
            except Exception:
                if "saved_opportunities" not in statement:
                    raise
        _migrate_saved_opportunities(connection)
        _migrate_api_logs(connection)
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_saved_user ON saved_opportunities(user_id)"
        )
        connection.commit()


def _table_columns(connection: Any, table: str) -> set[str]:
    if database_backend() == "sqlite":
        return {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})").fetchall()}
    rows = connection.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = 'public' AND table_name = %s",
        (table,),
    ).fetchall()
    return {str(row[0]) for row in rows}


def _migrate_saved_opportunities(connection: Any) -> None:
    columns = _table_columns(connection, "saved_opportunities")
    if not columns or {"id", "user_id", "opportunity_id", "payload"}.issubset(columns):
        return

    rows = connection.execute(
        "SELECT opportunity_id, payload FROM saved_opportunities"
    ).fetchall()
    connection.execute("DROP TABLE IF EXISTS saved_opportunities_v2")
    connection.execute(
        """
        CREATE TABLE saved_opportunities_v2 (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            opportunity_id TEXT NOT NULL,
            payload TEXT NOT NULL,
            UNIQUE(user_id, opportunity_id)
        )
        """
    )
    placeholder = _placeholder()
    for opportunity_id, raw_payload in rows:
        payload = json.loads(raw_payload)
        payload.setdefault("user_id", "legacy-demo")
        payload.setdefault("opportunity_id", opportunity_id)
        payload.setdefault("created_at", datetime.now(timezone.utc).isoformat())
        connection.execute(
            "INSERT INTO saved_opportunities_v2 "
            f"(id, user_id, opportunity_id, payload) VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder})",
            (
                f"legacy-demo:{opportunity_id}",
                "legacy-demo",
                opportunity_id,
                _json_payload(payload),
            ),
        )
    connection.execute("DROP TABLE saved_opportunities")
    connection.execute("ALTER TABLE saved_opportunities_v2 RENAME TO saved_opportunities")


def _migrate_api_logs(connection: Any) -> None:
    columns = _table_columns(connection, "api_logs")
    if columns and "created_at" not in columns:
        connection.execute("ALTER TABLE api_logs ADD COLUMN created_at TEXT")


def database_is_empty() -> bool:
    initialize_database()
    with connect() as connection:
        cursor = connection.execute("SELECT COUNT(*) FROM search_tasks")
        task_count = int(cursor.fetchone()[0])
        cursor = connection.execute("SELECT COUNT(*) FROM opportunities")
        opportunity_count = int(cursor.fetchone()[0])
        return task_count == 0 and opportunity_count == 0


def load_payload() -> dict[str, Any]:
    initialize_database()
    payload: dict[str, Any] = {
        "tasks": {},
        "opportunities": {},
        "trends": {},
        "patents": {},
        "competitors": {},
        "pain_points": {},
        "supply_chain": {},
        "innovation_ideas": {},
        "reports": {},
        "saved": {},
        "source_health_history": [],
    }
    with connect() as connection:
        for state_key, table in MODEL_TABLES.items():
            rows = connection.execute(f"SELECT id, payload FROM {table}").fetchall()
            payload[state_key] = {row[0]: json.loads(row[1]) for row in rows}

        for state_key, table in LIST_TABLES.items():
            rows = connection.execute(
                f"SELECT opportunity_id, payload FROM {table} ORDER BY opportunity_id, id"
            ).fetchall()
            grouped: dict[str, list[dict[str, Any]]] = {}
            for opportunity_id, raw_payload in rows:
                grouped.setdefault(opportunity_id, []).append(json.loads(raw_payload))
            payload[state_key] = grouped

        saved_rows = connection.execute(
            "SELECT id, payload FROM saved_opportunities"
        ).fetchall()
        payload["saved"] = {
            row_id: json.loads(raw_payload)
            for row_id, raw_payload in saved_rows
        }
        history_rows = connection.execute(
            "SELECT payload FROM source_health_history ORDER BY position"
        ).fetchall()
        payload["source_health_history"] = [json.loads(row[0]) for row in history_rows]
    return payload


def load_task_payload(task_id: str) -> dict[str, Any] | None:
    initialize_database()
    placeholder = _placeholder()
    with connect() as connection:
        row = connection.execute(
            f"SELECT payload FROM search_tasks WHERE id = {placeholder}",
            (task_id,),
        ).fetchone()
    return json.loads(row[0]) if row else None


def load_task_payloads() -> dict[str, dict[str, Any]]:
    initialize_database()
    with connect() as connection:
        rows = connection.execute("SELECT id, payload FROM search_tasks").fetchall()
    return {row[0]: json.loads(row[1]) for row in rows}


def load_user_payload(user_id: str) -> dict[str, Any] | None:
    initialize_database()
    placeholder = _placeholder()
    with connect() as connection:
        row = connection.execute(
            f"SELECT payload FROM users WHERE id = {placeholder}",
            (user_id,),
        ).fetchone()
    return json.loads(row[0]) if row else None


def load_user_payload_by_email(email: str) -> dict[str, Any] | None:
    initialize_database()
    placeholder = _placeholder()
    with connect() as connection:
        row = connection.execute(
            f"SELECT payload FROM users WHERE email = {placeholder}",
            (email.strip().lower(),),
        ).fetchone()
    return json.loads(row[0]) if row else None


def load_user_payloads() -> list[dict[str, Any]]:
    initialize_database()
    with connect() as connection:
        rows = connection.execute("SELECT payload FROM users").fetchall()
    return [json.loads(row[0]) for row in rows]


def upsert_user_payload(user: dict[str, Any]) -> None:
    initialize_database()
    placeholder = _placeholder()
    with connect() as connection:
        connection.execute(
            "INSERT INTO users (id, email, payload) "
            f"VALUES ({placeholder}, {placeholder}, {placeholder}) "
            "ON CONFLICT (id) DO UPDATE SET email = EXCLUDED.email, payload = EXCLUDED.payload",
            (str(user["id"]), str(user["email"]).lower(), _json_payload(user)),
        )
        connection.commit()


def create_user_payload(user: dict[str, Any]) -> bool:
    """Create an account and let only the first account claim legacy local data."""
    initialize_database()
    placeholder = _placeholder()
    with connect() as connection:
        if database_backend() == "sqlite":
            connection.execute("BEGIN IMMEDIATE")
        else:
            connection.execute("LOCK TABLE users IN EXCLUSIVE MODE")
        existing = connection.execute(
            f"SELECT id FROM users WHERE email = {placeholder}",
            (str(user["email"]).lower(),),
        ).fetchone()
        if existing:
            connection.rollback()
            raise DuplicateUserError("该邮箱已注册")
        is_first_user = int(connection.execute("SELECT COUNT(*) FROM users").fetchone()[0]) == 0
        connection.execute(
            "INSERT INTO users (id, email, payload) "
            f"VALUES ({placeholder}, {placeholder}, {placeholder})",
            (str(user["id"]), str(user["email"]).lower(), _json_payload(user)),
        )
        if is_first_user:
            _claim_legacy_workspace(connection, str(user["id"]))
        connection.commit()
        return is_first_user


def _claim_legacy_workspace(connection: Any, user_id: str) -> None:
    for table in ("search_tasks", "opportunities", "reports"):
        rows = connection.execute(f"SELECT id, payload FROM {table}").fetchall()
        for row_id, raw_payload in rows:
            payload = json.loads(raw_payload)
            if payload.get("user_id") not in {"demo-user", "legacy-demo"}:
                continue
            payload["user_id"] = user_id
            _upsert_payload(
                connection.cursor(),
                table=table,
                key_column="id",
                key=str(row_id),
                payload=payload,
            )

    rows = connection.execute(
        "SELECT id, opportunity_id, payload FROM saved_opportunities"
    ).fetchall()
    placeholder = _placeholder()
    for row_id, opportunity_id, raw_payload in rows:
        payload = json.loads(raw_payload)
        if payload.get("user_id") not in {"demo-user", "legacy-demo"}:
            continue
        payload["user_id"] = user_id
        payload["opportunity_id"] = opportunity_id
        connection.execute(
            f"DELETE FROM saved_opportunities WHERE id = {placeholder}",
            (row_id,),
        )
        connection.execute(
            "INSERT INTO saved_opportunities (id, user_id, opportunity_id, payload) "
            f"VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder})",
            (
                f"{user_id}:{opportunity_id}",
                user_id,
                opportunity_id,
                _json_payload(payload),
            ),
        )


def user_usage(user_id: str) -> dict[str, int | float]:
    initialize_database()
    now = datetime.now(timezone.utc)
    searches_today = 0
    reports_this_month = 0
    active_report_reservations = 0
    ai_cost_this_month_usd = 0.0
    with connect() as connection:
        task_rows = connection.execute("SELECT payload FROM search_tasks").fetchall()
        report_rows = connection.execute("SELECT payload FROM reports").fetchall()
    for row in task_rows:
        payload = json.loads(row[0])
        created_at = datetime.fromisoformat(str(payload["created_at"]).replace("Z", "+00:00"))
        if payload.get("user_id") == user_id and created_at.date() == now.date():
            searches_today += 1
        if (
            payload.get("user_id") == user_id
            and created_at.year == now.year
            and created_at.month == now.month
            and payload.get("status") not in {"completed", "failed", "cancelled"}
        ):
            active_report_reservations += 1
    for row in report_rows:
        payload = json.loads(row[0])
        created_at = datetime.fromisoformat(str(payload["created_at"]).replace("Z", "+00:00"))
        if (
            payload.get("user_id") == user_id
            and created_at.year == now.year
            and created_at.month == now.month
        ):
            reports_this_month += 1
            agent_run = payload.get("agent_run")
            if isinstance(agent_run, dict):
                try:
                    ai_cost_this_month_usd += max(0.0, float(agent_run.get("estimated_cost_usd") or 0))
                except (TypeError, ValueError):
                    pass
    return {
        "searches_today": searches_today,
        "reports_this_month": reports_this_month + active_report_reservations,
        "ai_cost_this_month_usd": round(ai_cost_this_month_usd, 6),
    }


def reserve_search_task(
    task: dict[str, Any],
    *,
    user_id: str,
    search_quota_daily: int,
    report_quota_monthly: int,
) -> None:
    """Atomically check account quotas and insert a queued search task."""
    initialize_database()
    now = datetime.now(timezone.utc)
    placeholder = _placeholder()
    with connect() as connection:
        if database_backend() == "sqlite":
            connection.execute("BEGIN IMMEDIATE")
        else:
            connection.execute("LOCK TABLE search_tasks IN EXCLUSIVE MODE")
            connection.execute("LOCK TABLE reports IN SHARE MODE")

        searches_today = 0
        active_report_reservations = 0
        for row in connection.execute("SELECT payload FROM search_tasks").fetchall():
            payload = json.loads(row[0])
            if payload.get("user_id") != user_id:
                continue
            created_at = datetime.fromisoformat(str(payload["created_at"]).replace("Z", "+00:00"))
            if created_at.date() == now.date():
                searches_today += 1
            if (
                created_at.year == now.year
                and created_at.month == now.month
                and payload.get("status") not in {"completed", "failed", "cancelled"}
            ):
                active_report_reservations += 1

        reports_this_month = active_report_reservations
        for row in connection.execute("SELECT payload FROM reports").fetchall():
            payload = json.loads(row[0])
            if payload.get("user_id") != user_id:
                continue
            created_at = datetime.fromisoformat(str(payload["created_at"]).replace("Z", "+00:00"))
            if created_at.year == now.year and created_at.month == now.month:
                reports_this_month += 1

        if searches_today >= search_quota_daily:
            connection.rollback()
            raise QuotaExceededError("今日搜索额度已用完")
        if reports_this_month >= report_quota_monthly:
            connection.rollback()
            raise QuotaExceededError("本月报告额度已用完")

        connection.execute(
            "INSERT INTO search_tasks (id, payload) "
            f"VALUES ({placeholder}, {placeholder})",
            (str(task["id"]), _json_payload(task)),
        )
        connection.commit()


def upsert_task_payload(task: dict[str, Any]) -> None:
    initialize_database()
    with connect() as connection:
        _upsert_payload(
            connection.cursor(),
            table="search_tasks",
            key_column="id",
            key=str(task["id"]),
            payload=task,
        )
        connection.commit()


def upsert_report_payload(report: dict[str, Any]) -> None:
    initialize_database()
    with connect() as connection:
        _upsert_payload(
            connection.cursor(),
            table="reports",
            key_column="id",
            key=str(report["id"]),
            payload=report,
        )
        connection.commit()


def load_saved_payloads(user_id: str) -> dict[str, dict[str, Any]]:
    initialize_database()
    placeholder = _placeholder()
    with connect() as connection:
        rows = connection.execute(
            f"SELECT opportunity_id, payload FROM saved_opportunities WHERE user_id = {placeholder}",
            (user_id,),
        ).fetchall()
    return {str(row[0]): json.loads(row[1]) for row in rows}


def upsert_saved_payload(user_id: str, opportunity_id: str, payload: dict[str, Any]) -> None:
    initialize_database()
    placeholder = _placeholder()
    row_id = f"{user_id}:{opportunity_id}"
    with connect() as connection:
        connection.execute(
            "INSERT INTO saved_opportunities (id, user_id, opportunity_id, payload) "
            f"VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}) "
            "ON CONFLICT (user_id, opportunity_id) DO UPDATE SET payload = EXCLUDED.payload",
            (row_id, user_id, opportunity_id, _json_payload(payload)),
        )
        connection.commit()


def delete_saved_payload(user_id: str, opportunity_id: str) -> None:
    initialize_database()
    placeholder = _placeholder()
    with connect() as connection:
        connection.execute(
            "DELETE FROM saved_opportunities "
            f"WHERE user_id = {placeholder} AND opportunity_id = {placeholder}",
            (user_id, opportunity_id),
        )
        connection.commit()


def load_source_credential_payload(user_id: str, source: str) -> dict[str, Any] | None:
    initialize_database()
    placeholder = _placeholder()
    with connect() as connection:
        row = connection.execute(
            "SELECT encrypted_secret, created_at, updated_at, payload "
            f"FROM source_credentials WHERE user_id = {placeholder} AND source = {placeholder}",
            (user_id, source),
        ).fetchone()
    if not row:
        return None
    return {
        "encrypted_secret": row[0],
        "created_at": row[1],
        "updated_at": row[2],
        "payload": json.loads(row[3]),
    }


def upsert_source_credential_payload(
    *,
    user_id: str,
    source: str,
    encrypted_secret: str,
    payload: dict[str, Any],
) -> None:
    initialize_database()
    placeholder = _placeholder()
    now = datetime.now(timezone.utc).isoformat()
    row_id = f"{user_id}:{source}"
    with connect() as connection:
        connection.execute(
            "INSERT INTO source_credentials "
            "(id, user_id, source, encrypted_secret, created_at, updated_at, payload) "
            f"VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}) "
            "ON CONFLICT (user_id, source) DO UPDATE SET "
            "encrypted_secret = EXCLUDED.encrypted_secret, "
            "updated_at = EXCLUDED.updated_at, payload = EXCLUDED.payload",
            (row_id, user_id, source, encrypted_secret, now, now, _json_payload(payload)),
        )
        connection.commit()


def delete_source_credential_payload(user_id: str, source: str) -> None:
    initialize_database()
    placeholder = _placeholder()
    with connect() as connection:
        connection.execute(
            f"DELETE FROM source_credentials WHERE user_id = {placeholder} AND source = {placeholder}",
            (user_id, source),
        )
        connection.commit()


def load_system_setting(key: str) -> dict[str, Any] | None:
    initialize_database()
    placeholder = _placeholder()
    with connect() as connection:
        row = connection.execute(
            f"SELECT encrypted_secret, created_at, updated_at, payload FROM system_settings WHERE key = {placeholder}",
            (key,),
        ).fetchone()
    if not row:
        return None
    return {
        "encrypted_secret": row[0],
        "created_at": row[1],
        "updated_at": row[2],
        "payload": json.loads(row[3]),
    }


def upsert_system_setting(
    key: str,
    *,
    encrypted_secret: str | None,
    payload: dict[str, Any],
) -> None:
    initialize_database()
    placeholder = _placeholder()
    now = datetime.now(timezone.utc).isoformat()
    with connect() as connection:
        existing = connection.execute(
            f"SELECT created_at FROM system_settings WHERE key = {placeholder}",
            (key,),
        ).fetchone()
        created_at = str(existing[0]) if existing else now
        connection.execute(
            "INSERT INTO system_settings (key, encrypted_secret, created_at, updated_at, payload) "
            f"VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}) "
            "ON CONFLICT (key) DO UPDATE SET encrypted_secret = EXCLUDED.encrypted_secret, "
            "updated_at = EXCLUDED.updated_at, payload = EXCLUDED.payload",
            (key, encrypted_secret, created_at, now, _json_payload(payload)),
        )
        connection.commit()


def delete_system_setting(key: str) -> None:
    initialize_database()
    placeholder = _placeholder()
    with connect() as connection:
        connection.execute(
            f"DELETE FROM system_settings WHERE key = {placeholder}",
            (key,),
        )
        connection.commit()


def append_api_log(payload: dict[str, Any]) -> None:
    initialize_database()
    placeholder = _placeholder()
    with connect() as connection:
        connection.execute(
            "INSERT INTO api_logs "
            "(id, user_id, endpoint, method, status_code, response_time_ms, created_at, payload) "
            f"VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder})",
            (
                str(payload["id"]),
                payload.get("user_id"),
                str(payload["endpoint"]),
                str(payload["method"]),
                int(payload["status_code"]),
                int(payload["response_time_ms"]),
                str(payload["created_at"]),
                _json_payload(payload),
            ),
        )
        connection.commit()


def load_api_logs(user_id: str, limit: int = 50) -> list[dict[str, Any]]:
    initialize_database()
    placeholder = _placeholder()
    with connect() as connection:
        rows = connection.execute(
            "SELECT payload FROM api_logs "
            f"WHERE user_id = {placeholder} ORDER BY created_at DESC LIMIT {placeholder}",
            (user_id, limit),
        ).fetchall()
    return [json.loads(row[0]) for row in rows]


def load_agent_run_billing(limit: int = 100) -> list[dict[str, Any]]:
    initialize_database()
    placeholder = _placeholder()
    with connect() as connection:
        run_rows = connection.execute(
            "SELECT id, user_id, task_id, opportunity_id, status, created_at, payload "
            f"FROM agent_runs ORDER BY created_at DESC LIMIT {placeholder}",
            (limit,),
        ).fetchall()
        user_rows = connection.execute("SELECT id, payload FROM users").fetchall()
        report_rows = connection.execute("SELECT id, payload FROM reports").fetchall()

    users = {str(row[0]): json.loads(row[1]) for row in user_rows}
    report_by_agent_run: dict[str, str] = {}
    for report_id, raw_payload in report_rows:
        payload = json.loads(raw_payload)
        agent_run = payload.get("agent_run")
        if isinstance(agent_run, dict) and agent_run.get("id"):
            report_by_agent_run[str(agent_run["id"])] = str(report_id)

    records: list[dict[str, Any]] = []
    for run_id, user_id, task_id, opportunity_id, status, created_at, raw_payload in run_rows:
        payload = json.loads(raw_payload)
        steps = payload.get("steps", [])
        if not isinstance(steps, list):
            steps = []
        user_payload = users.get(str(user_id), {})
        input_tokens = int(payload.get("input_tokens") or 0)
        output_tokens = int(payload.get("output_tokens") or 0)
        cost = payload.get("estimated_cost_usd")
        try:
            estimated_cost = float(cost) if cost is not None else None
        except (TypeError, ValueError):
            estimated_cost = None
        records.append(
            {
                "id": str(run_id),
                "user_id": str(user_id),
                "user_email": str(user_payload.get("email") or ""),
                "username": str(user_payload.get("username") or ""),
                "task_id": str(task_id),
                "opportunity_id": str(opportunity_id),
                "report_id": report_by_agent_run.get(str(run_id)),
                "provider": payload.get("provider"),
                "model": payload.get("model"),
                "status": str(status),
                "started_at": str(created_at),
                "finished_at": payload.get("finished_at"),
                "duration_ms": int(payload.get("duration_ms") or 0),
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens,
                "estimated_cost_usd": estimated_cost,
                "step_count": len(steps),
                "completed_steps": sum(1 for step in steps if isinstance(step, dict) and step.get("status") == "completed"),
                "failed_steps": sum(1 for step in steps if isinstance(step, dict) and step.get("status") == "failed"),
                "skipped_steps": sum(1 for step in steps if isinstance(step, dict) and step.get("status") == "skipped"),
            }
        )
    return records


def replace_source_health_history(history: list[dict[str, Any]]) -> None:
    initialize_database()
    placeholder = _placeholder()
    with connect() as connection:
        cursor = connection.cursor()
        cursor.execute("DELETE FROM source_health_history")
        rows = [(position, _json_payload(row)) for position, row in enumerate(history)]
        if rows:
            cursor.executemany(
                "INSERT INTO source_health_history (position, payload) "
                f"VALUES ({placeholder}, {placeholder})",
                rows,
            )
        connection.commit()


def persist_pipeline_result(
    *,
    task: dict[str, Any],
    opportunity: dict[str, Any],
    trends: list[dict[str, Any]],
    patents: list[dict[str, Any]],
    competitors: list[dict[str, Any]],
    pain_points: list[dict[str, Any]],
    supply_chain: list[dict[str, Any]],
    innovation_ideas: list[dict[str, Any]],
    report: dict[str, Any],
) -> None:
    """Commit a completed pipeline as one database transaction."""
    initialize_database()
    opportunity_id = str(opportunity["id"])
    placeholder = _placeholder()
    list_rows = {
        "trend_data": trends,
        "patents": patents,
        "competitors": competitors,
        "pain_points": pain_points,
        "supply_chain": supply_chain,
        "innovation_ideas": innovation_ideas,
    }
    with connect() as connection:
        cursor = connection.cursor()
        _upsert_payload(
            cursor,
            table="search_tasks",
            key_column="id",
            key=str(task["id"]),
            payload=task,
        )
        _upsert_payload(
            cursor,
            table="opportunities",
            key_column="id",
            key=opportunity_id,
            payload=opportunity,
        )
        _upsert_payload(
            cursor,
            table="reports",
            key_column="id",
            key=str(report["id"]),
            payload=report,
        )
        agent_run = report.get("agent_run")
        if isinstance(agent_run, dict) and agent_run.get("id"):
            cursor.execute(
                "INSERT INTO agent_runs "
                "(id, user_id, task_id, opportunity_id, status, created_at, payload) "
                f"VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}) "
                "ON CONFLICT (id) DO UPDATE SET status = EXCLUDED.status, payload = EXCLUDED.payload",
                (
                    str(agent_run["id"]),
                    str(task["user_id"]),
                    str(task["id"]),
                    opportunity_id,
                    str(agent_run.get("status", "unknown")),
                    str(agent_run.get("started_at") or datetime.now(timezone.utc).isoformat()),
                    _json_payload(agent_run),
                ),
            )
        for table, rows in list_rows.items():
            cursor.execute(
                f"DELETE FROM {table} WHERE opportunity_id = {placeholder}",
                (opportunity_id,),
            )
            values = [
                (str(row["id"]), opportunity_id, _json_payload(row))
                for row in rows
            ]
            if values:
                cursor.executemany(
                    f"INSERT INTO {table} (id, opportunity_id, payload) "
                    f"VALUES ({placeholder}, {placeholder}, {placeholder})",
                    values,
                )
        connection.commit()


def save_payload(payload: dict[str, Any], *, migration_source: str | None = None) -> None:
    initialize_database()
    placeholder = _placeholder()
    with connect() as connection:
        cursor = connection.cursor()
        for table in [
            *MODEL_TABLES.values(),
            *LIST_TABLES.values(),
            "saved_opportunities",
            "source_health_history",
            "agent_runs",
        ]:
            cursor.execute(f"DELETE FROM {table}")

        for state_key, table in MODEL_TABLES.items():
            rows = [
                (row_id, json.dumps(row, ensure_ascii=False))
                for row_id, row in payload.get(state_key, {}).items()
            ]
            if rows:
                cursor.executemany(
                    f"INSERT INTO {table} (id, payload) VALUES ({placeholder}, {placeholder})",
                    rows,
                )

        agent_rows = []
        for report in payload.get("reports", {}).values():
            agent_run = report.get("agent_run") if isinstance(report, dict) else None
            if not isinstance(agent_run, dict) or not agent_run.get("id"):
                continue
            agent_rows.append(
                (
                    str(agent_run["id"]),
                    str(report.get("user_id", "legacy-demo")),
                    str(report.get("search_task_id", "")),
                    str(report.get("opportunity_id", "")),
                    str(agent_run.get("status", "unknown")),
                    str(agent_run.get("started_at") or datetime.now(timezone.utc).isoformat()),
                    _json_payload(agent_run),
                )
            )
        if agent_rows:
            cursor.executemany(
                "INSERT INTO agent_runs "
                "(id, user_id, task_id, opportunity_id, status, created_at, payload) "
                f"VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder})",
                agent_rows,
            )

        for state_key, table in LIST_TABLES.items():
            rows = [
                (str(row.get("id")), opportunity_id, json.dumps(row, ensure_ascii=False))
                for opportunity_id, items in payload.get(state_key, {}).items()
                for row in items
            ]
            if rows:
                cursor.executemany(
                    f"INSERT INTO {table} (id, opportunity_id, payload) "
                    f"VALUES ({placeholder}, {placeholder}, {placeholder})",
                    rows,
                )

        saved_rows = []
        for row_id, row in payload.get("saved", {}).items():
            opportunity_id = str(row.get("opportunity_id") or row_id.split(":", 1)[-1])
            user_id = str(row.get("user_id") or "legacy-demo")
            normalized = {
                **row,
                "user_id": user_id,
                "opportunity_id": opportunity_id,
            }
            saved_rows.append(
                (f"{user_id}:{opportunity_id}", user_id, opportunity_id, _json_payload(normalized))
            )
        if saved_rows:
            cursor.executemany(
                "INSERT INTO saved_opportunities (id, user_id, opportunity_id, payload) "
                f"VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder})",
                saved_rows,
            )

        history_rows = [
            (position, json.dumps(row, ensure_ascii=False))
            for position, row in enumerate(payload.get("source_health_history", []))
        ]
        if history_rows:
            cursor.executemany(
                "INSERT INTO source_health_history (position, payload) "
                f"VALUES ({placeholder}, {placeholder})",
                history_rows,
            )

        if migration_source:
            cursor.execute(
                "DELETE FROM store_metadata WHERE key = "
                f"{placeholder}",
                ("migrated_from",),
            )
            cursor.execute(
                "INSERT INTO store_metadata (key, value) "
                f"VALUES ({placeholder}, {placeholder})",
                ("migrated_from", migration_source),
            )
        connection.commit()


def database_status() -> dict[str, Any]:
    initialize_database()
    backend = database_backend()
    counts: dict[str, int] = {}
    with connect() as connection:
        for label, table in {
            "tasks": "search_tasks",
            "opportunities": "opportunities",
            "reports": "reports",
            "patents": "patents",
            "competitors": "competitors",
            "pain_points": "pain_points",
            "suppliers": "supply_chain",
            "users": "users",
            "agent_runs": "agent_runs",
        }.items():
            counts[label] = int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
        migration_row = connection.execute(
            "SELECT value FROM store_metadata WHERE key = 'migrated_from'"
        ).fetchone()

    path = sqlite_path() if backend == "sqlite" else None
    return {
        "backend": backend,
        "url": safe_database_url(),
        "path": str(path) if path else safe_database_url(),
        "exists": path.exists() if path else True,
        "bytes": path.stat().st_size if path and path.exists() else 0,
        "counts": counts,
        "migrated_from": migration_row[0] if migration_row else None,
    }
