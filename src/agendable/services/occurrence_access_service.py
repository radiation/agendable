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


async def get_owned_occurrence(
    session: AsyncSession,
    *,
    occurrence_id: uuid.UUID,
    owner_user_id: uuid.UUID,
) -> tuple[MeetingOccurrence | None, MeetingSeries | None]:
    occ_repo = MeetingOccurrenceRepository(session)
    occurrence = await occ_repo.get_by_id(occurrence_id)
    if occurrence is None:
        return None, None

    series_repo = MeetingSeriesRepository(session)
    series = await series_repo.get_for_owner(occurrence.series_id, owner_user_id)
    if series is None:
        return None, None

    return occurrence, series


async def get_accessible_occurrence(
    session: AsyncSession,
    *,
    occurrence_id: uuid.UUID,
    user_id: uuid.UUID,
) -> tuple[MeetingOccurrence | None, MeetingSeries | None]:
    occ_repo = MeetingOccurrenceRepository(session)
    occurrence = await occ_repo.get_by_id(occurrence_id)
    if occurrence is None:
        return None, None

    series_repo = MeetingSeriesRepository(session)
    owner_series = await series_repo.get_for_owner(occurrence.series_id, user_id)
    if owner_series is not None:
        return occurrence, owner_series

    attendee_repo = MeetingOccurrenceAttendeeRepository(session)
    has_attendee_link = await attendee_repo.has_occurrence_user_link(
        occurrence_id=occurrence.id,
        user_id=user_id,
    )
    if not has_attendee_link:
        return None, None

    series = await series_repo.get(occurrence.series_id)
    if series is None:
        return None, None

    return occurrence, series


async def list_occurrence_attendee_users(
    session: AsyncSession,
    *,
    occurrence_id: uuid.UUID,
    current_user: User,
) -> list[User]:
    attendee_repo = MeetingOccurrenceAttendeeRepository(session)
    attendee_links = await attendee_repo.list_for_occurrence_with_users(occurrence_id)

    attendee_users = [current_user]
    attendee_user_ids: set[uuid.UUID] = {current_user.id}
    for link in attendee_links:
        if link.user_id in attendee_user_ids:
            continue
        attendee_users.append(link.user)
        attendee_user_ids.add(link.user_id)

    return attendee_users


async def assignee_exists(
    session: AsyncSession,
    *,
    assignee_id: uuid.UUID,
) -> bool:
    users_repo = UserRepository(session)
    assignee = await users_repo.get_by_id(assignee_id)
    return assignee is not None


async def is_occurrence_attendee(
    session: AsyncSession,
    *,
    occurrence_id: uuid.UUID,
    user_id: uuid.UUID,
) -> bool:
    attendee_repo = MeetingOccurrenceAttendeeRepository(session)
    return await attendee_repo.has_occurrence_user_link(
        occurrence_id=occurrence_id,
        user_id=user_id,
    )
