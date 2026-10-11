"""API endpoints for geospatial file upload, metadata lookup, and measurements."""
import os
import tempfile
import uuid
from typing import List
from fastapi import APIRouter, Depends, File, UploadFile, status
from sqlalchemy.orm import Session

from app.core.exceptions import FileNotFoundRecordError
from app.core.logging import logger
from app.db.models import FileModel, FeatureMeasurementModel
from app.db.session import get_db
from app.schemas.file import FileMetadataResponse
from app.schemas.measurement import (
    FileMeasurementsResponse,
    FeatureMeasurementResponse,
    MeasurementSummary,
)
from app.services.file_validator import save_upload_safely_to_disk
from app.services.zip_handler import safe_extract_shapefile_zip
from app.services.parsers.kml_parser import KmlParser
from app.services.parsers.shapefile_parser import ShapefileParser
from app.services.measurements import process_dataset_measurements

router = APIRouter(prefix="/files", tags=["files"])


@router.post(
    "/",
    response_model=FileMetadataResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload and process KML or Zipped Shapefile",
    description=(
        "Accepts a .kml file or a .zip file containing an ESRI Shapefile dataset. "
        "Validates magic bytes, extracts geometries, reprojects to suitable metric CRS, "
        "calculates feature measurements, and persists records in SQLite."
    ),
)
async def upload_file(
    file: UploadFile = File(..., description="A .kml file or a .zip archive containing a Shapefile dataset"),
    db: Session = Depends(get_db),
) -> FileMetadataResponse:
    # 1. Safely stream upload to temp file, enforcing upload limits
    temp_upload_path, file_type, file_size = await save_upload_safely_to_disk(file)

    try:
        # 2. Parse dataset based on type
        if file_type == "kml":
            parser = KmlParser()
            dataset = parser.parse(temp_upload_path)
        elif file_type == "shapefile":
            with tempfile.TemporaryDirectory(prefix="shp_extracted_") as extract_dir:
                bundle = safe_extract_shapefile_zip(temp_upload_path, extract_dir)
                parser = ShapefileParser(bundle.prj_path)
                dataset = parser.parse(bundle.shp_path)
        else:
            raise ValueError(f"Unrecognized file type: {file_type}")

        # 3. Calculate feature measurements in metric CRS
        measurement_result = process_dataset_measurements(dataset)

        # 4. Persist to SQLite
        file_id = str(uuid.uuid4())
        db_file = FileModel(
            id=file_id,
            filename=file.filename or "unknown_file",
            file_type=file_type,
            feature_count=len(measurement_result.features),
            crs=measurement_result.detected_crs,
            status=measurement_result.file_status,
            warnings=measurement_result.warnings,
            projected_crs_used=measurement_result.projected_crs_used,
        )
        db.add(db_file)

        for feat in measurement_result.features:
            db_feat = FeatureMeasurementModel(
                file_id=file_id,
                feature_index=feat.feature_index,
                feature_id=feat.feature_id,
                geometry_type=feat.geometry_type,
                area_sq_m=feat.area_sq_m,
                length_m=feat.length_m,
                measurement_unit=feat.measurement_unit,
                measurement_status=feat.measurement_status,
                status_message=feat.status_message,
                properties=feat.properties,
            )
            db.add(db_feat)

        db.commit()
        db.refresh(db_file)

        logger.info(
            f"Successfully processed and stored file '{db_file.filename}' (ID: {file_id}, "
            f"Features: {db_file.feature_count}, Status: {db_file.status})"
        )
        return FileMetadataResponse.model_validate(db_file)

    finally:
        # Guarantee cleanup of uploaded file
        if os.path.exists(temp_upload_path):
            try:
                os.remove(temp_upload_path)
            except OSError:
                pass


@router.get(
    "/{id}/",
    response_model=FileMetadataResponse,
    summary="Get file metadata and processing status",
    description="Returns metadata for an uploaded file: id, filename, feature_count, CRS, and status.",
)
def get_file_metadata(id: str, db: Session = Depends(get_db)) -> FileMetadataResponse:
    db_file = db.query(FileModel).filter(FileModel.id == id).first()
    if not db_file:
        raise FileNotFoundRecordError(file_id=id)

    return FileMetadataResponse.model_validate(db_file)


@router.get(
    "/{id}/measurements/",
    response_model=FileMeasurementsResponse,
    summary="Get feature-level measurements for a file",
    description="Returns feature-level measurements (area in sq_m, length in m, properties) and aggregate summary.",
)
def get_file_measurements(id: str, db: Session = Depends(get_db)) -> FileMeasurementsResponse:
    db_file = db.query(FileModel).filter(FileModel.id == id).first()
    if not db_file:
        raise FileNotFoundRecordError(file_id=id)

    # Compute summary statistics from persisted features
    total_area = 0.0
    total_length = 0.0
    poly_cnt = 0
    line_cnt = 0
    pt_cnt = 0
    unsupp_cnt = 0

    feature_responses: List[FeatureMeasurementResponse] = []
    for f in db_file.features:
        if f.area_sq_m is not None:
            total_area += f.area_sq_m
        if f.length_m is not None:
            total_length += f.length_m

        if f.geometry_type in ("Polygon", "MultiPolygon"):
            poly_cnt += 1
        elif f.geometry_type in ("LineString", "MultiLineString"):
            line_cnt += 1
        elif f.geometry_type in ("Point", "MultiPoint"):
            pt_cnt += 1
        else:
            unsupp_cnt += 1

        feature_responses.append(
            FeatureMeasurementResponse(
                feature_index=f.feature_index,
                feature_id=f.feature_id,
                geometry_type=f.geometry_type,
                area_sq_m=f.area_sq_m,
                length_m=f.length_m,
                measurement_unit=f.measurement_unit,
                measurement_status=f.measurement_status,
                status_message=f.status_message,
                properties=f.properties or {},
            )
        )

    summary = MeasurementSummary(
        total_area_sq_m=round(total_area, 4),
        total_length_m=round(total_length, 4),
        polygon_count=poly_cnt,
        linestring_count=line_cnt,
        point_count=pt_cnt,
        unsupported_count=unsupp_cnt,
    )

    return FileMeasurementsResponse(
        file_id=db_file.id,
        filename=db_file.filename,
        feature_count=db_file.feature_count,
        crs=db_file.crs,
        projected_crs_used=db_file.projected_crs_used,
        status=db_file.status,
        warnings=db_file.warnings or [],
        summary=summary,
        features=feature_responses,
    )
