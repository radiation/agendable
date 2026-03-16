from __future__ import annotations

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine

import agendable.db as db
from agendable import cli
from agendable.db.models import AgendaItem, MeetingOccurrence, MeetingSeries, Task, User


@pytest.mark.asyncio
async def test_seed_dev_data_creates_expected_records(test_engine: AsyncEngine) -> None:
    _ = test_engine

    summary = await cli.seed_dev_data(reset=False, password="Password123!")

    assert summary.reset_applied is False
    assert summary.users_created == 3
    assert summary.series_created == 3
    assert summary.occurrences_created == 36
    assert summary.attendees_added == 84
    assert summary.agenda_items_created == 72
    assert summary.tasks_created == 72

    second_summary = await cli.seed_dev_data(reset=False, password="Password123!")

    assert second_summary.users_created == 0
    assert second_summary.series_created == 0
    assert second_summary.occurrences_created == 0
    assert second_summary.attendees_added == 0
    assert second_summary.agenda_items_created == 0
    assert second_summary.tasks_created == 0


@pytest.mark.asyncio
async def test_seed_dev_data_reset_rebuilds_seed_state(test_engine: AsyncEngine) -> None:
    _ = test_engine

    await cli.seed_dev_data(reset=False, password="Password123!")
    summary = await cli.seed_dev_data(reset=True, password="Password123!")

    assert summary.reset_applied is True
    assert summary.users_created == 3
    assert summary.series_created == 3
    assert summary.occurrences_created == 36

    async with db.SessionMaker() as session:
        user_count = await session.scalar(select(func.count()).select_from(User))
        series_count = await session.scalar(select(func.count()).select_from(MeetingSeries))
        occurrence_count = await session.scalar(select(func.count()).select_from(MeetingOccurrence))
        agenda_count = await session.scalar(select(func.count()).select_from(AgendaItem))
        task_count = await session.scalar(select(func.count()).select_from(Task))

    assert user_count == 3
    assert series_count == 3
    assert occurrence_count == 36
    assert agenda_count == 72
    assert task_count == 72
