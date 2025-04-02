import pytest
from typing import Any, Optional
from pydantic import BaseModel

from common_lib.exceptions import NotFoundError
from common_lib.services import BaseService
from tests.conftest import DummyModel


class DummyCreate(BaseModel):
    id: int

class DummyUpdate(BaseModel):
    id: int

class DummyRepo:
    model = DummyModel

    async def create(self, data: dict[str, Any]) -> "DummyModel":
        return DummyModel(1)

    async def get_by_id(self, id: int) -> Optional["DummyModel"]:
        # Return a dummy model with ID 1 if the ID is 1, otherwise return None.
        return DummyModel(1) if id == 1 else None

    async def get_by_field(self, field: str, value: Any) -> list["DummyModel"]:
        return []

    async def get_all(self, skip: int, limit: int) -> list["DummyModel"]:
        return [DummyModel(1)]

    async def update(self, obj: "DummyModel") -> "DummyModel":
        return obj

    async def delete(self, id: int) -> bool:
        return True

class DummyRedisClient:
    async def publish(self, channel: str, message: str) -> None:
        # In the dummy implementation, just return None (or simulate a no-op).
        return None

@pytest.mark.asyncio
async def test_service_create() -> None:
    repo = DummyRepo()
    redis_client = DummyRedisClient()
    service: BaseService[DummyModel, DummyCreate, DummyUpdate] = BaseService(repo, redis_client)
    
    result = await service.create(DummyCreate(id=1))
    assert result is not None
    assert result.id == 1

@pytest.mark.asyncio
async def test_service_get_by_id_not_found() -> None:
    repo = DummyRepo()
    service: BaseService[DummyModel, DummyCreate, DummyUpdate] = BaseService(repo)
    with pytest.raises(NotFoundError):
        await service.get_by_id(999)

@pytest.mark.asyncio
async def test_publish_event_no_redis() -> None:
    repo = DummyRepo()
    service: BaseService[DummyModel, DummyCreate, DummyUpdate] = BaseService(repo, redis_client=None)
    with pytest.raises(RuntimeError):
        await service._publish_event("test_event", {"key": "value"})

@pytest.mark.asyncio
async def test_publish_event_with_redis() -> None:
    repo = DummyRepo()
    redis_client = DummyRedisClient()
    service: BaseService[DummyModel, DummyCreate, DummyUpdate] = BaseService(repo, redis_client=redis_client)
    # This should complete without raising.
    await service._publish_event("test_event", {"key": "value"})
