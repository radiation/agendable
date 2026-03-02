from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

import agendable.db as db
from agendable.db.models import MeetingOccurrence, MeetingSeries, User
from agendable.db.repos.meeting_occurrence_attendees import MeetingOccurrenceAttendeeRepository
from agendable.db.repos.users import UserRepository


async def _new_user(email: str) -> User:
    return User(
        email=email,
        first_name="Test",
        last_name="User",
        display_name="Test User",
        timezone="UTC",
        password_hash=None,
    )


async def _create_occurrence(
    db_session: AsyncSession, owner_user_id: uuid.UUID
) -> MeetingOccurrence:
    series = MeetingSeries(owner_user_id=owner_user_id, title="Weekly", default_interval_days=7)
    db_session.add(series)
    await db_session.flush()

    occurrence = MeetingOccurrence(
        series_id=series.id,
        scheduled_at=datetime.now(UTC) + timedelta(days=1),
        notes="",
        is_completed=False,
    )
    db_session.add(occurrence)
    await db_session.flush()
    return occurrence


@pytest.mark.asyncio
async def test_attendee_repo_get_and_list_occurrence_ids(db_session: AsyncSession) -> None:
    users_repo = UserRepository(db_session)
    owner = await _new_user(f"owner-{uuid.uuid4()}@example.com")
    attendee = await _new_user(f"attendee-{uuid.uuid4()}@example.com")
    await users_repo.add(owner)
    await users_repo.add(attendee)
    await users_repo.commit()

    occ_one = await _create_occurrence(db_session, owner.id)
    occ_two = await _create_occurrence(db_session, owner.id)

    repo = MeetingOccurrenceAttendeeRepository(db_session)
    await repo.add_link(occurrence_id=occ_one.id, user_id=attendee.id)
    await repo.commit()

    got = await repo.get_by_occurrence_and_user(occ_one.id, attendee.id)
    assert got is not None

    missing = await repo.get_by_occurrence_and_user(occ_two.id, attendee.id)
    assert missing is None

    linked_ids = await repo.list_occurrence_ids_for_user(
        user_id=attendee.id,
        occurrence_ids=[occ_one.id, occ_two.id],
    )
    assert linked_ids == {occ_one.id}


@pytest.mark.asyncio
async def test_attendee_repo_add_missing_links(db_session: AsyncSession) -> None:
    users_repo = UserRepository(db_session)
    owner = await _new_user(f"owner-{uuid.uuid4()}@example.com")
    attendee = await _new_user(f"attendee-{uuid.uuid4()}@example.com")
    await users_repo.add(owner)
    await users_repo.add(attendee)
    await users_repo.commit()

    occ_one = await _create_occurrence(db_session, owner.id)
    occ_two = await _create_occurrence(db_session, owner.id)

    repo = MeetingOccurrenceAttendeeRepository(db_session)
    await repo.add_link(occurrence_id=occ_one.id, user_id=attendee.id)
    await repo.commit()

    existing = await repo.list_occurrence_ids_for_user(
        user_id=attendee.id,
        occurrence_ids=[occ_one.id, occ_two.id],
    )

    added = await repo.add_missing_links(
        user_id=attendee.id,
        occurrence_ids=[occ_one.id, occ_two.id],
        existing_occurrence_ids=existing,
    )
    await repo.commit()

    assert added == 1

    async with db.SessionMaker() as verify_session:
        verify_repo = MeetingOccurrenceAttendeeRepository(verify_session)
        linked_ids = await verify_repo.list_occurrence_ids_for_user(
            user_id=attendee.id,
            occurrence_ids=[occ_one.id, occ_two.id],
        )
        assert linked_ids == {occ_one.id, occ_two.id}

        all_rows = await verify_repo.list(limit=10)
        attendee_rows = [
            row
            for row in all_rows
            if row.user_id == attendee.id and row.occurrence_id in {occ_one.id, occ_two.id}
        ]
        assert len(attendee_rows) == 2
