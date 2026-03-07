from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from agendable.db.models import CalendarProvider, ExternalCalendarConnection, User
from agendable.db.repos import (
    ExternalCalendarConnectionRepository,
    ExternalCalendarEventMirrorRepository,
)
from agendable.services.google_calendar_sync_service import (
    ExternalCalendarSyncBatch,
    ExternalRecurringEventDetails,
    GoogleCalendarSyncService,
)


class _ClientShouldNotBeCalled:
    async def list_events(
        self,
        *,
        access_token: str,
        refresh_token: str | None,
        calendar_id: str,
        sync_token: str | None,
    ) -> ExternalCalendarSyncBatch:  # pragma: no cover
        raise AssertionError("list_events should not be called when lock isn't acquired")

    async def get_recurring_event_details(
        self,
        *,
        access_token: str,
        refresh_token: str | None,
        calendar_id: str,
        recurring_event_id: str,
    ) -> ExternalRecurringEventDetails | None:  # pragma: no cover
        raise AssertionError("get_recurring_event_details should not be called")

    async def upsert_recurring_event_backlink(
        self,
        *,
        access_token: str,
        refresh_token: str | None,
        calendar_id: str,
        recurring_event_id: str,
        agendable_series_id: str,
        agendable_series_url: str | None,
    ) -> None:  # pragma: no cover
        raise AssertionError("upsert_recurring_event_backlink should not be called")

    async def upsert_event_backlink(
        self,
        *,
        access_token: str,
        refresh_token: str | None,
        calendar_id: str,
        event_id: str,
        agendable_occurrence_id: str,
        agendable_occurrence_url: str | None,
    ) -> None:  # pragma: no cover
        raise AssertionError("upsert_event_backlink should not be called")


async def _new_user(email: str) -> User:
    local = email.split("@", 1)[0]
    return User(
        email=email,
        first_name=local,
        last_name="",
        display_name=local,
        timezone="UTC",
        password_hash=None,
    )


class _Dialect:
    def __init__(self, name: str) -> None:
        self.name = name


class _Bind:
    def __init__(self, name: str) -> None:
        self.dialect = _Dialect(name)


class _ScalarResult:
    def __init__(self, value: object) -> None:
        self._value = value

    def scalar_one(self) -> object:
        return self._value


@pytest.mark.asyncio
async def test_sync_connection_skips_when_lock_not_acquired(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = await _new_user(f"lock-user-{uuid.uuid4()}@example.com")
    db_session.add(user)
    await db_session.flush()

    connection = ExternalCalendarConnection(
        user_id=user.id,
        provider=CalendarProvider.google,
        external_calendar_id="primary",
        access_token="access",
        refresh_token=None,
        sync_token=None,
        last_synced_at=None,
        is_enabled=True,
    )
    db_session.add(connection)
    await db_session.flush()

    # Simulate Postgres and a failed advisory lock acquisition, without actually
    # executing Postgres functions against SQLite.
    monkeypatch.setattr(db_session, "get_bind", lambda: _Bind("postgresql"))

    original_execute = db_session.execute

    async def _execute(stmt: Any, params: Any = None, **kw: Any) -> Any:
        sql = str(stmt)
        if "pg_try_advisory_xact_lock" in sql:
            return _ScalarResult(False)
        return await original_execute(stmt, params or {}, **kw)

    monkeypatch.setattr(db_session, "execute", _execute)

    service = GoogleCalendarSyncService(
        connection_repo=ExternalCalendarConnectionRepository(db_session),
        event_mirror_repo=ExternalCalendarEventMirrorRepository(db_session),
        calendar_client=_ClientShouldNotBeCalled(),
        event_mapper=None,
        settings=None,
    )

    count = await service.sync_connection(connection)
    assert count == 0
