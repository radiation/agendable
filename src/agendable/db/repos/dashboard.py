from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from agendable.db.models import (
    MeetingOccurrence,
    MeetingOccurrenceAttendee,
    MeetingSeries,
    Task,
)
from agendable.db.repos.access_predicates import (
    attendee_matches_user_predicate,
    kept_or_local_series_predicate,
    visible_occurrence_for_user_predicate,
)


class DashboardRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_upcoming_meetings(
        self,
        *,
        user_id: uuid.UUID,
        now: datetime,
        limit: int = 20,
    ) -> list[MeetingOccurrence]:
        result = await self.session.execute(
            select(MeetingOccurrence)
            .options(
                selectinload(MeetingOccurrence.series),
                selectinload(MeetingOccurrence.external_event_mirrors),
                selectinload(MeetingOccurrence.attendees),
                selectinload(MeetingOccurrence.agenda_items),
            )
            .join(MeetingSeries, MeetingOccurrence.series_id == MeetingSeries.id)
            .outerjoin(
                MeetingOccurrenceAttendee,
                MeetingOccurrenceAttendee.occurrence_id == MeetingOccurrence.id,
            )
            .where(
                visible_occurrence_for_user_predicate(
                    user_id=user_id,
                    attendee_user_match=attendee_matches_user_predicate(user_id=user_id),
                ),
                kept_or_local_series_predicate(),
                MeetingOccurrence.scheduled_at >= now,
            )
            .distinct()
            .order_by(MeetingOccurrence.scheduled_at.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def list_outstanding_tasks(
        self,
        *,
        user_id: uuid.UUID,
        limit: int = 200,
    ) -> list[Task]:
        result = await self.session.execute(
            select(Task)
            .join(MeetingOccurrence, Task.occurrence_id == MeetingOccurrence.id)
            .join(MeetingSeries, MeetingOccurrence.series_id == MeetingSeries.id)
            .outerjoin(
                MeetingOccurrenceAttendee,
                MeetingOccurrenceAttendee.occurrence_id == MeetingOccurrence.id,
            )
            .options(
                selectinload(Task.assignee),
                selectinload(Task.occurrence).selectinload(MeetingOccurrence.series),
            )
            .where(
                visible_occurrence_for_user_predicate(
                    user_id=user_id,
                    attendee_user_match=attendee_matches_user_predicate(user_id=user_id),
                ),
                kept_or_local_series_predicate(),
                Task.is_done.is_(False),
            )
            .distinct()
            .order_by(Task.due_at.asc(), Task.created_at.asc())
            .limit(limit)
        )
        return list(result.scalars().all())
