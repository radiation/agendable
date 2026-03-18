from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from agendable.db.models import MeetingOccurrenceAttendee
from agendable.db.repos.base import BaseRepository


class MeetingOccurrenceAttendeeRepository(BaseRepository[MeetingOccurrenceAttendee]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, MeetingOccurrenceAttendee)

    async def get_by_occurrence_and_user(
        self,
        occurrence_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> MeetingOccurrenceAttendee | None:
        result = await self.session.execute(
            select(MeetingOccurrenceAttendee).where(
                MeetingOccurrenceAttendee.occurrence_id == occurrence_id,
                MeetingOccurrenceAttendee.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_occurrence_ids_for_user(
        self,
        *,
        user_id: uuid.UUID,
        occurrence_ids: list[uuid.UUID],
    ) -> set[uuid.UUID]:
        if not occurrence_ids:
            return set()

        result = await self.session.execute(
            select(MeetingOccurrenceAttendee.occurrence_id).where(
                MeetingOccurrenceAttendee.user_id == user_id,
                MeetingOccurrenceAttendee.occurrence_id.in_(occurrence_ids),
            )
        )
        return set(result.scalars().all())

    async def add_link(
        self,
        *,
        occurrence_id: uuid.UUID,
        user_id: uuid.UUID,
        flush: bool = False,
    ) -> MeetingOccurrenceAttendee:
        link = MeetingOccurrenceAttendee(occurrence_id=occurrence_id, user_id=user_id)
        self.session.add(link)
        if flush:
            await self.session.flush()
        return link

    async def add_missing_links(
        self,
        *,
        user_id: uuid.UUID,
        occurrence_ids: list[uuid.UUID],
        existing_occurrence_ids: set[uuid.UUID],
    ) -> int:
        added_count = 0
        for occurrence_id in occurrence_ids:
            if occurrence_id in existing_occurrence_ids:
                continue
            await self.add_link(occurrence_id=occurrence_id, user_id=user_id, flush=False)
            added_count += 1
        return added_count

    async def has_occurrence_user_link(
        self,
        *,
        occurrence_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> bool:
        link = await self.get_by_occurrence_and_user(occurrence_id, user_id)
        return link is not None

    async def list_for_occurrence_with_users(
        self,
        occurrence_id: uuid.UUID,
    ) -> list[MeetingOccurrenceAttendee]:
        result = await self.session.execute(
            select(MeetingOccurrenceAttendee)
            .options(selectinload(MeetingOccurrenceAttendee.user))
            .where(MeetingOccurrenceAttendee.occurrence_id == occurrence_id)
        )
        return list(result.scalars().all())
