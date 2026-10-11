"""Abstract base classes and data transfer objects for geospatial parsers."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from shapely.geometry.base import BaseGeometry


@dataclass
class ParsedFeature:
    """Represents a single extracted geospatial feature."""

    feature_index: int
    feature_id: Optional[str]
    geometry: Optional[BaseGeometry]
    geometry_type: str
    properties: Dict[str, Any] = field(default_factory=dict)
    is_empty: bool = False
    is_valid: bool = True
    error_message: Optional[str] = None


@dataclass
class ParsedDataset:
    """Represents the complete extracted dataset from a KML or Shapefile."""

    file_type: str  # 'kml' or 'shapefile'
    crs: str  # e.g., 'EPSG:4326', 'UNKNOWN'
    is_crs_uncertain: bool = False
    crs_raw: Optional[str] = None
    features: List[ParsedFeature] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


class BaseParser(ABC):
    """Abstract interface for geospatial file parsers."""

    @abstractmethod
    def parse(self, file_path: str) -> ParsedDataset:
        """Parse geospatial file and return extracted dataset."""
        pass
