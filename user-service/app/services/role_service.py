from common_lib.redis_client import RedisClient
from app.db.models import Role
from app.db.repositories.role_repo import RoleRepository
from app.schemas.roles import RoleCreate, RoleUpdate
from common_lib.services import BaseService


class RoleService(BaseService[Role, RoleCreate, RoleUpdate]):
    def __init__(self, repository: RoleRepository, redis_client: RedisClient):
        super().__init__(repository, redis_client)
