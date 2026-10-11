"""Integration tests for FastAPI endpoints: upload, metadata retrieval, measurements, and persistence."""
import pytest
from tests.conftest import (
    EXPECTED_POLYGON_HOLE_AREA_SQ_M,
    EXPECTED_LINE_LENGTH_M,
)


def test_app_startup_and_health(client):
    """Verify health endpoint and root index."""
    res = client.get("/api/health/")
    assert res.status_code == 200
    assert res.json()["status"] == "healthy"

    root_res = client.get("/")
    assert root_res.status_code == 200
    assert "endpoints" in root_res.json()


def test_kml_upload_metadata_and_measurements_flow(client, sample_kml_bytes):
    """End-to-end integration test: upload KML, fetch metadata, and fetch feature measurements."""
    # 1. POST /api/files/
    files = {"file": ("parcels_and_roads.kml", sample_kml_bytes, "application/vnd.google-earth.kml+xml")}
    res_upload = client.post("/api/files/", files=files)
    assert res_upload.status_code == 201
    upload_data = res_upload.json()

    file_id = upload_data["id"]
    assert file_id is not None
    assert upload_data["filename"] == "parcels_and_roads.kml"
    assert upload_data["feature_count"] == 3
    assert upload_data["crs"] == "EPSG:4326"
    assert upload_data["CRS"] == "EPSG:4326"
    assert upload_data["status"] == "processed"
    assert upload_data["warnings"] == []

    # 2. GET /api/files/{id}/ (Mandatory Req 9)
    res_meta = client.get(f"/api/files/{file_id}/")
    assert res_meta.status_code == 200
    meta_data = res_meta.json()

    assert meta_data["id"] == file_id
    assert meta_data["filename"] == "parcels_and_roads.kml"
    assert meta_data["feature_count"] == 3
    assert meta_data["crs"] == "EPSG:4326"
    assert meta_data["CRS"] == "EPSG:4326"
    assert meta_data["status"] == "processed"

    # 3. GET /api/files/{id}/measurements/ (Mandatory Req 10)
    res_meas = client.get(f"/api/files/{file_id}/measurements/")
    assert res_meas.status_code == 200
    meas_data = res_meas.json()

    assert meas_data["file_id"] == file_id
    assert meas_data["filename"] == "parcels_and_roads.kml"
    assert meas_data["feature_count"] == 3
    assert meas_data["crs"] == "EPSG:4326"
    assert meas_data["CRS"] == "EPSG:4326"
    assert "EPSG:32631" in meas_data["projected_crs_used"]
    assert meas_data["status"] == "processed"

    # Verify Summary
    summary = meas_data["summary"]
    assert summary["polygon_count"] == 1
    assert summary["linestring_count"] == 1
    assert summary["point_count"] == 1
    assert summary["unsupported_count"] == 0

    # Verify Features
    features = meas_data["features"]
    assert len(features) == 3
    for f in features:
        assert f["crs"] == "EPSG:4326"

    # Feature 0: Polygon with hole
    f0 = features[0]
    assert f0["feature_index"] == 0
    assert f0["crs"] == "EPSG:4326"
    assert f0["geometry_type"] == "Polygon"
    assert f0["measurement_unit"] == "sq_m"
    assert f0["measurement_status"] == "success"
    assert f0["area_sq_m"] is not None
    assert f0["length_m"] is None
    # Within 0.5% tolerance of expected 9600.0 sq m
    poly_tol = EXPECTED_POLYGON_HOLE_AREA_SQ_M * 0.005
    assert abs(f0["area_sq_m"] - EXPECTED_POLYGON_HOLE_AREA_SQ_M) <= poly_tol
    assert f0["properties"]["zoning"] == "Commercial"
    assert f0["properties"]["tax_id"] == "TX-901"

    # Feature 1: LineString
    f1 = features[1]
    assert f1["feature_index"] == 1
    assert f1["crs"] == "EPSG:4326"
    assert f1["geometry_type"] == "LineString"
    assert f1["measurement_unit"] == "m"
    assert f1["measurement_status"] == "success"
    assert f1["length_m"] is not None
    assert f1["area_sq_m"] is None
    # Within 0.5% tolerance of expected 250.0 m
    line_tol = EXPECTED_LINE_LENGTH_M * 0.005
    assert abs(f1["length_m"] - EXPECTED_LINE_LENGTH_M) <= line_tol
    assert f1["properties"]["speed_limit"] == "45"

    # Feature 2: Point
    f2 = features[2]
    assert f2["feature_index"] == 2
    assert f2["crs"] == "EPSG:4326"
    assert f2["geometry_type"] == "Point"
    assert f2["area_sq_m"] is None
    assert f2["length_m"] is None
    assert f2["measurement_unit"] is None
    assert f2["measurement_status"] == "not_applicable"
    assert f2["properties"]["elevation_m"] == "124.5"


def test_shapefile_zip_upload_and_measurements(client, sample_shapefile_zip_bytes):
    """Verify upload and processing of valid Shapefile in a ZIP archive."""
    files = {"file": ("parcels.zip", sample_shapefile_zip_bytes, "application/zip")}
    res_upload = client.post("/api/files/", files=files)
    assert res_upload.status_code == 201
    data = res_upload.json()

    file_id = data["id"]
    assert data["filename"] == "parcels.zip"
    assert data["file_type"] == "shapefile"
    assert data["feature_count"] == 1
    assert data["status"] == "processed"

    # Check measurements
    res_meas = client.get(f"/api/files/{file_id}/measurements/")
    assert res_meas.status_code == 200
    meas = res_meas.json()
    assert len(meas["features"]) == 1
    f0 = meas["features"][0]
    assert "WGS_1984" in f0["crs"] or "4326" in f0["crs"]
    assert f0["geometry_type"] in ("Polygon", "MultiPolygon")
    assert f0["measurement_status"] == "success"
    assert f0["area_sq_m"] is not None
    poly_tol = EXPECTED_POLYGON_HOLE_AREA_SQ_M * 0.005
    assert abs(f0["area_sq_m"] - EXPECTED_POLYGON_HOLE_AREA_SQ_M) <= poly_tol


def test_shapefile_missing_prj_uncertainty_handling(client, shapefile_missing_prj_zip_bytes):
    """Verify Shapefile without .prj reports CRS uncertainty and skips misleading measurements."""
    files = {"file": ("no_prj.zip", shapefile_missing_prj_zip_bytes, "application/zip")}
    res_upload = client.post("/api/files/", files=files)
    assert res_upload.status_code == 201
    data = res_upload.json()

    file_id = data["id"]
    assert data["status"] == "processed_with_warnings"
    assert data["crs"] == "UNKNOWN"
    assert data["CRS"] == "UNKNOWN"
    assert any("Missing .prj" in w for w in data["warnings"])

    # Fetch measurements
    res_meas = client.get(f"/api/files/{file_id}/measurements/")
    assert res_meas.status_code == 200
    meas = res_meas.json()
    assert meas["status"] == "processed_with_warnings"
    assert len(meas["features"]) == 1

    f0 = meas["features"][0]
    assert f0["crs"] == "UNKNOWN"
    assert f0["measurement_status"] == "skipped_missing_crs"
    assert f0["area_sq_m"] is None
    assert f0["length_m"] is None
    assert "CRS uncertainty" in f0["status_message"]


def test_nonexistent_file_id_returns_404(client):
    """Verify unknown file IDs return 404 with structured error response."""
    bad_id = "00000000-0000-0000-0000-000000000000"
    res_meta = client.get(f"/api/files/{bad_id}/")
    assert res_meta.status_code == 404
    assert res_meta.json()["error_code"] == "FILE_NOT_FOUND"

    res_meas = client.get(f"/api/files/{bad_id}/measurements/")
    assert res_meas.status_code == 404
    assert res_meas.json()["error_code"] == "FILE_NOT_FOUND"


def test_invalid_file_extension_rejected(client):
    """Verify unsupported file extensions return 400 Bad Request."""
    files = {"file": ("data.geojson", b'{"type": "FeatureCollection"}', "application/geo+json")}
    res = client.post("/api/files/", files=files)
    assert res.status_code == 400
    assert res.json()["error_code"] == "INVALID_FILE_FORMAT"


def test_incomplete_shapefile_missing_shx_rejected(client, shapefile_missing_shx_zip_bytes):
    """Verify Shapefile archive missing .shx is rejected with 400."""
    files = {"file": ("incomplete.zip", shapefile_missing_shx_zip_bytes, "application/zip")}
    res = client.post("/api/files/", files=files)
    assert res.status_code == 400
    assert res.json()["error_code"] == "INVALID_SHAPEFILE_BUNDLE"
    assert "missing required index component" in res.json()["detail"]
