import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import Integer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class BaseForTest(DeclarativeBase):
    pass

class DummyModel(BaseForTest):
    __tablename__ = "dummy"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    def __init__(self, id: int) -> None:
        # Bypass __setattr__ so that mypy sees it as acceptable.
        object.__setattr__(self, "id", id)

@pytest.fixture
def dummy_model() -> DummyModel:
    return DummyModel(1)

# Fixture for a dummy async session that simulates SQLAlchemy's AsyncSession.
@pytest.fixture
def dummy_session() -> AsyncMock:
    session: AsyncMock = AsyncMock(spec=AsyncSession)
    session.commit.return_value = asyncio.sleep(0)
    session.refresh.return_value = asyncio.sleep(0)
    session.add.return_value = None
    return session

# Fixture to simulate a database execution result.
@pytest.fixture
def dummy_result() -> MagicMock:
    result = MagicMock()
    # Instead of nesting multiple MagicMock instances, directly set the final return value.
    result.unique.return_value.scalar.return_value = DummyModel(1)
    return result

# A dummy Redis client with an async publish method.
class DummyRedisClient:
    async def publish(self, channel: str, message: str) -> None:
        # For testing, simply do nothing.
        return

# Fixture for the dummy Redis client.
@pytest.fixture
def dummy_redis_client() -> DummyRedisClient:
    return DummyRedisClient()
