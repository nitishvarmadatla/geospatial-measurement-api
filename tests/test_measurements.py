"""Unit tests for feature measurements: area, length, points, holes, and unsupported types."""
import pytest
from shapely.geometry import (
    Polygon,
    LineString,
    Point,
    MultiPoint,
    MultiPolygon,
    MultiLineString,
    GeometryCollection,
)
from app.services.parsers.base import ParsedDataset, ParsedFeature
from app.services.measurements import process_dataset_measurements
from tests.conftest import (
    box_wgs_outer,
    box_wgs_hole,
    line_wgs,
    EXPECTED_POLYGON_HOLE_AREA_SQ_M,
    EXPECTED_LINE_LENGTH_M,
)


def test_polygon_with_hole_area_accuracy():
    """Verify polygon with interior hole calculates accurate area in square metres within 0.5% tolerance."""
    poly = Polygon(shell=box_wgs_outer, holes=[box_wgs_hole])
    feat = ParsedFeature(
        feature_index=0,
        feature_id="poly_1",
        geometry=poly,
        geometry_type="Polygon",
    )
    dataset = ParsedDataset(
        file_type="kml",
        crs="EPSG:4326",
        features=[feat],
    )

    result = process_dataset_measurements(dataset)
    assert len(result.features) == 1
    measured = result.features[0]

    assert measured.measurement_status == "success"
    assert measured.measurement_unit == "sq_m"
    assert measured.area_sq_m is not None
    assert measured.length_m is None

    # Check value within 0.5% of expected 9600 sq m
    tolerance = EXPECTED_POLYGON_HOLE_AREA_SQ_M * 0.005
    assert abs(measured.area_sq_m - EXPECTED_POLYGON_HOLE_AREA_SQ_M) <= tolerance
    assert result.polygon_count == 1
    assert abs(result.total_area_sq_m - EXPECTED_POLYGON_HOLE_AREA_SQ_M) <= tolerance


def test_linestring_length_accuracy():
    """Verify linestring calculates accurate length in metres within 0.5% tolerance."""
    line = LineString(line_wgs)
    feat = ParsedFeature(
        feature_index=0,
        feature_id="line_1",
        geometry=line,
        geometry_type="LineString",
    )
    dataset = ParsedDataset(
        file_type="kml",
        crs="EPSG:4326",
        features=[feat],
    )

    result = process_dataset_measurements(dataset)
    assert len(result.features) == 1
    measured = result.features[0]

    assert measured.measurement_status == "success"
    assert measured.measurement_unit == "m"
    assert measured.length_m is not None
    assert measured.area_sq_m is None

    tolerance = EXPECTED_LINE_LENGTH_M * 0.005
    assert abs(measured.length_m - EXPECTED_LINE_LENGTH_M) <= tolerance
    assert result.linestring_count == 1
    assert abs(result.total_length_m - EXPECTED_LINE_LENGTH_M) <= tolerance


def test_points_require_no_measurement():
    """Verify Point and MultiPoint return null area and length with not_applicable status."""
    pt = Point(box_wgs_outer[0])
    m_pt = MultiPoint([box_wgs_outer[0], box_wgs_outer[1]])

    features = [
        ParsedFeature(feature_index=0, feature_id="pt_1", geometry=pt, geometry_type="Point"),
        ParsedFeature(feature_index=1, feature_id="mpt_1", geometry=m_pt, geometry_type="MultiPoint"),
    ]
    dataset = ParsedDataset(file_type="kml", crs="EPSG:4326", features=features)

    result = process_dataset_measurements(dataset)
    assert len(result.features) == 2
    for m in result.features:
        assert m.measurement_status == "not_applicable"
        assert m.area_sq_m is None
        assert m.length_m is None
        assert m.measurement_unit is None
        assert "Point geometry requires no measurement" in m.status_message

    assert result.point_count == 2
    assert result.total_area_sq_m == 0.0
    assert result.total_length_m == 0.0


def test_unsupported_and_empty_geometries_graceful_handling():
    """Verify GeometryCollection and empty geometries are handled gracefully without crashing."""
    gc = GeometryCollection([Point(0, 0), LineString([(0, 0), (1, 1)])])
    empty_poly = Polygon()

    features = [
        ParsedFeature(feature_index=0, feature_id="gc_1", geometry=gc, geometry_type="GeometryCollection"),
        ParsedFeature(feature_index=1, feature_id="empty_1", geometry=empty_poly, geometry_type="Polygon", is_empty=True),
        ParsedFeature(
            feature_index=2,
            feature_id="valid_line",
            geometry=LineString(line_wgs),
            geometry_type="LineString",
        ),
    ]
    dataset = ParsedDataset(file_type="kml", crs="EPSG:4326", features=features)

    result = process_dataset_measurements(dataset)
    assert len(result.features) == 3

    # Feature 0: Unsupported GeometryCollection
    assert result.features[0].measurement_status == "unsupported_geometry"
    assert result.features[0].area_sq_m is None

    # Feature 1: Empty Polygon
    assert result.features[1].measurement_status == "empty_geometry"
    assert result.features[1].area_sq_m is None

    # Feature 2: Valid LineString is still successfully measured!
    assert result.features[2].measurement_status == "success"
    assert result.features[2].length_m is not None

    assert result.unsupported_count == 2
    assert result.linestring_count == 1


def test_missing_crs_skips_measurements_safely():
    """Verify that if CRS is missing or uncertain, measurements are skipped rather than producing misleading numbers."""
    poly = Polygon(shell=box_wgs_outer)
    feat = ParsedFeature(feature_index=0, feature_id="poly_1", geometry=poly, geometry_type="Polygon")
    dataset = ParsedDataset(
        file_type="shapefile",
        crs="UNKNOWN",
        is_crs_uncertain=True,
        crs_raw=None,
        features=[feat],
    )

    result = process_dataset_measurements(dataset)
    assert result.file_status == "processed_with_warnings"
    assert any("CRS uncertainty" in w for w in result.warnings)

    measured = result.features[0]
    assert measured.measurement_status == "skipped_missing_crs"
    assert measured.area_sq_m is None
    assert measured.length_m is None
    assert "CRS uncertainty" in measured.status_message
