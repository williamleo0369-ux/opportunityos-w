from __future__ import annotations

import os
import threading


_LOCK = threading.RLock()
_RUNTIME_1688_COOKIE = ""


def set_runtime_1688_cookie(cookie: str) -> None:
    global _RUNTIME_1688_COOKIE
    with _LOCK:
        _RUNTIME_1688_COOKIE = cookie.strip()


def clear_runtime_1688_cookie() -> None:
    global _RUNTIME_1688_COOKIE
    with _LOCK:
        _RUNTIME_1688_COOKIE = ""


def runtime_1688_cookie_configured() -> bool:
    with _LOCK:
        return bool(_RUNTIME_1688_COOKIE)


def env_1688_cookie_configured() -> bool:
    return bool(os.getenv("OPPORTUNITY_OS_1688_COOKIE", "").strip())


def get_1688_cookie() -> str:
    with _LOCK:
        runtime_cookie = _RUNTIME_1688_COOKIE
    return runtime_cookie or os.getenv("OPPORTUNITY_OS_1688_COOKIE", "").strip()


def get_1688_cookie_source() -> str:
    if runtime_1688_cookie_configured():
        return "runtime"
    if env_1688_cookie_configured():
        return "environment"
    return "none"
