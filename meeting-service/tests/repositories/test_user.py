import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from tests.factories import UserFactory

from app.db.models.user import User
from app.repositories.user import UserRepository


@pytest.mark.asyncio
async def test_create_user(db_session: AsyncSession) -> None:
    repo = UserRepository(db_session)

    user_factory = UserFactory.build()
    created_user = await repo.create(user_factory)

    assert created_user is not None
    assert created_user.email == user_factory.email
    assert created_user.first_name == user_factory.first_name
    assert created_user.last_name == user_factory.last_name


@pytest.mark.asyncio
async def test_get_user_by_id(db_session: AsyncSession) -> None:
    repo = UserRepository(db_session)

    user_factory = UserFactory.build()
    created_user = await repo.create(user_factory)
    assert created_user is not None

    retrieved = await repo.get_by_id(created_user.id)
    assert retrieved is not None
    assert retrieved.email == user_factory.email
    assert retrieved.first_name == user_factory.first_name
    assert retrieved.last_name == user_factory.last_name


@pytest.mark.asyncio
async def test_update_user(db_session: AsyncSession) -> None:
    repo = UserRepository(db_session)

    user_factory = UserFactory.build()
    created_user = await repo.create(user_factory)
    assert created_user is not None

    update_payload = UserFactory.build(
        first_name="Updated",
        last_name="Name",
    )
    updated_user = await repo.update(created_user.id, update_payload)

    assert updated_user is not None
    assert updated_user.first_name == update_payload.first_name
    assert updated_user.last_name == update_payload.last_name


@pytest.mark.asyncio
async def test_delete_user(db_session: AsyncSession) -> None:
    repo = UserRepository(db_session)

    user_factory = UserFactory.build()
    created_user = await repo.create(user_factory)
    assert created_user is not None

    await repo.delete(created_user.id)
    deleted = await repo.get_by_id(created_user.id)
    assert deleted is None


@pytest.mark.asyncio
async def test_get_all_users(db_session: AsyncSession) -> None:
    repo = UserRepository(db_session)

    user1 = User(
        id=uuid.uuid4(), email="test1@example.com", first_name="First", last_name="User"
    )
    user2 = User(
        id=uuid.uuid4(),
        email="test2@example.com",
        first_name="Second",
        last_name="User",
    )

    db_session.add_all([user1, user2])
    await db_session.commit()

    users = await repo.get_all()
    assert len(users) == 2
    assert users[0].email == "test1@example.com"
    assert users[1].email == "test2@example.com"
