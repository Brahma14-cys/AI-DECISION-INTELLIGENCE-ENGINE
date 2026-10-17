"""Encrypt legacy plaintext rows and uploads after APP_ENCRYPTION_KEY is configured."""

import hashlib
import os
from pathlib import Path
import tempfile
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.encryption import _BLOB_MAGIC, _TEXT_PREFIX, decrypt_bytes, encrypt_bytes, encryption_key
from app.db.models import (
    Case,
    CaseAnalysisExtractionItem,
    CaseAnalysisFact,
    CaseAnalysisFinding,
    CaseAnalysisRun,
    CaseClaimReview,
    CaseDocument,
    CaseKnowledgeGraphRun,
    CaseSummaryRun,
    DocumentTextUnit,
)


_PROTECTED_FIELDS = {
    Case: ("title", "client_reference", "court", "jurisdiction", "case_type", "stage"),
    CaseDocument: ("original_filename", "extraction_error"),
    DocumentTextUnit: ("text",),
    CaseAnalysisRun: ("error_message", "advocate_claims"),
    CaseAnalysisFact: ("topic_key", "statement", "evidence_quote", "normalized_value"),
    CaseAnalysisExtractionItem: ("category", "text", "normalized_value", "legal_role", "evidence_quote"),
    CaseAnalysisFinding: ("relation_label", "explanation"),
    CaseClaimReview: ("claim_text", "support_status", "explanation", "overstatement_reason"),
    CaseSummaryRun: ("narrative_summary", "structured_summary", "error_message"),
    CaseKnowledgeGraphRun: ("graph_snapshot", "error_message"),
}


def _needs_encryption(value) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return not value.startswith(_TEXT_PREFIX)
    return True  # JSON columns are encrypted as a serialized string payload.


def _normalize_upload_encryption(value: bytes, expected_sha256: str) -> tuple[bytes, int, bool]:
    """Return exactly one encryption layer, verified against the upload hash.

    Older startup runs encrypted already-encrypted files again. Decrypting
    until the immutable upload hash matches lets this migration repair those
    nested blobs without guessing or writing unverifiable file contents.
    """
    if hashlib.sha256(value).hexdigest() == expected_sha256:
        return encrypt_bytes(value), 0, True  # Legacy plaintext upload.

    candidate = value
    layers = 0
    while candidate.startswith(_BLOB_MAGIC) and layers < 8:
        candidate = decrypt_bytes(candidate)
        layers += 1
        if hashlib.sha256(candidate).hexdigest() == expected_sha256:
            if layers == 1:
                return value, layers, False  # Already encrypted exactly once.
            return encrypt_bytes(candidate), layers, True

    raise RuntimeError(
        "A stored upload could not be matched to its recorded SHA-256; it was left unchanged."
    )


def main() -> None:
    if encryption_key() is None:
        raise SystemExit("Set APP_ENCRYPTION_KEY before migrating existing case data.")
    encrypted_columns = 0
    normalized_files = 0
    repaired_nested_files = 0
    recovery_dir: Path | None = None
    with SessionLocal() as db:
        for model, fields in _PROTECTED_FIELDS.items():
            for row in db.scalars(select(model)).all():
                for field in fields:
                    if _needs_encryption(getattr(row, field)):
                        flag_modified(row, field)
                        encrypted_columns += 1
        db.commit()

        storage_root = settings.uploads_dir.resolve()
        for document in db.scalars(select(CaseDocument)).all():
            path = (storage_root / document.storage_key).resolve()
            if not path.is_relative_to(storage_root) or not path.is_file():
                continue
            original = path.read_bytes()
            encrypted, encryption_layers, needs_write = _normalize_upload_encryption(
                original, document.sha256
            )
            if not needs_write:
                continue

            if encryption_layers > 1:
                if recovery_dir is None:
                    recovery_dir = (
                        Path(__file__).resolve().parents[3]
                        / ".runtime"
                        / f"encryption-recovery-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}"
                    )
                    recovery_dir.mkdir(parents=True, exist_ok=False)
                # Keep the prior encrypted blob so the repair can be reversed.
                (recovery_dir / f"{document.id}.encrypted-backup").write_bytes(original)

            descriptor, temporary_name = tempfile.mkstemp(prefix=".encrypt-", dir=path.parent)
            try:
                with os.fdopen(descriptor, "wb") as stream:
                    stream.write(encrypted)
                os.replace(temporary_name, path)
            except Exception:
                Path(temporary_name).unlink(missing_ok=True)
                raise
            normalized_files += 1
            if encryption_layers > 1:
                repaired_nested_files += 1
    print(
        f"Encrypted legacy case fields: {encrypted_columns}; normalized uploads: {normalized_files}; "
        f"repaired nested uploads: {repaired_nested_files}; "
        f"recovery copies: {recovery_dir if recovery_dir else 'none'}."
    )


if __name__ == "__main__":
    main()
