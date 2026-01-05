"""
Custom exceptions and error codes for the SLD Viewer API.
"""
from enum import Enum
from fastapi import HTTPException, status


class ErrorCode(str, Enum):
    """Enumeration of error codes for consistent error handling."""

    # File errors
    FILE_NOT_FOUND = "FILE_NOT_FOUND"
    FILE_INVALID_FORMAT = "FILE_INVALID_FORMAT"
    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    FILE_UPLOAD_FAILED = "FILE_UPLOAD_FAILED"

    # Parse errors
    PARSE_FAILED = "PARSE_FAILED"
    PARSE_INVALID_DATA = "PARSE_INVALID_DATA"

    # View errors
    VIEW_BUS_NOT_FOUND = "VIEW_BUS_NOT_FOUND"
    VIEW_SUBSTATION_NOT_FOUND = "VIEW_SUBSTATION_NOT_FOUND"
    VIEW_INVALID_SPEC = "VIEW_INVALID_SPEC"

    # Cache errors
    CACHE_MISS = "CACHE_MISS"

    # General errors
    INTERNAL_ERROR = "INTERNAL_ERROR"
    VALIDATION_ERROR = "VALIDATION_ERROR"


class SLDError(Exception):
    """Base exception for SLD Viewer errors."""

    def __init__(self, code: ErrorCode, message: str, details: dict | None = None):
        self.code = code
        self.message = message
        self.details = details or {}
        super().__init__(message)


class FileNotFoundError(SLDError):
    """Raised when a requested file is not found."""

    def __init__(self, file_id: str):
        super().__init__(
            code=ErrorCode.FILE_NOT_FOUND,
            message=f"File not found: {file_id}",
            details={"file_id": file_id},
        )


class InvalidFileFormatError(SLDError):
    """Raised when file format is not supported."""

    def __init__(self, filename: str, expected: list[str]):
        super().__init__(
            code=ErrorCode.FILE_INVALID_FORMAT,
            message=f"Invalid file format: {filename}. Expected: {', '.join(expected)}",
            details={"filename": filename, "expected_formats": expected},
        )


class FileTooLargeError(SLDError):
    """Raised when uploaded file exceeds size limit."""

    def __init__(self, size_mb: float, max_mb: int):
        super().__init__(
            code=ErrorCode.FILE_TOO_LARGE,
            message=f"File too large: {size_mb:.1f}MB exceeds limit of {max_mb}MB",
            details={"size_mb": size_mb, "max_mb": max_mb},
        )


class ParseError(SLDError):
    """Raised when parsing a case file fails."""

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(
            code=ErrorCode.PARSE_FAILED,
            message=f"Parse failed: {message}",
            details=details or {},
        )


class BusNotFoundError(SLDError):
    """Raised when a requested bus is not found."""

    def __init__(self, bus_number: int):
        super().__init__(
            code=ErrorCode.VIEW_BUS_NOT_FOUND,
            message=f"Bus not found: {bus_number}",
            details={"bus_number": bus_number},
        )


class SubstationNotFoundError(SLDError):
    """Raised when a requested substation is not found."""

    def __init__(self, substation_id: str):
        super().__init__(
            code=ErrorCode.VIEW_SUBSTATION_NOT_FOUND,
            message=f"Substation not found: {substation_id}",
            details={"substation_id": substation_id},
        )


def sld_error_to_http_exception(error: SLDError) -> HTTPException:
    """Convert SLDError to FastAPI HTTPException."""
    status_map = {
        ErrorCode.FILE_NOT_FOUND: status.HTTP_404_NOT_FOUND,
        ErrorCode.FILE_INVALID_FORMAT: status.HTTP_400_BAD_REQUEST,
        ErrorCode.FILE_TOO_LARGE: 413,  # HTTP_413_CONTENT_TOO_LARGE
        ErrorCode.FILE_UPLOAD_FAILED: status.HTTP_500_INTERNAL_SERVER_ERROR,
        ErrorCode.PARSE_FAILED: 422,  # HTTP_422_UNPROCESSABLE_CONTENT
        ErrorCode.PARSE_INVALID_DATA: 422,  # HTTP_422_UNPROCESSABLE_CONTENT
        ErrorCode.VIEW_BUS_NOT_FOUND: status.HTTP_404_NOT_FOUND,
        ErrorCode.VIEW_SUBSTATION_NOT_FOUND: status.HTTP_404_NOT_FOUND,
        ErrorCode.VIEW_INVALID_SPEC: status.HTTP_400_BAD_REQUEST,
        ErrorCode.CACHE_MISS: status.HTTP_404_NOT_FOUND,
        ErrorCode.INTERNAL_ERROR: status.HTTP_500_INTERNAL_SERVER_ERROR,
        ErrorCode.VALIDATION_ERROR: status.HTTP_400_BAD_REQUEST,
    }

    return HTTPException(
        status_code=status_map.get(error.code, status.HTTP_500_INTERNAL_SERVER_ERROR),
        detail={
            "code": error.code.value,
            "message": error.message,
            "details": error.details,
        },
    )
