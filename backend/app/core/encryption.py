"""Application-level encryption for case text and uploaded source files."""

import base64
import json
import secrets

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import JSON, Text
from sqlalchemy.types import TypeDecorator

from app.core.config import settings


_BLOB_MAGIC = b"LEC1"
_TEXT_PREFIX = "lec1:"
_AAD = b"ai-legal-case-engine:v1"


def encryption_key() -> bytes | None:
    encoded = settings.app_encryption_key
    if not encoded:
        return None
    try:
        key = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
    except (ValueError, TypeError) as error:
        raise RuntimeError("APP_ENCRYPTION_KEY must be URL-safe base64 for a 32-byte key.") from error
    if len(key) != 32:
        raise RuntimeError("APP_ENCRYPTION_KEY must decode to exactly 32 bytes.")
    return key


def generate_encryption_key() -> str:
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii").rstrip("=")


def encrypt_bytes(value: bytes) -> bytes:
    key = encryption_key()
    if key is None:
        return value
    nonce = secrets.token_bytes(12)
    return _BLOB_MAGIC + nonce + AESGCM(key).encrypt(nonce, value, _AAD)


def decrypt_bytes(value: bytes) -> bytes:
    if not value.startswith(_BLOB_MAGIC):
        return value  # Supports pre-encryption local files during migration.
    key = encryption_key()
    if key is None:
        raise RuntimeError("This stored document is encrypted; configure APP_ENCRYPTION_KEY before processing it.")
    nonce = value[len(_BLOB_MAGIC) : len(_BLOB_MAGIC) + 12]
    return AESGCM(key).decrypt(nonce, value[len(_BLOB_MAGIC) + 12 :], _AAD)


def _encrypt_text(value: str) -> str:
    encrypted = encrypt_bytes(value.encode("utf-8"))
    if encrypted == value.encode("utf-8"):
        return value
    return _TEXT_PREFIX + base64.urlsafe_b64encode(encrypted[len(_BLOB_MAGIC) :]).decode("ascii")


def _decrypt_text(value: str) -> str:
    if not value.startswith(_TEXT_PREFIX):
        return value  # Legacy database plaintext is readable and becomes encrypted on next write.
    encoded = base64.urlsafe_b64decode(value[len(_TEXT_PREFIX) :])
    return decrypt_bytes(_BLOB_MAGIC + encoded).decode("utf-8")


class EncryptedText(TypeDecorator):
    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return _encrypt_text(value) if value is not None else None

    def process_result_value(self, value, dialect):
        return _decrypt_text(value) if value is not None else None


class EncryptedJSON(TypeDecorator):
    impl = JSON
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None or encryption_key() is None:
            return value
        return _encrypt_text(json.dumps(value, ensure_ascii=False, separators=(",", ":")))

    def process_result_value(self, value, dialect):
        if not isinstance(value, str) or not value.startswith(_TEXT_PREFIX):
            return value
        return json.loads(_decrypt_text(value))
