from typing import Optional

from common_lib.redis_client import RedisClient
from app.db.models.user import User
from app.db.repositories.user_repo import UserRepository
from app.schemas.user_schemas import UserCreate, UserUpdate
from common_lib.services import BaseService


class UserService(BaseService[User, UserCreate, UserUpdate]):
    def __init__(
        self, repo: UserRepository, redis_client: Optional[RedisClient] = None
    ) -> None:
        super().__init__(repo, redis_client=redis_client)
        self.repo: UserRepository = repo
