from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from agendable.db.models import MeetingOccurrence, MeetingSeries, User
from agendable.db.repos import (
    MeetingOccurrenceAttendeeRepository,
    MeetingOccurrenceRepository,
    MeetingSeriesRepository,
    UserRepository,
)


class OccurrenceAccessService:
    def __init__(
        self,
        *,
        session: AsyncSession,
        attendees: MeetingOccurrenceAttendeeRepository | None = None,
        occurrences: MeetingOccurrenceRepository | None = None,
        series: MeetingSeriesRepository | None = None,
        users: UserRepository | None = None,
    ) -> None:
        self.session = session
        self.attendees = attendees or MeetingOccurrenceAttendeeRepository(session)
        self.occurrences = occurrences or MeetingOccurrenceRepository(session)
        self.series = series or MeetingSeriesRepository(session)
        self.users = users or UserRepository(session)

    @classmethod
    def from_session(cls, session: AsyncSession) -> OccurrenceAccessService:
        return cls(
            session=session,
            attendees=MeetingOccurrenceAttendeeRepository(session),
            occurrences=MeetingOccurrenceRepository(session),
            series=MeetingSeriesRepository(session),
            users=UserRepository(session),
        )

    async def get_owned_occurrence(
        self,
        *,
        occurrence_id: uuid.UUID,
        owner_user_id: uuid.UUID,
    ) -> tuple[MeetingOccurrence | None, MeetingSeries | None]:
        occurrence = await self.occurrences.get_by_id(occurrence_id)
        if occurrence is None:
            return None, None

        series = await self.series.get_for_owner(occurrence.series_id, owner_user_id)
        if series is None:
            return None, None

        return occurrence, series

    async def get_accessible_occurrence(
        self,
        *,
        occurrence_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> tuple[MeetingOccurrence | None, MeetingSeries | None]:
        occurrence_with_series = await self.occurrences.get_occurrence_with_series_for_user(
            occurrence_id=occurrence_id,
            user_id=user_id,
        )
        if occurrence_with_series is None:
            return None, None
        return occurrence_with_series

    async def list_occurrence_attendee_users(
        self,
        *,
        occurrence_id: uuid.UUID,
        current_user: User,
    ) -> list[User]:
        attendee_links = await self.attendees.list_for_occurrence_with_users(occurrence_id)

        attendee_users = [current_user]
        attendee_user_ids: set[uuid.UUID] = {current_user.id}
        for link in attendee_links:
            if link.user_id in attendee_user_ids:
                continue
            attendee_users.append(link.user)
            attendee_user_ids.add(link.user_id)

        return attendee_users

    async def assignee_exists(
        self,
        *,
        assignee_id: uuid.UUID,
    ) -> bool:
        assignee = await self.users.get_by_id(assignee_id)
        return assignee is not None

    async def is_occurrence_attendee(
        self,
        *,
        occurrence_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> bool:
        return await self.attendees.has_occurrence_user_link(
            occurrence_id=occurrence_id,
            user_id=user_id,
        )


async def get_owned_occurrence(
    session: AsyncSession,
    *,
    occurrence_id: uuid.UUID,
    owner_user_id: uuid.UUID,
) -> tuple[MeetingOccurrence | None, MeetingSeries | None]:
    return await OccurrenceAccessService.from_session(session).get_owned_occurrence(
        occurrence_id=occurrence_id,
        owner_user_id=owner_user_id,
    )


async def get_accessible_occurrence(
    session: AsyncSession,
    *,
    occurrence_id: uuid.UUID,
    user_id: uuid.UUID,
) -> tuple[MeetingOccurrence | None, MeetingSeries | None]:
    return await OccurrenceAccessService.from_session(session).get_accessible_occurrence(
        occurrence_id=occurrence_id,
        user_id=user_id,
    )


async def list_occurrence_attendee_users(
    session: AsyncSession,
    *,
    occurrence_id: uuid.UUID,
    current_user: User,
) -> list[User]:
    return await OccurrenceAccessService.from_session(session).list_occurrence_attendee_users(
        occurrence_id=occurrence_id,
        current_user=current_user,
    )


async def assignee_exists(
    session: AsyncSession,
    *,
    assignee_id: uuid.UUID,
) -> bool:
    return await OccurrenceAccessService.from_session(session).assignee_exists(
        assignee_id=assignee_id,
    )


async def is_occurrence_attendee(
    session: AsyncSession,
    *,
    occurrence_id: uuid.UUID,
    user_id: uuid.UUID,
) -> bool:
    return await OccurrenceAccessService.from_session(session).is_occurrence_attendee(
        occurrence_id=occurrence_id,
        user_id=user_id,
    )
