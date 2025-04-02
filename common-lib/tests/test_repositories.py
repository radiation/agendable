import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock
from typing import Union
from uuid import UUID
from common_lib.repositories import BaseRepository
from tests.conftest import DummyModel

@pytest.fixture
def dummy_session() -> AsyncMock:
    session = AsyncMock()
    session.commit.return_value = asyncio.sleep(0)
    session.refresh.return_value = asyncio.sleep(0)
    session.add.return_value = None
    return session

@pytest.fixture
def dummy_result(dummy_model: DummyModel) -> MagicMock:
    result = MagicMock()
    # Configure the chain for get_by_id()
    result.unique.return_value.scalar.return_value = dummy_model
    # Configure the chain for create()
    result.scalars.return_value.first.return_value = dummy_model
    return result

async def test_create(dummy_session: AsyncMock, dummy_result: MagicMock) -> None:
    dummy_session.execute.return_value = dummy_result
    repo = BaseRepository(DummyModel, dummy_session)
    obj = DummyModel(1)
    created = await repo.create(obj)
    assert created is not None
    assert created.id == 1
    dummy_session.add.assert_called_once_with(obj)
    dummy_session.commit.assert_called_once()
    dummy_session.refresh.assert_called_once_with(obj)
    dummy_session.execute.assert_called_once()

@pytest.mark.asyncio
async def test_get_by_id(dummy_session: AsyncMock, dummy_result: MagicMock) -> None:
    dummy_session.execute.return_value = dummy_result
    repo = BaseRepository(DummyModel, dummy_session)
    obj = await repo.get_by_id(1)
    assert obj is not None
    assert obj.id == 1
    dummy_session.execute.assert_called_once()

@pytest.mark.asyncio
async def test_delete_not_found(dummy_session: AsyncMock) -> None:
    # Override get_by_id to return None to simulate not found.
    async def fake_get_by_id(_: Union[int, UUID]) -> None:
        return None

    repo = BaseRepository(DummyModel, dummy_session)
    repo.get_by_id = fake_get_by_id
    result = await repo.delete(1)
    assert result is False
