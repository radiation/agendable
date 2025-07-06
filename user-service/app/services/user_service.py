from typing import Optional

from common_lib.services import BaseService
from redis.asyncio import Redis

from app.db.models import User
from app.db.repositories.user_repo import UserRepository
from app.schemas.user import UserCreate, UserUpdate


class UserService(BaseService[User, UserCreate, UserUpdate]):
    def __init__(self, repository: UserRepository, redis_client: Optional[Redis]):
        super().__init__(repository, redis_client)
