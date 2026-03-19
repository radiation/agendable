from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from agendable.datetime_utils import format_datetime_local_value
from agendable.db.models import AgendaItem, MeetingOccurrence, Task, User
from agendable.db.repos import AgendaItemRepository, MeetingOccurrenceRepository, TaskRepository
from agendable.services.occurrence_access_service import OccurrenceAccessService


class OccurrenceViewService:
    def __init__(
        self,
        *,
        access: OccurrenceAccessService,
        agenda_items: AgendaItemRepository,
        occurrences: MeetingOccurrenceRepository,
        tasks: TaskRepository,
    ) -> None:
        self.access = access
        self.agenda_items = agenda_items
        self.occurrences = occurrences
        self.tasks = tasks

    @classmethod
    def from_session(cls, session: AsyncSession) -> OccurrenceViewService:
        return cls(
            access=OccurrenceAccessService.from_session(session),
            agenda_items=AgendaItemRepository(session),
            occurrences=MeetingOccurrenceRepository(session),
            tasks=TaskRepository(session),
        )

    async def get_default_task_due_at(
        self,
        *,
        occurrence: MeetingOccurrence,
    ) -> datetime:
        next_occurrence = await self.occurrences.get_next_for_series(
            occurrence.series_id, occurrence.scheduled_at
        )
        if next_occurrence is not None:
            return next_occurrence.scheduled_at
        return occurrence.scheduled_at

    async def task_due_default_value(
        self,
        *,
        occurrence: MeetingOccurrence,
        timezone: str,
    ) -> str:
        due_at = await self.get_default_task_due_at(occurrence=occurrence)
        return format_datetime_local_value(due_at, timezone)

    async def occurrence_collections(
        self,
        *,
        occurrence: MeetingOccurrence,
        current_user: User,
    ) -> tuple[list[Task], list[AgendaItem], list[User]]:
        tasks = await self.tasks.list_for_occurrence(occurrence.id)
        agenda_items = await self.agenda_items.list_for_occurrence(occurrence.id)
        attendee_users = await self.access.list_occurrence_attendee_users(
            occurrence_id=occurrence.id,
            current_user=current_user,
        )
        return tasks, agenda_items, attendee_users


async def get_default_task_due_at(
    session: AsyncSession,
    *,
    occurrence: MeetingOccurrence,
) -> datetime:
    return await OccurrenceViewService.from_session(session).get_default_task_due_at(
        occurrence=occurrence,
    )


async def task_due_default_value(
    session: AsyncSession,
    *,
    occurrence: MeetingOccurrence,
    timezone: str,
) -> str:
    return await OccurrenceViewService.from_session(session).task_due_default_value(
        occurrence=occurrence,
        timezone=timezone,
    )


async def occurrence_collections(
    session: AsyncSession,
    *,
    occurrence: MeetingOccurrence,
    current_user: User,
) -> tuple[list[Task], list[AgendaItem], list[User]]:
    return await OccurrenceViewService.from_session(session).occurrence_collections(
        occurrence=occurrence,
        current_user=current_user,
    )
