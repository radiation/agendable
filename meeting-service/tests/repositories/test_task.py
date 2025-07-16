import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from tests.factories import TaskFactory

from app.repositories.task import TaskRepository


@pytest.mark.asyncio
async def test_create_task(db_session: AsyncSession) -> None:
    repo = TaskRepository(db_session)

    task_factory = TaskFactory.build()
    created_task = await repo.create(task_factory)

    assert created_task is not None
    assert created_task.title == task_factory.title


@pytest.mark.asyncio
async def test_get_task_by_id(db_session: AsyncSession) -> None:
    repo = TaskRepository(db_session)

    task_factory = TaskFactory.build()
    created_task = await repo.create(task_factory)
    assert created_task is not None

    retrieved = await repo.get_by_id(created_task.id)

    assert retrieved is not None
    assert retrieved.title == created_task.title


@pytest.mark.asyncio
async def test_update_task(db_session: AsyncSession) -> None:
    repo = TaskRepository(db_session)

    task_factory = TaskFactory.build()
    created_task = await repo.create(task_factory)
    assert created_task is not None
    assert created_task.title == task_factory.title

    updated_payload = TaskFactory.build(
        title="Updated Task",
        description="Updated Description",
        completed=True,
    )
    updated_task = await repo.update(created_task.id, updated_payload)

    assert updated_task is not None
    assert updated_task.title == updated_payload.title
    assert updated_task.description == updated_payload.description


@pytest.mark.asyncio
async def test_delete_task(db_session: AsyncSession) -> None:
    repo = TaskRepository(db_session)

    task_factory = TaskFactory.build()
    created_task = await repo.create(task_factory)
    assert created_task is not None

    await repo.delete(created_task.id)
    deleted = await repo.get_by_id(created_task.id)
    assert deleted is None


@pytest.mark.asyncio
async def test_get_all_tasks(db_session: AsyncSession) -> None:
    repo = TaskRepository(db_session)

    task1 = TaskFactory.build()
    task2 = TaskFactory.build()

    db_session.add_all([task1, task2])
    await db_session.commit()

    tasks = await repo.get_all()
    assert len(tasks) == 2
    assert tasks[0].title == task1.title
    assert tasks[1].title == task2.title
