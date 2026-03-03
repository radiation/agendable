from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from typing import Any

import httpx

from agendable.services.google_calendar_sync_service import (
    ExternalCalendarEvent,
    ExternalCalendarSyncBatch,
)


def _parse_iso_datetime(value: str) -> datetime:
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _parse_event_datetime(value: object) -> tuple[datetime | None, bool]:
    if not isinstance(value, dict):
        return None, False

    datetime_value = value.get("dateTime")
    if isinstance(datetime_value, str):
        return _parse_iso_datetime(datetime_value), False

    date_value = value.get("date")
    if isinstance(date_value, str):
        parsed_date = date.fromisoformat(date_value)
        return datetime.combine(parsed_date, time.min, tzinfo=UTC), True

    return None, False


def _optional_str(value: object) -> str | None:
    if isinstance(value, str):
        normalized = value.strip()
        if normalized:
            return normalized
    return None


def _parse_external_updated_at(item: dict[str, object]) -> datetime | None:
    updated_raw = _optional_str(item.get("updated"))
    if updated_raw is None:
        return None
    return _parse_iso_datetime(updated_raw)


class GoogleCalendarHttpClient:
    def __init__(
        self,
        *,
        api_base_url: str = "https://www.googleapis.com/calendar/v3",
        initial_sync_days_back: int = 90,
        timeout_seconds: float = 15.0,
    ) -> None:
        self.api_base_url = api_base_url.rstrip("/")
        self.initial_sync_days_back = max(1, initial_sync_days_back)
        self.timeout_seconds = timeout_seconds

    async def list_events(
        self,
        *,
        access_token: str,
        refresh_token: str | None,
        calendar_id: str,
        sync_token: str | None,
    ) -> ExternalCalendarSyncBatch:
        del refresh_token

        events: list[ExternalCalendarEvent] = []
        next_sync_token: str | None = None
        next_page_token: str | None = None

        headers = {"Authorization": f"Bearer {access_token}"}
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            while True:
                params: dict[str, str] = {
                    "showDeleted": "true",
                    "maxResults": "2500",
                }

                if sync_token is not None:
                    params["syncToken"] = sync_token
                else:
                    time_min = datetime.now(UTC) - timedelta(days=self.initial_sync_days_back)
                    params["timeMin"] = (
                        time_min.replace(microsecond=0).isoformat().replace("+00:00", "Z")
                    )

                if next_page_token is not None:
                    params["pageToken"] = next_page_token

                response = await client.get(
                    f"{self.api_base_url}/calendars/{calendar_id}/events",
                    headers=headers,
                    params=params,
                )
                response.raise_for_status()

                payload = response.json()
                if not isinstance(payload, dict):
                    raise ValueError("Google Calendar events response must be a JSON object")

                items = payload.get("items")
                if isinstance(items, list):
                    events.extend(self._parse_items(items))

                token = payload.get("nextSyncToken")
                if isinstance(token, str) and token.strip():
                    next_sync_token = token

                page = payload.get("nextPageToken")
                if isinstance(page, str) and page.strip():
                    next_page_token = page
                    continue

                break

        return ExternalCalendarSyncBatch(events=events, next_sync_token=next_sync_token)

    def _parse_items(self, items: list[Any]) -> list[ExternalCalendarEvent]:
        parsed: list[ExternalCalendarEvent] = []
        for item in items:
            parsed_event = self._parse_item(item)
            if parsed_event is not None:
                parsed.append(parsed_event)

        return parsed

    def _parse_item(self, item: Any) -> ExternalCalendarEvent | None:
        if not isinstance(item, dict):
            return None

        event_id = _optional_str(item.get("id"))
        if event_id is None:
            return None

        start_at, is_all_day = _parse_event_datetime(item.get("start"))
        end_at, _ = _parse_event_datetime(item.get("end"))

        return ExternalCalendarEvent(
            event_id=event_id,
            recurring_event_id=_optional_str(item.get("recurringEventId")),
            status=_optional_str(item.get("status")),
            etag=_optional_str(item.get("etag")),
            summary=_optional_str(item.get("summary")),
            start_at=start_at,
            end_at=end_at,
            is_all_day=is_all_day,
            external_updated_at=_parse_external_updated_at(item),
        )
