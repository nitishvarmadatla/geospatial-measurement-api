"""Root API router combining all endpoint sub-routers."""
from fastapi import APIRouter
from app.api.routes import files, health

api_router = APIRouter(prefix="/api")
api_router.include_router(files.router)
api_router.include_router(health.router)
