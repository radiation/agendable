from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession

from agendable.db.models import (
    CalendarProvider,
    ExternalCalendarConnection,
    ExternalCalendarEventMirror,
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


class _Fake410ThenBootstrapClient:
    def __init__(self, batch: ExternalCalendarSyncBatch) -> None:
        self.batch = batch
        self.calls: list[str | None] = []

    async def list_events(
        self,
        *,
        auth: ExternalCalendarAuth,
        calendar_id: str,
        sync_token: str | None,
    ) -> ExternalCalendarSyncBatch:
        self.calls.append(sync_token)
        assert auth.access_token == "access-token"
        assert auth.refresh_token == "refresh-token"
        assert calendar_id == "primary"

        if sync_token is not None:
            request = httpx.Request("GET", "https://example.test")
            response = httpx.Response(410, request=request)
            raise httpx.HTTPStatusError("Gone", request=request, response=response)

        return self.batch

    async def get_recurring_event_details(
        self,
        *,
        auth: ExternalCalendarAuth,
        calendar_id: str,
        recurring_event_id: str,
    ) -> ExternalRecurringEventDetails | None:
        raise AssertionError("get_recurring_event_details should not be called in this test")

    async def upsert_recurring_event_backlink(
        self,
        *,
        auth: ExternalCalendarAuth,
        calendar_id: str,
        recurring_event_id: str,
        agendable_series_id: str,
        agendable_series_url: str | None,
    ) -> None:
        raise AssertionError("upsert_recurring_event_backlink should not be called in this test")

    async def upsert_event_backlink(
        self,
        *,
        auth: ExternalCalendarAuth,
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
        auth: ExternalCalendarAuth,
        calendar_id: str,
        sync_token: str | None,
    ) -> ExternalCalendarSyncBatch:
        assert auth.access_token == "new-access-token"
        assert auth.refresh_token == "refresh-token"
        assert calendar_id == "primary"
        assert sync_token is None
        return self.batch

    async def get_recurring_event_details(
        self,
        *,
        auth: ExternalCalendarAuth,
        calendar_id: str,
        recurring_event_id: str,
    ) -> ExternalRecurringEventDetails | None:
        raise AssertionError("get_recurring_event_details should not be called in this test")

    async def upsert_recurring_event_backlink(
        self,
        *,
        auth: ExternalCalendarAuth,
        calendar_id: str,
        recurring_event_id: str,
        agendable_series_id: str,
        agendable_series_url: str | None,
    ) -> None:
        raise AssertionError("upsert_recurring_event_backlink should not be called in this test")

    async def upsert_event_backlink(
        self,
        *,
        auth: ExternalCalendarAuth,
        calendar_id: str,
        event_id: str,
        agendable_occurrence_id: str,
        agendable_occurrence_url: str | None,
    ) -> None:
        raise AssertionError("upsert_event_backlink should not be called in this test")


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
