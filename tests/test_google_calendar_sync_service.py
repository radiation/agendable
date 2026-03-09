from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from pydantic import SecretStr
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
from agendable.settings import Settings


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

    async def upsert_event_backlink(
        self,
        *,
        access_token: str,
        refresh_token: str | None,
        calendar_id: str,
        event_id: str,
        agendable_occurrence_id: str,
        agendable_occurrence_url: str | None,
    ) -> None:
        raise AssertionError("upsert_event_backlink should not be called in this test")

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

    async def upsert_event_backlink(
        self,
        *,
        access_token: str,
        refresh_token: str | None,
        calendar_id: str,
        event_id: str,
        agendable_occurrence_id: str,
        agendable_occurrence_url: str | None,
    ) -> None:
        raise AssertionError("upsert_event_backlink should not be called in this test")


class _Fake410ThenBootstrapClient:
    def __init__(self, batch: ExternalCalendarSyncBatch) -> None:
        self.batch = batch
        self.calls: list[str | None] = []

    async def list_events(
        self,
        *,
        access_token: str,
        refresh_token: str | None,
        calendar_id: str,
        sync_token: str | None,
    ) -> ExternalCalendarSyncBatch:
        self.calls.append(sync_token)
        assert access_token == "access-token"
        assert refresh_token == "refresh-token"
        assert calendar_id == "primary"

        if sync_token is not None:
            request = httpx.Request("GET", "https://example.test")
            response = httpx.Response(410, request=request)
            raise httpx.HTTPStatusError("Gone", request=request, response=response)

        return self.batch

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

    async def upsert_event_backlink(
        self,
        *,
        access_token: str,
        refresh_token: str | None,
        calendar_id: str,
        event_id: str,
        agendable_occurrence_id: str,
        agendable_occurrence_url: str | None,
    ) -> None:
        raise AssertionError("upsert_event_backlink should not be called in this test")


class _FakeRefreshAwareClient:
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
        assert access_token == "new-access-token"
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

    async def upsert_event_backlink(
        self,
        *,
        access_token: str,
        refresh_token: str | None,
        calendar_id: str,
        event_id: str,
        agendable_occurrence_id: str,
        agendable_occurrence_url: str | None,
    ) -> None:
        raise AssertionError("upsert_event_backlink should not be called in this test")


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


@pytest.mark.asyncio
async def test_google_calendar_sync_service_refreshes_expired_access_token(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = User(
        email=f"sync-refresh-{uuid.uuid4()}@example.com",
        first_name="Sync",
        last_name="Refresh",
        display_name="Sync Refresh",
        timezone="UTC",
        password_hash=None,
    )
    db_session.add(user)
    await db_session.flush()

    connection = ExternalCalendarConnection(
        user_id=user.id,
        provider=CalendarProvider.google,
        external_calendar_id="primary",
        access_token="old-access-token",
        refresh_token="refresh-token",
        access_token_expires_at=datetime.now(UTC) - timedelta(seconds=10),
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

    class _FakeTokenResponse:
        status_code = 200

        def json(self) -> dict[str, object]:
            return {"access_token": "new-access-token", "expires_in": 3600}

    class _FakeAsyncClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        async def __aenter__(self) -> _FakeAsyncClient:
            return self

        async def __aexit__(
            self,
            exc_type: object,
            exc: object,
            tb: object,
        ) -> None:
            return None

        async def post(self, url: str, data: dict[str, str]) -> _FakeTokenResponse:
            assert "oauth2.googleapis.com" in url
            assert data["grant_type"] == "refresh_token"
            assert data["refresh_token"] == "refresh-token"
            return _FakeTokenResponse()

    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)

    service = GoogleCalendarSyncService(
        connection_repo=ExternalCalendarConnectionRepository(db_session),
        event_mirror_repo=ExternalCalendarEventMirrorRepository(db_session),
        calendar_client=_FakeRefreshAwareClient(batch),
        event_mapper=CalendarEventMappingService(session=db_session),
        settings=Settings(
            google_calendar_sync_enabled=True,
            oidc_client_id="client-id",
            oidc_client_secret=SecretStr("client-secret"),
            oidc_metadata_url="https://example.com/.well-known/openid-configuration",
        ),
    )

    synced_count = await service.sync_connection(connection)
    assert synced_count == 1

    refreshed = await db_session.get(ExternalCalendarConnection, connection.id)
    assert refreshed is not None
    assert refreshed.access_token == "new-access-token"
    assert refreshed.access_token_expires_at is not None


@pytest.mark.asyncio
async def test_google_calendar_sync_service_recovers_from_expired_sync_token_410(
    db_session: AsyncSession,
) -> None:
    user = User(
        email=f"sync-410-{uuid.uuid4()}@example.com",
        first_name="Sync",
        last_name="Gone",
        display_name="Sync Gone",
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
        sync_token="stale-sync-token",
    )
    db_session.add(connection)
    await db_session.flush()

    # Ensure the service will attempt an incremental sync using `sync_token`.
    # Without any mirrors, the sync service intentionally avoids using `sync_token`
    # to prevent missing data on a connection's first sync.
    db_session.add(
        ExternalCalendarEventMirror(
            connection_id=connection.id,
            external_event_id="existing-evt",
            is_all_day=False,
        )
    )

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
    batch = ExternalCalendarSyncBatch(events=[event], next_sync_token="new-sync-token")

    fake_client = _Fake410ThenBootstrapClient(batch)
    service = GoogleCalendarSyncService(
        connection_repo=ExternalCalendarConnectionRepository(db_session),
        event_mirror_repo=ExternalCalendarEventMirrorRepository(db_session),
        calendar_client=fake_client,
        event_mapper=CalendarEventMappingService(session=db_session),
    )

    synced_count = await service.sync_connection(connection)
    assert synced_count == 1
    assert fake_client.calls == ["stale-sync-token", None]

    refreshed_connection = await db_session.get(ExternalCalendarConnection, connection.id)
    assert refreshed_connection is not None
    assert refreshed_connection.sync_token == "new-sync-token"


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

    async def upsert_event_backlink(
        self,
        *,
        access_token: str,
        refresh_token: str | None,
        calendar_id: str,
        event_id: str,
        agendable_occurrence_id: str,
        agendable_occurrence_url: str | None,
    ) -> None:
        raise AssertionError("upsert_event_backlink should not be called in this test")


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
