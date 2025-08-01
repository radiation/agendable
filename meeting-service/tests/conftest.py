"""
Fixtures for testing the FastAPI application
"""

from typing import AsyncGenerator, cast
from unittest.mock import AsyncMock

from common_lib.models import Base
from httpx import ASGITransport, AsyncClient
import pytest
from pytest import FixtureRequest
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.dependencies import (
    get_meeting_service,
    get_recurrence_service,
    get_task_service,
    get_user_service,
)
from app.db.session import get_db
from app.main import app
from app.repositories.meeting import MeetingRepository
from app.repositories.recurrence import RecurrenceRepository
from app.repositories.task import TaskRepository
from app.repositories.user import UserRepository
from app.services.meeting import MeetingService
from app.services.recurrence import RecurrenceService
from app.services.task import TaskService
from app.services.user import UserService

# Use an in-memory SQLite database for tests
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(name="engine", scope="function")
async def _engine() -> AsyncGenerator[AsyncEngine, None]:
    """Create a new test database for the entire test session"""
    _engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    yield _engine
    await _engine.dispose()


@pytest.fixture(scope="session")
async def tables(engine: AsyncEngine) -> AsyncGenerator[None, None]:
    """Create tables for the test database"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture(name="db_session", scope="function")
async def _db_session(engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    """Create a new test session for each test function"""
    async_session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session_factory() as session:
        yield session

    await engine.dispose()


@pytest.fixture
def mock_redis_client() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
async def test_client(
    db_session: AsyncSession, request: FixtureRequest
) -> AsyncGenerator[AsyncClient, None]:
    """Test client with dependency overrides for services"""
    mock_obj = request.getfixturevalue("mock_redis_client")
    mock_redis: Redis = cast(Redis, mock_obj)
    app.dependency_overrides[get_db] = lambda: db_session

    app.dependency_overrides[get_meeting_service] = lambda: MeetingService(
        MeetingRepository(db_session), mock_redis
    )

    app.dependency_overrides[get_recurrence_service] = lambda: RecurrenceService(
        RecurrenceRepository(db_session), mock_redis
    )

    app.dependency_overrides[get_task_service] = lambda: TaskService(
        TaskRepository(db_session), mock_redis
    )

    app.dependency_overrides[get_user_service] = lambda: UserService(
        UserRepository(db_session), mock_redis
    )

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        yield client


@pytest.fixture
async def meeting_service(
    db_session: AsyncSession, request: FixtureRequest
) -> MeetingService:
    """Create a new MeetingService instance for each test function"""
    mock_obj = request.getfixturevalue("mock_redis_client")
    mock_redis: Redis = cast(Redis, mock_obj)
    repo = MeetingRepository(db_session)
    service = MeetingService(repo, mock_redis)
    return service


@pytest.fixture
async def recurrence_service(
    db_session: AsyncSession, request: FixtureRequest
) -> RecurrenceService:
    """Create a new RecurrenceService instance for each test function"""
    mock_obj = request.getfixturevalue("mock_redis_client")
    mock_redis: Redis = cast(Redis, mock_obj)
    repo = RecurrenceRepository(db_session)
    service = RecurrenceService(repo, mock_redis)
    return service


@pytest.fixture
async def task_service(
    db_session: AsyncSession, request: FixtureRequest
) -> TaskService:
    """Create a new TaskService instance for each test function"""
    mock_obj = request.getfixturevalue("mock_redis_client")
    mock_redis: Redis = cast(Redis, mock_obj)
    repo = TaskRepository(db_session)
    service = TaskService(repo, mock_redis)
    return service


@pytest.fixture
async def user_service(
    db_session: AsyncSession, request: FixtureRequest
) -> UserService:
    """Create a new UserService instance for each test function"""
    mock_obj = request.getfixturevalue("mock_redis_client")
    mock_redis: Redis = cast(Redis, mock_obj)
    repo = UserRepository(db_session)
    service = UserService(repo, mock_redis)
    return service
