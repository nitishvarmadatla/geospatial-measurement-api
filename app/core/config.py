"""Application configuration settings."""
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    APP_NAME: str = "AEREO Geospatial File Measurement API"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    DATABASE_URL: str = "sqlite:///./geospatial_measurements.db"

    # Upload & streaming limits
    MAX_UPLOAD_SIZE_BYTES: int = 25 * 1024 * 1024  # 25 MB
    CHUNK_SIZE_BYTES: int = 64 * 1024  # 64 KB per stream chunk

    # Safe ZIP extraction limits
    MAX_ZIP_DECOMPRESSED_SIZE_BYTES: int = 100 * 1024 * 1024  # 100 MB total uncompressed
    MAX_ZIP_SINGLE_FILE_BYTES: int = 50 * 1024 * 1024  # 50 MB single file
    MAX_ZIP_FILE_COUNT: int = 50  # Max files allowed in archive
    MAX_ZIP_COMPRESSION_RATIO: float = 100.0  # Max compression ratio

    # Logging
    LOG_LEVEL: str = "INFO"

    model_config = SettingsConfigDict(env_prefix="GEO_API_", case_sensitive=True)


settings = Settings()
