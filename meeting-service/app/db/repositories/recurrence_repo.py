from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.recurrence import Recurrence
from common_lib.repositories import BaseRepository


class RecurrenceRepository(BaseRepository[Recurrence]):
    def __init__(self, db: AsyncSession):
        super().__init__(Recurrence, db)
