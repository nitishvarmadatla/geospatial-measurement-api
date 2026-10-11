"""FastAPI application factory, lifespan management, and router registration."""
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.logging import logger
from app.core.exceptions import GeoApiException
from app.db.session import init_db
from app.api.router import api_router
from app.api.errors import (
    geo_api_exception_handler,
    http_exception_handler,
    validation_exception_handler,
    unhandled_exception_handler,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle: initialize database tables on startup."""
    logger.info("Initializing database schema...")
    init_db()
    logger.info("Database initialized successfully.")
    yield
    logger.info("Application shutting down.")


def create_app() -> FastAPI:
    """Create and configure FastAPI application."""
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description=(
            "Production-grade FastAPI service for uploading, validating, reprojecting, "
            "and calculating planar metric measurements (area in m², length in m) "
            "for geospatial datasets (.kml and zipped Shapefiles)."
        ),
        lifespan=lifespan,
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Exception Handlers
    app.add_exception_handler(GeoApiException, geo_api_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)

    # Routes
    app.include_router(api_router)

    @app.get("/", tags=["root"], summary="API Root / Overview")
    def root():
        return {
            "name": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "docs_url": "/docs",
            "openapi_url": "/openapi.json",
            "endpoints": {
                "upload": "POST /api/files/",
                "get_file": "GET /api/files/{id}/",
                "get_measurements": "GET /api/files/{id}/measurements/",
                "health": "GET /api/health/",
            },
        }

    return app


app = create_app()
