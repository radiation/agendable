from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import select

from agendable.db.models import (
    CalendarProvider,
    ExternalCalendarConnection,
    ExternalCalendarEventMirror,
    MeetingOccurrence,
    MeetingSeries,
)
from agendable.db.repos import (
    ExternalCalendarConnectionRepository,
    ExternalCalendarEventMirrorRepository,
)
from agendable.settings import Settings


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
class ExternalRecurringEventDetails:
    """Details for a recurring *master* event.

    For Google Calendar, `event_id` here is the recurring master event id
    referenced by instances via `recurringEventId`.
    """

    event_id: str
    recurrence_rrule: str | None
    recurrence_dtstart: datetime | None
    recurrence_timezone: str | None


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

    async def get_recurring_event_details(
        self,
        *,
        access_token: str,
        refresh_token: str | None,
        calendar_id: str,
        recurring_event_id: str,
    ) -> ExternalRecurringEventDetails | None: ...

    async def upsert_recurring_event_backlink(
        self,
        *,
        access_token: str,
        refresh_token: str | None,
        calendar_id: str,
        recurring_event_id: str,
        agendable_series_id: str,
        agendable_series_url: str | None,
    ) -> None: ...


class CalendarEventMapper(Protocol):
    async def map_mirrors(
        self,
        *,
        connection: ExternalCalendarConnection,
        mirrors: list[ExternalCalendarEventMirror],
        recurring_event_details_by_id: dict[str, ExternalRecurringEventDetails],
    ) -> int: ...


class GoogleCalendarSyncService:
    def __init__(
        self,
        *,
        connection_repo: ExternalCalendarConnectionRepository,
        event_mirror_repo: ExternalCalendarEventMirrorRepository,
        calendar_client: GoogleCalendarClient,
        event_mapper: CalendarEventMapper | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.connection_repo = connection_repo
        self.event_mirror_repo = event_mirror_repo
        self.calendar_client = calendar_client
        self.event_mapper = event_mapper
        self.settings = settings

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
            recurring_ids = {
                m.external_recurring_event_id
                for m in touched_mirrors
                if m.external_recurring_event_id is not None
            }

            recurring_event_details_by_id: dict[str, ExternalRecurringEventDetails] = {}
            for recurring_event_id in recurring_ids:
                details = await self.calendar_client.get_recurring_event_details(
                    access_token=connection.access_token,
                    refresh_token=connection.refresh_token,
                    calendar_id=connection.external_calendar_id,
                    recurring_event_id=recurring_event_id,
                )
                if details is not None:
                    recurring_event_details_by_id[recurring_event_id] = details

            await self.event_mapper.map_mirrors(
                connection=connection,
                mirrors=touched_mirrors,
                recurring_event_details_by_id=recurring_event_details_by_id,
            )

            await self._maybe_write_back_recurring_backlinks(
                connection=connection,
                recurring_event_ids=sorted(recurring_ids),
            )

        connection.sync_token = batch.next_sync_token
        connection.last_synced_at = datetime.now(UTC)
        connection.last_sync_error_code = None
        connection.last_sync_error_at = None
        await self.connection_repo.commit()

        return len(batch.events)

    async def _maybe_write_back_recurring_backlinks(
        self,
        *,
        connection: ExternalCalendarConnection,
        recurring_event_ids: list[str],
    ) -> None:
        if not recurring_event_ids:
            return

        settings = self.settings
        if settings is None or not settings.google_calendar_backlink_enabled:
            return

        if not connection.access_token:
            return

        # Requires a write scope; default is readonly.
        scopes = set((connection.scope or "").split())
        has_write_scope = any(
            s in scopes
            for s in {
                "https://www.googleapis.com/auth/calendar",
                "https://www.googleapis.com/auth/calendar.events",
                "https://www.googleapis.com/auth/calendar.events.owned",
            }
        )
        if not has_write_scope:
            return

        base_url = (settings.public_base_url or "").strip().rstrip("/")
        if not base_url:
            # Without a public base URL we can still store the private key,
            # but avoid partially implementing the requested "link" behavior.
            return

        for recurring_event_id in recurring_event_ids:
            series = await self._find_series_for_recurring_event(
                connection_id=connection.id,
                recurring_event_id=recurring_event_id,
            )
            if series is None:
                continue

            series_url = f"{base_url}/series/{series.id}"
            await self.calendar_client.upsert_recurring_event_backlink(
                access_token=connection.access_token,
                refresh_token=connection.refresh_token,
                calendar_id=connection.external_calendar_id,
                recurring_event_id=recurring_event_id,
                agendable_series_id=str(series.id),
                agendable_series_url=series_url,
            )

    async def _find_series_for_recurring_event(
        self,
        *,
        connection_id: object,
        recurring_event_id: str,
    ) -> MeetingSeries | None:
        session = self.event_mirror_repo.session
        result = await session.execute(
            select(MeetingSeries)
            .join(MeetingOccurrence, MeetingOccurrence.series_id == MeetingSeries.id)
            .join(
                ExternalCalendarEventMirror,
                ExternalCalendarEventMirror.linked_occurrence_id == MeetingOccurrence.id,
            )
            .where(
                ExternalCalendarEventMirror.connection_id == connection_id,
                ExternalCalendarEventMirror.external_recurring_event_id == recurring_event_id,
            )
            .order_by(MeetingSeries.created_at.asc())
            .limit(1)
        )
        return result.scalar_one_or_none()

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
