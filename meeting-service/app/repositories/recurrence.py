from common_lib.repositories import BaseRepository
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.recurrence import Recurrence


class RecurrenceRepository(BaseRepository[Recurrence]):
    def __init__(self, db: AsyncSession):
        super().__init__(Recurrence, db)
