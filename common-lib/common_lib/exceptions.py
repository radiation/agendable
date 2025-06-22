import functools
from typing import Any, Awaitable, Callable, TypeVar, Union, cast

from fastapi import Request
from fastapi.responses import JSONResponse, Response

from common_lib.logging_config import logger

T = TypeVar("T", bound=Callable[..., Awaitable[Any]])


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
def handle_service_exceptions(func: T) -> T:
    """Decorator to handle exceptions while preserving FastAPI dependencies."""

    @functools.wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return await func(*args, **kwargs)
        except ValidationError as ve:
            logger.warning(f"Validation error: {ve}")
            raise
        except Exception as exc:
            logger.exception(f"Unexpected error: {exc}")
            raise ValidationError("An unexpected error occurred.") from exc

    return cast(T, wrapper)


# Exception Handlers
def forbidden_exception_handler(
    _request: Request, exc: ForbiddenError
) -> Union[Response, Awaitable[Response]]:
    return JSONResponse(
        status_code=403,
        content={"detail": exc.detail},
    )


def not_found_exception_handler(
    _request: Request, exc: NotFoundError
) -> Union[Response, Awaitable[Response]]:
    return JSONResponse(
        status_code=404,
        content={"detail": exc.detail},
    )


def validation_exception_handler(
    _request: Request, exc: ValidationError
) -> Union[Response, Awaitable[Response]]:
    return JSONResponse(
        status_code=400,
        content={"detail": exc.detail},
    )


def generic_exception_handler(
    _request: Request, exc: Exception
) -> Union[Response, Awaitable[Response]]:
    return JSONResponse(
        status_code=500,
        content={"detail": exc or "An unexpected error occurred"},
    )
