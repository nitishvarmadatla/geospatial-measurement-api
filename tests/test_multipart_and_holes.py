"""Tests for multipart geometries (MultiPolygon, MultiLineString) and multiple holes."""
import pytest
from shapely.geometry import Polygon, MultiPolygon, LineString, MultiLineString
from app.services.parsers.base import ParsedDataset, ParsedFeature
from app.services.measurements import process_dataset_measurements
from tests.conftest import (
    box_wgs_outer,
    box_wgs_hole,
    line_wgs,
    EXPECTED_POLYGON_HOLE_AREA_SQ_M,
    EXPECTED_LINE_LENGTH_M,
)


def test_multipolygon_with_holes_measurement():
    """Verify MultiPolygon containing multiple polygons with holes calculates aggregate area."""
    poly1 = Polygon(shell=box_wgs_outer, holes=[box_wgs_hole])
    # Shift second polygon slightly
    poly2 = Polygon(
        shell=[(x + 0.005, y + 0.005) for x, y in box_wgs_outer],
        holes=[[(x + 0.005, y + 0.005) for x, y in box_wgs_hole]],
    )
    multi_poly = MultiPolygon([poly1, poly2])

    feat = ParsedFeature(
        feature_index=0,
        feature_id="mpoly_1",
        geometry=multi_poly,
        geometry_type="MultiPolygon",
    )
    dataset = ParsedDataset(file_type="kml", crs="EPSG:4326", features=[feat])
    res = process_dataset_measurements(dataset)

    assert len(res.features) == 1
    m = res.features[0]
    assert m.geometry_type == "MultiPolygon"
    assert m.measurement_status == "success"
    assert m.measurement_unit == "sq_m"
    # Should be approx double the single polygon area
    expected_double_area = EXPECTED_POLYGON_HOLE_AREA_SQ_M * 2.0
    tol = expected_double_area * 0.01
    assert abs(m.area_sq_m - expected_double_area) <= tol


def test_multilinestring_measurement():
    """Verify MultiLineString aggregates length of all component line strings."""
    line1 = LineString(line_wgs)
    line2 = LineString([(x, y + 0.005) for x, y in line_wgs])
    multi_line = MultiLineString([line1, line2])

    feat = ParsedFeature(
        feature_index=0,
        feature_id="mline_1",
        geometry=multi_line,
        geometry_type="MultiLineString",
    )
    dataset = ParsedDataset(file_type="kml", crs="EPSG:4326", features=[feat])
    res = process_dataset_measurements(dataset)

    assert len(res.features) == 1
    m = res.features[0]
    assert m.geometry_type == "MultiLineString"
    assert m.measurement_status == "success"
    assert m.measurement_unit == "m"
    expected_double_len = EXPECTED_LINE_LENGTH_M * 2.0
    tol = expected_double_len * 0.01
    assert abs(m.length_m - expected_double_len) <= tol
