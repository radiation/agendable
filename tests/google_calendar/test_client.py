from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

import agendable.services.google_calendar_client as gcal
from agendable.services.external_calendar_api import ExternalCalendarAuth
from agendable.services.google_calendar_client import GoogleCalendarHttpClient


@dataclass
class _StubResponse:
    payload: object
    status_code: int = 200

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self) -> object:
        return self.payload


class _StubAsyncClient:
    def __init__(self, scripted: list[tuple[str, _StubResponse]]) -> None:
        self._scripted = scripted
        self.calls: list[dict[str, object]] = []

    async def __aenter__(self) -> _StubAsyncClient:
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        return None

    async def get(self, url: str, **kwargs: object) -> _StubResponse:
        self.calls.append({"method": "GET", "url": url, **kwargs})
        method, resp = self._scripted.pop(0)
        assert method == "GET"
        return resp

    async def patch(self, url: str, **kwargs: object) -> _StubResponse:
        self.calls.append({"method": "PATCH", "url": url, **kwargs})
        method, resp = self._scripted.pop(0)
        assert method == "PATCH"
        return resp


@pytest.mark.asyncio
async def test_list_events_paginates_and_parses_items(monkeypatch: pytest.MonkeyPatch) -> None:
    resp1 = _StubResponse(
        {
            "items": [
                {
                    "id": "evt-1",
                    "recurringEventId": "master-1",
                    "status": "confirmed",
                    "etag": "etag-1",
                    "summary": "Team Sync",
                    "start": {"dateTime": "2026-03-04T18:00:00Z"},
                    "end": {"dateTime": "2026-03-04T18:30:00Z"},
                    "updated": "2026-03-04T17:00:00Z",
                }
            ],
            "nextPageToken": "page-2",
        }
    )
    resp2 = _StubResponse(
        {
            "items": [
                {
                    "id": "evt-2",
                    "status": "confirmed",
                    "start": {"date": "2026-03-05"},
                    "end": {"date": "2026-03-06"},
                }
            ],
            "nextSyncToken": "sync-2",
        }
    )

    stub = _StubAsyncClient([("GET", resp1), ("GET", resp2)])
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: stub)

    client = GoogleCalendarHttpClient(api_base_url="https://example.test")
    batch = await client.list_events(
        auth=ExternalCalendarAuth(access_token="access", refresh_token=None),
        calendar_id="primary",
        sync_token=None,
    )

    assert batch.next_sync_token == "sync-2"
    assert [e.event_id for e in batch.events] == ["evt-1", "evt-2"]
    assert batch.events[0].recurring_event_id == "master-1"
    assert batch.events[0].is_all_day is False
    assert batch.events[1].is_all_day is True

    assert len(stub.calls) == 2
    first_params = stub.calls[0]["params"]
    assert isinstance(first_params, dict)
    assert first_params["showDeleted"] == "true"
    assert first_params["singleEvents"] == "true"
    assert "timeMin" in first_params
    assert first_params["orderBy"] == "startTime"

    second_params = stub.calls[1]["params"]
    assert isinstance(second_params, dict)
    assert second_params["pageToken"] == "page-2"


@pytest.mark.asyncio
async def test_list_events_uses_sync_token_when_provided(monkeypatch: pytest.MonkeyPatch) -> None:
    resp = _StubResponse({"items": [], "nextSyncToken": "sync-1"})
    stub = _StubAsyncClient([("GET", resp)])
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: stub)

    client = GoogleCalendarHttpClient(api_base_url="https://example.test")
    batch = await client.list_events(
        auth=ExternalCalendarAuth(access_token="access", refresh_token=None),
        calendar_id="primary",
        sync_token="prev-sync",
    )
    assert batch.next_sync_token == "sync-1"
    params = stub.calls[0]["params"]
    assert isinstance(params, dict)
    assert params["syncToken"] == "prev-sync"
    assert "timeMin" not in params


@pytest.mark.asyncio
async def test_get_recurring_event_details_parses_rrule_and_timezone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resp = _StubResponse(
        {
            "status": "confirmed",
            "start": {"dateTime": "2026-03-04T18:00:00Z", "timeZone": "UTC"},
            "recurrence": ["RRULE:FREQ=WEEKLY;INTERVAL=1;BYDAY=WE"],
        }
    )
    stub = _StubAsyncClient([("GET", resp)])
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: stub)

    client = GoogleCalendarHttpClient(api_base_url="https://example.test")
    details = await client.get_recurring_event_details(
        auth=ExternalCalendarAuth(access_token="access", refresh_token=None),
        calendar_id="primary",
        recurring_event_id="master-1",
    )

    assert details is not None
    assert details.event_id == "master-1"
    assert details.recurrence_rrule == "FREQ=WEEKLY;INTERVAL=1;BYDAY=WE"
    assert details.recurrence_dtstart == datetime(2026, 3, 4, 18, 0, tzinfo=UTC)
    assert details.recurrence_timezone == "UTC"


@pytest.mark.asyncio
async def test_get_recurring_event_details_returns_none_for_cancelled_master(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resp = _StubResponse({"status": "cancelled"})
    stub = _StubAsyncClient([("GET", resp)])
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: stub)

    client = GoogleCalendarHttpClient(api_base_url="https://example.test")
    details = await client.get_recurring_event_details(
        auth=ExternalCalendarAuth(access_token="access", refresh_token=None),
        calendar_id="primary",
        recurring_event_id="master-1",
    )
    assert details is None


@pytest.mark.asyncio
async def test_get_recurring_event_details_returns_none_for_all_day_master(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resp = _StubResponse(
        {
            "status": "confirmed",
            "start": {"date": "2026-03-04"},
            "recurrence": ["RRULE:FREQ=WEEKLY;BYDAY=WE"],
        }
    )
    stub = _StubAsyncClient([("GET", resp)])
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: stub)

    client = GoogleCalendarHttpClient(api_base_url="https://example.test")
    details = await client.get_recurring_event_details(
        auth=ExternalCalendarAuth(access_token="access", refresh_token=None),
        calendar_id="primary",
        recurring_event_id="master-1",
    )
    assert details is None


@pytest.mark.asyncio
async def test_upsert_recurring_event_backlink_patches_when_needed_and_replaces_link_line(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current = _StubResponse(
        {
            "status": "confirmed",
            "description": "Hello\nAgendable: https://old.example/series/old",
            "extendedProperties": {"private": {}},
        }
    )
    patched = _StubResponse({})
    stub = _StubAsyncClient([("GET", current), ("PATCH", patched)])
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: stub)

    client = GoogleCalendarHttpClient(api_base_url="https://example.test")
    await client.upsert_recurring_event_backlink(
        auth=ExternalCalendarAuth(access_token="access", refresh_token=None),
        calendar_id="primary",
        recurring_event_id="master-1",
        agendable_series_id="series-123",
        agendable_series_url="https://new.example/series/series-123",
    )

    assert [c["method"] for c in stub.calls] == ["GET", "PATCH"]
    patch_call = stub.calls[1]
    assert patch_call["params"] == {"sendUpdates": "none"}
    payload = patch_call["json"]
    assert isinstance(payload, dict)
    assert payload["extendedProperties"] == {"private": {"agendable_series_id": "series-123"}}
    assert "description" in payload
    assert "Agendable: https://new.example/series/series-123" in str(payload["description"])
    assert "old.example" not in str(payload["description"])


@pytest.mark.asyncio
async def test_upsert_recurring_event_backlink_noops_when_already_up_to_date(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current = _StubResponse(
        {
            "status": "confirmed",
            "description": "Agendable: https://app.example/series/series-123",
            "extendedProperties": {"private": {"agendable_series_id": "series-123"}},
        }
    )
    stub = _StubAsyncClient([("GET", current)])
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: stub)

    client = GoogleCalendarHttpClient(api_base_url="https://example.test")
    await client.upsert_recurring_event_backlink(
        auth=ExternalCalendarAuth(access_token="access", refresh_token=None),
        calendar_id="primary",
        recurring_event_id="master-1",
        agendable_series_id="series-123",
        agendable_series_url="https://app.example/series/series-123",
    )

    assert [c["method"] for c in stub.calls] == ["GET"]


@pytest.mark.asyncio
async def test_upsert_event_backlink_is_idempotent_when_already_up_to_date(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current = _StubResponse(
        {
            "status": "confirmed",
            "description": "Agendable: https://app.example/occurrences/occ-1",
            "extendedProperties": {"private": {"agendable_occurrence_id": "occ-1"}},
        }
    )
    stub = _StubAsyncClient([("GET", current)])
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: stub)

    client = GoogleCalendarHttpClient(api_base_url="https://example.test")
    await client.upsert_event_backlink(
        auth=ExternalCalendarAuth(access_token="access", refresh_token=None),
        calendar_id="primary",
        event_id="evt-1",
        agendable_occurrence_id="occ-1",
        agendable_occurrence_url="https://app.example/occurrences/occ-1",
    )

    assert [c["method"] for c in stub.calls] == ["GET"]


@pytest.mark.asyncio
async def test_upsert_event_backlink_patches_when_needed_and_appends_link(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current = _StubResponse(
        {
            "status": "confirmed",
            "description": "Some notes",
            "extendedProperties": {"private": {}},
        }
    )
    patched = _StubResponse({})
    stub = _StubAsyncClient([("GET", current), ("PATCH", patched)])
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: stub)

    client = GoogleCalendarHttpClient(api_base_url="https://example.test")
    await client.upsert_event_backlink(
        auth=ExternalCalendarAuth(access_token="access", refresh_token=None),
        calendar_id="primary",
        event_id="evt-1",
        agendable_occurrence_id="occ-1",
        agendable_occurrence_url="https://app.example/occurrences/occ-1",
    )

    assert [c["method"] for c in stub.calls] == ["GET", "PATCH"]
    patch_call = stub.calls[1]
    payload = patch_call["json"]
    assert isinstance(payload, dict)
    assert payload["extendedProperties"] == {"private": {"agendable_occurrence_id": "occ-1"}}
    assert "Agendable: https://app.example/occurrences/occ-1" in str(payload["description"])


def test_extract_first_rrule_accepts_freq_only_form() -> None:
    assert gcal._extract_first_rrule(["FREQ=WEEKLY;BYDAY=WE"]) == "FREQ=WEEKLY;BYDAY=WE"


def test_parse_private_extended_properties_filters_non_strings() -> None:
    payload: dict[str, object] = {
        "extendedProperties": {"private": {" ok ": " yes ", "bad": 123}},
    }
    assert gcal._parse_private_extended_properties(payload) == {"ok": "yes"}


def test_append_agendable_link_replaces_existing_link_line() -> None:
    desc = "Line1\nAgendable: https://old\nLine3"
    out = gcal._append_agendable_link(desc, "https://new")
    assert "Agendable: https://new" in out
    assert "https://old" not in out
    assert out.count("Agendable:") == 1
