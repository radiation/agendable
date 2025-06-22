from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Group
from common_lib.repositories import BaseRepository


class GroupRepository(BaseRepository[Group]):
    def __init__(self, db: AsyncSession):
        super().__init__(model=Group, db=db)
