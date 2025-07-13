import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from tests.factories import MeetingFactory

from app.db.models.meeting import Meeting
from app.db.models.recurrence import Recurrence
from app.db.repositories.meeting_repo import MeetingRepository


@pytest.mark.asyncio
async def test_create_meeting(db_session: AsyncSession) -> None:
    repo = MeetingRepository(db_session)
    meeting_data = MeetingFactory.build()
    created_meeting = await repo.create(meeting_data)

    assert created_meeting is not None
    assert created_meeting.title == meeting_data.title
    assert created_meeting.start_date == meeting_data.start_date


@pytest.mark.asyncio
async def test_get_meeting_by_id(db_session: AsyncSession) -> None:
    repo = MeetingRepository(db_session)

    meeting_data = MeetingFactory.build()
    created_meeting = await repo.create(meeting_data)
    assert created_meeting is not None

    retrieved = await repo.get_by_id(created_meeting.id)

    assert retrieved is not None
    assert retrieved.title == meeting_data.title
    assert retrieved.duration == meeting_data.duration


# TODO: Have this test actually test getting a meeting by user
@pytest.mark.asyncio
async def test_get_meeting_by_user(db_session: AsyncSession) -> None:
    repo = MeetingRepository(db_session)

    meeting_data = MeetingFactory.build()
    created_meeting = await repo.create(meeting_data)
    assert created_meeting is not None

    # Use the repo's get_by_field method
    retrieved_meetings: list[Meeting] = await repo.get_by_field(
        "title", meeting_data.title
    )

    # Assertions
    assert len(retrieved_meetings) == 1
    assert retrieved_meetings[0] is not None
    assert retrieved_meetings[0].title == meeting_data.title
    assert retrieved_meetings[0].duration == meeting_data.duration
    assert retrieved_meetings[0].id == created_meeting.id


@pytest.mark.asyncio
async def test_update_meeting(db_session: AsyncSession) -> None:
    repo = MeetingRepository(db_session)

    meeting_factory = MeetingFactory.build()
    created_meeting = await repo.create(meeting_factory)
    assert created_meeting is not None

    updated_payload = MeetingFactory.build(title="Updated Meeting", duration=120)
    updated_meeting = await repo.update(created_meeting.id, updated_payload)

    assert updated_meeting.title == updated_payload.title
    assert updated_meeting.duration == updated_payload.duration


@pytest.mark.asyncio
async def test_delete_meeting(db_session: AsyncSession) -> None:
    repo = MeetingRepository(db_session)

    meeting_data = MeetingFactory.build()
    created_meeting = await repo.create(meeting_data)
    assert created_meeting is not None

    await repo.delete(created_meeting.id)
    deleted = await repo.get_by_id(created_meeting.id)
    assert deleted is None


@pytest.mark.asyncio
async def test_relationships(db_session: AsyncSession) -> None:
    repo = MeetingRepository(db_session)

    recurrence = Recurrence(title="Weekly Recurrence", rrule="FREQ=WEEKLY;INTERVAL=1")
    db_session.add(recurrence)
    await db_session.commit()

    meeting_data = MeetingFactory.build(recurrence_id=recurrence.id)
    created_meeting = await repo.create(meeting_data)
    assert created_meeting is not None

    repo = MeetingRepository(db_session)
    result = await repo.get_by_id(created_meeting.id)

    assert result is not None
    assert result.recurrence.title == "Weekly Recurrence"
