from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agendable.db.models import (
    CalendarProvider,
    ExternalCalendarConnection,
    ExternalCalendarEventMirror,
    MeetingOccurrence,
    MeetingSeries,
    Task,
    User,
)
from agendable.services.calendar_event_mapping_service import CalendarEventMappingService


@pytest.mark.asyncio
async def test_calendar_event_mapping_service_rolls_tasks_forward_on_cancelled_instance(
    db_session: AsyncSession,
) -> None:
    user = User(
        email=f"sync-cancelled-{uuid.uuid4()}@example.com",
        first_name="Sync",
        last_name="Cancelled",
        display_name="Sync Cancelled",
        timezone="UTC",
        password_hash=None,
    )
    db_session.add(user)
    await db_session.flush()

    connection = ExternalCalendarConnection(
        user_id=user.id,
        provider=CalendarProvider.google,
        external_calendar_id="primary",
        access_token="access-token",
        refresh_token="refresh-token",
    )
    db_session.add(connection)
    await db_session.flush()

    series = MeetingSeries(
        owner_user_id=user.id,
        title="Team Sync",
        default_interval_days=7,
        reminder_minutes_before=60,
    )
    db_session.add(series)
    await db_session.flush()

    occ1 = MeetingOccurrence(
        series_id=series.id,
        scheduled_at=datetime(2026, 3, 4, 18, 0, tzinfo=UTC),
        notes="",
        is_completed=False,
    )
    occ2 = MeetingOccurrence(
        series_id=series.id,
        scheduled_at=datetime(2026, 3, 11, 18, 0, tzinfo=UTC),
        notes="",
        is_completed=False,
    )
    db_session.add_all([occ1, occ2])
    await db_session.flush()

    task = Task(
        occurrence_id=occ1.id,
        assigned_user_id=user.id,
        title="Prep updates",
        description=None,
        due_at=occ1.scheduled_at,
        is_done=False,
    )
    db_session.add(task)
    await db_session.flush()

    mirror = ExternalCalendarEventMirror(
        connection_id=connection.id,
        external_event_id="evt-1",
        external_recurring_event_id="master-1",
        external_status="cancelled",
        etag="etag-1",
        summary="Team Sync",
        start_at=occ1.scheduled_at,
        end_at=occ1.scheduled_at,
        is_all_day=False,
        external_updated_at=datetime(2026, 3, 4, 17, 0, tzinfo=UTC),
        linked_occurrence_id=occ1.id,
    )
    db_session.add(mirror)
    await db_session.flush()

    mapped = await CalendarEventMappingService(session=db_session).map_mirrors(
        connection=connection,
        mirrors=[mirror],
        recurring_event_details_by_id=None,
    )
    assert mapped == 1

    refreshed_occ1 = await db_session.get(MeetingOccurrence, occ1.id)
    assert refreshed_occ1 is not None
    assert refreshed_occ1.is_completed is True

    refreshed_task = await db_session.get(Task, task.id)
    assert refreshed_task is not None
    assert refreshed_task.occurrence_id == occ2.id
    assert refreshed_task.due_at == occ2.scheduled_at


@pytest.mark.asyncio
async def test_calendar_event_mapping_service_creates_next_occurrence_on_cancelled_instance_when_missing(
    db_session: AsyncSession,
) -> None:
    user = User(
        email=f"sync-cancelled-create-next-{uuid.uuid4()}@example.com",
        first_name="Sync",
        last_name="Cancelled",
        display_name="Sync Cancelled",
        timezone="UTC",
        password_hash=None,
    )
    db_session.add(user)
    await db_session.flush()

    connection = ExternalCalendarConnection(
        user_id=user.id,
        provider=CalendarProvider.google,
        external_calendar_id="primary",
        access_token="access-token",
        refresh_token="refresh-token",
    )
    db_session.add(connection)
    await db_session.flush()

    occ1_at = datetime(2026, 3, 4, 18, 0, tzinfo=UTC)
    expected_occ2_at = datetime(2026, 3, 11, 18, 0, tzinfo=UTC)

    series = MeetingSeries(
        owner_user_id=user.id,
        title="Team Sync",
        default_interval_days=7,
        reminder_minutes_before=60,
        recurrence_rrule="FREQ=WEEKLY;INTERVAL=1;BYDAY=WE",
        recurrence_dtstart=occ1_at,
        recurrence_timezone="UTC",
    )
    db_session.add(series)
    await db_session.flush()

    occ1 = MeetingOccurrence(
        series_id=series.id,
        scheduled_at=occ1_at,
        notes="",
        is_completed=False,
    )
    db_session.add(occ1)
    await db_session.flush()

    task = Task(
        occurrence_id=occ1.id,
        assigned_user_id=user.id,
        title="Prep updates",
        description=None,
        due_at=occ1.scheduled_at,
        is_done=False,
    )
    db_session.add(task)
    await db_session.flush()

    mirror = ExternalCalendarEventMirror(
        connection_id=connection.id,
        external_event_id="evt-1",
        external_recurring_event_id="master-1",
        external_status="cancelled",
        etag="etag-1",
        summary="Team Sync",
        start_at=occ1.scheduled_at,
        end_at=occ1.scheduled_at,
        is_all_day=False,
        external_updated_at=datetime(2026, 3, 4, 17, 0, tzinfo=UTC),
        linked_occurrence_id=occ1.id,
    )
    db_session.add(mirror)
    await db_session.flush()

    mapped = await CalendarEventMappingService(session=db_session).map_mirrors(
        connection=connection,
        mirrors=[mirror],
        recurring_event_details_by_id=None,
    )
    assert mapped == 1

    occ2 = (
        (
            await db_session.execute(
                select(MeetingOccurrence).where(
                    MeetingOccurrence.series_id == series.id,
                    MeetingOccurrence.scheduled_at == expected_occ2_at,
                )
            )
        )
        .scalars()
        .one()
    )
    assert occ2.is_completed is False

    refreshed_task = await db_session.get(Task, task.id)
    assert refreshed_task is not None
    assert refreshed_task.occurrence_id == occ2.id
    assert refreshed_task.due_at == expected_occ2_at
