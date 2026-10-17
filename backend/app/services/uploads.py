import asyncio
import hashlib
import os
import subprocess
import zipfile
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import UploadFile
from PIL import Image, UnidentifiedImageError

from app.core.config import settings
from app.core.encryption import encrypt_bytes


CHUNK_SIZE = 1024 * 1024
MAX_DOCX_ARCHIVE_ENTRIES = 2_000
MAX_DOCX_UNCOMPRESSED_BYTES = 250 * 1024 * 1024
MAX_ARCHIVE_COMPRESSION_RATIO = 500
MAX_IMAGE_PIXELS = 150_000_000
MAX_TIFF_FRAMES = 500
ALLOWED_TYPES = {
    ".pdf": ("application/pdf",),
    ".docx": ("application/vnd.openxmlformats-officedocument.wordprocessingml.document",),
    ".jpg": ("image/jpeg",),
    ".jpeg": ("image/jpeg",),
    ".png": ("image/png",),
    ".tif": ("image/tiff",),
    ".tiff": ("image/tiff",),
}


class UploadRejected(ValueError):
    """Raised when an uploaded file fails validation."""


def safe_filename(filename: str | None) -> str:
    if not filename:
        raise UploadRejected("The file has no name.")
    name = filename.replace("\\", "/").rsplit("/", maxsplit=1)[-1].strip()
    if not name or name in {".", ".."}:
        raise UploadRejected("The file has no valid name.")
    if len(name) > 255:
        raise UploadRejected("The filename must be 255 characters or fewer.")
    return name


def _matches_signature(path: Path, extension: str) -> bool:
    with path.open("rb") as stream:
        header = stream.read(16)

    if extension == ".pdf":
        return header.startswith(b"%PDF-")
    if extension == ".docx":
        if not zipfile.is_zipfile(path):
            return False
        try:
            with zipfile.ZipFile(path) as archive:
                entries = archive.infolist()
                names = {item.filename for item in entries}
                if len(entries) > MAX_DOCX_ARCHIVE_ENTRIES:
                    return False
                total_uncompressed = sum(item.file_size for item in entries)
                if total_uncompressed > MAX_DOCX_UNCOMPRESSED_BYTES:
                    return False
                for item in entries:
                    if item.file_size > MAX_DOCX_UNCOMPRESSED_BYTES:
                        return False
                    if item.file_size > 1024 * 1024 and item.file_size / max(item.compress_size, 1) > MAX_ARCHIVE_COMPRESSION_RATIO:
                        return False
            return {"[Content_Types].xml", "word/document.xml"}.issubset(names)
        except (OSError, zipfile.BadZipFile):
            return False
    if extension in {".jpg", ".jpeg"}:
        return header.startswith(b"\xff\xd8\xff") and _image_dimensions_are_safe(path)
    if extension == ".png":
        return header.startswith(b"\x89PNG\r\n\x1a\n") and _image_dimensions_are_safe(path)
    if extension in {".tif", ".tiff"}:
        if not header.startswith((b"II*\x00", b"MM\x00*", b"II+\x00", b"MM\x00+")):
            return False
        return _image_dimensions_are_safe(path)
    return False


def _image_dimensions_are_safe(path: Path) -> bool:
    try:
        with Image.open(path) as image:
            frame_count = getattr(image, "n_frames", 1)
            if frame_count > MAX_TIFF_FRAMES:
                return False
            pixel_total = 0
            for frame in range(frame_count):
                image.seek(frame)
                width, height = image.size
                if width <= 0 or height <= 0 or width * height > MAX_IMAGE_PIXELS:
                    return False
                pixel_total += width * height
                if pixel_total > MAX_IMAGE_PIXELS:
                    return False
        return True
    except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError):
        return False


def content_type_for(extension: str) -> str:
    content_types = ALLOWED_TYPES.get(extension)
    if content_types is None:
        raise UploadRejected("Unsupported file type. Upload PDF, DOCX, JPG, PNG, or TIFF files.")
    return content_types[0]


def _scan_malware(path: Path) -> None:
    scanner = settings.clamav_command
    if not scanner:
        if settings.app_env.strip().lower() == "production":
            raise UploadRejected("Uploads are disabled because the configured malware scanner is unavailable.")
        return
    try:
        result = subprocess.run(
            [scanner, "--no-summary", str(path)],
            check=False,
            capture_output=True,
            timeout=60,
            shell=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise UploadRejected("The malware scanner could not complete; the file was not accepted.") from error
    if result.returncode == 1:
        raise UploadRejected("The file was flagged by the malware scanner and was not accepted.")
    if result.returncode != 0:
        raise UploadRejected("The malware scanner failed; the file was not accepted.")


def _encrypt_uploaded_file(plaintext_path: Path, encrypted_path: Path) -> None:
    encrypted_path.write_bytes(encrypt_bytes(plaintext_path.read_bytes()))


async def save_upload(
    upload: UploadFile, case_id: UUID, case_remaining_bytes: int | None = None
) -> tuple[str, str, int, str, str]:
    """Stream a file to private local storage and return metadata for the DB row."""
    filename = safe_filename(upload.filename)
    extension = Path(filename).suffix.lower()
    content_type = content_type_for(extension)
    max_bytes = min(
        settings.max_upload_size_bytes,
        case_remaining_bytes if case_remaining_bytes is not None else settings.max_upload_size_bytes,
    )
    case_directory = settings.uploads_dir / str(case_id)
    case_directory.mkdir(parents=True, exist_ok=True)

    document_id = uuid4()
    storage_name = f"{document_id}{extension}"
    final_path = case_directory / storage_name
    temporary_path = case_directory / f".{document_id}.part"
    digest = hashlib.sha256()
    size_bytes = 0

    try:
        with temporary_path.open("wb") as destination:
            while chunk := await upload.read(CHUNK_SIZE):
                size_bytes += len(chunk)
                if size_bytes > max_bytes:
                    if max_bytes < settings.max_upload_size_bytes:
                        raise UploadRejected("The file exceeds the remaining storage quota for this case.")
                    raise UploadRejected("The file exceeds the configured per-file size limit.")
                digest.update(chunk)
                destination.write(chunk)

        if size_bytes == 0:
            raise UploadRejected("The file is empty.")
        if not await asyncio.to_thread(_matches_signature, temporary_path, extension):
            raise UploadRejected("The file contents do not match its extension or are unreadable.")

        # Scanner subprocesses can take several seconds (and up to the configured
        # timeout). Keep that blocking work off FastAPI's event loop so one upload
        # cannot stall unrelated API requests.
        await asyncio.to_thread(_scan_malware, temporary_path)

        encrypted_temporary_path = case_directory / f".{document_id}.encrypted.part"
        await asyncio.to_thread(_encrypt_uploaded_file, temporary_path, encrypted_temporary_path)
        temporary_path.unlink(missing_ok=True)
        os.replace(encrypted_temporary_path, final_path)
        storage_key = f"{case_id}/{storage_name}"
        return filename, content_type, size_bytes, digest.hexdigest(), storage_key
    except Exception:
        temporary_path.unlink(missing_ok=True)
        encrypted_temporary_path = case_directory / f".{document_id}.encrypted.part"
        encrypted_temporary_path.unlink(missing_ok=True)
        final_path.unlink(missing_ok=True)
        raise
    finally:
        await upload.close()
