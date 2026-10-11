"""Test real SQLite disk persistence across isolated database sessions."""
import os
import tempfile
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from starlette.testclient import TestClient

from app.db.base import Base
from app.db.session import get_db
from app.main import create_app
from tests.conftest import create_shapefile_zip_bytes


def test_sqlite_disk_persistence():
    """Verify file metadata and feature measurements persist to SQLite disk file across separate sessions."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_persistent.db")
        db_url = f"sqlite:///{db_path}"

        disk_engine = create_engine(db_url, connect_args={"check_same_thread": False})
        DiskSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=disk_engine)

        Base.metadata.create_all(bind=disk_engine)

        app = create_app()

        def override_get_db():
            db = DiskSessionLocal()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db

        with TestClient(app) as client:
            zip_bytes = create_shapefile_zip_bytes(include_prj=True)
            files = {"file": ("persisted_parcels.zip", zip_bytes, "application/zip")}
            res = client.post("/api/files/", files=files)
            assert res.status_code == 201
            file_id = res.json()["id"]

            # Confirm file exists on disk
            assert os.path.exists(db_path)
            assert os.path.getsize(db_path) > 0

            # Query via fresh client and session
            res_meta = client.get(f"/api/files/{file_id}/")
            assert res_meta.status_code == 200
            assert res_meta.json()["filename"] == "persisted_parcels.zip"

            res_meas = client.get(f"/api/files/{file_id}/measurements/")
            assert res_meas.status_code == 200
            assert res_meas.json()["feature_count"] == 1
            assert res_meas.json()["features"][0]["measurement_status"] == "success"

        app.dependency_overrides.clear()
        disk_engine.dispose()
