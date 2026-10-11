"""Unit tests for KML and Shapefile parsers."""
import os
import tempfile
import pytest
from app.core.exceptions import InvalidKmlError
from app.services.parsers.kml_parser import KmlParser
from app.services.parsers.shapefile_parser import ShapefileParser
from tests.conftest import create_shapefile_zip_bytes
import zipfile


def test_kml_parser_feature_extraction(sample_kml_bytes):
    """Verify KML parser extracts polygons, holes, lines, points, and attributes."""
    with tempfile.NamedTemporaryFile(suffix=".kml", delete=False) as f:
        f.write(sample_kml_bytes)
        temp_path = f.name

    try:
        parser = KmlParser()
        dataset = parser.parse(temp_path)

        assert dataset.file_type == "kml"
        assert dataset.crs == "EPSG:4326"
        assert len(dataset.features) == 3

        # Feature 0: Polygon with hole
        f0 = dataset.features[0]
        assert f0.geometry_type == "Polygon"
        assert f0.geometry is not None
        assert len(f0.geometry.interiors) == 1  # 1 interior hole!
        assert f0.properties.get("name") == "Parcel with Courtyard"
        assert f0.properties.get("zoning") == "Commercial"
        assert f0.properties.get("tax_id") == "TX-901"

        # Feature 1: LineString
        f1 = dataset.features[1]
        assert f1.geometry_type == "LineString"
        assert f1.properties.get("name") == "Access Road"
        assert f1.properties.get("speed_limit") == "45"

        # Feature 2: Point
        f2 = dataset.features[2]
        assert f2.geometry_type == "Point"
        assert f2.properties.get("name") == "Survey Benchmark"
        assert f2.properties.get("elevation_m") == "124.5"
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_kml_parser_malformed_xml():
    """Verify malformed XML raises InvalidKmlError."""
    with tempfile.NamedTemporaryFile(suffix=".kml", delete=False) as f:
        f.write(b"<kml><unclosed>")
        temp_path = f.name

    try:
        parser = KmlParser()
        with pytest.raises(InvalidKmlError):
            parser.parse(temp_path)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_shapefile_parser_with_and_without_prj():
    """Verify Shapefile parser extracts features and detects presence/absence of .prj."""
    zip_bytes_with_prj = create_shapefile_zip_bytes(include_prj=True)
    zip_bytes_no_prj = create_shapefile_zip_bytes(include_prj=False)

    # Test 1: With .prj
    with tempfile.TemporaryDirectory() as tmpdir:
        zip_path = os.path.join(tmpdir, "valid.zip")
        with open(zip_path, "wb") as f:
            f.write(zip_bytes_with_prj)

        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(tmpdir)

        shp_path = os.path.join(tmpdir, "test_parcels.shp")
        parser = ShapefileParser(prj_path=os.path.join(tmpdir, "test_parcels.prj"))
        dataset = parser.parse(shp_path)

        assert dataset.file_type == "shapefile"
        assert dataset.is_crs_uncertain is False
        assert "WGS_1984" in dataset.crs or "4326" in dataset.crs
        assert len(dataset.features) == 1
        assert dataset.features[0].geometry_type in ("Polygon", "MultiPolygon")
        assert dataset.features[0].properties.get("name") == "Parcel A"

    # Test 2: Without .prj (missing CRS)
    with tempfile.TemporaryDirectory() as tmpdir:
        zip_path = os.path.join(tmpdir, "no_prj.zip")
        with open(zip_path, "wb") as f:
            f.write(zip_bytes_no_prj)

        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(tmpdir)

        shp_path = os.path.join(tmpdir, "test_parcels.shp")
        parser = ShapefileParser(prj_path=None)
        dataset = parser.parse(shp_path)

        assert dataset.is_crs_uncertain is True
        assert dataset.crs == "UNKNOWN"
        assert any("Missing .prj" in w for w in dataset.warnings)
