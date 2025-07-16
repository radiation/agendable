import json
from typing import Any, Type, TypeVar

from common_lib.exceptions import ValidationError
from common_lib.logging_config import logger
from pydantic import BaseModel
from redis.asyncio import Redis
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import RedisError

from app.schemas.user import UserCreate, UserUpdate
from app.services.task import TaskService
from app.services.user import UserService

T = TypeVar("T", bound=BaseModel)


class RedisSubscriber:
    def __init__(
        self,
        redis_client: Redis,
        task_service: TaskService,
        user_service: UserService,
    ) -> None:
        self.redis_client = redis_client
        self.task_service = task_service
        self.user_service = user_service

    async def listen_to_events(self, channels: list[str]) -> None:
        try:
            pubsub = self.redis_client.pubsub()
            await pubsub.subscribe(*channels)
            logger.info(f"Subscribed to {channels} channel.")

            async for message in pubsub.listen():
                logger.info(f"Received message: {message}")
                if message["type"] == "message":
                    event = json.loads(message["data"])
                    logger.info(f"Received message from {message['channel']}: {event}")
                    await self.handle_event(event, channel=message["channel"])
        except (
            RedisConnectionError,
            RedisError,
            ValueError,
            TypeError,
            json.JSONDecodeError,
        ) as exc:
            logger.warning(f"Error in listening to events: {exc}")

    async def handle_event(self, event: dict[str, Any], channel: str) -> None:
        event_type = event["event_type"]
        event_data = event["payload"]

        def filter_valid_fields(data_dict: Any, schema: Type[T]) -> dict[str, Any]:
            return {
                key: value
                for key, value in data_dict.items()
                if key in schema.model_fields
            }

        try:
            if channel == "user-events":
                match event_type:
                    case "create":
                        filtered_data = filter_valid_fields(event_data, UserCreate)
                        created_user_data: UserCreate = UserCreate.model_validate(
                            filtered_data
                        )
                        await self.user_service.create(created_user_data)
                    case "update":
                        filtered_data = filter_valid_fields(event_data, UserUpdate)
                        updated_user_data: UserUpdate = UserUpdate.model_validate(
                            filtered_data
                        )
                        await self.user_service.update(
                            object_id=event_data.id, update_data=updated_user_data
                        )
                    case "delete":
                        if user_id := event_data.get("id"):
                            await self.user_service.delete(user_id)
                        else:
                            raise ValueError(
                                "Delete event must include 'id' in payload"
                            )
                    case _:
                        raise ValueError(f"Unsupported event type: {event_type}")
            elif channel == "meeting-events":
                if event_type == "complete":
                    meeting_id = event_data["meeting_id"]
                    next_meeting_id = event_data["next_meeting_id"]

                    if meeting_id:
                        await self.task_service.reassign_tasks_to_meeting(
                            meeting_id, next_meeting_id
                        )
                    else:
                        logger.warning(
                            f"Next meeting for completed M:{meeting_id} not found"
                        )
            else:
                logger.warning(f"Unhandled channel: {channel}")
        except ValidationError as e:
            logger.error(f"Validation error for event {event_type}: {e}")
            raise
