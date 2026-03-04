from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

import agendable.db as db
from agendable import cli


class _FakeSessionContext:
    async def __aenter__(self) -> object:
        return object()

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        return None


class _DummyConnectionRepo:
    def __init__(self, session: object) -> None:
        self.session = session


class _DummyMirrorRepo:
    def __init__(self, session: object) -> None:
        self.session = session


class _FakeSyncService:
    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs

    async def sync_all_enabled_connections(self) -> int:
        return 7


@pytest.mark.asyncio
async def test_run_google_calendar_sync_is_noop_when_feature_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        cli,
        "get_settings",
        lambda: SimpleNamespace(
            google_calendar_sync_enabled=False,
            google_calendar_api_base_url="https://www.googleapis.com/calendar/v3",
            google_calendar_initial_sync_days_back=90,
        ),
    )

    synced = await cli._run_google_calendar_sync()
    assert synced == 0


@pytest.mark.asyncio
async def test_run_google_calendar_sync_executes_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        cli,
        "get_settings",
        lambda: SimpleNamespace(
            google_calendar_sync_enabled=True,
            google_calendar_api_base_url="https://www.googleapis.com/calendar/v3",
            google_calendar_initial_sync_days_back=90,
        ),
    )
    monkeypatch.setattr(db, "SessionMaker", lambda: _FakeSessionContext())
    monkeypatch.setattr(cli, "ExternalCalendarConnectionRepository", _DummyConnectionRepo)
    monkeypatch.setattr(cli, "ExternalCalendarEventMirrorRepository", _DummyMirrorRepo)
    monkeypatch.setattr(cli, "GoogleCalendarSyncService", _FakeSyncService)

    synced = await cli._run_google_calendar_sync()
    assert synced == 7
