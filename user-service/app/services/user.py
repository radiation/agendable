from typing import Optional

from common_lib.services import BaseService
from redis.asyncio import Redis

from app.db.models.user import User
from app.repositories.user import UserRepository
from app.schemas.user import UserCreate, UserRegistration, UserUpdate


class UserService(BaseService[User, UserCreate, UserUpdate]):
    def __init__(self, repository: UserRepository, redis_client: Optional[Redis]):
        super().__init__(repository, redis_client)

    async def register_user(self, payload: UserRegistration) -> User:
        return await super().create(create_data=payload.to_create())
