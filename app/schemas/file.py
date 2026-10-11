"""Pydantic schemas for file upload and metadata endpoints."""
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field, model_validator


class FileMetadataResponse(BaseModel):
    """File metadata response returned by upload and GET /api/files/{id}/."""

    id: str = Field(..., description="Unique file identifier (UUID)")
    filename: str = Field(..., description="Original uploaded filename")
    feature_count: int = Field(..., description="Total count of features in dataset")
    crs: str = Field(..., description="Detected coordinate reference system (e.g., EPSG:4326)")
    CRS: Optional[str] = Field(default=None, description="Uppercase alias for CRS requirement")
    status: str = Field(..., description="Processing status: 'processed', 'processed_with_warnings', or 'failed'")
    warnings: List[str] = Field(default_factory=list, description="List of warnings encountered during processing")
    file_type: Optional[str] = Field(default=None, description="Dataset type: 'kml' or 'shapefile'")
    projected_crs_used: Optional[str] = Field(default=None, description="Projected metric CRS used for measurement")
    created_at: Optional[datetime] = Field(default=None, description="Timestamp of file upload and processing")

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="after")
    def sync_crs_aliases(self) -> "FileMetadataResponse":
        if self.CRS is None:
            self.CRS = self.crs
        return self
