"""Unit tests for upload validation, header sniffing, and streaming limits."""
import io
import pytest
from starlette.datastructures import UploadFile
from app.core.exceptions import FileValidationError, UploadSizeLimitExceeded
from app.services.file_validator import (
    detect_file_type_and_validate_header,
    save_upload_safely_to_disk,
)


def test_invalid_extension_rejected():
    """Verify non-kml/non-zip extensions are rejected."""
    with pytest.raises(FileValidationError) as exc:
        detect_file_type_and_validate_header("dataset.geojson", b"{}")
    assert "Unsupported file format" in str(exc.value)


def test_kml_invalid_magic_bytes_rejected():
    """Verify .kml file without XML/KML signature is rejected."""
    with pytest.raises(FileValidationError) as exc:
        detect_file_type_and_validate_header("fake.kml", b"\x00\x01\x02\x03\x04")
    assert "does not contain valid KML/XML header" in str(exc.value)


def test_zip_invalid_magic_bytes_rejected():
    """Verify .zip file without ZIP magic bytes is rejected."""
    with pytest.raises(FileValidationError) as exc:
        detect_file_type_and_validate_header("fake.zip", b"This is plain text pretending to be a zip")
    assert "does not contain valid ZIP archive header" in str(exc.value)


import asyncio


def test_streaming_upload_size_limit_enforced():
    """Verify upload size limit is enforced while reading the stream, not after loading all into memory."""
    # Valid KML header with oversized content (2 KB stream with 1 KB limit)
    large_content = b"<?xml version='1.0'?><kml>" + (b"A" * 2048)
    stream = io.BytesIO(large_content)
    upload_file = UploadFile(filename="large.kml", file=stream)

    with pytest.raises(UploadSizeLimitExceeded) as exc:
        asyncio.run(save_upload_safely_to_disk(upload_file, max_bytes=1024, chunk_size=512))
    assert "exceeds maximum allowed upload limit" in str(exc.value)


def test_empty_upload_rejected():
    """Verify empty upload (0 bytes) is rejected."""
    stream = io.BytesIO(b"")
    upload_file = UploadFile(filename="empty.kml", file=stream)

    with pytest.raises(FileValidationError) as exc:
        asyncio.run(save_upload_safely_to_disk(upload_file))
    assert "Uploaded file is empty" in str(exc.value)
