from app.core.logging_config import logger
from app.db.models import MeetingTask, Task
from app.db.repositories.base_repo import BaseRepository
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select


class MeetingTaskRepository(BaseRepository[MeetingTask]):
    def __init__(self, db: AsyncSession):
        super().__init__(MeetingTask, db)

    async def get_tasks_by_meeting(self, meeting_id: int) -> list[Task]:
        logger.debug(f"Fetching tasks for meeting ID: {meeting_id}")
        stmt = (
            select(Task)
            .join(MeetingTask, MeetingTask.task_id == Task.id)
            .where(MeetingTask.meeting_id == meeting_id)
        )
        result = await self.db.execute(stmt)
        tasks = result.scalars().all()
        logger.debug(f"Retrieved {len(tasks)} tasks for meeting ID: {meeting_id}")
        return tasks
