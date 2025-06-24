from common_lib.exceptions import NotFoundError
import pytest

from app.schemas.recurrence_schemas import RecurrenceUpdate
from app.services.recurrence_service import RecurrenceService
from tests.factories import RecurrenceCreateFactory


@pytest.mark.asyncio
async def test_create_recurrence_service(recurrence_service: RecurrenceService) -> None:
    recurrence_create_factory = RecurrenceCreateFactory.build()
    created_recurrence = await recurrence_service.create(recurrence_create_factory)
    assert created_recurrence.title == recurrence_create_factory.title
    assert created_recurrence.rrule == recurrence_create_factory.rrule


@pytest.mark.asyncio
async def test_get_recurrence_service(recurrence_service: RecurrenceService) -> None:
    recurrence_create_factory = RecurrenceCreateFactory.build()
    created_recurrence = await recurrence_service.create(recurrence_create_factory)

    retrieved_recurrence = await recurrence_service.get_by_id(created_recurrence.id)
    assert retrieved_recurrence.title == recurrence_create_factory.title
    assert retrieved_recurrence.rrule == recurrence_create_factory.rrule


@pytest.mark.asyncio
async def test_update_recurrence_service(recurrence_service: RecurrenceService) -> None:
    recurrence_create_factory = RecurrenceCreateFactory.build()
    created_recurrence = await recurrence_service.create(recurrence_create_factory)

    recurrence_payload = RecurrenceUpdate(
        title="Updated Test Recurrence", rrule="FREQ=WEEKLY;INTERVAL=2"
    )

    updated_recurrence = await recurrence_service.update(
        created_recurrence.id, recurrence_payload
    )
    assert updated_recurrence.title == updated_recurrence.title
    assert updated_recurrence.rrule == updated_recurrence.rrule


@pytest.mark.asyncio
async def test_delete_recurrence_service(recurrence_service: RecurrenceService) -> None:
    recurrence_create_factory = RecurrenceCreateFactory.build()
    created_recurrence = await recurrence_service.create(recurrence_create_factory)

    await recurrence_service.delete(created_recurrence.id)

    with pytest.raises(NotFoundError):
        await recurrence_service.get_by_id(created_recurrence.id)
