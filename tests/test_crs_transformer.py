"""Unit tests for CRS analysis, UTM zone selection, and multi-zone handling."""
from app.services.crs_transformer import (
    analyze_crs_and_prepare_transformer,
    parse_and_validate_crs,
)


def test_utm_zone_selection_northern_hemisphere():
    """Verify local UTM zone selection in Northern Hemisphere."""
    # Centroid: Lon 77.0, Lat 12.0 (India) -> Zone (77 + 180)/6 + 1 = 43 -> EPSG:32643
    res = analyze_crs_and_prepare_transformer("EPSG:4326", bbox=(76.9, 11.9, 77.1, 12.1))
    assert res.is_valid_crs is True
    assert res.is_geographic is True
    assert res.projected_crs_str == "EPSG:32643"
    assert res.transformer is not None
    assert res.warning is None


def test_utm_zone_selection_southern_hemisphere():
    """Verify local UTM zone selection in Southern Hemisphere."""
    # Centroid: Lon 151.0, Lat -33.0 (Sydney) -> Zone (151 + 180)/6 + 1 = 56 -> EPSG:32756
    res = analyze_crs_and_prepare_transformer("EPSG:4326", bbox=(150.9, -33.1, 151.1, -32.9))
    assert res.is_valid_crs is True
    assert res.projected_crs_str == "EPSG:32756"
    assert res.transformer is not None


def test_multi_zone_dataset_selection():
    """Verify wide extent datasets spanning > 6 deg lon select LAEA equal-area projection."""
    # Bbox spans from Lon 0 to Lon 15 (15 degrees > 6.0 deg)
    res = analyze_crs_and_prepare_transformer("EPSG:4326", bbox=(0.0, 10.0, 15.0, 12.0))
    assert res.is_valid_crs is True
    assert "+proj=laea" in res.projected_crs_str
    assert res.warning is not None
    assert "spans multiple UTM zones" in res.warning


def test_polar_region_ups_projection():
    """Verify polar datasets select Universal Polar Stereographic (UPS)."""
    # Lat 85 deg N
    res_north = analyze_crs_and_prepare_transformer("EPSG:4326", bbox=(10.0, 84.5, 12.0, 85.5))
    assert res_north.projected_crs_str == "EPSG:32661"
    assert "UPS North" in res_north.warning

    # Lat -85 deg S
    res_south = analyze_crs_and_prepare_transformer("EPSG:4326", bbox=(10.0, -86.0, 12.0, -84.5))
    assert res_south.projected_crs_str == "EPSG:32761"
    assert "UPS South" in res_south.warning


def test_missing_crs_flags_uncertainty():
    """Verify missing or empty CRS is flagged as uncertain without guessing EPSG:4326."""
    res = analyze_crs_and_prepare_transformer(None, is_kml=False)
    assert res.is_valid_crs is False
    assert res.is_uncertain is True
    assert res.source_crs_str == "UNKNOWN"
    assert res.transformer is None
    assert "CRS uncertainty" in res.warning


def test_pre_projected_crs_with_feet_units():
    """Verify pre-projected CRS with US Survey Feet converts units to metres."""
    # EPSG:2263: NAD83 / New York Long Island (ftUS)
    res = analyze_crs_and_prepare_transformer("EPSG:2263")
    assert res.is_projected is True
    assert res.is_valid_crs is True
    assert "foot" in res.unit_name.lower() or "feet" in res.unit_name.lower()
    # Linear scale should be ~0.3048
    assert abs(res.linear_unit_scale_to_meters - (1200.0 / 3937.0)) < 1e-6
    assert abs(res.area_unit_scale_to_sq_meters - (1200.0 / 3937.0) ** 2) < 1e-6


def test_antimeridian_crossing_selection():
    """Verify antimeridian crossing dataset (minx > maxx) triggers LAEA equal-area projection."""
    # Bbox crossing 180 degrees: minx=175.0, maxx=-175.0
    res = analyze_crs_and_prepare_transformer("EPSG:4326", bbox=(175.0, -10.0, -175.0, 10.0))
    assert res.is_valid_crs is True
    assert "+proj=laea" in res.projected_crs_str
    assert res.warning is not None
