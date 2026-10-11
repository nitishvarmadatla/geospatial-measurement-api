"""CRS analysis, validation, metric projection selection, and coordinate transformation."""
import math
from dataclasses import dataclass
from typing import Optional, Tuple, List
import pyproj
from pyproj import CRS, Transformer
import shapely.ops
from shapely.geometry.base import BaseGeometry

from app.core.logging import logger


@dataclass
class CrsAnalysisResult:
    """Result of CRS inspection and metric projection selection."""

    source_crs_str: str
    is_valid_crs: bool
    is_uncertain: bool
    is_geographic: bool
    is_projected: bool
    projected_crs_str: Optional[str]
    unit_name: str
    linear_unit_scale_to_meters: float
    area_unit_scale_to_sq_meters: float
    transformer: Optional[Transformer]
    warning: Optional[str] = None


def parse_and_validate_crs(crs_input: Optional[str]) -> Tuple[Optional[CRS], bool, Optional[str]]:
    """Parse user CRS string or WKT.

    Returns:
        (pyproj.CRS object or None, is_valid, error_reason)
    """
    if not crs_input or crs_input.strip() in ("", "UNKNOWN", "None"):
        return None, False, "Missing CRS specification (.prj not provided or empty)"

    try:
        crs_obj = CRS.from_user_input(crs_input)
        return crs_obj, True, None
    except Exception as e:
        logger.warning(f"Failed to parse CRS '{crs_input}': {e}")
        return None, False, f"Invalid or unparseable CRS definition: {str(e)}"


def determine_utm_or_projected_crs(
    source_crs: CRS,
    bbox: Optional[Tuple[float, float, float, float]] = None,
) -> Tuple[str, Optional[Transformer], Optional[str]]:
    """For a geographic CRS, select a suitable projected metric CRS based on bbox/centroid.

    Args:
        source_crs: Source geographic CRS
        bbox: (minx, miny, maxx, maxy) in geographic coordinates (lon, lat)

    Returns:
        (target_crs_str, transformer, warning_or_note)
    """
    minx, miny, maxx, maxy = bbox or (0.0, 0.0, 0.0, 0.0)

    # 1. Antimeridian crossing check
    # In standard GIS, if minx > maxx or bbox crosses 180 / -180
    antimeridian = False
    if minx > maxx:
        antimeridian = True
        lon_span = (180 - minx) + (maxx - (-180))
        centroid_lon = ((minx + (lon_span / 2.0) + 180) % 360) - 180
    else:
        lon_span = maxx - minx
        centroid_lon = (minx + maxx) / 2.0

    centroid_lat = (miny + maxy) / 2.0
    # Clamp centroid coordinates
    centroid_lat = max(-89.9, min(89.9, centroid_lat))
    centroid_lon = max(-180.0, min(180.0, centroid_lon))

    # 2. Polar region check (UPS instead of UTM)
    if centroid_lat > 84.0:
        target_crs_str = "EPSG:32661"  # WGS 84 / UPS North
        warning = "High-latitude dataset (above 84°N); projected to WGS 84 / UPS North (EPSG:32661)."
        target_crs = CRS.from_user_input(target_crs_str)
        transformer = Transformer.from_crs(source_crs, target_crs, always_xy=True)
        return target_crs_str, transformer, warning
    elif centroid_lat < -80.0:
        target_crs_str = "EPSG:32761"  # WGS 84 / UPS South
        warning = "High-latitude dataset (below 80°S); projected to WGS 84 / UPS South (EPSG:32761)."
        target_crs = CRS.from_user_input(target_crs_str)
        transformer = Transformer.from_crs(source_crs, target_crs, always_xy=True)
        return target_crs_str, transformer, warning

    # 3. Check longitude span / Multi-zone extent
    if lon_span > 6.0 or antimeridian:
        # Multi-zone dataset (> 6 degrees longitude).
        # A single UTM zone would induce unacceptable scale distortion at edges (> 1:1000).
        # Use custom centered Lambert Azimuthal Equal-Area (LAEA) projection in metric units.
        target_crs_str = (
            f"+proj=laea +lat_0={centroid_lat:.4f} +lon_0={centroid_lon:.4f} "
            f"+x_0=0 +y_0=0 +datum=WGS84 +units=m +no_defs"
        )
        warning = (
            f"Dataset spans multiple UTM zones (longitude extent {lon_span:.2f}° > 6.0°); "
            f"projected to custom centered Lambert Azimuthal Equal-Area (LAEA) metric projection to preserve true surface area."
        )
        target_crs = CRS.from_proj4(target_crs_str)
        transformer = Transformer.from_crs(source_crs, target_crs, always_xy=True)
        return target_crs_str, transformer, warning

    # 4. Standard local UTM Zone calculation
    utm_zone = int(math.floor((centroid_lon + 180.0) / 6.0)) + 1
    utm_zone = max(1, min(60, utm_zone))

    if centroid_lat >= 0:
        epsg_code = 32600 + utm_zone
    else:
        epsg_code = 32700 + utm_zone

    target_crs_str = f"EPSG:{epsg_code}"
    target_crs = CRS.from_user_input(target_crs_str)
    transformer = Transformer.from_crs(source_crs, target_crs, always_xy=True)
    return target_crs_str, transformer, None


def analyze_crs_and_prepare_transformer(
    raw_crs_str: Optional[str],
    bbox: Optional[Tuple[float, float, float, float]] = None,
    is_kml: bool = False,
) -> CrsAnalysisResult:
    """Analyze source CRS, check validity, unit scale, and prepare metric projection transformer."""
    # KML format standard defines WGS84 (EPSG:4326)
    if is_kml:
        raw_crs_str = "EPSG:4326"

    crs_obj, is_valid, err_msg = parse_and_validate_crs(raw_crs_str)

    # Clarification 1: Do not silently assume EPSG:4326 for Shapefiles with missing or invalid .prj!
    if not is_valid or crs_obj is None:
        return CrsAnalysisResult(
            source_crs_str="UNKNOWN",
            is_valid_crs=False,
            is_uncertain=True,
            is_geographic=False,
            is_projected=False,
            projected_crs_str=None,
            unit_name="unknown",
            linear_unit_scale_to_meters=1.0,
            area_unit_scale_to_sq_meters=1.0,
            transformer=None,
            warning=f"CRS uncertainty: {err_msg}. Planar measurements skipped to prevent inaccurate results.",
        )

    # Check if geographic
    if crs_obj.is_geographic:
        projected_crs_str, transformer, warning = determine_utm_or_projected_crs(crs_obj, bbox)
        return CrsAnalysisResult(
            source_crs_str=crs_obj.to_string(),
            is_valid_crs=True,
            is_uncertain=False,
            is_geographic=True,
            is_projected=False,
            projected_crs_str=projected_crs_str,
            unit_name="metre",
            linear_unit_scale_to_meters=1.0,
            area_unit_scale_to_sq_meters=1.0,
            transformer=transformer,
            warning=warning,
        )

    # Check if projected
    if crs_obj.is_projected:
        # Determine linear unit
        unit_name = "metre"
        linear_scale = 1.0
        area_scale = 1.0

        try:
            axis_unit = crs_obj.axis_info[0].unit_name.lower()
            unit_name = axis_unit
            if "foot" in axis_unit or "feet" in axis_unit:
                if "survey" in axis_unit:
                    linear_scale = 1200.0 / 3937.0  # US Survey foot ~ 0.3048006096 m
                else:
                    linear_scale = 0.3048  # International foot
                area_scale = linear_scale ** 2
        except Exception:
            unit_name = "metre"

        return CrsAnalysisResult(
            source_crs_str=crs_obj.to_string(),
            is_valid_crs=True,
            is_uncertain=False,
            is_geographic=False,
            is_projected=True,
            projected_crs_str=crs_obj.to_string(),
            unit_name=unit_name,
            linear_unit_scale_to_meters=linear_scale,
            area_unit_scale_to_sq_meters=area_scale,
            transformer=None,  # Already projected; direct planar calculation with scale factor
            warning=None if unit_name == "metre" else f"Source CRS uses non-metric units ('{unit_name}'); scaled to standard metres and square metres.",
        )

    # Other CRS types (e.g., compound, engineering)
    return CrsAnalysisResult(
        source_crs_str=crs_obj.to_string(),
        is_valid_crs=True,
        is_uncertain=True,
        is_geographic=False,
        is_projected=False,
        projected_crs_str=None,
        unit_name="unknown",
        linear_unit_scale_to_meters=1.0,
        area_unit_scale_to_sq_meters=1.0,
        transformer=None,
        warning="CRS is neither standard geographic nor projected. Planar measurements skipped.",
    )


def project_geometry(geom: BaseGeometry, transformer: Optional[Transformer]) -> BaseGeometry:
    """Transform geometry coordinates to projected metric system (strips 3rd dimension if present)."""
    if transformer is None:
        return geom

    def _transform_coords(x, y, z=None):
        res = transformer.transform(x, y)
        return (res[0], res[1])

    return shapely.ops.transform(_transform_coords, geom)
