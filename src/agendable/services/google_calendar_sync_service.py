from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from agendable.db.models import (
    CalendarProvider,
    ExternalCalendarConnection,
    ExternalCalendarEventMirror,
)
from agendable.db.repos import (
    ExternalCalendarConnectionRepository,
    ExternalCalendarEventMirrorRepository,
)


@dataclass(frozen=True)
class ExternalCalendarEvent:
    event_id: str
    recurring_event_id: str | None
    status: str | None
    etag: str | None
    summary: str | None
    start_at: datetime | None
    end_at: datetime | None
    is_all_day: bool
    external_updated_at: datetime | None


@dataclass(frozen=True)
class ExternalCalendarSyncBatch:
    events: Sequence[ExternalCalendarEvent]
    next_sync_token: str | None


class GoogleCalendarClient(Protocol):
    async def list_events(
        self,
        *,
        access_token: str,
        refresh_token: str | None,
        calendar_id: str,
        sync_token: str | None,
    ) -> ExternalCalendarSyncBatch: ...


class CalendarEventMapper(Protocol):
    async def map_mirrors(
        self,
        *,
        connection: ExternalCalendarConnection,
        mirrors: list[ExternalCalendarEventMirror],
    ) -> int: ...


class GoogleCalendarSyncService:
    def __init__(
        self,
        *,
        connection_repo: ExternalCalendarConnectionRepository,
        event_mirror_repo: ExternalCalendarEventMirrorRepository,
        calendar_client: GoogleCalendarClient,
        event_mapper: CalendarEventMapper | None = None,
    ) -> None:
        self.connection_repo = connection_repo
        self.event_mirror_repo = event_mirror_repo
        self.calendar_client = calendar_client
        self.event_mapper = event_mapper

    async def sync_connection(self, connection: ExternalCalendarConnection) -> int:
        if not connection.access_token:
            raise ValueError("Calendar connection is missing an access token")

        sync_token_for_request = connection.sync_token
        if sync_token_for_request is not None:
            has_mirrored_events = await self.event_mirror_repo.has_any_for_connection(connection.id)
            if not has_mirrored_events:
                sync_token_for_request = None

        batch = await self.calendar_client.list_events(
            access_token=connection.access_token,
            refresh_token=connection.refresh_token,
            calendar_id=connection.external_calendar_id,
            sync_token=sync_token_for_request,
        )

        touched_mirrors: list[ExternalCalendarEventMirror] = []
        for event in batch.events:
            touched_mirrors.append(
                await self._upsert_mirror_event(connection=connection, event=event)
            )

        if self.event_mapper is not None and touched_mirrors:
            await self.event_mapper.map_mirrors(connection=connection, mirrors=touched_mirrors)

        connection.sync_token = batch.next_sync_token
        connection.last_synced_at = datetime.now(UTC)
        connection.last_sync_error_code = None
        connection.last_sync_error_at = None
        await self.connection_repo.commit()

        return len(batch.events)

    async def sync_all_enabled_connections(self) -> int:
        synced_event_count = 0
        connections = await self.connection_repo.list_enabled_for_provider(
            provider=CalendarProvider.google,
        )
        for connection in connections:
            synced_event_count += await self.sync_connection(connection)
        return synced_event_count

    async def _upsert_mirror_event(
        self,
        *,
        connection: ExternalCalendarConnection,
        event: ExternalCalendarEvent,
    ) -> ExternalCalendarEventMirror:
        existing = await self.event_mirror_repo.get_for_connection_event(
            connection_id=connection.id,
            external_event_id=event.event_id,
        )
        if existing is None:
            existing = ExternalCalendarEventMirror(
                connection_id=connection.id,
                external_event_id=event.event_id,
            )
            await self.event_mirror_repo.add(existing)

        existing.external_recurring_event_id = event.recurring_event_id
        existing.external_status = event.status
        existing.etag = event.etag
        existing.summary = event.summary
        existing.start_at = event.start_at
        existing.end_at = event.end_at
        existing.is_all_day = event.is_all_day
        existing.external_updated_at = event.external_updated_at
        existing.last_seen_at = datetime.now(UTC)
        await self.event_mirror_repo.session.flush()
        return existing
