from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Role
from common_lib.repositories import BaseRepository


class RoleRepository(BaseRepository[Role]):
    def __init__(self, db: AsyncSession):
        super().__init__(model=Role, db=db)
