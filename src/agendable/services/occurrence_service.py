from __future__ import annotations

import uuid
from datetime import UTC, datetime, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dateutil.rrule import rrulestr
from sqlalchemy.ext.asyncio import AsyncSession

from agendable.db.models import AgendaItem, MeetingOccurrence, Task, User
from agendable.db.repos import (
    AgendaItemRepository,
    MeetingOccurrenceAttendeeRepository,
    MeetingOccurrenceRepository,
    MeetingSeriesRepository,
    TaskRepository,
    UserRepository,
)
from agendable.recurrence import normalize_rrule


class OccurrenceTaskNotFoundError(Exception):
    pass


class OccurrenceAgendaItemNotFoundError(Exception):
    pass


class OccurrenceNotFoundError(Exception):
    pass


class OccurrenceAssigneeNotFoundError(Exception):
    pass


def _coerce_tzinfo(*, dtstart_tzinfo: tzinfo | None, timezone_name: str) -> tzinfo:
    if dtstart_tzinfo is None:
        dtstart_tzinfo = UTC
    if not timezone_name.strip():
        return dtstart_tzinfo
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        return dtstart_tzinfo


def _ensure_dt_aware_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


def _compute_next_occurrence_utc(
    *,
    rrule: str,
    dtstart: datetime,
    timezone_name: str,
    scheduled_after: datetime,
) -> datetime | None:
    dtstart = _ensure_dt_aware_utc(dtstart)
    scheduled_after = _ensure_dt_aware_utc(scheduled_after)

    tzinfo = _coerce_tzinfo(dtstart_tzinfo=dtstart.tzinfo, timezone_name=timezone_name)
    local_dtstart = dtstart.astimezone(tzinfo)
    local_after = scheduled_after.astimezone(tzinfo)

    rule = rrulestr(normalize_rrule(rrule), dtstart=local_dtstart)
    next_local = rule.after(local_after, inc=False)
    if next_local is None:
        return None
    if next_local.tzinfo is None:
        next_local = next_local.replace(tzinfo=tzinfo)
    return next_local.astimezone(UTC)


async def _get_occurrence_by_scheduled_at(
    session: AsyncSession,
    *,
    series_id: uuid.UUID,
    scheduled_at: datetime,
) -> MeetingOccurrence | None:
    occurrence_repo = MeetingOccurrenceRepository(session)
    return await occurrence_repo.get_for_series_scheduled_at(
        series_id=series_id,
        scheduled_at=scheduled_at,
    )


async def _ensure_next_occurrence_from_rrule(
    session: AsyncSession,
    *,
    occurrence: MeetingOccurrence,
) -> MeetingOccurrence | None:
    series_repo = MeetingSeriesRepository(session)
    series = await series_repo.get(occurrence.series_id)
    if series is None:
        return None

    rrule = (series.recurrence_rrule or "").strip()
    dtstart = series.recurrence_dtstart
    if not rrule or dtstart is None:
        return None

    timezone_name = (series.recurrence_timezone or "").strip()
    next_utc = _compute_next_occurrence_utc(
        rrule=rrule,
        dtstart=dtstart,
        timezone_name=timezone_name,
        scheduled_after=occurrence.scheduled_at,
    )
    if next_utc is None:
        return None

    existing = await _get_occurrence_by_scheduled_at(
        session,
        series_id=occurrence.series_id,
        scheduled_at=next_utc,
    )
    if existing is not None:
        return existing

    occurrence_repo = MeetingOccurrenceRepository(session)
    next_occurrence = MeetingOccurrence(
        series_id=occurrence.series_id,
        scheduled_at=next_utc,
        notes="",
        is_completed=False,
    )
    await occurrence_repo.add(next_occurrence)
    return next_occurrence


async def complete_occurrence_and_roll_forward(
    session: AsyncSession,
    *,
    occurrence: MeetingOccurrence,
    commit: bool = True,
    create_next_if_missing: bool = True,
) -> MeetingOccurrence | None:
    occ_repo = MeetingOccurrenceRepository(session)
    task_repo = TaskRepository(session)
    agenda_item_repo = AgendaItemRepository(session)
    next_occurrence = await occ_repo.get_next_for_series(
        occurrence.series_id,
        occurrence.scheduled_at,
    )

    if next_occurrence is None and create_next_if_missing:
        next_occurrence = await _ensure_next_occurrence_from_rrule(
            session,
            occurrence=occurrence,
        )

    if next_occurrence is not None:
        await task_repo.reassign_open_tasks(
            from_occurrence_id=occurrence.id,
            to_occurrence_id=next_occurrence.id,
            to_due_at=next_occurrence.scheduled_at,
        )
        await agenda_item_repo.reassign_open_items(
            from_occurrence_id=occurrence.id,
            to_occurrence_id=next_occurrence.id,
        )

    occurrence.is_completed = True
    if commit:
        await session.commit()
    else:
        await session.flush()
    return next_occurrence


async def create_task_for_occurrence(
    session: AsyncSession,
    *,
    occurrence_id: uuid.UUID,
    title: str,
    description: str | None,
    assigned_user_id: uuid.UUID,
    due_at: datetime,
) -> Task:
    task = Task(
        occurrence_id=occurrence_id,
        title=title,
        description=description,
        assigned_user_id=assigned_user_id,
        due_at=due_at,
    )
    session.add(task)
    await session.commit()
    return task


async def add_attendee_by_email(
    session: AsyncSession,
    *,
    occurrence_id: uuid.UUID,
    email: str,
) -> tuple[User | None, bool]:
    users_repo = UserRepository(session)
    attendee = await users_repo.get_by_email(email)
    if attendee is None:
        return None, False

    attendee_repo = MeetingOccurrenceAttendeeRepository(session)
    existing = await attendee_repo.get_by_occurrence_and_user(occurrence_id, attendee.id)
    if existing is not None:
        return attendee, False

    await attendee_repo.add_link(
        occurrence_id=occurrence_id,
        user_id=attendee.id,
        flush=False,
    )
    await session.commit()
    return attendee, True


async def get_task_with_occurrence(
    session: AsyncSession,
    *,
    task_id: uuid.UUID,
) -> tuple[Task, MeetingOccurrence]:
    tasks_repo = TaskRepository(session)
    task = await tasks_repo.get_by_id(task_id)
    if task is None:
        raise OccurrenceTaskNotFoundError

    occ_repo = MeetingOccurrenceRepository(session)
    occurrence = await occ_repo.get_by_id(task.occurrence_id)
    if occurrence is None:
        raise OccurrenceNotFoundError

    return task, occurrence


async def toggle_task_done(
    session: AsyncSession,
    *,
    task: Task,
) -> None:

    task.is_done = not task.is_done
    await session.commit()


async def add_agenda_item_for_occurrence(
    session: AsyncSession,
    *,
    occurrence_id: uuid.UUID,
    body: str,
    description: str | None,
) -> AgendaItem:
    item = AgendaItem(
        occurrence_id=occurrence_id,
        body=body,
        description=description,
    )
    session.add(item)
    await session.commit()
    return item


async def get_agenda_item_with_occurrence(
    session: AsyncSession,
    *,
    item_id: uuid.UUID,
) -> tuple[AgendaItem, MeetingOccurrence]:
    agenda_repo = AgendaItemRepository(session)
    item = await agenda_repo.get_by_id(item_id)
    if item is None:
        raise OccurrenceAgendaItemNotFoundError

    occ_repo = MeetingOccurrenceRepository(session)
    occurrence = await occ_repo.get_by_id(item.occurrence_id)
    if occurrence is None:
        raise OccurrenceNotFoundError

    return item, occurrence


async def convert_agenda_item_to_task(
    session: AsyncSession,
    *,
    item: AgendaItem,
    occurrence: MeetingOccurrence,
    assigned_user_id: uuid.UUID,
    due_at: datetime,
) -> Task:

    title = item.body.strip() if item.body.strip() else "Agenda follow-up"
    task = Task(
        occurrence_id=occurrence.id,
        title=title,
        description=item.description,
        assigned_user_id=assigned_user_id,
        due_at=due_at,
    )
    item.is_done = True
    session.add(task)
    await session.commit()
    return task


async def toggle_agenda_item_done(
    session: AsyncSession,
    *,
    item: AgendaItem,
) -> None:

    item.is_done = not item.is_done
    await session.commit()
