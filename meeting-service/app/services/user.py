from typing import Optional

from common_lib.services import BaseService
from redis.asyncio import Redis

from app.db.models.user import User
from app.repositories.user import UserRepository
from app.schemas.user import UserCreate, UserUpdate


class UserService(BaseService[User, UserCreate, UserUpdate]):
    def __init__(
        self, repo: UserRepository, redis_client: Optional[Redis] = None
    ) -> None:
        super().__init__(repo, redis_client=redis_client)
        self.repo: UserRepository = repo
