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
    ImportedSeriesDecision,
    MeetingOccurrence,
    MeetingSeries,
)
from agendable.services.external_calendar_api import ExternalCalendarAuth
from agendable.services.google_calendar_sync_service import (
    ExternalCalendarEvent,
    ExternalCalendarSyncBatch,
    ExternalRecurringEventDetails,
)
from agendable.web.routes.auth import seams as auth_seams
from tests.auth.account_linking_test_helpers import get_user_by_email, signup_and_login


class _FakeGoogleCalendarClient:
    async def list_events(
        self,
        *,
        auth: ExternalCalendarAuth,
        calendar_id: str,
        sync_token: str | None,
    ) -> ExternalCalendarSyncBatch:
        assert auth.access_token == "google-access-token"
        assert auth.refresh_token == "google-refresh-token"
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
        auth_seams, "build_google_calendar_client", lambda: _FakeGoogleCalendarClient()
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


@pytest.mark.asyncio
async def test_keep_imported_series_marks_kept_and_maps_occurrence(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENDABLE_GOOGLE_CALENDAR_SYNC_ENABLED", "true")

    await signup_and_login(
        client,
        first_name="Google",
        last_name="KeepImported",
        email="google-keep-imported@example.com",
    )
    user = await get_user_by_email(db_session, "google-keep-imported@example.com")

    connection = ExternalCalendarConnection(
        user_id=user.id,
        provider=CalendarProvider.google,
        external_calendar_id="primary",
        access_token="google-access-token",
        refresh_token="google-refresh-token",
        is_enabled=True,
    )
    db_session.add(connection)
    await db_session.flush()

    series = MeetingSeries(
        owner_user_id=user.id,
        title="Imported Pending",
        default_interval_days=7,
        imported_from_provider=CalendarProvider.google,
        import_external_series_id="master-keep-route",
        import_decision=ImportedSeriesDecision.pending,
    )
    db_session.add(series)
    await db_session.flush()

    db_session.add(
        ExternalCalendarEventMirror(
            connection_id=connection.id,
            linked_occurrence_id=None,
            external_event_id="evt-keep-route",
            external_recurring_event_id="master-keep-route",
            external_status="confirmed",
            summary="Imported Pending",
            start_at=datetime(2026, 6, 10, 15, 0, tzinfo=UTC),
            end_at=datetime(2026, 6, 10, 15, 30, tzinfo=UTC),
            is_all_day=False,
        )
    )
    await db_session.commit()

    response = await client.post(
        f"/profile/calendar/google/import-series/{series.id}/keep",
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/profile"

    await db_session.refresh(series)
    assert series.import_decision == ImportedSeriesDecision.kept

    occurrences = (
        (
            await db_session.execute(
                select(MeetingOccurrence).where(MeetingOccurrence.series_id == series.id)
            )
        )
        .scalars()
        .all()
    )
    assert len(occurrences) == 1


@pytest.mark.asyncio
async def test_keep_imported_series_requires_connection_renders_profile_error(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENDABLE_GOOGLE_CALENDAR_SYNC_ENABLED", "true")

    await signup_and_login(
        client,
        first_name="Google",
        last_name="KeepNoConnection",
        email="google-keep-no-connection@example.com",
    )
    user = await get_user_by_email(db_session, "google-keep-no-connection@example.com")

    series = MeetingSeries(
        owner_user_id=user.id,
        title="Imported Pending",
        default_interval_days=7,
        imported_from_provider=CalendarProvider.google,
        import_external_series_id="master-keep-no-connection",
        import_decision=ImportedSeriesDecision.pending,
    )
    db_session.add(series)
    await db_session.commit()

    response = await client.post(
        f"/profile/calendar/google/import-series/{series.id}/keep",
        follow_redirects=False,
    )
    assert response.status_code == 400
    assert "No Google Calendar connection found yet." in response.text

    await db_session.refresh(series)
    assert series.import_decision == ImportedSeriesDecision.pending


@pytest.mark.asyncio
async def test_reject_imported_series_marks_rejected_and_clears_occurrences(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENDABLE_GOOGLE_CALENDAR_SYNC_ENABLED", "true")

    await signup_and_login(
        client,
        first_name="Google",
        last_name="RejectImported",
        email="google-reject-imported@example.com",
    )
    user = await get_user_by_email(db_session, "google-reject-imported@example.com")

    connection = ExternalCalendarConnection(
        user_id=user.id,
        provider=CalendarProvider.google,
        external_calendar_id="primary",
        access_token="google-access-token",
        refresh_token="google-refresh-token",
        is_enabled=True,
    )
    db_session.add(connection)
    await db_session.flush()

    series = MeetingSeries(
        owner_user_id=user.id,
        title="Imported Reject",
        default_interval_days=7,
        imported_from_provider=CalendarProvider.google,
        import_external_series_id="master-reject-route",
        import_decision=ImportedSeriesDecision.pending,
    )
    db_session.add(series)
    await db_session.flush()

    occurrence = MeetingOccurrence(
        series_id=series.id,
        scheduled_at=datetime(2026, 6, 11, 15, 0, tzinfo=UTC),
        notes="",
    )
    db_session.add(occurrence)
    await db_session.flush()

    mirror = ExternalCalendarEventMirror(
        connection_id=connection.id,
        linked_occurrence_id=occurrence.id,
        external_event_id="evt-reject-route",
        external_recurring_event_id="master-reject-route",
        external_status="confirmed",
        summary="Imported Reject",
        start_at=occurrence.scheduled_at,
        end_at=occurrence.scheduled_at,
        is_all_day=False,
    )
    db_session.add(mirror)
    await db_session.commit()

    response = await client.post(
        f"/profile/calendar/google/import-series/{series.id}/reject",
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/profile"

    await db_session.refresh(series)
    assert series.import_decision == ImportedSeriesDecision.rejected

    remaining_occurrences = (
        (
            await db_session.execute(
                select(MeetingOccurrence).where(MeetingOccurrence.series_id == series.id)
            )
        )
        .scalars()
        .all()
    )
    assert remaining_occurrences == []

    await db_session.refresh(mirror)
    assert mirror.linked_occurrence_id is None


@pytest.mark.asyncio
async def test_reject_imported_series_kept_state_returns_404(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENDABLE_GOOGLE_CALENDAR_SYNC_ENABLED", "true")

    await signup_and_login(
        client,
        first_name="Google",
        last_name="RejectKept",
        email="google-reject-kept@example.com",
    )
    user = await get_user_by_email(db_session, "google-reject-kept@example.com")

    series = MeetingSeries(
        owner_user_id=user.id,
        title="Imported Kept",
        default_interval_days=7,
        imported_from_provider=CalendarProvider.google,
        import_external_series_id="master-reject-kept",
        import_decision=ImportedSeriesDecision.kept,
    )
    db_session.add(series)
    await db_session.commit()

    response = await client.post(
        f"/profile/calendar/google/import-series/{series.id}/reject",
        follow_redirects=False,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["keep", "reject"])
async def test_import_review_routes_disabled_return_404(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    action: str,
) -> None:
    monkeypatch.setenv("AGENDABLE_GOOGLE_CALENDAR_SYNC_ENABLED", "false")

    await signup_and_login(
        client,
        first_name="Google",
        last_name="FeatureDisabled",
        email=f"google-feature-disabled-{action}@example.com",
    )
    user = await get_user_by_email(db_session, f"google-feature-disabled-{action}@example.com")

    series = MeetingSeries(
        owner_user_id=user.id,
        title="Imported Pending",
        default_interval_days=7,
        imported_from_provider=CalendarProvider.google,
        import_external_series_id=f"master-feature-disabled-{action}",
        import_decision=ImportedSeriesDecision.pending,
    )
    db_session.add(series)
    await db_session.commit()

    response = await client.post(
        f"/profile/calendar/google/import-series/{series.id}/{action}",
        follow_redirects=False,
    )
    assert response.status_code == 404
