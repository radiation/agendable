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

_GOOGLE_CALENDAR_WRITE_SCOPES = frozenset(
    {
        "https://www.googleapis.com/auth/calendar",
        "https://www.googleapis.com/auth/calendar.events",
        "https://www.googleapis.com/auth/calendar.events.owned",
    }
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
        access_token = self._require_access_token(connection)
        sync_token_for_request = await self._resolve_sync_token_for_request(connection)

        batch = await self.calendar_client.list_events(
            access_token=access_token,
            refresh_token=connection.refresh_token,
            calendar_id=connection.external_calendar_id,
            sync_token=sync_token_for_request,
        )

        touched_mirrors = await self._upsert_mirror_events(
            connection=connection, events=batch.events
        )
        await self._map_mirrors_and_write_back(connection=connection, mirrors=touched_mirrors)

        self._touch_successful_sync(connection, next_sync_token=batch.next_sync_token)
        await self.connection_repo.commit()
        return len(batch.events)

    def _require_access_token(self, connection: ExternalCalendarConnection) -> str:
        if not connection.access_token:
            raise ValueError("Calendar connection is missing an access token")
        return connection.access_token

    async def _resolve_sync_token_for_request(
        self, connection: ExternalCalendarConnection
    ) -> str | None:
        sync_token_for_request = connection.sync_token
        if sync_token_for_request is None:
            return None

        has_mirrored_events = await self.event_mirror_repo.has_any_for_connection(connection.id)
        if has_mirrored_events:
            return sync_token_for_request
        return None

    async def _upsert_mirror_events(
        self,
        *,
        connection: ExternalCalendarConnection,
        events: Sequence[ExternalCalendarEvent],
    ) -> list[ExternalCalendarEventMirror]:
        touched_mirrors: list[ExternalCalendarEventMirror] = []
        for event in events:
            touched_mirrors.append(
                await self._upsert_mirror_event(connection=connection, event=event)
            )
        return touched_mirrors

    async def _map_mirrors_and_write_back(
        self,
        *,
        connection: ExternalCalendarConnection,
        mirrors: list[ExternalCalendarEventMirror],
    ) -> None:
        if self.event_mapper is None or not mirrors:
            return

        recurring_event_ids = self._recurring_event_ids(mirrors)
        details_by_id = await self._fetch_recurring_event_details(
            connection=connection,
            recurring_event_ids=recurring_event_ids,
        )

        await self.event_mapper.map_mirrors(
            connection=connection,
            mirrors=mirrors,
            recurring_event_details_by_id=details_by_id,
        )

        await self._maybe_write_back_recurring_backlinks(
            connection=connection,
            recurring_event_ids=sorted(recurring_event_ids),
        )

    def _recurring_event_ids(self, mirrors: Sequence[ExternalCalendarEventMirror]) -> set[str]:
        out: set[str] = set()
        for mirror in mirrors:
            recurring_id = mirror.external_recurring_event_id
            if recurring_id:
                out.add(recurring_id)
        return out

    async def _fetch_recurring_event_details(
        self,
        *,
        connection: ExternalCalendarConnection,
        recurring_event_ids: set[str],
    ) -> dict[str, ExternalRecurringEventDetails]:
        if not recurring_event_ids:
            return {}

        access_token = self._require_access_token(connection)
        details_by_id: dict[str, ExternalRecurringEventDetails] = {}
        for recurring_event_id in recurring_event_ids:
            details = await self.calendar_client.get_recurring_event_details(
                access_token=access_token,
                refresh_token=connection.refresh_token,
                calendar_id=connection.external_calendar_id,
                recurring_event_id=recurring_event_id,
            )
            if details is not None:
                details_by_id[recurring_event_id] = details
        return details_by_id

    def _touch_successful_sync(
        self,
        connection: ExternalCalendarConnection,
        *,
        next_sync_token: str | None,
    ) -> None:
        connection.sync_token = next_sync_token
        connection.last_synced_at = datetime.now(UTC)
        connection.last_sync_error_code = None
        connection.last_sync_error_at = None

    async def _maybe_write_back_recurring_backlinks(
        self,
        *,
        connection: ExternalCalendarConnection,
        recurring_event_ids: list[str],
    ) -> None:
        base_url = self._resolve_backlink_base_url(connection)
        if base_url is None or not recurring_event_ids:
            return
        await self._write_back_recurring_backlinks(
            connection=connection,
            recurring_event_ids=recurring_event_ids,
            base_url=base_url,
        )

    def _resolve_backlink_base_url(self, connection: ExternalCalendarConnection) -> str | None:
        settings = self.settings
        if settings is None or not settings.google_calendar_backlink_enabled:
            return None

        if not self._has_google_calendar_write_scope(connection.scope):
            return None

        base_url = (settings.public_base_url or "").strip().rstrip("/")
        if not base_url:
            return None
        return base_url

    def _has_google_calendar_write_scope(self, scope: str | None) -> bool:
        if not scope:
            return False
        scopes = set(scope.split())
        return bool(scopes.intersection(_GOOGLE_CALENDAR_WRITE_SCOPES))

    async def _write_back_recurring_backlinks(
        self,
        *,
        connection: ExternalCalendarConnection,
        recurring_event_ids: Sequence[str],
        base_url: str,
    ) -> None:
        access_token = self._require_access_token(connection)
        for recurring_event_id in recurring_event_ids:
            series = await self._find_series_for_recurring_event(
                connection_id=connection.id,
                recurring_event_id=recurring_event_id,
            )
            if series is None:
                continue

            series_url = f"{base_url}/series/{series.id}"
            await self.calendar_client.upsert_recurring_event_backlink(
                access_token=access_token,
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
