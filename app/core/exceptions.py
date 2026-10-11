"""Domain exceptions for the Geospatial File Measurement API."""
from typing import Optional, Dict, Any


class GeoApiException(Exception):
    """Base exception for all domain-specific errors."""

    def __init__(
        self,
        message: str,
        status_code: int = 400,
        error_code: str = "GEO_API_ERROR",
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        self.details = details or {}


class FileValidationError(GeoApiException):
    """Raised when uploaded file fails validation (format, header, extension)."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            status_code=400,
            error_code="INVALID_FILE_FORMAT",
            details=details,
        )


class UploadSizeLimitExceeded(GeoApiException):
    """Raised when file upload exceeds size limits."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            status_code=413,
            error_code="PAYLOAD_TOO_LARGE",
            details=details,
        )


class ZipSecurityError(GeoApiException):
    """Raised when ZIP archive violates safety rules (zip slip, zip bomb, limits)."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None, status_code: int = 400):
        super().__init__(
            message=message,
            status_code=status_code,
            error_code="UNSAFE_ZIP_ARCHIVE",
            details=details,
        )


class InvalidShapefileBundleError(GeoApiException):
    """Raised when required shapefile components (.shp, .shx, .dbf) are missing or ambiguous."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            status_code=400,
            error_code="INVALID_SHAPEFILE_BUNDLE",
            details=details,
        )


class InvalidKmlError(GeoApiException):
    """Raised when KML content is malformed or violates XML safety."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            status_code=400,
            error_code="INVALID_KML_DOCUMENT",
            details=details,
        )


class FileNotFoundRecordError(GeoApiException):
    """Raised when a requested file record is not found in database."""

    def __init__(self, file_id: str):
        super().__init__(
            message=f"File with ID '{file_id}' not found.",
            status_code=404,
            error_code="FILE_NOT_FOUND",
            details={"file_id": file_id},
        )


class GeospatialProcessingError(GeoApiException):
    """Raised when processing or transformation encounters an unrecoverable failure."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            status_code=422,
            error_code="GEOSPATIAL_PROCESSING_ERROR",
            details=details,
        )
