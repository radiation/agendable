from __future__ import annotations

import uuid

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from agendable.db.models import (
    MeetingOccurrence,
    MeetingSeries,
    User,
)
from agendable.services import OccurrenceService


def ensure_occurrence_writable(occurrence_id: uuid.UUID, is_completed: bool) -> None:
    if is_completed:
        raise HTTPException(
            status_code=400,
            detail=f"Meeting {occurrence_id} is completed and read-only",
        )


def normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    return normalized


async def get_owned_occurrence(
    session: AsyncSession,
    occurrence_id: uuid.UUID,
    owner_user_id: uuid.UUID,
) -> tuple[MeetingOccurrence, MeetingSeries]:
    occurrence, series = await OccurrenceService.from_session(session).get_owned_occurrence(
        occurrence_id=occurrence_id,
        owner_user_id=owner_user_id,
    )
    if occurrence is None or series is None:
        raise HTTPException(status_code=404)

    return occurrence, series


async def get_accessible_occurrence(
    session: AsyncSession,
    occurrence_id: uuid.UUID,
    user_id: uuid.UUID,
) -> tuple[MeetingOccurrence, MeetingSeries]:
    occurrence, series = await OccurrenceService.from_session(session).get_accessible_occurrence(
        occurrence_id=occurrence_id,
        user_id=user_id,
    )
    if occurrence is None or series is None:
        raise HTTPException(status_code=404)

    return occurrence, series


async def list_occurrence_attendee_users(
    session: AsyncSession,
    occurrence_id: uuid.UUID,
    current_user: User,
) -> list[User]:
    return await OccurrenceService.from_session(session).list_occurrence_attendee_users(
        occurrence_id=occurrence_id,
        current_user=current_user,
    )


async def validate_task_assignee(
    *,
    occurrence_service: OccurrenceService,
    occurrence_id: uuid.UUID,
    series_owner_user_id: uuid.UUID,
    assignee_id: uuid.UUID,
    task_form_errors: dict[str, str],
) -> None:
    exists = await occurrence_service.assignee_exists(assignee_id=assignee_id)
    if not exists:
        task_form_errors["assigned_user_id"] = "Choose a valid assignee."
        return

    if assignee_id == series_owner_user_id:
        return

    attendee = await occurrence_service.is_occurrence_attendee(
        occurrence_id=occurrence_id,
        user_id=assignee_id,
    )
    if not attendee:
        task_form_errors["assigned_user_id"] = "Assignee must be a meeting attendee."
