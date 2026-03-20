from __future__ import annotations

import uuid
from datetime import UTC, datetime, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dateutil.rrule import rrulestr
from sqlalchemy.ext.asyncio import AsyncSession

from agendable.datetime_utils import format_datetime_local_value
from agendable.db.models import AgendaItem, MeetingOccurrence, MeetingSeries, Task, User
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


class OccurrenceService:
    def __init__(
        self,
        *,
        session: AsyncSession,
        agenda_items: AgendaItemRepository | None = None,
        attendees: MeetingOccurrenceAttendeeRepository | None = None,
        occurrences: MeetingOccurrenceRepository | None = None,
        series: MeetingSeriesRepository | None = None,
        tasks: TaskRepository | None = None,
        users: UserRepository | None = None,
    ) -> None:
        self.session = session
        self.agenda_items = agenda_items or AgendaItemRepository(session)
        self.attendees = attendees or MeetingOccurrenceAttendeeRepository(session)
        self.occurrences = occurrences or MeetingOccurrenceRepository(session)
        self.series = series or MeetingSeriesRepository(session)
        self.tasks = tasks or TaskRepository(session)
        self.users = users or UserRepository(session)

    @classmethod
    def from_session(cls, session: AsyncSession) -> OccurrenceService:
        return cls(
            session=session,
            agenda_items=AgendaItemRepository(session),
            attendees=MeetingOccurrenceAttendeeRepository(session),
            occurrences=MeetingOccurrenceRepository(session),
            series=MeetingSeriesRepository(session),
            tasks=TaskRepository(session),
            users=UserRepository(session),
        )

    async def _get_occurrence_by_scheduled_at(
        self,
        *,
        series_id: uuid.UUID,
        scheduled_at: datetime,
    ) -> MeetingOccurrence | None:
        return await self.occurrences.get_for_series_scheduled_at(
            series_id=series_id,
            scheduled_at=scheduled_at,
        )

    async def _ensure_next_occurrence_from_rrule(
        self,
        *,
        occurrence: MeetingOccurrence,
    ) -> MeetingOccurrence | None:
        series = await self.series.get(occurrence.series_id)
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

        existing = await self._get_occurrence_by_scheduled_at(
            series_id=occurrence.series_id,
            scheduled_at=next_utc,
        )
        if existing is not None:
            return existing

        next_occurrence = MeetingOccurrence(
            series_id=occurrence.series_id,
            scheduled_at=next_utc,
            notes="",
            is_completed=False,
        )
        await self.occurrences.add(next_occurrence)
        return next_occurrence

    async def get_owned_occurrence(
        self,
        *,
        occurrence_id: uuid.UUID,
        owner_user_id: uuid.UUID,
    ) -> tuple[MeetingOccurrence | None, MeetingSeries | None]:
        occurrence = await self.occurrences.get_by_id(occurrence_id)
        if occurrence is None:
            return None, None

        series = await self.series.get_for_owner(occurrence.series_id, owner_user_id)
        if series is None:
            return None, None

        return occurrence, series

    async def get_accessible_occurrence(
        self,
        *,
        occurrence_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> tuple[MeetingOccurrence | None, MeetingSeries | None]:
        occurrence_with_series = await self.occurrences.get_occurrence_with_series_for_user(
            occurrence_id=occurrence_id,
            user_id=user_id,
        )
        if occurrence_with_series is None:
            return None, None
        return occurrence_with_series

    async def list_occurrence_attendee_users(
        self,
        *,
        occurrence_id: uuid.UUID,
        current_user: User,
    ) -> list[User]:
        attendee_links = await self.attendees.list_for_occurrence_with_users(occurrence_id)

        attendee_users = [current_user]
        attendee_user_ids: set[uuid.UUID] = {current_user.id}
        for link in attendee_links:
            if link.user_id in attendee_user_ids:
                continue
            attendee_users.append(link.user)
            attendee_user_ids.add(link.user_id)

        return attendee_users

    async def assignee_exists(
        self,
        *,
        assignee_id: uuid.UUID,
    ) -> bool:
        assignee = await self.users.get_by_id(assignee_id)
        return assignee is not None

    async def is_occurrence_attendee(
        self,
        *,
        occurrence_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> bool:
        return await self.attendees.has_occurrence_user_link(
            occurrence_id=occurrence_id,
            user_id=user_id,
        )

    async def get_default_task_due_at(
        self,
        *,
        occurrence: MeetingOccurrence,
    ) -> datetime:
        next_occurrence = await self.occurrences.get_next_for_series(
            occurrence.series_id,
            occurrence.scheduled_at,
        )
        if next_occurrence is not None:
            return next_occurrence.scheduled_at
        return occurrence.scheduled_at

    async def task_due_default_value(
        self,
        *,
        occurrence: MeetingOccurrence,
        timezone: str,
    ) -> str:
        due_at = await self.get_default_task_due_at(occurrence=occurrence)
        return format_datetime_local_value(due_at, timezone)

    async def occurrence_collections(
        self,
        *,
        occurrence: MeetingOccurrence,
        current_user: User,
    ) -> tuple[list[Task], list[AgendaItem], list[User]]:
        tasks = await self.tasks.list_for_occurrence(occurrence.id)
        agenda_items = await self.agenda_items.list_for_occurrence(occurrence.id)
        attendee_users = await self.list_occurrence_attendee_users(
            occurrence_id=occurrence.id,
            current_user=current_user,
        )
        return tasks, agenda_items, attendee_users

    async def complete_occurrence_and_roll_forward(
        self,
        *,
        occurrence: MeetingOccurrence,
        commit: bool = True,
        create_next_if_missing: bool = True,
    ) -> MeetingOccurrence | None:
        next_occurrence = await self.occurrences.get_next_for_series(
            occurrence.series_id,
            occurrence.scheduled_at,
        )

        if next_occurrence is None and create_next_if_missing:
            next_occurrence = await self._ensure_next_occurrence_from_rrule(
                occurrence=occurrence,
            )

        if next_occurrence is not None:
            await self.tasks.reassign_open_tasks(
                from_occurrence_id=occurrence.id,
                to_occurrence_id=next_occurrence.id,
                to_due_at=next_occurrence.scheduled_at,
            )
            await self.agenda_items.reassign_open_items(
                from_occurrence_id=occurrence.id,
                to_occurrence_id=next_occurrence.id,
            )

        occurrence.is_completed = True
        if commit:
            await self.session.commit()
        else:
            await self.session.flush()
        return next_occurrence

    async def create_task_for_occurrence(
        self,
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
        self.session.add(task)
        await self.session.commit()
        return task

    async def add_attendee_by_email(
        self,
        *,
        occurrence_id: uuid.UUID,
        email: str,
    ) -> tuple[User | None, bool]:
        attendee = await self.users.get_by_email(email)
        if attendee is None:
            return None, False

        existing = await self.attendees.get_by_occurrence_and_user(occurrence_id, attendee.id)
        if existing is not None:
            return attendee, False

        await self.attendees.add_link(
            occurrence_id=occurrence_id,
            user_id=attendee.id,
            flush=False,
        )
        await self.session.commit()
        return attendee, True

    async def get_task_with_occurrence(
        self,
        *,
        task_id: uuid.UUID,
    ) -> tuple[Task, MeetingOccurrence]:
        task = await self.tasks.get_by_id(task_id)
        if task is None:
            raise OccurrenceTaskNotFoundError

        occurrence = await self.occurrences.get_by_id(task.occurrence_id)
        if occurrence is None:
            raise OccurrenceNotFoundError

        return task, occurrence

    async def toggle_task_done(
        self,
        *,
        task: Task,
    ) -> None:
        task.is_done = not task.is_done
        await self.session.commit()

    async def add_agenda_item_for_occurrence(
        self,
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
        self.session.add(item)
        await self.session.commit()
        return item

    async def get_agenda_item_with_occurrence(
        self,
        *,
        item_id: uuid.UUID,
    ) -> tuple[AgendaItem, MeetingOccurrence]:
        item = await self.agenda_items.get_by_id(item_id)
        if item is None:
            raise OccurrenceAgendaItemNotFoundError

        occurrence = await self.occurrences.get_by_id(item.occurrence_id)
        if occurrence is None:
            raise OccurrenceNotFoundError

        return item, occurrence

    async def convert_agenda_item_to_task(
        self,
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
        self.session.add(task)
        await self.session.commit()
        return task

    async def toggle_agenda_item_done(
        self,
        *,
        item: AgendaItem,
    ) -> None:
        item.is_done = not item.is_done
        await self.session.commit()


async def complete_occurrence_and_roll_forward(
    session: AsyncSession,
    *,
    occurrence: MeetingOccurrence,
    commit: bool = True,
    create_next_if_missing: bool = True,
) -> MeetingOccurrence | None:
    return await OccurrenceService.from_session(session).complete_occurrence_and_roll_forward(
        occurrence=occurrence,
        commit=commit,
        create_next_if_missing=create_next_if_missing,
    )


async def create_task_for_occurrence(
    session: AsyncSession,
    *,
    occurrence_id: uuid.UUID,
    title: str,
    description: str | None,
    assigned_user_id: uuid.UUID,
    due_at: datetime,
) -> Task:
    return await OccurrenceService.from_session(session).create_task_for_occurrence(
        occurrence_id=occurrence_id,
        title=title,
        description=description,
        assigned_user_id=assigned_user_id,
        due_at=due_at,
    )


async def add_attendee_by_email(
    session: AsyncSession,
    *,
    occurrence_id: uuid.UUID,
    email: str,
) -> tuple[User | None, bool]:
    return await OccurrenceService.from_session(session).add_attendee_by_email(
        occurrence_id=occurrence_id,
        email=email,
    )


async def get_task_with_occurrence(
    session: AsyncSession,
    *,
    task_id: uuid.UUID,
) -> tuple[Task, MeetingOccurrence]:
    return await OccurrenceService.from_session(session).get_task_with_occurrence(task_id=task_id)


async def toggle_task_done(
    session: AsyncSession,
    *,
    task: Task,
) -> None:
    await OccurrenceService.from_session(session).toggle_task_done(task=task)


async def add_agenda_item_for_occurrence(
    session: AsyncSession,
    *,
    occurrence_id: uuid.UUID,
    body: str,
    description: str | None,
) -> AgendaItem:
    return await OccurrenceService.from_session(session).add_agenda_item_for_occurrence(
        occurrence_id=occurrence_id,
        body=body,
        description=description,
    )


async def get_agenda_item_with_occurrence(
    session: AsyncSession,
    *,
    item_id: uuid.UUID,
) -> tuple[AgendaItem, MeetingOccurrence]:
    return await OccurrenceService.from_session(session).get_agenda_item_with_occurrence(
        item_id=item_id,
    )


async def convert_agenda_item_to_task(
    session: AsyncSession,
    *,
    item: AgendaItem,
    occurrence: MeetingOccurrence,
    assigned_user_id: uuid.UUID,
    due_at: datetime,
) -> Task:
    return await OccurrenceService.from_session(session).convert_agenda_item_to_task(
        item=item,
        occurrence=occurrence,
        assigned_user_id=assigned_user_id,
        due_at=due_at,
    )


async def toggle_agenda_item_done(
    session: AsyncSession,
    *,
    item: AgendaItem,
) -> None:
    await OccurrenceService.from_session(session).toggle_agenda_item_done(item=item)


async def get_owned_occurrence(
    session: AsyncSession,
    *,
    occurrence_id: uuid.UUID,
    owner_user_id: uuid.UUID,
) -> tuple[MeetingOccurrence | None, MeetingSeries | None]:
    return await OccurrenceService.from_session(session).get_owned_occurrence(
        occurrence_id=occurrence_id,
        owner_user_id=owner_user_id,
    )


async def get_accessible_occurrence(
    session: AsyncSession,
    *,
    occurrence_id: uuid.UUID,
    user_id: uuid.UUID,
) -> tuple[MeetingOccurrence | None, MeetingSeries | None]:
    return await OccurrenceService.from_session(session).get_accessible_occurrence(
        occurrence_id=occurrence_id,
        user_id=user_id,
    )


async def list_occurrence_attendee_users(
    session: AsyncSession,
    *,
    occurrence_id: uuid.UUID,
    current_user: User,
) -> list[User]:
    return await OccurrenceService.from_session(session).list_occurrence_attendee_users(
        occurrence_id=occurrence_id,
        current_user=current_user,
    )


async def assignee_exists(
    session: AsyncSession,
    *,
    assignee_id: uuid.UUID,
) -> bool:
    return await OccurrenceService.from_session(session).assignee_exists(
        assignee_id=assignee_id,
    )


async def is_occurrence_attendee(
    session: AsyncSession,
    *,
    occurrence_id: uuid.UUID,
    user_id: uuid.UUID,
) -> bool:
    return await OccurrenceService.from_session(session).is_occurrence_attendee(
        occurrence_id=occurrence_id,
        user_id=user_id,
    )


async def get_default_task_due_at(
    session: AsyncSession,
    *,
    occurrence: MeetingOccurrence,
) -> datetime:
    return await OccurrenceService.from_session(session).get_default_task_due_at(
        occurrence=occurrence,
    )


async def task_due_default_value(
    session: AsyncSession,
    *,
    occurrence: MeetingOccurrence,
    timezone: str,
) -> str:
    return await OccurrenceService.from_session(session).task_due_default_value(
        occurrence=occurrence,
        timezone=timezone,
    )


async def occurrence_collections(
    session: AsyncSession,
    *,
    occurrence: MeetingOccurrence,
    current_user: User,
) -> tuple[list[Task], list[AgendaItem], list[User]]:
    return await OccurrenceService.from_session(session).occurrence_collections(
        occurrence=occurrence,
        current_user=current_user,
    )
