from __future__ import annotations

import base64

from cryptography.fernet import Fernet, InvalidToken

from app.services.auth import derive_secret_key
from app.services.database_store import (
    delete_source_credential_payload,
    load_source_credential_payload,
    upsert_source_credential_payload,
)


SOURCE_1688 = "1688"


class CredentialDecryptionError(RuntimeError):
    pass


def _cipher() -> Fernet:
    key = base64.urlsafe_b64encode(derive_secret_key("source-credentials:v1"))
    return Fernet(key)


def save_1688_cookie(user_id: str, cookie: str, metadata: dict[str, object]) -> None:
    encrypted = _cipher().encrypt(cookie.strip().encode("utf-8")).decode("ascii")
    upsert_source_credential_payload(
        user_id=user_id,
        source=SOURCE_1688,
        encrypted_secret=encrypted,
        payload=metadata,
    )


def load_1688_cookie(user_id: str) -> str:
    record = load_source_credential_payload(user_id, SOURCE_1688)
    if not record:
        return ""
    try:
        return _cipher().decrypt(str(record["encrypted_secret"]).encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, TypeError) as exc:
        raise CredentialDecryptionError("1688 凭据无法解密，请重新连接") from exc


def load_1688_metadata(user_id: str) -> dict[str, object] | None:
    record = load_source_credential_payload(user_id, SOURCE_1688)
    return dict(record["payload"]) if record else None


def clear_1688_cookie(user_id: str) -> None:
    delete_source_credential_payload(user_id, SOURCE_1688)
