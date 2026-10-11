"""Health check endpoint."""
from fastapi import APIRouter
from app.core.config import settings

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/")
def health_check():
    return {
        "status": "healthy",
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
    }
