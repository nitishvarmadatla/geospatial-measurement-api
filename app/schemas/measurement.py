"""Pydantic schemas for feature measurements and aggregation summaries."""
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field, model_validator


class FeatureMeasurementResponse(BaseModel):
    """Measurement result for an individual geospatial feature."""

    feature_index: int = Field(..., description="0-based sequential index from source dataset")
    feature_id: Optional[str] = Field(default=None, description="Feature ID or Placemark identifier")
    geometry_type: str = Field(..., description="Geometry type: Polygon, LineString, Point, etc.")
    area_sq_m: Optional[float] = Field(default=None, description="Polygon/MultiPolygon planar area in square metres (sq_m)")
    length_m: Optional[float] = Field(default=None, description="LineString/MultiLineString length in metres (m)")
    measurement_unit: Optional[str] = Field(default=None, description="Measurement unit ('sq_m', 'm', or null for Points/unsupported)")
    measurement_status: str = Field(..., description="Status: 'success', 'not_applicable', 'unsupported_geometry', 'empty_geometry', 'skipped_missing_crs', 'projection_error'")
    status_message: Optional[str] = Field(default=None, description="Explanatory message if not standard measurement")
    properties: Dict[str, Any] = Field(default_factory=dict, description="Feature attributes and properties")

    model_config = ConfigDict(from_attributes=True)


class MeasurementSummary(BaseModel):
    """Aggregate summary statistics across all features in the file."""

    total_area_sq_m: float = Field(0.0, description="Sum of polygon areas in square metres")
    total_length_m: float = Field(0.0, description="Sum of linestring lengths in metres")
    polygon_count: int = Field(0, description="Count of Polygon and MultiPolygon features")
    linestring_count: int = Field(0, description="Count of LineString and MultiLineString features")
    point_count: int = Field(0, description="Count of Point and MultiPoint features")
    unsupported_count: int = Field(0, description="Count of unsupported or empty geometries")


class FileMeasurementsResponse(BaseModel):
    """Complete measurement response returned by GET /api/files/{id}/measurements/."""

    file_id: str = Field(..., description="File identifier UUID")
    filename: str = Field(..., description="Original filename")
    feature_count: int = Field(..., description="Total count of features")
    crs: str = Field(..., description="Detected coordinate reference system")
    CRS: Optional[str] = Field(default=None, description="Uppercase CRS alias")
    projected_crs_used: Optional[str] = Field(default=None, description="Projected metric CRS used for measurement")
    status: str = Field(..., description="Processing status")
    warnings: List[str] = Field(default_factory=list, description="Warnings encountered during processing")
    summary: MeasurementSummary = Field(..., description="Aggregate measurement summary")
    features: List[FeatureMeasurementResponse] = Field(default_factory=list, description="List of feature-level measurements")

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="after")
    def sync_crs_aliases(self) -> "FileMeasurementsResponse":
        if self.CRS is None:
            self.CRS = self.crs
        return self
