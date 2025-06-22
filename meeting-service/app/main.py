import asyncio
from builtins import anext
from contextlib import asynccontextmanager
import os
from typing import AsyncIterator

from dotenv import load_dotenv
from fastapi import FastAPI
from redis.asyncio import Redis

from app.api.routes import meeting_routes, recurrence_routes, task_routes, user_routes
from app.core.dependencies import (
    get_db,
    get_redis_client,
    get_task_service,
    get_user_service,
)
from app.core.logging_config import logger
from app.exceptions import (
    NotFoundError,
    ValidationError,
    generic_exception_handler,
    not_found_exception_handler,
    validation_exception_handler,
)
from app.services.redis_subscriber import RedisSubscriber

load_dotenv()

logger.info("Starting application...")


# redis-py isn't statically typed, so we skip mypy checks
async def test_redis_connection(redis_client: Redis) -> None:  # type: ignore
    try:
        pong = await redis_client.ping()
        if pong:
            logger.info("Redis connection is successful.")
    except (ConnectionError, TimeoutError) as exc:
        logger.error(f"Redis connection failed: {exc}")
        raise exc


@asynccontextmanager
async def lifespan(fastapi_app: FastAPI) -> AsyncIterator[None]:
    logger.info("Lifespan startup")

    # Resolve database session manually
    db_session_generator = get_db()  # This is an async generator
    db_session = await anext(db_session_generator)  # Get the first yielded value

    redis_client = get_redis_client()

    user_service = get_user_service(db=db_session, redis=redis_client)
    task_service = get_task_service(db=db_session, redis=redis_client)

    subscriber = RedisSubscriber(
        redis_client=redis_client, task_service=task_service, user_service=user_service
    )

    fastapi_app.state.redis_subscriber_task = asyncio.create_task(
        subscriber.listen_to_events(["user-events", "meeting-events"])
    )

    yield

    fastapi_app.state.redis_subscriber_task.cancel()
    try:
        await fastapi_app.state.redis_subscriber_task
    except asyncio.CancelledError:
        logger.warning("Redis subscriber task cancelled.")

    await db_session_generator.aclose()  # Close the async generator
    logger.info("Lifespan shutdown complete.")


app = FastAPI(lifespan=lifespan)

# Access the secret key
SECRET_KEY = os.getenv("SECRET_KEY", "default_secret_key")

if not SECRET_KEY:
    raise ValueError("SECRET_KEY is not set in the environment variables!")

# Register exception handlers
app.add_exception_handler(NotFoundError, not_found_exception_handler)
app.add_exception_handler(ValidationError, validation_exception_handler)
app.add_exception_handler(Exception, generic_exception_handler)

# Include routers that might use the database internally
app.include_router(meeting_routes.router, prefix="/meetings", tags=["meetings"])
app.include_router(task_routes.router, prefix="/tasks", tags=["tasks"])
app.include_router(user_routes.router, prefix="/meeting_users", tags=["users"])
app.include_router(
    recurrence_routes.router,
    prefix="/recurrences",
    tags=["recurrences"],
)


@app.get("/")
async def root() -> dict[str, str]:
    return {"message": "Welcome to the Meeting Service API"}
