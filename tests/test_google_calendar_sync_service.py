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
    User,
)
from agendable.db.repos import (
    ExternalCalendarConnectionRepository,
    ExternalCalendarEventMirrorRepository,
)
from agendable.services.google_calendar_sync_service import (
    ExternalCalendarEvent,
    ExternalCalendarSyncBatch,
    GoogleCalendarSyncService,
)


class _FakeGoogleCalendarClient:
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
