"""File upload streaming validation and content verification."""
import os
import tempfile
from typing import Tuple
from fastapi import UploadFile

from app.core.config import settings
from app.core.exceptions import (
    FileValidationError,
    UploadSizeLimitExceeded,
)


def detect_file_type_and_validate_header(filename: str, header_bytes: bytes) -> str:
    """Validate file extension and magic bytes.

    Returns:
        'kml' or 'shapefile'
    """
    ext = os.path.splitext(filename)[1].lower()

    if ext == ".kml":
        # Check for XML / KML signatures
        stripped_header = header_bytes.lstrip()
        if not (
            stripped_header.startswith(b"<?xml")
            or stripped_header.startswith(b"<kml")
            or b"<kml" in stripped_header[:1024]
        ):
            raise FileValidationError(
                f"File '{filename}' has .kml extension but does not contain valid KML/XML header.",
                details={"header_sample": header_bytes[:50].decode("latin-1", errors="replace")},
            )
        return "kml"

    if ext == ".zip":
        # Check ZIP magic bytes (PK\x03\x04 or PK\x05\x06)
        if not header_bytes.startswith(b"PK\x03\x04") and not header_bytes.startswith(b"PK\x05\x06"):
            raise FileValidationError(
                f"File '{filename}' has .zip extension but does not contain valid ZIP archive header.",
                details={"header_bytes": list(header_bytes[:4])},
            )
        return "shapefile"

    raise FileValidationError(
        f"Unsupported file format '{ext}'. Only .kml or .zip (containing Shapefile) are accepted.",
        details={"allowed_extensions": [".kml", ".zip"], "provided_filename": filename},
    )


async def save_upload_safely_to_disk(
    upload_file: UploadFile,
    max_bytes: int = settings.MAX_UPLOAD_SIZE_BYTES,
    chunk_size: int = settings.CHUNK_SIZE_BYTES,
) -> Tuple[str, str, int]:
    """Stream incoming upload file to a secure temporary file enforcing upload limits during streaming.

    Returns:
        Tuple of (temp_file_path, file_type, total_bytes_written)
    """
    filename = upload_file.filename or "uploaded_file"
    ext = os.path.splitext(filename)[1].lower()

    # Pre-check extension before reading stream
    if ext not in [".kml", ".zip"]:
        raise FileValidationError(
            f"Unsupported file extension '{ext}'. Only .kml and .zip are supported.",
            details={"allowed_extensions": [".kml", ".zip"]},
        )

    fd, temp_path = tempfile.mkstemp(prefix="geo_upload_", suffix=ext)
    total_bytes = 0
    first_chunk = True
    file_type = ""

    try:
        with os.fdopen(fd, "wb") as f_out:
            while True:
                chunk = await upload_file.read(chunk_size)
                if not chunk:
                    break

                total_bytes += len(chunk)
                if total_bytes > max_bytes:
                    raise UploadSizeLimitExceeded(
                        f"File size exceeds maximum allowed upload limit of {max_bytes} bytes ({max_bytes // (1024 * 1024)} MB).",
                        details={"max_allowed_bytes": max_bytes, "received_bytes": total_bytes},
                    )

                if first_chunk:
                    file_type = detect_file_type_and_validate_header(filename, chunk[:512])
                    first_chunk = False

                f_out.write(chunk)

        if total_bytes == 0:
            raise FileValidationError("Uploaded file is empty (0 bytes).")

        return temp_path, file_type, total_bytes

    except Exception:
        # Guarantee cleanup on any failure
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass
        raise
