from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class ExternalCalendarAuth:
    """Provider auth material for calendar API calls.

    Today this is token-shaped (works for Google/Microsoft delegated flows).
    Keeping it as a single object makes it easier to evolve toward other auth
    strategies (SAML-backed app sessions, app-only credentials, etc.) without
    pushing OAuth concepts through every interface.
    """

    access_token: str
    refresh_token: str | None = None


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

    This is currently shaped around Google Calendar semantics (instances reference a
    recurring master via `recurringEventId`), but is kept provider-neutral so other
    providers can implement the same interface.
    """

    event_id: str
    recurrence_rrule: str | None
    recurrence_dtstart: datetime | None
    recurrence_timezone: str | None


@dataclass(frozen=True)
class ExternalCalendarSyncBatch:
    events: Sequence[ExternalCalendarEvent]
    next_sync_token: str | None


class ExternalCalendarClient(Protocol):
    async def list_events(
        self,
        *,
        auth: ExternalCalendarAuth,
        calendar_id: str,
        sync_token: str | None,
    ) -> ExternalCalendarSyncBatch: ...

    async def get_recurring_event_details(
        self,
        *,
        auth: ExternalCalendarAuth,
        calendar_id: str,
        recurring_event_id: str,
    ) -> ExternalRecurringEventDetails | None: ...

    async def upsert_recurring_event_backlink(
        self,
        *,
        auth: ExternalCalendarAuth,
        calendar_id: str,
        recurring_event_id: str,
        agendable_series_id: str,
        agendable_series_url: str | None,
    ) -> None: ...

    async def upsert_event_backlink(
        self,
        *,
        auth: ExternalCalendarAuth,
        calendar_id: str,
        event_id: str,
        agendable_occurrence_id: str,
        agendable_occurrence_url: str | None,
    ) -> None: ...
