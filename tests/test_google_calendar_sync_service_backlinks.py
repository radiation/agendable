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
    MeetingSeries,
    User,
)
from agendable.db.repos import (
    ExternalCalendarConnectionRepository,
    ExternalCalendarEventMirrorRepository,
)
from agendable.services.calendar_event_mapping_service import CalendarEventMappingService
from agendable.services.external_calendar_api import ExternalCalendarAuth
from agendable.services.google_calendar_sync_service import (
    ExternalCalendarEvent,
    ExternalCalendarSyncBatch,
    ExternalRecurringEventDetails,
    GoogleCalendarSyncService,
)
from agendable.settings import Settings


class _RecordingClient:
    def __init__(self, batch: ExternalCalendarSyncBatch) -> None:
        self.batch = batch
        self.series_calls: list[tuple[str, str]] = []
        self.occ_calls: list[tuple[str, str]] = []

    async def list_events(
        self,
        *,
        auth: ExternalCalendarAuth,
        calendar_id: str,
        sync_token: str | None,
    ) -> ExternalCalendarSyncBatch:
        del auth
        del calendar_id
        del sync_token
        return self.batch

    async def get_recurring_event_details(
        self,
        *,
        auth: ExternalCalendarAuth,
        calendar_id: str,
        recurring_event_id: str,
    ) -> ExternalRecurringEventDetails | None:
        del auth
        del calendar_id
        return ExternalRecurringEventDetails(
            event_id=recurring_event_id,
            recurrence_rrule="FREQ=WEEKLY;INTERVAL=1;BYDAY=WE",
            recurrence_dtstart=datetime(2026, 3, 4, 18, 0, tzinfo=UTC),
            recurrence_timezone="UTC",
        )

    async def upsert_recurring_event_backlink(
        self,
        *,
        auth: ExternalCalendarAuth,
        calendar_id: str,
        recurring_event_id: str,
        agendable_series_id: str,
        agendable_series_url: str | None,
    ) -> None:
        del auth
        del calendar_id
        del agendable_series_id
        assert agendable_series_url is not None
        self.series_calls.append((recurring_event_id, agendable_series_url))

    async def upsert_event_backlink(
        self,
        *,
        auth: ExternalCalendarAuth,
        calendar_id: str,
        event_id: str,
        agendable_occurrence_id: str,
        agendable_occurrence_url: str | None,
    ) -> None:
        del auth
        del calendar_id
        del agendable_occurrence_id
        assert agendable_occurrence_url is not None
        self.occ_calls.append((event_id, agendable_occurrence_url))


async def _make_user_and_connection(
    session: AsyncSession, *, scope: str | None
) -> ExternalCalendarConnection:
    user = User(
        email=f"sync-backlinks-{uuid.uuid4()}@example.com",
        first_name="Sync",
        last_name="Backlinks",
        display_name="Sync Backlinks",
        timezone="UTC",
        password_hash=None,
    )
    session.add(user)
    await session.flush()

    connection = ExternalCalendarConnection(
        user_id=user.id,
        provider=CalendarProvider.google,
        external_calendar_id="primary",
        access_token="access-token",
        refresh_token="refresh-token",
        scope=scope,
    )
    session.add(connection)
    await session.commit()
    return connection


@pytest.mark.asyncio
async def test_sync_service_writes_back_occurrence_links_when_enabled(
    db_session: AsyncSession,
) -> None:
    connection = await _make_user_and_connection(
        db_session,
        scope="https://www.googleapis.com/auth/calendar.events",
    )

    evt = ExternalCalendarEvent(
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
    client = _RecordingClient(ExternalCalendarSyncBatch(events=[evt], next_sync_token=None))
    settings = Settings(
        public_base_url="https://app.example",
        google_calendar_backlink_enabled=True,
        google_calendar_backlink_target="occurrence",
    )

    service = GoogleCalendarSyncService(
        connection_repo=ExternalCalendarConnectionRepository(db_session),
        event_mirror_repo=ExternalCalendarEventMirrorRepository(db_session),
        calendar_client=client,
        event_mapper=CalendarEventMappingService(session=db_session),
        settings=settings,
    )
    await service.sync_connection(connection)

    mirror = (
        (
            await db_session.execute(
                select(ExternalCalendarEventMirror).where(
                    ExternalCalendarEventMirror.connection_id == connection.id,
                    ExternalCalendarEventMirror.external_event_id == "evt-1",
                )
            )
        )
        .scalars()
        .one()
    )
    assert mirror.linked_occurrence_id is not None
    assert client.occ_calls == [
        ("evt-1", f"https://app.example/occurrences/{mirror.linked_occurrence_id}")
    ]


@pytest.mark.asyncio
async def test_sync_service_writes_back_series_links_when_enabled(
    db_session: AsyncSession,
) -> None:
    connection = await _make_user_and_connection(
        db_session,
        scope="https://www.googleapis.com/auth/calendar.events",
    )

    evt = ExternalCalendarEvent(
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
    client = _RecordingClient(ExternalCalendarSyncBatch(events=[evt], next_sync_token=None))
    settings = Settings(
        public_base_url="https://app.example",
        google_calendar_backlink_enabled=True,
        google_calendar_backlink_target="series",
    )

    service = GoogleCalendarSyncService(
        connection_repo=ExternalCalendarConnectionRepository(db_session),
        event_mirror_repo=ExternalCalendarEventMirrorRepository(db_session),
        calendar_client=client,
        event_mapper=CalendarEventMappingService(session=db_session),
        settings=settings,
    )
    await service.sync_connection(connection)

    series = (await db_session.execute(select(MeetingSeries))).scalars().one()
    assert client.series_calls == [("master-1", f"https://app.example/series/{series.id}")]


@pytest.mark.asyncio
async def test_sync_service_does_not_write_back_without_write_scope(
    db_session: AsyncSession,
) -> None:
    connection = await _make_user_and_connection(db_session, scope=None)
    evt = ExternalCalendarEvent(
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

    client = _RecordingClient(ExternalCalendarSyncBatch(events=[evt], next_sync_token=None))
    settings = Settings(
        public_base_url="https://app.example",
        google_calendar_backlink_enabled=True,
        google_calendar_backlink_target="both",
    )

    service = GoogleCalendarSyncService(
        connection_repo=ExternalCalendarConnectionRepository(db_session),
        event_mirror_repo=ExternalCalendarEventMirrorRepository(db_session),
        calendar_client=client,
        event_mapper=CalendarEventMappingService(session=db_session),
        settings=settings,
    )
    await service.sync_connection(connection)

    assert client.series_calls == []
    assert client.occ_calls == []


@pytest.mark.asyncio
async def test_sync_service_does_not_write_back_when_backlink_feature_disabled(
    db_session: AsyncSession,
) -> None:
    connection = await _make_user_and_connection(
        db_session,
        scope="https://www.googleapis.com/auth/calendar.events",
    )
    evt = ExternalCalendarEvent(
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

    client = _RecordingClient(ExternalCalendarSyncBatch(events=[evt], next_sync_token=None))
    settings = Settings(
        public_base_url="https://app.example",
        google_calendar_backlink_enabled=False,
        google_calendar_backlink_target="both",
    )

    service = GoogleCalendarSyncService(
        connection_repo=ExternalCalendarConnectionRepository(db_session),
        event_mirror_repo=ExternalCalendarEventMirrorRepository(db_session),
        calendar_client=client,
        event_mapper=CalendarEventMappingService(session=db_session),
        settings=settings,
    )
    await service.sync_connection(connection)
    assert client.series_calls == []
    assert client.occ_calls == []


@pytest.mark.asyncio
async def test_sync_service_skips_occurrence_write_back_for_cancelled_instances(
    db_session: AsyncSession,
) -> None:
    connection = await _make_user_and_connection(
        db_session,
        scope="https://www.googleapis.com/auth/calendar.events",
    )
    evt = ExternalCalendarEvent(
        event_id="evt-1",
        recurring_event_id="master-1",
        status="cancelled",
        etag="etag-1",
        summary="Team Sync",
        start_at=datetime(2026, 3, 4, 18, 0, tzinfo=UTC),
        end_at=datetime(2026, 3, 4, 18, 30, tzinfo=UTC),
        is_all_day=False,
        external_updated_at=datetime(2026, 3, 4, 17, 0, tzinfo=UTC),
    )

    client = _RecordingClient(ExternalCalendarSyncBatch(events=[evt], next_sync_token=None))
    settings = Settings(
        public_base_url="https://app.example",
        google_calendar_backlink_enabled=True,
        google_calendar_backlink_target="occurrence",
    )

    service = GoogleCalendarSyncService(
        connection_repo=ExternalCalendarConnectionRepository(db_session),
        event_mirror_repo=ExternalCalendarEventMirrorRepository(db_session),
        calendar_client=client,
        event_mapper=CalendarEventMappingService(session=db_session),
        settings=settings,
    )
    await service.sync_connection(connection)
    assert client.occ_calls == []
