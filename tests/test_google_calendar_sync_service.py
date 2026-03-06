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
    User,
)
from agendable.db.repos import (
    ExternalCalendarConnectionRepository,
    ExternalCalendarEventMirrorRepository,
)
from agendable.services.calendar_event_mapping_service import CalendarEventMappingService
from agendable.services.google_calendar_sync_service import (
    ExternalCalendarEvent,
    ExternalCalendarSyncBatch,
    ExternalRecurringEventDetails,
    GoogleCalendarSyncService,
)


class _FakeGoogleCalendarClient:
    def __init__(self, batch: ExternalCalendarSyncBatch) -> None:
        self.batch = batch

    async def get_recurring_event_details(
        self,
        *,
        access_token: str,
        refresh_token: str | None,
        calendar_id: str,
        recurring_event_id: str,
    ) -> ExternalRecurringEventDetails | None:
        raise AssertionError("get_recurring_event_details should not be called in this test")

    async def upsert_recurring_event_backlink(
        self,
        *,
        access_token: str,
        refresh_token: str | None,
        calendar_id: str,
        recurring_event_id: str,
        agendable_series_id: str,
        agendable_series_url: str | None,
    ) -> None:
        raise AssertionError("upsert_recurring_event_backlink should not be called in this test")

    async def list_events(
        self,
        *,
        access_token: str,
        refresh_token: str | None,
        calendar_id: str,
        sync_token: str | None,
    ) -> ExternalCalendarSyncBatch:
        assert access_token == "access-token"
        assert refresh_token == "refresh-token"
        assert calendar_id == "primary"
        assert sync_token is None
        return self.batch


class _FakeBootstrapRecoveryClient:
    def __init__(self) -> None:
        self.received_sync_tokens: list[str | None] = []

    async def list_events(
        self,
        *,
        access_token: str,
        refresh_token: str | None,
        calendar_id: str,
        sync_token: str | None,
    ) -> ExternalCalendarSyncBatch:
        self.received_sync_tokens.append(sync_token)
        return ExternalCalendarSyncBatch(events=[], next_sync_token="sync-token-after-recovery")

    async def get_recurring_event_details(
        self,
        *,
        access_token: str,
        refresh_token: str | None,
        calendar_id: str,
        recurring_event_id: str,
    ) -> ExternalRecurringEventDetails | None:
        raise AssertionError("get_recurring_event_details should not be called in this test")

    async def upsert_recurring_event_backlink(
        self,
        *,
        access_token: str,
        refresh_token: str | None,
        calendar_id: str,
        recurring_event_id: str,
        agendable_series_id: str,
        agendable_series_url: str | None,
    ) -> None:
        raise AssertionError("upsert_recurring_event_backlink should not be called in this test")


@pytest.mark.asyncio
async def test_google_calendar_sync_service_upserts_mirror_and_sync_token(
    db_session: AsyncSession,
) -> None:
    user = User(
        email=f"sync-{uuid.uuid4()}@example.com",
        first_name="Sync",
        last_name="User",
        display_name="Sync User",
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
    await db_session.commit()

    event = ExternalCalendarEvent(
        event_id="evt-1",
        recurring_event_id=None,
        status="confirmed",
        etag="etag-1",
        summary="1:1 Meeting",
        start_at=datetime(2026, 3, 4, 18, 0, tzinfo=UTC),
        end_at=datetime(2026, 3, 4, 18, 30, tzinfo=UTC),
        is_all_day=False,
        external_updated_at=datetime(2026, 3, 4, 17, 0, tzinfo=UTC),
    )
    batch = ExternalCalendarSyncBatch(events=[event], next_sync_token="sync-token-1")

    service = GoogleCalendarSyncService(
        connection_repo=ExternalCalendarConnectionRepository(db_session),
        event_mirror_repo=ExternalCalendarEventMirrorRepository(db_session),
        calendar_client=_FakeGoogleCalendarClient(batch),
        event_mapper=CalendarEventMappingService(session=db_session),
    )

    synced_count = await service.sync_connection(connection)
    assert synced_count == 1

    refreshed_connection = await db_session.get(ExternalCalendarConnection, connection.id)
    assert refreshed_connection is not None
    assert refreshed_connection.sync_token == "sync-token-1"
    assert refreshed_connection.last_synced_at is not None

    mirror = (
        await db_session.execute(
            select(ExternalCalendarEventMirror).where(
                ExternalCalendarEventMirror.connection_id == connection.id,
                ExternalCalendarEventMirror.external_event_id == "evt-1",
            )
        )
    ).scalar_one()
    assert mirror.summary == "1:1 Meeting"
    assert mirror.external_status == "confirmed"
    # One-off events are mirrored but not mapped into Agendable meetings.
    assert mirror.linked_occurrence_id is None
    series_count = (await db_session.execute(select(MeetingSeries))).scalars().all()
    assert series_count == []


class _FakeRecurringDetailsClient:
    def __init__(self, batch: ExternalCalendarSyncBatch) -> None:
        self.batch = batch

    async def list_events(
        self,
        *,
        access_token: str,
        refresh_token: str | None,
        calendar_id: str,
        sync_token: str | None,
    ) -> ExternalCalendarSyncBatch:
        assert access_token == "access-token"
        assert refresh_token == "refresh-token"
        assert calendar_id == "primary"
        assert sync_token is None
        return self.batch

    async def get_recurring_event_details(
        self,
        *,
        access_token: str,
        refresh_token: str | None,
        calendar_id: str,
        recurring_event_id: str,
    ) -> ExternalRecurringEventDetails | None:
        assert access_token == "access-token"
        assert refresh_token == "refresh-token"
        assert calendar_id == "primary"
        assert recurring_event_id == "master-1"
        # Weekly on Wed, starting at 18:00 UTC.
        return ExternalRecurringEventDetails(
            event_id="master-1",
            recurrence_rrule="FREQ=WEEKLY;INTERVAL=1;BYDAY=WE",
            recurrence_dtstart=datetime(2026, 3, 4, 18, 0, tzinfo=UTC),
            recurrence_timezone="UTC",
        )

    async def upsert_recurring_event_backlink(
        self,
        *,
        access_token: str,
        refresh_token: str | None,
        calendar_id: str,
        recurring_event_id: str,
        agendable_series_id: str,
        agendable_series_url: str | None,
    ) -> None:
        raise AssertionError("upsert_recurring_event_backlink should not be called in this test")


@pytest.mark.asyncio
async def test_google_calendar_sync_service_maps_recurring_instances_with_rrule(
    db_session: AsyncSession,
) -> None:
    user = User(
        email=f"sync-recurring-{uuid.uuid4()}@example.com",
        first_name="Sync",
        last_name="Recurring",
        display_name="Sync Recurring",
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
    await db_session.commit()

    evt1 = ExternalCalendarEvent(
        event_id="evt-1",
        recurring_event_id="master-1",
        status="confirmed",
        etag="etag-1",
        summary="Team Sync",
        start_at=datetime(2026, 3, 4, 18, 0, tzinfo=UTC),
        end_at=datetime(2026, 3, 4, 18, 30, tzinfo=UTC),
        is_all_day=False,
        external_updated_at=datetime(2026, 3, 4, 17, 0, tzinfo=UTC),
    )
    evt2 = ExternalCalendarEvent(
        event_id="evt-2",
        recurring_event_id="master-1",
        status="confirmed",
        etag="etag-2",
        summary="Team Sync",
        start_at=datetime(2026, 3, 11, 18, 0, tzinfo=UTC),
        end_at=datetime(2026, 3, 11, 18, 30, tzinfo=UTC),
        is_all_day=False,
        external_updated_at=datetime(2026, 3, 11, 17, 0, tzinfo=UTC),
    )
    batch = ExternalCalendarSyncBatch(events=[evt1, evt2], next_sync_token="sync-token-1")

    service = GoogleCalendarSyncService(
        connection_repo=ExternalCalendarConnectionRepository(db_session),
        event_mirror_repo=ExternalCalendarEventMirrorRepository(db_session),
        calendar_client=_FakeRecurringDetailsClient(batch),
        event_mapper=CalendarEventMappingService(session=db_session),
    )

    synced_count = await service.sync_connection(connection)
    assert synced_count == 2

    mirrors = (
        (
            await db_session.execute(
                select(ExternalCalendarEventMirror).where(
                    ExternalCalendarEventMirror.connection_id == connection.id
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(mirrors) == 2
    assert all(m.linked_occurrence_id is not None for m in mirrors)

    occurrences = (await db_session.execute(select(MeetingOccurrence))).scalars().all()
    assert len(occurrences) == 2
    series_ids = {occ.series_id for occ in occurrences}
    assert len(series_ids) == 1

    series = await db_session.get(MeetingSeries, next(iter(series_ids)))
    assert series is not None
    assert series.title == "Team Sync"
    assert series.recurrence_rrule == "FREQ=WEEKLY;INTERVAL=1;BYDAY=WE"
    assert series.recurrence_timezone == "UTC"


@pytest.mark.asyncio
async def test_google_calendar_sync_service_ignores_stale_bootstrap_sync_token_when_no_mirrors(
    db_session: AsyncSession,
) -> None:
    user = User(
        email=f"sync-bootstrap-{uuid.uuid4()}@example.com",
        first_name="Sync",
        last_name="Bootstrap",
        display_name="Sync Bootstrap",
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
        sync_token="stale-bootstrap-token",
    )
    db_session.add(connection)
    await db_session.commit()

    fake_client = _FakeBootstrapRecoveryClient()
    service = GoogleCalendarSyncService(
        connection_repo=ExternalCalendarConnectionRepository(db_session),
        event_mirror_repo=ExternalCalendarEventMirrorRepository(db_session),
        calendar_client=fake_client,
    )

    synced_count = await service.sync_connection(connection)
    assert synced_count == 0
    assert fake_client.received_sync_tokens == [None]

    refreshed_connection = await db_session.get(ExternalCalendarConnection, connection.id)
    assert refreshed_connection is not None
    assert refreshed_connection.sync_token == "sync-token-after-recovery"
