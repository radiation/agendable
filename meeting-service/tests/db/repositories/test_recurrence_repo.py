import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from tests.factories import RecurrenceFactory

from app.db.repositories.recurrence_repo import RecurrenceRepository


@pytest.mark.asyncio
async def test_create_recurrence(db_session: AsyncSession) -> None:
    repo = RecurrenceRepository(db_session)

    recurrence_factory = RecurrenceFactory.build()
    created_recurrence = await repo.create(recurrence_factory)

    assert created_recurrence is not None
    assert created_recurrence.title == recurrence_factory.title
    assert created_recurrence.rrule == recurrence_factory.rrule


@pytest.mark.asyncio
async def test_get_recurrence(db_session: AsyncSession) -> None:
    repo = RecurrenceRepository(db_session)

    recurrence_factory = RecurrenceFactory.build()
    created_recurrence = await repo.create(recurrence_factory)
    assert created_recurrence is not None

    retrieved = await repo.get_by_id(created_recurrence.id)
    assert retrieved is not None
    assert retrieved.id == created_recurrence.id
    assert retrieved.title == created_recurrence.title


@pytest.mark.asyncio
async def test_delete_recurrence(db_session: AsyncSession) -> None:
    repo = RecurrenceRepository(db_session)

    recurrence_factory = RecurrenceFactory.build()
    created_recurrence = await repo.create(recurrence_factory)
    assert created_recurrence is not None

    await repo.delete(created_recurrence.id)
    deleted = await repo.get_by_id(created_recurrence.id)
    assert deleted is None
