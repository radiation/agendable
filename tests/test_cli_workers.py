from __future__ import annotations

import asyncio
import logging

import pytest

from agendable import cli


@pytest.mark.asyncio
async def test_google_calendar_sync_worker_logs_iteration_complete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[tuple[str, dict[str, object]]] = []

    async def _fake_run() -> int:
        return 3

    async def _cancel_sleep(_: int) -> None:
        raise asyncio.CancelledError

    def _capture_log_with_fields(
        _logger: logging.Logger,
        _level: int,
        message: str,
        **fields: object,
    ) -> None:
        captured.append((message, fields))

    monkeypatch.setattr(cli, "_run_google_calendar_sync", _fake_run)
    monkeypatch.setattr(asyncio, "sleep", _cancel_sleep)
    monkeypatch.setattr(cli, "log_with_fields", _capture_log_with_fields)

    with pytest.raises(asyncio.CancelledError):
        await cli._run_google_calendar_sync_worker(30)

    assert any(
        msg == "google calendar sync worker iteration complete"
        and fields.get("synced_event_count") == 3
        for msg, fields in captured
    )


@pytest.mark.asyncio
async def test_google_calendar_sync_worker_survives_exception(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    captured: list[tuple[str, dict[str, object]]] = []

    async def _boom() -> int:
        raise RuntimeError("boom")

    async def _cancel_sleep(_: int) -> None:
        raise asyncio.CancelledError

    def _capture_log_with_fields(
        _logger: logging.Logger,
        _level: int,
        message: str,
        **fields: object,
    ) -> None:
        captured.append((message, fields))

    monkeypatch.setattr(cli, "_run_google_calendar_sync", _boom)
    monkeypatch.setattr(asyncio, "sleep", _cancel_sleep)
    monkeypatch.setattr(cli, "log_with_fields", _capture_log_with_fields)

    caplog.set_level(logging.ERROR)
    with pytest.raises(asyncio.CancelledError):
        await cli._run_google_calendar_sync_worker(30)

    assert any(
        "google calendar sync worker iteration failed" in r.getMessage() for r in caplog.records
    )
    assert any(
        msg == "google calendar sync worker iteration complete"
        and fields.get("synced_event_count") is None
        for msg, fields in captured
    )


@pytest.mark.asyncio
async def test_reminders_worker_logs_iteration_complete(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[tuple[str, dict[str, object]]] = []

    async def _fake_run_due() -> None:
        return None

    async def _cancel_sleep(_: int) -> None:
        raise asyncio.CancelledError

    def _capture_log_with_fields(
        _logger: logging.Logger,
        _level: int,
        message: str,
        **fields: object,
    ) -> None:
        captured.append((message, fields))

    monkeypatch.setattr(cli, "_run_due_reminders", _fake_run_due)
    monkeypatch.setattr(asyncio, "sleep", _cancel_sleep)
    monkeypatch.setattr(cli, "log_with_fields", _capture_log_with_fields)

    with pytest.raises(asyncio.CancelledError):
        await cli._run_reminders_worker(30)

    assert any(msg == "reminders worker iteration complete" for msg, _ in captured)
