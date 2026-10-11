"""Feature measurement service computing projected area and length with unit scaling."""
from dataclasses import dataclass
from typing import List, Dict, Any, Optional, Tuple
from shapely.geometry.base import BaseGeometry

from app.core.logging import logger
from app.services.parsers.base import ParsedDataset, ParsedFeature
from app.services.crs_transformer import (
    analyze_crs_and_prepare_transformer,
    project_geometry,
    CrsAnalysisResult,
)


@dataclass
class MeasuredFeature:
    """Calculated measurement record for a single feature."""

    feature_index: int
    feature_id: Optional[str]
    geometry_type: str
    area_sq_m: Optional[float]
    length_m: Optional[float]
    measurement_unit: Optional[str]
    measurement_status: str
    status_message: Optional[str]
    properties: Dict[str, Any]


@dataclass
class ProcessedDatasetResult:
    """Complete measurement result for a processed file."""

    detected_crs: str
    projected_crs_used: Optional[str]
    file_status: str
    warnings: List[str]
    features: List[MeasuredFeature]
    total_area_sq_m: float
    total_length_m: float
    polygon_count: int
    linestring_count: int
    point_count: int
    unsupported_count: int


def calculate_dataset_bbox(features: List[ParsedFeature]) -> Optional[Tuple[float, float, float, float]]:
    """Compute combined bounding box across all valid geometries in dataset."""
    minx, miny, maxx, maxy = float("inf"), float("inf"), float("-inf"), float("-inf")
    found_any = False

    for feat in features:
        if feat.geometry is not None and not feat.geometry.is_empty:
            bounds = feat.geometry.bounds  # (minx, miny, maxx, maxy)
            minx = min(minx, bounds[0])
            miny = min(miny, bounds[1])
            maxx = max(maxx, bounds[2])
            maxy = max(maxy, bounds[3])
            found_any = True

    if not found_any:
        return None
    return (minx, miny, maxx, maxy)


def process_dataset_measurements(dataset: ParsedDataset) -> ProcessedDatasetResult:
    """Transform features into metric CRS and calculate exact area and length.

    Adheres strictly to assignment rules:
    - Polygons/MultiPolygons: area in sq metres (sq_m)
    - LineStrings/MultiLineStrings: length in metres (m)
    - Points/MultiPoints: no measurement (null values with clear status)
    - Unsupported or empty geometries: handled gracefully per feature
    - Missing/invalid CRS: skipped measurements with structured uncertainty warning
    """
    warnings: List[str] = list(dataset.warnings)

    # 1. Compute dataset bounding box
    bbox = calculate_dataset_bbox(dataset.features)

    # 2. Analyze CRS and get transformer
    is_kml = dataset.file_type == "kml"
    raw_crs = dataset.crs_raw if dataset.crs_raw else dataset.crs
    crs_analysis: CrsAnalysisResult = analyze_crs_and_prepare_transformer(
        raw_crs_str=raw_crs,
        bbox=bbox,
        is_kml=is_kml,
    )

    if crs_analysis.warning:
        warnings.append(crs_analysis.warning)

    measured_features: List[MeasuredFeature] = []
    total_area = 0.0
    total_length = 0.0
    polygon_count = 0
    linestring_count = 0
    point_count = 0
    unsupported_count = 0

    for feat in dataset.features:
        f_idx = feat.feature_index
        f_id = feat.feature_id
        g_type = feat.geometry_type
        props = feat.properties

        # Case A: Feature is empty or corrupted
        if feat.is_empty or feat.geometry is None:
            unsupported_count += 1
            measured_features.append(
                MeasuredFeature(
                    feature_index=f_idx,
                    feature_id=f_id,
                    geometry_type=g_type if g_type != "Unknown" else "Empty",
                    area_sq_m=None,
                    length_m=None,
                    measurement_unit=None,
                    measurement_status="empty_geometry",
                    status_message=feat.error_message or "Feature contains empty or null geometry",
                    properties=props,
                )
            )
            continue

        # Case B: Point or MultiPoint (Req 6: Points require no measurement)
        if g_type in ("Point", "MultiPoint"):
            point_count += 1
            measured_features.append(
                MeasuredFeature(
                    feature_index=f_idx,
                    feature_id=f_id,
                    geometry_type=g_type,
                    area_sq_m=None,
                    length_m=None,
                    measurement_unit=None,
                    measurement_status="not_applicable",
                    status_message="Point geometry requires no measurement",
                    properties=props,
                )
            )
            continue

        # Case C: Missing / uncertain CRS (Clarification 1)
        if crs_analysis.is_uncertain or not crs_analysis.is_valid_crs:
            if g_type in ("Polygon", "MultiPolygon"):
                polygon_count += 1
            elif g_type in ("LineString", "MultiLineString"):
                linestring_count += 1
            else:
                unsupported_count += 1

            measured_features.append(
                MeasuredFeature(
                    feature_index=f_idx,
                    feature_id=f_id,
                    geometry_type=g_type,
                    area_sq_m=None,
                    length_m=None,
                    measurement_unit=None,
                    measurement_status="skipped_missing_crs",
                    status_message="Planar measurement skipped due to missing or unparseable .prj file (CRS uncertainty)",
                    properties=props,
                )
            )
            continue

        # Case D: Polygon or MultiPolygon (Req 4: Area in sq metres)
        if g_type in ("Polygon", "MultiPolygon"):
            polygon_count += 1
            try:
                proj_geom = project_geometry(feat.geometry, crs_analysis.transformer)
                area_val = proj_geom.area * crs_analysis.area_unit_scale_to_sq_meters
                area_rounded = round(float(area_val), 4)
                total_area += area_rounded

                measured_features.append(
                    MeasuredFeature(
                        feature_index=f_idx,
                        feature_id=f_id,
                        geometry_type=g_type,
                        area_sq_m=area_rounded,
                        length_m=None,
                        measurement_unit="sq_m",
                        measurement_status="success",
                        status_message=None,
                        properties=props,
                    )
                )
            except Exception as e:
                logger.error(f"Error calculating area for feature {f_idx}: {e}")
                measured_features.append(
                    MeasuredFeature(
                        feature_index=f_idx,
                        feature_id=f_id,
                        geometry_type=g_type,
                        area_sq_m=None,
                        length_m=None,
                        measurement_unit=None,
                        measurement_status="projection_error",
                        status_message=f"Projection or measurement calculation failed: {str(e)}",
                        properties=props,
                    )
                )
            continue

        # Case E: LineString or MultiLineString (Req 5: Length in metres)
        if g_type in ("LineString", "MultiLineString"):
            linestring_count += 1
            try:
                proj_geom = project_geometry(feat.geometry, crs_analysis.transformer)
                len_val = proj_geom.length * crs_analysis.linear_unit_scale_to_meters
                len_rounded = round(float(len_val), 4)
                total_length += len_rounded

                measured_features.append(
                    MeasuredFeature(
                        feature_index=f_idx,
                        feature_id=f_id,
                        geometry_type=g_type,
                        area_sq_m=None,
                        length_m=len_rounded,
                        measurement_unit="m",
                        measurement_status="success",
                        status_message=None,
                        properties=props,
                    )
                )
            except Exception as e:
                logger.error(f"Error calculating length for feature {f_idx}: {e}")
                measured_features.append(
                    MeasuredFeature(
                        feature_index=f_idx,
                        feature_id=f_id,
                        geometry_type=g_type,
                        area_sq_m=None,
                        length_m=None,
                        measurement_unit=None,
                        measurement_status="projection_error",
                        status_message=f"Projection or measurement calculation failed: {str(e)}",
                        properties=props,
                    )
                )
            continue

        # Case F: Unsupported geometry type (Req 7: Handle gracefully without crashing)
        unsupported_count += 1
        measured_features.append(
            MeasuredFeature(
                feature_index=f_idx,
                feature_id=f_id,
                geometry_type=g_type,
                area_sq_m=None,
                length_m=None,
                measurement_unit=None,
                measurement_status="unsupported_geometry",
                status_message=f"Geometry type '{g_type}' is unsupported for area/length measurement",
                properties=props,
            )
        )

    # Determine overall file processing status
    if warnings:
        file_status = "processed_with_warnings"
    else:
        file_status = "processed"

    return ProcessedDatasetResult(
        detected_crs=crs_analysis.source_crs_str,
        projected_crs_used=crs_analysis.projected_crs_str,
        file_status=file_status,
        warnings=warnings,
        features=measured_features,
        total_area_sq_m=round(total_area, 4),
        total_length_m=round(total_length, 4),
        polygon_count=polygon_count,
        linestring_count=linestring_count,
        point_count=point_count,
        unsupported_count=unsupported_count,
    )
