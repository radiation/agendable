from typing import Optional

from common_lib.services import BaseService
from redis.asyncio import Redis

from app.db.models import Group
from app.db.repositories.group_repo import GroupRepository
from app.schemas.groups import GroupCreate, GroupUpdate


class GroupService(BaseService[Group, GroupCreate, GroupUpdate]):
    def __init__(self, repository: GroupRepository, redis_client: Optional[Redis]):
        super().__init__(repository, redis_client)
