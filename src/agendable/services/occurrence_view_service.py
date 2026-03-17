from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from agendable.db.models import AgendaItem, MeetingOccurrence, Task, User
from agendable.db.repos import AgendaItemRepository, MeetingOccurrenceRepository, TaskRepository
from agendable.services.occurrence_access_service import list_occurrence_attendee_users
from agendable.web.routes.common import format_datetime_local_value


async def get_default_task_due_at(
    session: AsyncSession,
    *,
    occurrence: MeetingOccurrence,
) -> datetime:
    occ_repo = MeetingOccurrenceRepository(session)
    next_occurrence = await occ_repo.get_next_for_series(
        occurrence.series_id, occurrence.scheduled_at
    )
    if next_occurrence is not None:
        return next_occurrence.scheduled_at
    return occurrence.scheduled_at


async def task_due_default_value(
    session: AsyncSession,
    *,
    occurrence: MeetingOccurrence,
    timezone: str,
) -> str:
    due_at = await get_default_task_due_at(session, occurrence=occurrence)
    return format_datetime_local_value(due_at, timezone)


async def occurrence_collections(
    session: AsyncSession,
    *,
    occurrence: MeetingOccurrence,
    current_user: User,
) -> tuple[list[Task], list[AgendaItem], list[User]]:
    tasks_repo = TaskRepository(session)
    tasks = await tasks_repo.list_for_occurrence(occurrence.id)

    agenda_repo = AgendaItemRepository(session)
    agenda_items = await agenda_repo.list_for_occurrence(occurrence.id)

    attendee_users = await list_occurrence_attendee_users(
        session,
        occurrence_id=occurrence.id,
        current_user=current_user,
    )
    return tasks, agenda_items, attendee_users
