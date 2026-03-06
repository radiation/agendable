from __future__ import annotations

from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agendable.db.models import (
    CalendarProvider,
    ExternalCalendarConnection,
    ExternalCalendarEventMirror,
)
from agendable.services.google_calendar_sync_service import (
    ExternalCalendarEvent,
    ExternalCalendarSyncBatch,
    ExternalRecurringEventDetails,
)
from agendable.web.routes.auth import oidc as oidc_routes
from tests.auth.account_linking_test_helpers import get_user_by_email, signup_and_login


class _FakeGoogleCalendarClient:
    async def list_events(
        self,
        *,
        access_token: str,
        refresh_token: str | None,
        calendar_id: str,
        sync_token: str | None,
    ) -> ExternalCalendarSyncBatch:
        assert access_token == "google-access-token"
        assert refresh_token == "google-refresh-token"
        assert calendar_id == "primary"
        assert sync_token is None
        return ExternalCalendarSyncBatch(
            events=[
                ExternalCalendarEvent(
                    event_id="evt-manual-sync",
                    recurring_event_id=None,
                    status="confirmed",
                    etag='"etag-manual-sync"',
                    summary="Manual Sync Meeting",
                    start_at=datetime(2026, 3, 10, 15, 0, tzinfo=UTC),
                    end_at=datetime(2026, 3, 10, 15, 30, tzinfo=UTC),
                    is_all_day=False,
                    external_updated_at=datetime(2026, 3, 9, 12, 0, tzinfo=UTC),
                )
            ],
            next_sync_token="sync-token-manual",
        )

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
async def test_google_calendar_sync_route_disabled_returns_404(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENDABLE_GOOGLE_CALENDAR_SYNC_ENABLED", "false")

    await signup_and_login(
        client,
        first_name="Google",
        last_name="Disabled",
        email="google-sync-disabled@example.com",
    )

    response = await client.post("/profile/calendar/google/sync", follow_redirects=False)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_google_calendar_sync_route_requires_connection(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENDABLE_GOOGLE_CALENDAR_SYNC_ENABLED", "true")

    await signup_and_login(
        client,
        first_name="Google",
        last_name="NoConnection",
        email="google-sync-no-connection@example.com",
    )

    response = await client.post("/profile/calendar/google/sync", follow_redirects=False)
    assert response.status_code == 400
    assert "No Google Calendar connection found yet." in response.text


@pytest.mark.asyncio
async def test_google_calendar_sync_route_syncs_primary_connection(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENDABLE_GOOGLE_CALENDAR_SYNC_ENABLED", "true")
    monkeypatch.setattr(
        oidc_routes, "build_google_calendar_client", lambda: _FakeGoogleCalendarClient()
    )

    await signup_and_login(
        client,
        first_name="Google",
        last_name="Sync",
        email="google-sync-success@example.com",
    )
    user = await get_user_by_email(db_session, "google-sync-success@example.com")

    db_session.add(
        ExternalCalendarConnection(
            user_id=user.id,
            provider=CalendarProvider.google,
            external_calendar_id="primary",
            access_token="google-access-token",
            refresh_token="google-refresh-token",
            scope="openid email profile https://www.googleapis.com/auth/calendar.readonly",
            is_enabled=True,
        )
    )
    await db_session.commit()

    response = await client.post("/profile/calendar/google/sync", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/profile"

    connection = (
        await db_session.execute(
            select(ExternalCalendarConnection).where(
                ExternalCalendarConnection.user_id == user.id,
                ExternalCalendarConnection.external_calendar_id == "primary",
            )
        )
    ).scalar_one()
    assert connection.sync_token == "sync-token-manual"
    assert connection.last_synced_at is not None

    mirror = (
        await db_session.execute(
            select(ExternalCalendarEventMirror).where(
                ExternalCalendarEventMirror.connection_id == connection.id,
                ExternalCalendarEventMirror.external_event_id == "evt-manual-sync",
            )
        )
    ).scalar_one()
    assert mirror.summary == "Manual Sync Meeting"
