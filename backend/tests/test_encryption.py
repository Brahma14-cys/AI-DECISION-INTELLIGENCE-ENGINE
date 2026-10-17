import base64

import pytest
from cryptography.exceptions import InvalidTag
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.encryption import EncryptedText, decrypt_bytes, encrypt_bytes
from app.db.base import Base
from app.db.models import Case


def test_encrypted_text_columns_round_trip_and_ciphertext_is_randomized(monkeypatch) -> None:
    monkeypatch.setattr(settings, "app_encryption_key", base64.urlsafe_b64encode(b"k" * 32).decode().rstrip("="))
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(Case(title="Synthetic protected case"))
        db.commit()
        stored = db.connection().exec_driver_sql("SELECT title FROM cases").scalar_one()
        assert stored.startswith("lec1:")
        assert "Synthetic protected case" not in stored
        assert db.scalar(select(Case.title)) == "Synthetic protected case"

    column_type = EncryptedText()
    first = column_type.process_bind_param("same text", None)
    second = column_type.process_bind_param("same text", None)
    assert first != second
    assert column_type.process_result_value(first, None) == "same text"


def test_encrypted_upload_bytes_round_trip_and_wrong_key_fails(monkeypatch) -> None:
    first_key = base64.urlsafe_b64encode(b"a" * 32).decode().rstrip("=")
    second_key = base64.urlsafe_b64encode(b"b" * 32).decode().rstrip("=")
    monkeypatch.setattr(settings, "app_encryption_key", first_key)
    ciphertext = encrypt_bytes(b"synthetic source bytes")
    assert ciphertext != b"synthetic source bytes"
    assert decrypt_bytes(ciphertext) == b"synthetic source bytes"
    monkeypatch.setattr(settings, "app_encryption_key", second_key)
    with pytest.raises(InvalidTag):
        decrypt_bytes(ciphertext)
