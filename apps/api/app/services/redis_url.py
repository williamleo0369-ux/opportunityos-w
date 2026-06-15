from __future__ import annotations

import os
from urllib.parse import urlsplit, urlunsplit


REDIS_ENV_KEYS = ("REDIS_URL", "REDIS_PRIVATE_URL", "REDIS_PUBLIC_URL", "RAILWAY_REDIS_URL")
DEFAULT_REDIS_URL = "redis://127.0.0.1:6379/0"


def resolve_redis_url() -> str:
    for key in REDIS_ENV_KEYS:
        value = os.getenv(key, "").strip()
        if value.startswith(("redis://", "rediss://")):
            return value
    return DEFAULT_REDIS_URL


def safe_redis_url(value: str) -> str:
    parts = urlsplit(value)
    hostname = parts.hostname or ""
    port = f":{parts.port}" if parts.port else ""
    username = f"{parts.username}@" if parts.username else ""
    return urlunsplit((parts.scheme, f"{username}{hostname}{port}", parts.path, parts.query, parts.fragment))
