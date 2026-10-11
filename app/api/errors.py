"""Global exception handlers for consistent API error responses."""
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

from app.core.exceptions import GeoApiException
from app.core.logging import logger


async def geo_api_exception_handler(request: Request, exc: GeoApiException) -> JSONResponse:
    """Handle domain-specific exceptions."""
    logger.warning(f"GeoApiException [{exc.error_code}]: {exc.message} - Path: {request.url.path}")
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": exc.message,
            "error_code": exc.error_code,
            "details": exc.details if exc.details else None,
        },
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Handle standard FastAPI HTTPExceptions."""
    logger.warning(f"HTTPException [{exc.status_code}]: {exc.detail} - Path: {request.url.path}")
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": str(exc.detail),
            "error_code": "HTTP_ERROR",
            "details": None,
        },
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Handle request validation errors."""
    logger.warning(f"Validation error: {exc.errors()} - Path: {request.url.path}")
    return JSONResponse(
        status_code=422,
        content={
            "detail": "Request validation failed.",
            "error_code": "VALIDATION_ERROR",
            "details": exc.errors(),
        },
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle unhandled unexpected exceptions."""
    logger.exception(f"Unhandled server error on {request.url.path}: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "detail": "An unexpected server error occurred.",
            "error_code": "INTERNAL_SERVER_ERROR",
            "details": None,
        },
    )
