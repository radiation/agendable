import json
from typing import Any, Generic, Optional, TypeVar, Union
from uuid import UUID

from common_lib.exceptions import NotFoundError
from common_lib.logging_config import logger
from common_lib.models import Base
from common_lib.repositories import BaseRepository
from pydantic import BaseModel
from redis.asyncio import Redis

ModelType = TypeVar("ModelType", bound=Base)
CreateSchemaType = TypeVar("CreateSchemaType", bound=BaseModel)
UpdateSchemaType = TypeVar("UpdateSchemaType", bound=BaseModel)


class BaseService(Generic[ModelType, CreateSchemaType, UpdateSchemaType]):
    def __init__(
        self,
        repo: BaseRepository[ModelType],
        redis_client: Optional[Redis] = None,
    ) -> None:
        self.repo = repo
        self.model_name = self.repo.model.__name__
        self.redis_client = redis_client

    def _get_model_name(self) -> str:
        return self.repo.model.__name__

    async def _publish_event(self, event_type: str, payload: dict[str, Any]) -> None:
        for sensitive in ("password", "hashed_password"):
            payload.pop(sensitive, None)
        event = {
            "event_type": event_type,
            "model": self._get_model_name(),
            "payload": payload,
        }
        channel = f"{self._get_model_name().lower()}-events"
        logger.info(f"Publishing event to channel {channel}: {event}")
        logger.info(f"Redis client: {self.redis_client}")
        if not self.redis_client:
            logger.warning("Redis client not initialized. Skipping event publish")
            raise RuntimeError("Redis client not initialized")
        await self.redis_client.publish(channel, json.dumps(event, default=str))

    async def create(self, create_data: CreateSchemaType) -> ModelType:
        logger.info(f"Creating {self.model_name} with data: {create_data.model_dump()}")
        model_instance = self.repo.model(**create_data.model_dump())
        result = await self.repo.create(model_instance)
        if not result:
            logger.error(f"Failed to create {self.model_name}")
            raise RuntimeError(f"Failed to create {self.model_name}")
        logger.info(f"{self.model_name} created successfully with ID: {result.id}")
        await self._publish_event(
            event_type="create",
            payload=result.as_dict(),
        )
        return result

    async def get_by_id(self, object_id: Union[UUID, int]) -> ModelType:
        logger.info(
            f"Fetching {self.model_name} with ID: {object_id} (type: {type(object_id)})"
        )
        entity = await self.repo.get_by_id(object_id)
        if not entity:
            logger.warning(f"{self.model_name} with ID {object_id} not found")
            raise NotFoundError(
                detail=f"{self.model_name} with ID {object_id} not found"
            )
        logger.info(f"{self.model_name} retrieved: {entity}")
        return entity

    async def get_by_field(self, field_name: str, value: Any) -> list[ModelType]:
        logger.info(f"Fetching {self.model_name} by {field_name}={value}")
        result = await self.repo.get_by_field(field_name, value)
        logger.info(
            f"Retrieved {len(result)} {self.model_name}(s) \
                matching {field_name}={value}"
        )
        return result

    async def get_all(self, skip: int = 0, limit: int = 10) -> list[ModelType]:
        logger.info(f"Fetching all {self.model_name}s with skip={skip}, limit={limit}")
        result = await self.repo.get_all(skip, limit)
        logger.info(f"Retrieved {len(result)} {self.model_name}(s)")
        return result

    async def update(
        self, object_id: Union[UUID, int], update_data: UpdateSchemaType
    ) -> ModelType:
        logger.info(
            f"Updating {self.model_name} with ID: \
                {id} and data: {update_data.model_dump()}"
        )
        entity = await self.repo.get_by_id(object_id)
        if not entity:
            logger.warning(f"{self.model_name} with ID {object_id} not found")
            raise NotFoundError(
                detail=f"{self.model_name} with ID {object_id} not found"
            )
        update_dict = update_data.model_dump(exclude_unset=True)
        for key, value in update_dict.items():
            setattr(entity, key, value)
        updated_entity = await self.repo.update(object_id, entity)
        logger.info(f"{self.model_name} with ID {object_id} updated successfully")
        await self._publish_event(
            event_type="update",
            payload=update_dict,
        )
        return updated_entity

    async def delete(self, object_id: Union[UUID, int]) -> bool:
        logger.info(
            f"Deleting {self.model_name} with ID: {object_id} (type: {type(object_id)})"
        )
        entity = await self.repo.get_by_id(object_id)
        if not entity:
            logger.warning(f"{self.model_name} with ID {object_id} not found")
            raise NotFoundError(
                detail=f"{self.model_name} with ID {object_id} not found"
            )
        success = await self.repo.delete(object_id)
        if success:
            logger.info(f"{self.model_name} with ID {object_id} deleted successfully")
        else:
            logger.error(f"Failed to delete {self.model_name} with ID {object_id}")
        await self._publish_event(
            event_type="delete",
            payload={"id": object_id},
        )
        return success
