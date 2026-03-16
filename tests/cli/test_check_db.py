from __future__ import annotations

import importlib
import sys
from typing import Any

import pytest

import agendable.db as db
from agendable.cli import db as cli_db
from agendable.settings import Settings


class _FakeConn:
    def __init__(self, captured: list[object]) -> None:
        self._captured = captured

    async def execute(self, clause: object) -> None:
        self._captured.append(clause)


class _FakeConnectContext:
    def __init__(self, captured: list[object]) -> None:
        self._captured = captured

    async def __aenter__(self) -> _FakeConn:
        return _FakeConn(self._captured)

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        return None


class _FakeEngine:
    def __init__(self, captured: list[object]) -> None:
        self._captured = captured

    def connect(self) -> _FakeConnectContext:
        return _FakeConnectContext(self._captured)


@pytest.mark.asyncio
async def test_check_db_executes_select_1(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[object] = []
    monkeypatch.setattr(db, "engine", _FakeEngine(captured))

    await cli_db.check_db(timeout_seconds=0.5)

    assert len(captured) == 1
    assert "SELECT 1" in str(captured[0]).upper()


def test_main_check_db_exits_nonzero_on_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    cli_main_module = importlib.import_module("agendable.cli.main")

    monkeypatch.setattr(
        cli_main_module,
        "get_settings",
        lambda: Settings(
            reminder_worker_poll_seconds=60,
            google_calendar_sync_worker_poll_seconds=60,
        ),
    )

    async def _boom(*, timeout_seconds: float) -> None:
        raise RuntimeError("db is down")

    monkeypatch.setattr(cli_main_module, "check_db", _boom)
    monkeypatch.setattr(sys, "argv", ["agendable", "check-db"])

    with pytest.raises(SystemExit) as exc:
        cli_main_module.main()

    assert exc.value.code == 1
