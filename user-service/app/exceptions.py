import functools

from fastapi import Request
from fastapi.responses import JSONResponse
from loguru import logger


# Custom Exceptions
class NotFoundError(Exception):
    """Exception raised for missing resources."""

    def __init__(self, detail: str = "Resource not found"):
        self.detail = detail


class ValidationError(Exception):
    """Exception raised for validation errors."""

    def __init__(self, detail: str = "Validation error"):
        self.detail = detail


class ForbiddenError(Exception):
    """Exception raised for unauthorized access."""

    def __init__(self, detail: str = "Access forbidden"):
        self.detail = detail


# Decorators
def handle_service_exceptions(func):
    """Decorator to handle exceptions while preserving FastAPI dependencies."""

    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except ValidationError as ve:
            logger.warning(f"Validation error: {ve}")
            raise
        except Exception as exc:
            logger.exception(f"Unexpected error: {exc}")
            raise ValidationError("An unexpected error occurred.") from exc

    return wrapper


# Exception Handlers
async def forbidden_exception_handler(_request: Request, exc: ForbiddenError):
    return JSONResponse(
        status_code=403,
        content={"detail": exc.detail},
    )


async def not_found_exception_handler(_request: Request, exc: NotFoundError):
    return JSONResponse(
        status_code=404,
        content={"detail": exc.detail},
    )


async def validation_exception_handler(_request: Request, exc: ValidationError):
    return JSONResponse(
        status_code=400,
        content={"detail": exc.detail},
    )


async def generic_exception_handler(_request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc) or "An unexpected error occurred"},
    )
