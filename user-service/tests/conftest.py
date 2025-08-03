# pylint: disable=redefined-outer-name

from typing import AsyncGenerator
from unittest.mock import AsyncMock

from common_lib.models import Base
from httpx import ASGITransport, AsyncClient
import pytest
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.dependencies import get_group_service, get_role_service, get_user_service
from app.db.session import get_db
from app.main import app
from app.repositories.group import GroupRepository
from app.repositories.role import RoleRepository
from app.repositories.user import UserRepository
from app.services.group import GroupService
from app.services.role import RoleService
from app.services.user import UserService

# Use an in-memory SQLite database for tests
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
SERVICE_NAME = "user-service"


@pytest.fixture(name="engine", scope="function")
async def _engine() -> AsyncGenerator[AsyncEngine, None]:
    # Create an in-memory SQLite engine
    _engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    yield _engine
    await _engine.dispose()


@pytest.fixture(scope="session")
async def tables(engine: AsyncEngine) -> AsyncGenerator[None, None]:
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
    db_session: AsyncSession, mock_redis_client: AsyncMock
) -> AsyncGenerator[AsyncClient, None]:
    app.dependency_overrides[get_db] = lambda: db_session

    app.dependency_overrides[get_group_service] = lambda: GroupService(
        GroupRepository(db_session), mock_redis_client
    )

    app.dependency_overrides[get_role_service] = lambda: RoleService(
        RoleRepository(db_session), mock_redis_client
    )

    app.dependency_overrides[get_user_service] = lambda: UserService(
        UserRepository(db_session), mock_redis_client
    )

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        yield client


@pytest.fixture
async def user_service(
    db_session: AsyncSession, mock_redis_client: AsyncMock
) -> UserService:
    repo = UserRepository(db_session)
    service = UserService(repo, mock_redis_client)
    return service


@pytest.fixture
async def group_service(
    db_session: AsyncSession, mock_redis_client: AsyncMock
) -> GroupService:
    repo = GroupRepository(db_session)
    service = GroupService(repo, mock_redis_client)
    return service


@pytest.fixture
async def role_service(
    db_session: AsyncSession, mock_redis_client: AsyncMock
) -> RoleService:
    repo = RoleRepository(db_session)
    service = RoleService(repo, mock_redis_client)
    return service
