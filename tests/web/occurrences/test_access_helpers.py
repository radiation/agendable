from __future__ import annotations

import uuid
from typing import cast

import pytest

from agendable.services import OccurrenceService
from agendable.web.routes.occurrences.access import validate_task_assignee


class StubOccurrenceService:
    def __init__(self, *, assignee_exists: bool, is_attendee: bool) -> None:
        self._assignee_exists = assignee_exists
        self._is_attendee = is_attendee
        self.is_occurrence_attendee_calls = 0

    async def assignee_exists(self, *, assignee_id: uuid.UUID) -> bool:
        return self._assignee_exists

    async def is_occurrence_attendee(
        self,
        *,
        occurrence_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> bool:
        self.is_occurrence_attendee_calls += 1
        return self._is_attendee


@pytest.mark.asyncio
async def test_validate_task_assignee_rejects_unknown_assignee() -> None:
    service = StubOccurrenceService(assignee_exists=False, is_attendee=False)
    errors: dict[str, str] = {}

    await validate_task_assignee(
        occurrence_service=cast(OccurrenceService, service),
        occurrence_id=uuid.uuid4(),
        series_owner_user_id=uuid.uuid4(),
        assignee_id=uuid.uuid4(),
        task_form_errors=errors,
    )

    assert errors["assigned_user_id"] == "Choose a valid assignee."
    assert service.is_occurrence_attendee_calls == 0


@pytest.mark.asyncio
async def test_validate_task_assignee_allows_series_owner_without_attendee_check() -> None:
    owner_id = uuid.uuid4()
    service = StubOccurrenceService(assignee_exists=True, is_attendee=False)
    errors: dict[str, str] = {}

    await validate_task_assignee(
        occurrence_service=cast(OccurrenceService, service),
        occurrence_id=uuid.uuid4(),
        series_owner_user_id=owner_id,
        assignee_id=owner_id,
        task_form_errors=errors,
    )

    assert errors == {}
    assert service.is_occurrence_attendee_calls == 0


@pytest.mark.asyncio
async def test_validate_task_assignee_rejects_non_attendee_assignee() -> None:
    service = StubOccurrenceService(assignee_exists=True, is_attendee=False)
    errors: dict[str, str] = {}

    await validate_task_assignee(
        occurrence_service=cast(OccurrenceService, service),
        occurrence_id=uuid.uuid4(),
        series_owner_user_id=uuid.uuid4(),
        assignee_id=uuid.uuid4(),
        task_form_errors=errors,
    )

    assert errors["assigned_user_id"] == "Assignee must be a meeting attendee."
    assert service.is_occurrence_attendee_calls == 1


@pytest.mark.asyncio
async def test_validate_task_assignee_allows_attendee_assignee() -> None:
    service = StubOccurrenceService(assignee_exists=True, is_attendee=True)
    errors: dict[str, str] = {}

    await validate_task_assignee(
        occurrence_service=cast(OccurrenceService, service),
        occurrence_id=uuid.uuid4(),
        series_owner_user_id=uuid.uuid4(),
        assignee_id=uuid.uuid4(),
        task_form_errors=errors,
    )

    assert errors == {}
    assert service.is_occurrence_attendee_calls == 1
