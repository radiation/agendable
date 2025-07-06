from typing import Optional

from common_lib.services import BaseService
from redis.asyncio import Redis

from app.db.models import Role
from app.db.repositories.role_repo import RoleRepository
from app.schemas.roles import RoleCreate, RoleUpdate


class RoleService(BaseService[Role, RoleCreate, RoleUpdate]):
    def __init__(self, repository: RoleRepository, redis_client: Optional[Redis]):
        super().__init__(repository, redis_client)
