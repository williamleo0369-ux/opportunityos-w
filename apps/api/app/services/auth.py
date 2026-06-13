from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


AUTH_SECRET_PATH = Path.home() / ".opportunity-os" / "auth-secret"
SESSION_TTL_DAYS = int(os.getenv("OPPORTUNITY_OS_SESSION_TTL_DAYS", "30"))


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _auth_secret() -> bytes:
    configured = os.getenv("OPPORTUNITY_OS_AUTH_SECRET", "").strip()
    if configured:
        return configured.encode("utf-8")
    AUTH_SECRET_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not AUTH_SECRET_PATH.exists():
        AUTH_SECRET_PATH.write_text(secrets.token_urlsafe(48))
        AUTH_SECRET_PATH.chmod(0o600)
    return AUTH_SECRET_PATH.read_text().strip().encode("utf-8")


def derive_secret_key(purpose: str) -> bytes:
    return hmac.new(_auth_secret(), purpose.encode("utf-8"), hashlib.sha256).digest()


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    derived = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=2**14,
        r=8,
        p=1,
        dklen=32,
    )
    return f"scrypt$16384$8$1${_b64encode(salt)}${_b64encode(derived)}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, n, r, p, salt, expected = encoded.split("$", 5)
        if algorithm != "scrypt":
            return False
        derived = hashlib.scrypt(
            password.encode("utf-8"),
            salt=_b64decode(salt),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=32,
        )
        return hmac.compare_digest(derived, _b64decode(expected))
    except (ValueError, TypeError):
        return False


DUMMY_PASSWORD_HASH = hash_password("opportunity-os-dummy-password")


def create_session_token(user_id: str) -> str:
    now = utc_now()
    payload = {
        "sub": user_id,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(days=SESSION_TTL_DAYS)).timestamp()),
        "nonce": secrets.token_urlsafe(8),
    }
    encoded = _b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signature = _b64encode(hmac.new(_auth_secret(), encoded.encode("ascii"), hashlib.sha256).digest())
    return f"{encoded}.{signature}"


def verify_session_token(token: str) -> dict[str, Any] | None:
    try:
        encoded, signature = token.split(".", 1)
        expected = _b64encode(hmac.new(_auth_secret(), encoded.encode("ascii"), hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected):
            return None
        payload = json.loads(_b64decode(encoded))
        if int(payload.get("exp", 0)) <= int(utc_now().timestamp()):
            return None
        if not payload.get("sub"):
            return None
        return payload
    except (ValueError, TypeError, json.JSONDecodeError):
        return None
