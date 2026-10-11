"""Pytest fixtures and test data generators for KML and Shapefiles."""
import io
import os
import tempfile
import zipfile
import pytest
from starlette.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
import pyproj
import shapefile

from app.db.base import Base
from app.db.session import get_db
from app.main import create_app

# Test database using in-memory SQLite with StaticPool for multi-threaded test access
TEST_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="function")
def db_session():
    """Create fresh database tables for each test function."""
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def client(db_session):
    """FastAPI TestClient with overridden get_db dependency."""
    app = create_app()

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


# =========================================================================
# Realistic Test Data Builders (KML & Shapefile)
# =========================================================================

# EPSG:32631 (UTM Zone 31N) around (0 deg N, 0 deg E)
# In UTM 31N: Central meridian is 3 deg E (x=500000). At 0 deg E, x is approx 166021.44, y is 0.0.
# Let's project exact metric shapes to WGS84 coordinates:
transformer_to_wgs84 = pyproj.Transformer.from_crs("EPSG:32631", "EPSG:4326", always_xy=True)
transformer_to_utm = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:32631", always_xy=True)

# 1. Outer box: 100m x 100m (area = 10,000 sq m)
# Coordinates in UTM: (500000, 10000) to (500100, 10100)
# Hole: 20m x 20m (area = 400 sq m) at (500040, 10040) to (500060, 10060)
# Net Area: 10,000 - 400 = 9,600 sq m
box_utm_outer = [
    (500000.0, 10000.0),
    (500100.0, 10000.0),
    (500100.0, 10100.0),
    (500000.0, 10100.0),
    (500000.0, 10000.0),
]
box_utm_hole = [
    (500040.0, 10040.0),
    (500060.0, 10040.0),
    (500060.0, 10060.0),
    (500040.0, 10060.0),
    (500040.0, 10040.0),
]

# Convert to WGS84 for KML / Shapefile WGS84
box_wgs_outer = [transformer_to_wgs84.transform(x, y) for x, y in box_utm_outer]
box_wgs_hole = [transformer_to_wgs84.transform(x, y) for x, y in box_utm_hole]

# 2. LineString of exact 250m: (500000, 20000) to (500250, 20000)
line_utm = [(500000.0, 20000.0), (500250.0, 20000.0)]
line_wgs = [transformer_to_wgs84.transform(x, y) for x, y in line_utm]

EXPECTED_POLYGON_HOLE_AREA_SQ_M = 9600.0
EXPECTED_LINE_LENGTH_M = 250.0


@pytest.fixture
def sample_kml_bytes() -> bytes:
    """Generate realistic KML with Polygon (with hole), LineString, Point, and MultiGeometry."""
    outer_kml_str = " ".join(f"{lon},{lat},0" for lon, lat in box_wgs_outer)
    hole_kml_str = " ".join(f"{lon},{lat},0" for lon, lat in box_wgs_hole)
    line_kml_str = " ".join(f"{lon},{lat},0" for lon, lat in line_wgs)

    kml_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <name>Sample Parcels and Roads</name>
    <Placemark id="pm_poly_1">
      <name>Parcel with Courtyard</name>
      <description>Commercial parcel with an interior courtyard hole</description>
      <ExtendedData>
        <Data name="zoning"><value>Commercial</value></Data>
        <Data name="tax_id"><value>TX-901</value></Data>
      </ExtendedData>
      <Polygon>
        <outerBoundaryIs>
          <LinearRing>
            <coordinates>{outer_kml_str}</coordinates>
          </LinearRing>
        </outerBoundaryIs>
        <innerBoundaryIs>
          <LinearRing>
            <coordinates>{hole_kml_str}</coordinates>
          </LinearRing>
        </innerBoundaryIs>
      </Polygon>
    </Placemark>
    <Placemark id="pm_line_1">
      <name>Access Road</name>
      <description>250-metre paved access road</description>
      <ExtendedData>
        <Data name="speed_limit"><value>45</value></Data>
      </ExtendedData>
      <LineString>
        <coordinates>{line_kml_str}</coordinates>
      </LineString>
    </Placemark>
    <Placemark id="pm_point_1">
      <name>Survey Benchmark</name>
      <description>High precision survey control point</description>
      <ExtendedData>
        <Data name="elevation_m"><value>124.5</value></Data>
      </ExtendedData>
      <Point>
        <coordinates>{box_wgs_outer[0][0]},{box_wgs_outer[0][1]},0</coordinates>
      </Point>
    </Placemark>
  </Document>
</kml>
"""
    return kml_content.encode("utf-8")


WGS84_WKT = (
    'GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",SPHEROID["WGS_1984",6378137.0,298.257223563]],'
    'PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]]'
)


def create_shapefile_zip_bytes(
    include_prj: bool = True,
    prj_content: str = WGS84_WKT,
    include_shx: bool = True,
    include_dbf: bool = True,
) -> bytes:
    """Create in-memory zipped Shapefile containing Polygon with hole, Line, and Point."""
    with tempfile.TemporaryDirectory() as tmpdir:
        base_path = os.path.join(tmpdir, "test_parcels")

        # 1. Write Shapefile
        with shapefile.Writer(base_path, shapeType=shapefile.POLYGON) as w:
            w.field("name", "C", size=50)
            w.field("category", "C", size=20)

            # In Shapefile specification: outer ring is clockwise, inner hole is counter-clockwise.
            # box_wgs_outer is CCW; reversing makes it CW. box_wgs_hole is CCW.
            outer_ring = list(reversed(box_wgs_outer))
            hole_ring = list(box_wgs_hole)

            w.poly([outer_ring, hole_ring])
            w.record(name="Parcel A", category="Commercial")

        # Write .prj if requested
        if include_prj:
            with open(f"{base_path}.prj", "w", encoding="utf-8") as f_prj:
                f_prj.write(prj_content)

        # 2. Package into zip bytes
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(f"{base_path}.shp", "test_parcels.shp")
            if include_shx and os.path.exists(f"{base_path}.shx"):
                zf.write(f"{base_path}.shx", "test_parcels.shx")
            if include_dbf and os.path.exists(f"{base_path}.dbf"):
                zf.write(f"{base_path}.dbf", "test_parcels.dbf")
            if include_prj and os.path.exists(f"{base_path}.prj"):
                zf.write(f"{base_path}.prj", "test_parcels.prj")

        zip_buf.seek(0)
        return zip_buf.getvalue()


@pytest.fixture
def sample_shapefile_zip_bytes() -> bytes:
    """Valid Shapefile with .shp, .shx, .dbf, and WGS84 .prj."""
    return create_shapefile_zip_bytes(include_prj=True)


@pytest.fixture
def shapefile_missing_prj_zip_bytes() -> bytes:
    """Shapefile without .prj to test CRS uncertainty handling."""
    return create_shapefile_zip_bytes(include_prj=False)


@pytest.fixture
def shapefile_missing_shx_zip_bytes() -> bytes:
    """Incomplete Shapefile missing .shx component."""
    return create_shapefile_zip_bytes(include_shx=False)
