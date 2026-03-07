from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from agendable.db.models import (
    CalendarProvider,
    ExternalCalendarConnection,
    ExternalCalendarEventMirror,
    User,
)
from agendable.db.repos import ExternalCalendarEventMirrorRepository


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


@pytest.mark.asyncio
async def test_get_or_create_for_connection_event_handles_unique_violation_race(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = await _new_user(f"mirror-user-{uuid.uuid4()}@example.com")
    db_session.add(user)
    await db_session.flush()

    connection = ExternalCalendarConnection(
        user_id=user.id,
        provider=CalendarProvider.google,
        external_calendar_id="primary",
        calendar_display_name="Primary",
    )
    db_session.add(connection)
    await db_session.flush()

    mirror = ExternalCalendarEventMirror(
        connection_id=connection.id,
        external_event_id="evt-1",
    )
    db_session.add(mirror)
    await db_session.commit()

    repo = ExternalCalendarEventMirrorRepository(db_session)

    calls = 0
    original = repo.get_for_connection_event

    async def _flaky_get_for_connection_event(
        *,
        connection_id: uuid.UUID,
        external_event_id: str,
    ) -> ExternalCalendarEventMirror | None:
        nonlocal calls
        calls += 1
        if calls == 1:
            return None
        return await original(connection_id=connection_id, external_event_id=external_event_id)

    monkeypatch.setattr(repo, "get_for_connection_event", _flaky_get_for_connection_event)

    got = await repo.get_or_create_for_connection_event(
        connection_id=connection.id,
        external_event_id="evt-1",
    )
    assert got.id == mirror.id
