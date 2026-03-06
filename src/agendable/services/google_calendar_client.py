from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from urllib.parse import quote
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx

from agendable.services.google_calendar_sync_service import (
    ExternalCalendarEvent,
    ExternalCalendarSyncBatch,
    ExternalRecurringEventDetails,
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


def _parse_google_datetime_with_timezone(
    *,
    start_obj: object,
) -> tuple[datetime | None, str | None, bool]:
    """Parse a Google Calendar start/end object.

    Returns: (datetime, timezone_name, is_all_day)
    - datetime is tz-aware when possible
    - timezone_name is from the 'timeZone' field when provided
    """

    if not isinstance(start_obj, dict):
        return None, None, False

    tz_name = _optional_str(start_obj.get("timeZone"))

    datetime_raw = _optional_str(start_obj.get("dateTime"))
    if datetime_raw is not None:
        normalized = datetime_raw
        if normalized.endswith("Z"):
            normalized = f"{normalized[:-1]}+00:00"
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)

        if tz_name is not None:
            try:
                zone = ZoneInfo(tz_name)
                return parsed.astimezone(zone), tz_name, False
            except ZoneInfoNotFoundError:
                return parsed, None, False

        return parsed, None, False

    date_raw = _optional_str(start_obj.get("date"))
    if date_raw is not None:
        parsed_date = date.fromisoformat(date_raw)
        return datetime.combine(parsed_date, time.min, tzinfo=UTC), None, True

    return None, None, False


def _extract_first_rrule(recurrence: object) -> str | None:
    if not isinstance(recurrence, list):
        return None
    for item in recurrence:
        if not isinstance(item, str):
            continue
        normalized = item.strip()
        if not normalized:
            continue
        if normalized.upper().startswith("RRULE:"):
            return normalized[6:].strip() or None
        if normalized.upper().startswith("FREQ="):
            return normalized
    return None


def _parse_private_extended_properties(payload: dict[str, object]) -> dict[str, str]:
    extended = payload.get("extendedProperties")
    if not isinstance(extended, dict):
        return {}
    private = extended.get("private")
    if not isinstance(private, dict):
        return {}
    out: dict[str, str] = {}
    for k, v in private.items():
        if isinstance(k, str) and isinstance(v, str) and k.strip() and v.strip():
            out[k.strip()] = v.strip()
    return out


def _append_agendable_link(description: str | None, url: str) -> str:
    existing = (description or "").strip()
    link_line = f"Agendable: {url}".strip()
    if not existing:
        return link_line

    # If an Agendable link line exists already, replace it (supports base-url changes).
    lines = existing.splitlines()
    replaced = False
    out_lines: list[str] = []
    for line in lines:
        if line.strip().startswith("Agendable:"):
            if not replaced:
                out_lines.append(link_line)
                replaced = True
            continue
        out_lines.append(line)

    rebuilt = "\n".join(out_lines).strip()
    if replaced:
        return rebuilt

    # Otherwise append a new line at the end.
    return f"{rebuilt}\n\n{link_line}".strip()


def _event_url(*, api_base_url: str, calendar_id: str, event_id: str) -> str:
    encoded_event_id = quote(event_id, safe="")
    return f"{api_base_url}/calendars/{calendar_id}/events/{encoded_event_id}"


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
                    "singleEvents": "true",
                }

                if sync_token is not None:
                    params["syncToken"] = sync_token
                else:
                    time_min = datetime.now(UTC) - timedelta(days=self.initial_sync_days_back)
                    params["timeMin"] = (
                        time_min.replace(microsecond=0).isoformat().replace("+00:00", "Z")
                    )
                    params["orderBy"] = "startTime"

                if next_page_token is not None:
                    params["pageToken"] = next_page_token

                response = await client.get(
                    f"{self.api_base_url}/calendars/{calendar_id}/events",
                    headers=headers,
                    params=params,
                )
                response.raise_for_status()

                payload: dict[str, object] = response.json()
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

    async def get_recurring_event_details(
        self,
        *,
        access_token: str,
        refresh_token: str | None,
        calendar_id: str,
        recurring_event_id: str,
    ) -> ExternalRecurringEventDetails | None:
        del refresh_token

        headers = {"Authorization": f"Bearer {access_token}"}
        encoded_event_id = quote(recurring_event_id, safe="")
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.get(
                f"{self.api_base_url}/calendars/{calendar_id}/events/{encoded_event_id}",
                headers=headers,
            )
            response.raise_for_status()

            payload: object = response.json()
            if not isinstance(payload, dict):
                raise ValueError("Google Calendar event response must be a JSON object")

            status = _optional_str(payload.get("status"))
            if status == "cancelled":
                return None

            start_dt, start_tz, is_all_day = _parse_google_datetime_with_timezone(
                start_obj=payload.get("start")
            )
            if start_dt is None or is_all_day:
                return None

            rrule = _extract_first_rrule(payload.get("recurrence"))
            return ExternalRecurringEventDetails(
                event_id=recurring_event_id,
                recurrence_rrule=rrule,
                recurrence_dtstart=start_dt,
                recurrence_timezone=start_tz,
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
        del refresh_token

        headers = {"Authorization": f"Bearer {access_token}"}
        event_url = _event_url(
            api_base_url=self.api_base_url,
            calendar_id=calendar_id,
            event_id=recurring_event_id,
        )

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            current_resp = await client.get(event_url, headers=headers)
            current_resp.raise_for_status()
            payload_obj: object = current_resp.json()
            if not isinstance(payload_obj, dict):
                raise ValueError("Google Calendar event response must be a JSON object")

            status = _optional_str(payload_obj.get("status"))
            if status == "cancelled":
                return

            current_private = _parse_private_extended_properties(payload_obj)
            current_series = current_private.get("agendable_series_id")

            current_desc = _optional_str(payload_obj.get("description"))
            desired_desc = current_desc
            if agendable_series_url is not None and agendable_series_url.strip():
                desired_desc = _append_agendable_link(current_desc, agendable_series_url.strip())

            if current_series == agendable_series_id and desired_desc == current_desc:
                return

            desired_private = dict(current_private)
            desired_private["agendable_series_id"] = agendable_series_id

            patch_payload: dict[str, object] = {
                "extendedProperties": {"private": desired_private},
            }
            if desired_desc is not None:
                patch_payload["description"] = desired_desc

            patch_resp = await client.patch(
                event_url,
                headers=headers,
                params={"sendUpdates": "none"},
                json=patch_payload,
            )
            patch_resp.raise_for_status()

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
        del refresh_token

        headers = {"Authorization": f"Bearer {access_token}"}
        event_url = _event_url(
            api_base_url=self.api_base_url,
            calendar_id=calendar_id,
            event_id=event_id,
        )

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            current_resp = await client.get(event_url, headers=headers)
            current_resp.raise_for_status()
            payload_obj: object = current_resp.json()
            if not isinstance(payload_obj, dict):
                raise ValueError("Google Calendar event response must be a JSON object")

            status = _optional_str(payload_obj.get("status"))
            if status == "cancelled":
                return

            current_private = _parse_private_extended_properties(payload_obj)
            current_occurrence = current_private.get("agendable_occurrence_id")

            current_desc = _optional_str(payload_obj.get("description"))
            desired_desc = current_desc
            if agendable_occurrence_url is not None and agendable_occurrence_url.strip():
                desired_desc = _append_agendable_link(
                    current_desc, agendable_occurrence_url.strip()
                )

            if current_occurrence == agendable_occurrence_id and desired_desc == current_desc:
                return

            desired_private = dict(current_private)
            desired_private["agendable_occurrence_id"] = agendable_occurrence_id

            patch_payload: dict[str, object] = {
                "extendedProperties": {"private": desired_private},
            }
            if desired_desc is not None:
                patch_payload["description"] = desired_desc

            patch_resp = await client.patch(
                event_url,
                headers=headers,
                params={"sendUpdates": "none"},
                json=patch_payload,
            )
            patch_resp.raise_for_status()

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
