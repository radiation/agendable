from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

import agendable.db as db
from agendable.auth import hash_password
from agendable.db.models import AgendaItem, Base, MeetingOccurrence, MeetingSeries, Task, User
from agendable.db.repos import MeetingOccurrenceAttendeeRepository
from agendable.recurrence import build_rrule
from agendable.services.series_service import create_series_with_occurrences
from agendable.settings import Settings, get_settings


@dataclass(frozen=True)
class _SeedUserSpec:
    email: str
    first_name: str
    last_name: str
    timezone: str


@dataclass(frozen=True)
class _SeedSeriesSpec:
    owner_email: str
    title: str
    recurrence_rrule: str
    recurrence_dtstart: datetime
    recurrence_timezone: str
    reminder_minutes_before: int
    generate_count: int
    attendee_emails: tuple[str, ...]


@dataclass(frozen=True)
class _SeedSummary:
    users_created: int = 0
    series_created: int = 0
    occurrences_created: int = 0
    attendees_added: int = 0
    agenda_items_created: int = 0
    tasks_created: int = 0
    reset_applied: bool = False


@dataclass
class _SeedCounters:
    users_created: int = 0
    series_created: int = 0
    occurrences_created: int = 0
    attendees_added: int = 0
    agenda_items_created: int = 0
    tasks_created: int = 0


async def _reset_database() -> None:
    bind = db.SessionMaker.kw.get("bind")
    if bind is None or not isinstance(bind, AsyncEngine):
        raise RuntimeError("SessionMaker is not bound to an async engine")

    async with bind.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)


def _seed_users() -> tuple[_SeedUserSpec, ...]:
    return (
        _SeedUserSpec(
            email="alex.manager+seed@example.com",
            first_name="Alex",
            last_name="Manager",
            timezone="America/Chicago",
        ),
        _SeedUserSpec(
            email="jamie.engineer+seed@example.com",
            first_name="Jamie",
            last_name="Engineer",
            timezone="America/New_York",
        ),
        _SeedUserSpec(
            email="riley.designer+seed@example.com",
            first_name="Riley",
            last_name="Designer",
            timezone="America/Los_Angeles",
        ),
    )


def _seed_series() -> tuple[_SeedSeriesSpec, ...]:
    now_utc = datetime.now(UTC)

    one_on_one_tz = ZoneInfo("America/Chicago")
    one_on_one_start = (
        (now_utc - timedelta(days=28))
        .astimezone(one_on_one_tz)
        .replace(
            hour=10,
            minute=0,
            second=0,
            microsecond=0,
        )
    )

    design_sync_tz = ZoneInfo("America/Los_Angeles")
    design_sync_start = (
        (now_utc - timedelta(days=21))
        .astimezone(design_sync_tz)
        .replace(
            hour=14,
            minute=30,
            second=0,
            microsecond=0,
        )
    )

    planning_tz = ZoneInfo("America/New_York")
    planning_start = (
        (now_utc - timedelta(days=12))
        .astimezone(planning_tz)
        .replace(
            hour=9,
            minute=15,
            second=0,
            microsecond=0,
        )
    )

    return (
        _SeedSeriesSpec(
            owner_email="alex.manager+seed@example.com",
            title="[Seed] 1:1 Alex <> Jamie",
            recurrence_rrule=build_rrule(
                freq="WEEKLY",
                interval=1,
                dtstart=one_on_one_start,
                weekly_byday=["MO"],
            ),
            recurrence_dtstart=one_on_one_start,
            recurrence_timezone="America/Chicago",
            reminder_minutes_before=30,
            generate_count=10,
            attendee_emails=(
                "alex.manager+seed@example.com",
                "jamie.engineer+seed@example.com",
            ),
        ),
        _SeedSeriesSpec(
            owner_email="riley.designer+seed@example.com",
            title="[Seed] Product Design Sync",
            recurrence_rrule=build_rrule(
                freq="WEEKLY",
                interval=1,
                dtstart=design_sync_start,
                weekly_byday=["WE"],
            ),
            recurrence_dtstart=design_sync_start,
            recurrence_timezone="America/Los_Angeles",
            reminder_minutes_before=45,
            generate_count=12,
            attendee_emails=(
                "riley.designer+seed@example.com",
                "alex.manager+seed@example.com",
                "jamie.engineer+seed@example.com",
            ),
        ),
        _SeedSeriesSpec(
            owner_email="jamie.engineer+seed@example.com",
            title="[Seed] Engineering Planning",
            recurrence_rrule=build_rrule(
                freq="DAILY",
                interval=2,
                dtstart=planning_start,
            ),
            recurrence_dtstart=planning_start,
            recurrence_timezone="America/New_York",
            reminder_minutes_before=20,
            generate_count=14,
            attendee_emails=(
                "jamie.engineer+seed@example.com",
                "alex.manager+seed@example.com",
            ),
        ),
    )


async def _get_or_create_seed_users(
    session: AsyncSession,
    *,
    password: str,
) -> tuple[dict[str, User], int]:
    user_by_email: dict[str, User] = {}
    users_created = 0

    for spec in _seed_users():
        existing_user = (
            await session.execute(select(User).where(User.email == spec.email))
        ).scalar_one_or_none()
        if existing_user is not None:
            user_by_email[spec.email] = existing_user
            continue

        created_user = User(
            email=spec.email,
            first_name=spec.first_name,
            last_name=spec.last_name,
            display_name=f"{spec.first_name} {spec.last_name}",
            timezone=spec.timezone,
            password_hash=hash_password(password),
        )
        session.add(created_user)
        await session.flush()
        user_by_email[spec.email] = created_user
        users_created += 1

    return user_by_email, users_created


async def _get_or_create_series_with_occurrences(
    session: AsyncSession,
    *,
    series_spec: _SeedSeriesSpec,
    owner: User,
    settings: Settings,
) -> tuple[list[MeetingOccurrence], int, int]:
    existing_series = (
        await session.execute(
            select(MeetingSeries).where(
                MeetingSeries.owner_user_id == owner.id,
                MeetingSeries.title == series_spec.title,
            )
        )
    ).scalar_one_or_none()

    if existing_series is None:
        _, occurrences = await create_series_with_occurrences(
            session,
            owner_user_id=owner.id,
            title=series_spec.title,
            reminder_minutes_before=series_spec.reminder_minutes_before,
            recurrence_rrule=series_spec.recurrence_rrule,
            recurrence_dtstart=series_spec.recurrence_dtstart,
            recurrence_timezone=series_spec.recurrence_timezone,
            generate_count=series_spec.generate_count,
            settings=settings,
        )
        return occurrences, 1, len(occurrences)

    occurrences = list(
        (
            await session.execute(
                select(MeetingOccurrence)
                .where(MeetingOccurrence.series_id == existing_series.id)
                .order_by(MeetingOccurrence.scheduled_at.asc())
            )
        )
        .scalars()
        .all()
    )
    return occurrences, 0, 0


async def _ensure_occurrence_attendees(
    attendee_repo: MeetingOccurrenceAttendeeRepository,
    *,
    occurrence: MeetingOccurrence,
    attendee_users: list[User],
) -> int:
    attendees_added = 0
    for attendee in attendee_users:
        has_link = await attendee_repo.get_by_occurrence_and_user(
            occurrence_id=occurrence.id,
            user_id=attendee.id,
        )
        if has_link is not None:
            continue
        await attendee_repo.add_link(
            occurrence_id=occurrence.id,
            user_id=attendee.id,
            flush=False,
        )
        attendees_added += 1
    return attendees_added


async def _ensure_occurrence_agenda_items(
    session: AsyncSession,
    *,
    occurrence: MeetingOccurrence,
    occurrence_index: int,
) -> int:
    agenda_items_created = 0
    agenda_titles = [
        "Wins since last check-in",
        "Blockers and risks",
    ]

    for agenda_index, agenda_title in enumerate(agenda_titles):
        existing_agenda = (
            await session.execute(
                select(AgendaItem).where(
                    AgendaItem.occurrence_id == occurrence.id,
                    AgendaItem.body == agenda_title,
                )
            )
        ).scalar_one_or_none()
        if existing_agenda is not None:
            continue

        session.add(
            AgendaItem(
                occurrence_id=occurrence.id,
                body=agenda_title,
                description="Seeded item for layout/dev testing.",
                is_done=((occurrence_index + agenda_index) % 2 == 0),
            )
        )
        agenda_items_created += 1

    return agenda_items_created


async def _ensure_occurrence_tasks(
    session: AsyncSession,
    *,
    occurrence: MeetingOccurrence,
    occurrence_index: int,
    owner: User,
    attendee_users: list[User],
) -> int:
    tasks_created = 0
    assignees = attendee_users if attendee_users else [owner]
    task_specs = (
        ("Prepare updates", 0),
        ("Follow up action items", 1),
    )

    for task_index, (task_title, day_offset) in enumerate(task_specs):
        existing_task = (
            await session.execute(
                select(Task).where(
                    Task.occurrence_id == occurrence.id,
                    Task.title == task_title,
                )
            )
        ).scalar_one_or_none()
        if existing_task is not None:
            continue

        assignee = assignees[(occurrence_index + task_index) % len(assignees)]
        session.add(
            Task(
                occurrence_id=occurrence.id,
                assigned_user_id=assignee.id,
                title=task_title,
                description="Seeded task for local UX iteration.",
                due_at=occurrence.scheduled_at + timedelta(days=day_offset),
                is_done=((occurrence_index + task_index) % 3 == 0),
            )
        )
        tasks_created += 1

    return tasks_created


async def _seed_series_occurrences(
    session: AsyncSession,
    attendee_repo: MeetingOccurrenceAttendeeRepository,
    *,
    owner: User,
    occurrences: list[MeetingOccurrence],
    attendee_users: list[User],
) -> tuple[int, int, int]:
    attendees_added = 0
    agenda_items_created = 0
    tasks_created = 0

    for occurrence_index, occurrence in enumerate(occurrences):
        occurrence.is_completed = occurrence_index < max(0, len(occurrences) - 2)
        attendees_added += await _ensure_occurrence_attendees(
            attendee_repo,
            occurrence=occurrence,
            attendee_users=attendee_users,
        )
        agenda_items_created += await _ensure_occurrence_agenda_items(
            session,
            occurrence=occurrence,
            occurrence_index=occurrence_index,
        )
        tasks_created += await _ensure_occurrence_tasks(
            session,
            occurrence=occurrence,
            occurrence_index=occurrence_index,
            owner=owner,
            attendee_users=attendee_users,
        )

    return attendees_added, agenda_items_created, tasks_created


async def _seed_series_data(
    session: AsyncSession,
    attendee_repo: MeetingOccurrenceAttendeeRepository,
    *,
    series_spec: _SeedSeriesSpec,
    user_by_email: dict[str, User],
    settings: Settings,
) -> tuple[int, int, int, int, int]:
    owner = user_by_email[series_spec.owner_email]
    occurrences, series_created, occurrences_created = await _get_or_create_series_with_occurrences(
        session,
        series_spec=series_spec,
        owner=owner,
        settings=settings,
    )
    attendee_users = [user_by_email[email] for email in series_spec.attendee_emails]
    attendees_added, agenda_items_created, tasks_created = await _seed_series_occurrences(
        session,
        attendee_repo,
        owner=owner,
        occurrences=occurrences,
        attendee_users=attendee_users,
    )

    return (
        series_created,
        occurrences_created,
        attendees_added,
        agenda_items_created,
        tasks_created,
    )


def _build_seed_summary(*, counters: _SeedCounters, reset_applied: bool) -> _SeedSummary:
    return _SeedSummary(
        users_created=counters.users_created,
        series_created=counters.series_created,
        occurrences_created=counters.occurrences_created,
        attendees_added=counters.attendees_added,
        agenda_items_created=counters.agenda_items_created,
        tasks_created=counters.tasks_created,
        reset_applied=reset_applied,
    )


async def seed_dev_data(*, reset: bool, password: str) -> _SeedSummary:
    settings = get_settings()

    if reset:
        await _reset_database()

    counters = _SeedCounters()
    async with db.SessionMaker() as session:
        user_by_email, counters.users_created = await _get_or_create_seed_users(
            session,
            password=password,
        )
        attendee_repo = MeetingOccurrenceAttendeeRepository(session)

        for series_spec in _seed_series():
            (
                series_created,
                occurrences_created,
                attendees_added,
                agenda_items_created,
                tasks_created,
            ) = await _seed_series_data(
                session,
                attendee_repo,
                series_spec=series_spec,
                user_by_email=user_by_email,
                settings=settings,
            )
            counters.series_created += series_created
            counters.occurrences_created += occurrences_created
            counters.attendees_added += attendees_added
            counters.agenda_items_created += agenda_items_created
            counters.tasks_created += tasks_created

        await session.commit()

    return _build_seed_summary(counters=counters, reset_applied=reset)
