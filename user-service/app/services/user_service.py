from common_lib.redis_client import RedisClient
from app.db.models import User
from app.db.repositories.user_repo import UserRepository
from app.schemas.user import UserCreate, UserUpdate
from common_lib.services import BaseService


class UserService(BaseService[User, UserCreate, UserUpdate]):
    def __init__(self, repository: UserRepository, redis_client: RedisClient):
        super().__init__(repository, redis_client)
