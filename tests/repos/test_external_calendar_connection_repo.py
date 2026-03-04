from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from agendable.db.models import CalendarProvider, ExternalCalendarConnection, User
from agendable.db.repos import ExternalCalendarConnectionRepository


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
async def test_calendar_connection_repo_get_for_user_provider_calendar(
    db_session: AsyncSession,
) -> None:
    user = await _new_user(f"calendar-user-{uuid.uuid4()}@example.com")
    db_session.add(user)
    await db_session.flush()

    repo = ExternalCalendarConnectionRepository(db_session)
    connection = ExternalCalendarConnection(
        user_id=user.id,
        provider=CalendarProvider.google,
        external_calendar_id="primary",
        calendar_display_name="Primary",
    )
    await repo.add(connection)
    await repo.commit()

    got = await repo.get_for_user_provider_calendar(
        user_id=user.id,
        provider=CalendarProvider.google,
        external_calendar_id="primary",
    )
    assert got is not None
    assert got.id == connection.id


@pytest.mark.asyncio
async def test_calendar_connection_repo_list_enabled_for_provider(db_session: AsyncSession) -> None:
    user = await _new_user(f"calendar-enabled-{uuid.uuid4()}@example.com")
    db_session.add(user)
    await db_session.flush()

    repo = ExternalCalendarConnectionRepository(db_session)
    enabled = ExternalCalendarConnection(
        user_id=user.id,
        provider=CalendarProvider.google,
        external_calendar_id="primary",
        is_enabled=True,
    )
    disabled = ExternalCalendarConnection(
        user_id=user.id,
        provider=CalendarProvider.google,
        external_calendar_id="team",
        is_enabled=False,
    )

    await repo.add(enabled)
    await repo.add(disabled)
    await repo.commit()

    rows = await repo.list_enabled_for_provider(CalendarProvider.google)
    assert [row.external_calendar_id for row in rows] == ["primary"]
