from functools import wraps
import time
from typing import Any, Awaitable, Callable, TypeVar, cast

from loguru import logger

T = TypeVar("T", bound=Callable[..., Awaitable[Any]])


def log_execution_time(func: T) -> T:
    """Decorator to log the execution time of a function."""

    @wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        start_time = time.time()
        result = await func(*args, **kwargs)
        elapsed_time = time.time() - start_time
        logger.info(f"{func.__name__} executed in {elapsed_time:.2f} seconds")
        return result

    return cast(T, wrapper)
