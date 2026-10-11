"""SQLAlchemy ORM models for file metadata and feature measurements."""
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, Float, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship

from app.db.base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class FileModel(Base):
    """Stores geospatial file metadata and processing summary."""

    __tablename__ = "files"

    id = Column(String(36), primary_key=True, index=True)
    filename = Column(String(255), nullable=False)
    file_type = Column(String(32), nullable=False)  # 'kml' or 'shapefile'
    feature_count = Column(Integer, nullable=False, default=0)
    crs = Column(String(128), nullable=False, default="UNKNOWN")
    status = Column(String(64), nullable=False, default="processed")  # 'processed', 'processed_with_warnings', 'failed'
    warnings = Column(JSON, nullable=False, default=list)
    projected_crs_used = Column(String(128), nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    # Relationships
    features = relationship(
        "FeatureMeasurementModel",
        back_populates="file",
        cascade="all, delete-orphan",
        order_by="FeatureMeasurementModel.feature_index",
    )


class FeatureMeasurementModel(Base):
    """Stores feature-level measurements and properties."""

    __tablename__ = "feature_measurements"

    id = Column(Integer, primary_key=True, autoincrement=True)
    file_id = Column(String(36), ForeignKey("files.id", ondelete="CASCADE"), nullable=False, index=True)
    feature_index = Column(Integer, nullable=False)
    feature_id = Column(String(128), nullable=True)
    geometry_type = Column(String(64), nullable=False)

    # Measurements
    area_sq_m = Column(Float, nullable=True)
    length_m = Column(Float, nullable=True)
    measurement_unit = Column(String(32), nullable=True)  # 'sq_m', 'm', or None
    measurement_status = Column(String(64), nullable=False, default="success")
    status_message = Column(String(255), nullable=True)

    # GeoJSON / DBF / KML attributes
    properties = Column(JSON, nullable=False, default=dict)

    # Relationships
    file = relationship("FileModel", back_populates="features")
