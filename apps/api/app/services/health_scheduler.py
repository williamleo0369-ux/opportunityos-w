from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable


HealthCheckFn = Callable[[], dict[str, Any]]


class SourceHealthScheduler:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._run_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._check_fn: HealthCheckFn | None = None
        self._interval_seconds = 0
        self._run_count = 0
        self._last_started_at: str | None = None
        self._last_run_at: str | None = None
        self._next_run_at: str | None = None
        self._last_error: str | None = None
        self._last_summary: dict[str, Any] | None = None

    def configure(self, check_fn: HealthCheckFn) -> None:
        with self._lock:
            self._check_fn = check_fn

    def start(self, *, interval_seconds: int, run_immediately: bool = False) -> dict[str, Any]:
        if interval_seconds < 60:
            raise ValueError("interval_seconds must be at least 60")
        with self._lock:
            if self._check_fn is None:
                raise RuntimeError("source health scheduler is not configured")
            self._interval_seconds = interval_seconds
            self._stop_event.clear()
            if self._thread is None or not self._thread.is_alive():
                self._last_started_at = _now()
                next_run = time.time() if run_immediately else time.time() + interval_seconds
                self._set_next_run(next_run)
                self._thread = threading.Thread(target=self._loop, args=(next_run,), daemon=True)
                self._thread.start()
            else:
                self._set_next_run(time.time() + interval_seconds)
            return self.status()

    def stop(self) -> dict[str, Any]:
        with self._lock:
            self._stop_event.set()
            self._next_run_at = None
            return self.status()

    def run_once(self) -> dict[str, Any]:
        return self._run_check()

    def status(self) -> dict[str, Any]:
        with self._lock:
            running = bool(self._thread and self._thread.is_alive() and not self._stop_event.is_set())
            return {
                "running": running,
                "interval_seconds": self._interval_seconds,
                "run_count": self._run_count,
                "last_started_at": self._last_started_at,
                "last_run_at": self._last_run_at,
                "next_run_at": self._next_run_at if running else None,
                "last_error": self._last_error,
                "last_summary": self._last_summary,
            }

    def _loop(self, next_run: float) -> None:
        while not self._stop_event.is_set():
            wait_seconds = max(0.0, next_run - time.time())
            if self._stop_event.wait(wait_seconds):
                break
            self._run_check()
            next_run = time.time() + self._interval_seconds
            self._set_next_run(next_run)

    def _run_check(self) -> dict[str, Any]:
        with self._run_lock:
            with self._lock:
                check_fn = self._check_fn
            if check_fn is None:
                raise RuntimeError("source health scheduler is not configured")
            try:
                result = check_fn()
            except Exception as exc:
                with self._lock:
                    self._last_error = str(exc)[:300]
                    self._last_run_at = _now()
                raise
            with self._lock:
                self._run_count += 1
                self._last_error = None
                self._last_run_at = str(result.get("generated_at") or _now())
                self._last_summary = result.get("summary") if isinstance(result.get("summary"), dict) else None
            return result

    def _set_next_run(self, value: float) -> None:
        with self._lock:
            self._next_run_at = datetime.fromtimestamp(value, timezone.utc).isoformat()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
