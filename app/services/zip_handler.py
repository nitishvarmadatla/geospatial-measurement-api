"""Secure ZIP extraction and Shapefile bundle verification."""
import os
import zipfile
from dataclasses import dataclass
from typing import Optional

from app.core.config import settings
from app.core.exceptions import (
    ZipSecurityError,
    InvalidShapefileBundleError,
)


@dataclass
class ShapefileBundle:
    """Verified Shapefile bundle paths."""

    shp_path: str
    shx_path: str
    dbf_path: str
    prj_path: Optional[str]
    base_name: str
    has_prj: bool


def safe_extract_shapefile_zip(zip_file_path: str, extract_to_dir: str) -> ShapefileBundle:
    """Safely validate and extract a Shapefile ZIP archive.

    Guards:
    1. Validates zip file integrity.
    2. Enforces maximum file count (Zip bomb guard).
    3. Enforces single-file and total uncompressed size limits before extraction.
    4. Enforces compression ratio limits.
    5. Prevents path traversal (Zip Slip vulnerability).
    6. Verifies presence of mandatory .shp, .shx, .dbf components.
    7. Detects ambiguous multi-shapefile archives.
    8. Identifies optional .prj file or flags its absence.
    """
    if not zipfile.is_zipfile(zip_file_path):
        raise ZipSecurityError("Uploaded file is not a valid ZIP archive or is corrupted.")

    try:
        with zipfile.ZipFile(zip_file_path, "r") as zf:
            members = zf.infolist()

            if len(members) == 0:
                raise ZipSecurityError("ZIP archive is empty.")

            if len(members) > settings.MAX_ZIP_FILE_COUNT:
                raise ZipSecurityError(
                    f"ZIP archive contains {len(members)} files, which exceeds maximum allowed limit of {settings.MAX_ZIP_FILE_COUNT}.",
                    details={"file_count": len(members), "max_allowed": settings.MAX_ZIP_FILE_COUNT},
                )

            total_uncompressed_size = 0
            dest_dir_abs = os.path.abspath(extract_to_dir)

            for member in members:
                # 1. Path traversal guard
                # Disallow absolute paths, drive letters, and parent traversal
                filename = member.filename
                if filename.startswith("/") or filename.startswith("\\") or (len(filename) > 1 and filename[1] == ":"):
                    raise ZipSecurityError(
                        f"Zip Slip path traversal attempt detected in member '{filename}'.",
                        details={"suspicious_path": filename},
                    )

                norm_path = os.path.normpath(filename)
                if norm_path.startswith("..") or "/../" in filename or "\\..\\" in filename:
                    raise ZipSecurityError(
                        f"Zip Slip relative path traversal attempt detected in member '{filename}'.",
                        details={"suspicious_path": filename},
                    )

                target_path = os.path.abspath(os.path.join(dest_dir_abs, filename))
                if os.path.commonpath([dest_dir_abs, target_path]) != dest_dir_abs:
                    raise ZipSecurityError(
                        f"Zip Slip illegal target directory attempt detected in member '{filename}'.",
                        details={"target_path": target_path, "dest_dir": dest_dir_abs},
                    )

                # 2. Size guards
                if member.file_size > settings.MAX_ZIP_SINGLE_FILE_BYTES:
                    raise ZipSecurityError(
                        f"ZIP member '{filename}' exceeds maximum allowed uncompressed size ({member.file_size} > {settings.MAX_ZIP_SINGLE_FILE_BYTES} bytes).",
                        status_code=413,
                        details={"member": filename, "size": member.file_size},
                    )

                total_uncompressed_size += member.file_size
                if total_uncompressed_size > settings.MAX_ZIP_DECOMPRESSED_SIZE_BYTES:
                    raise ZipSecurityError(
                        f"Total uncompressed ZIP size exceeds maximum allowed limit ({total_uncompressed_size} > {settings.MAX_ZIP_DECOMPRESSED_SIZE_BYTES} bytes).",
                        status_code=413,
                        details={"total_size": total_uncompressed_size},
                    )

                # 3. Compression ratio check (for members with non-zero compressed size)
                if member.compress_size > 0:
                    ratio = member.file_size / member.compress_size
                    if ratio > settings.MAX_ZIP_COMPRESSION_RATIO and member.file_size > 1024 * 1024:
                        raise ZipSecurityError(
                            f"Suspicious compression ratio ({ratio:.1f}:1) detected for member '{filename}' (Zip bomb defense).",
                            details={"member": filename, "ratio": ratio},
                        )

            # Safe extraction
            for member in members:
                zf.extract(member, dest_dir_abs)

    except zipfile.BadZipFile as e:
        raise ZipSecurityError(f"Corrupted or invalid ZIP file: {str(e)}")

    # Discover Shapefile components
    shp_files = []
    for root, _, files in os.walk(dest_dir_abs):
        for f in files:
            if f.lower().endswith(".shp") and not f.startswith("."):
                shp_files.append(os.path.join(root, f))

    if not shp_files:
        raise InvalidShapefileBundleError(
            "ZIP archive does not contain any .shp file.",
            details={"extracted_dir": extract_to_dir},
        )

    if len(shp_files) > 1:
        base_names = [os.path.basename(p) for p in shp_files]
        raise InvalidShapefileBundleError(
            f"Ambiguous archive: found multiple Shapefiles ({', '.join(base_names)}). Please upload an archive containing exactly one Shapefile dataset.",
            details={"found_shapefiles": base_names},
        )

    shp_path = shp_files[0]
    shp_dir = os.path.dirname(shp_path)
    base_name = os.path.splitext(os.path.basename(shp_path))[0]

    # Look for matching components (case-insensitive on filesystem)
    shx_path = None
    dbf_path = None
    prj_path = None

    for fname in os.listdir(shp_dir):
        name_no_ext, ext = os.path.splitext(fname)
        if name_no_ext.lower() == base_name.lower():
            ext_lower = ext.lower()
            full_path = os.path.join(shp_dir, fname)
            if ext_lower == ".shx":
                shx_path = full_path
            elif ext_lower == ".dbf":
                dbf_path = full_path
            elif ext_lower == ".prj":
                prj_path = full_path

    if not shx_path:
        raise InvalidShapefileBundleError(
            f"Incomplete Shapefile bundle: missing required index component '{base_name}.shx'.",
            details={"missing_file": f"{base_name}.shx"},
        )

    if not dbf_path:
        raise InvalidShapefileBundleError(
            f"Incomplete Shapefile bundle: missing required attributes component '{base_name}.dbf'.",
            details={"missing_file": f"{base_name}.dbf"},
        )

    has_prj = prj_path is not None and os.path.exists(prj_path)

    return ShapefileBundle(
        shp_path=shp_path,
        shx_path=shx_path,
        dbf_path=dbf_path,
        prj_path=prj_path,
        base_name=base_name,
        has_prj=has_prj,
    )
