"""Security tests for ZIP extraction: path traversal, zip bombs, and shapefile completeness."""
import io
import os
import tempfile
import zipfile
import pytest

from app.core.exceptions import (
    ZipSecurityError,
    InvalidShapefileBundleError,
)
from app.services.zip_handler import safe_extract_shapefile_zip
from tests.conftest import create_shapefile_zip_bytes


def test_zip_slip_relative_path_traversal():
    """Verify Zip Slip path traversal attempts are detected and blocked."""
    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w") as zf:
        zf.writestr("../../evil.txt", "malicious payload")
    zip_buf.seek(0)

    with tempfile.TemporaryDirectory() as tmpdir:
        bad_zip_path = os.path.join(tmpdir, "bad.zip")
        with open(bad_zip_path, "wb") as f:
            f.write(zip_buf.getvalue())

        with pytest.raises(ZipSecurityError) as exc_info:
            safe_extract_shapefile_zip(bad_zip_path, os.path.join(tmpdir, "out"))
        assert "Zip Slip" in str(exc_info.value)


def test_zip_excessive_file_count_rejected():
    """Verify ZIP files with excessive member counts are rejected (Zip bomb defense)."""
    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w") as zf:
        for i in range(55):  # Max allowed is 50
            zf.writestr(f"file_{i}.txt", "test")
    zip_buf.seek(0)

    with tempfile.TemporaryDirectory() as tmpdir:
        zip_path = os.path.join(tmpdir, "many_files.zip")
        with open(zip_path, "wb") as f:
            f.write(zip_buf.getvalue())

        with pytest.raises(ZipSecurityError) as exc_info:
            safe_extract_shapefile_zip(zip_path, os.path.join(tmpdir, "out"))
        assert "exceeds maximum allowed limit" in str(exc_info.value)


def test_zip_missing_mandatory_components():
    """Verify missing .shx or .dbf components raise InvalidShapefileBundleError."""
    # 1. Missing .shx
    zip_no_shx = create_shapefile_zip_bytes(include_shx=False)
    with tempfile.TemporaryDirectory() as tmpdir:
        zip_path = os.path.join(tmpdir, "no_shx.zip")
        with open(zip_path, "wb") as f:
            f.write(zip_no_shx)

        with pytest.raises(InvalidShapefileBundleError) as exc_info:
            safe_extract_shapefile_zip(zip_path, os.path.join(tmpdir, "out"))
        assert "missing required index component" in str(exc_info.value)

    # 2. Missing .dbf
    zip_no_dbf = create_shapefile_zip_bytes(include_dbf=False)
    with tempfile.TemporaryDirectory() as tmpdir:
        zip_path = os.path.join(tmpdir, "no_dbf.zip")
        with open(zip_path, "wb") as f:
            f.write(zip_no_dbf)

        with pytest.raises(InvalidShapefileBundleError) as exc_info:
            safe_extract_shapefile_zip(zip_path, os.path.join(tmpdir, "out"))
        assert "missing required attributes component" in str(exc_info.value)


def test_zip_ambiguous_multiple_shapefiles():
    """Verify ZIP containing multiple distinct Shapefile datasets is rejected as ambiguous."""
    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w") as zf:
        zf.writestr("parcels.shp", "shp_content")
        zf.writestr("parcels.shx", "shx_content")
        zf.writestr("parcels.dbf", "dbf_content")
        zf.writestr("roads.shp", "shp_content")
        zf.writestr("roads.shx", "shx_content")
        zf.writestr("roads.dbf", "dbf_content")
    zip_buf.seek(0)

    with tempfile.TemporaryDirectory() as tmpdir:
        zip_path = os.path.join(tmpdir, "multi.zip")
        with open(zip_path, "wb") as f:
            f.write(zip_buf.getvalue())

        with pytest.raises(InvalidShapefileBundleError) as exc_info:
            safe_extract_shapefile_zip(zip_path, os.path.join(tmpdir, "out"))
        assert "Ambiguous archive: found multiple Shapefiles" in str(exc_info.value)


def test_corrupt_zip_file():
    """Verify corrupt ZIP file is rejected."""
    with tempfile.TemporaryDirectory() as tmpdir:
        zip_path = os.path.join(tmpdir, "corrupt.zip")
        with open(zip_path, "wb") as f:
            f.write(b"not a valid zip file binary")

        with pytest.raises(ZipSecurityError):
            safe_extract_shapefile_zip(zip_path, os.path.join(tmpdir, "out"))
