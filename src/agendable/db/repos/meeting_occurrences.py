from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from agendable.db.models import MeetingOccurrence, MeetingOccurrenceAttendee, MeetingSeries
from agendable.db.repos.base import BaseRepository


class MeetingOccurrenceRepository(BaseRepository[MeetingOccurrence]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, MeetingOccurrence)

    async def list_for_series(self, series_id: uuid.UUID) -> list[MeetingOccurrence]:
        result = await self.session.execute(
            select(MeetingOccurrence)
            .where(MeetingOccurrence.series_id == series_id)
            .order_by(MeetingOccurrence.scheduled_at.asc())
        )
        return list(result.scalars().all())

    async def get_by_id(self, occurrence_id: uuid.UUID) -> MeetingOccurrence | None:
        return await self.get(occurrence_id)

    async def get_for_series_scheduled_at(
        self,
        *,
        series_id: uuid.UUID,
        scheduled_at: datetime,
    ) -> MeetingOccurrence | None:
        result = await self.session.execute(
            select(MeetingOccurrence)
            .where(
                MeetingOccurrence.series_id == series_id,
                MeetingOccurrence.scheduled_at == scheduled_at,
            )
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_next_for_series(
        self, series_id: uuid.UUID, scheduled_after: datetime
    ) -> MeetingOccurrence | None:
        result = await self.session.execute(
            select(MeetingOccurrence)
            .where(
                MeetingOccurrence.series_id == series_id,
                MeetingOccurrence.scheduled_at > scheduled_after,
                MeetingOccurrence.is_completed.is_(False),
            )
            .order_by(MeetingOccurrence.scheduled_at.asc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_occurrence_with_series_for_user(
        self,
        *,
        occurrence_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> tuple[MeetingOccurrence, MeetingSeries] | None:
        result = await self.session.execute(
            select(MeetingOccurrence, MeetingSeries)
            .join(MeetingSeries, MeetingOccurrence.series_id == MeetingSeries.id)
            .outerjoin(
                MeetingOccurrenceAttendee,
                and_(
                    MeetingOccurrenceAttendee.occurrence_id == MeetingOccurrence.id,
                    MeetingOccurrenceAttendee.user_id == user_id,
                ),
            )
            .where(
                MeetingOccurrence.id == occurrence_id,
                or_(
                    MeetingSeries.owner_user_id == user_id,
                    MeetingOccurrenceAttendee.user_id.is_not(None),
                ),
            )
            .limit(1)
        )
        row = result.first()
        if row is None:
            return None
        return row[0], row[1]
