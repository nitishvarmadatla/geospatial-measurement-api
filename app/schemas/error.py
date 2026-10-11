"""Standard error response schemas."""
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    """Standardized API error response body."""

    detail: str = Field(..., description="Human-readable explanation of error")
    error_code: str = Field(..., description="Machine-readable application error code")
    details: Optional[Dict[str, Any]] = Field(default=None, description="Additional context or validation details")
