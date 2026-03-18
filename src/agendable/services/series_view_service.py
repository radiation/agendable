from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from agendable.db.models import MeetingOccurrence, MeetingSeries, User
from agendable.db.repos import (
    MeetingOccurrenceAttendeeRepository,
    MeetingOccurrenceRepository,
    MeetingSeriesRepository,
    UserRepository,
)


async def get_owned_series(
    session: AsyncSession,
    *,
    series_id: uuid.UUID,
    owner_user_id: uuid.UUID,
) -> MeetingSeries | None:
    series_repo = MeetingSeriesRepository(session)
    return await series_repo.get_for_owner(series_id, owner_user_id)


async def list_series_occurrences(
    session: AsyncSession,
    *,
    series_id: uuid.UUID,
) -> list[MeetingOccurrence]:
    occ_repo = MeetingOccurrenceRepository(session)
    return await occ_repo.list_for_series(series_id)


def select_active_occurrence(
    occurrences: list[MeetingOccurrence],
    *,
    now: datetime | None = None,
) -> MeetingOccurrence | None:
    active_now = now or datetime.now(UTC)
    for occurrence in occurrences:
        scheduled_at = occurrence.scheduled_at
        if scheduled_at.tzinfo is None:
            scheduled_at = scheduled_at.replace(tzinfo=UTC)
        if scheduled_at >= active_now:
            return occurrence

    if occurrences:
        return occurrences[-1]
    return None


async def resolve_attendee_user(
    session: AsyncSession,
    *,
    email: str,
) -> User | None:
    users_repo = UserRepository(session)
    return await users_repo.get_by_email(email)


async def existing_attendee_occurrence_ids(
    session: AsyncSession,
    *,
    attendee_user_id: uuid.UUID,
    occurrence_ids: list[uuid.UUID],
) -> set[uuid.UUID]:
    attendee_repo = MeetingOccurrenceAttendeeRepository(session)
    return await attendee_repo.list_occurrence_ids_for_user(
        user_id=attendee_user_id,
        occurrence_ids=occurrence_ids,
    )


async def add_missing_attendee_links(
    session: AsyncSession,
    *,
    attendee_user_id: uuid.UUID,
    occurrence_ids: list[uuid.UUID],
    existing_occurrence_ids: set[uuid.UUID],
) -> int:
    attendee_repo = MeetingOccurrenceAttendeeRepository(session)
    return await attendee_repo.add_missing_links(
        user_id=attendee_user_id,
        occurrence_ids=occurrence_ids,
        existing_occurrence_ids=existing_occurrence_ids,
    )
