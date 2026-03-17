from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from agendable.auth import hash_password
from agendable.db.models import AgendaItem, Base, MeetingOccurrence, MeetingSeries, Task, User
from agendable.db.repos import (
    AgendaItemRepository,
    MeetingOccurrenceAttendeeRepository,
    MeetingOccurrenceRepository,
    MeetingSeriesRepository,
    TaskRepository,
    UserRepository,
)
from agendable.services.series_service import SeriesService
from agendable.settings import Settings


@dataclass(frozen=True)
class SeedUserSpec:
    email: str
    first_name: str
    last_name: str
    timezone: str


@dataclass(frozen=True)
class SeedSeriesSpec:
    owner_email: str
    title: str
    recurrence_rrule: str
    recurrence_dtstart: datetime
    recurrence_timezone: str
    reminder_minutes_before: int
    generate_count: int
    attendee_emails: tuple[str, ...]


@dataclass(frozen=True)
class SeedSummary:
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


async def reset_database(bind: AsyncEngine) -> None:
    async with bind.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)


class DevSeedService:
    def __init__(
        self,
        *,
        session: AsyncSession,
        settings: Settings,
        users: UserRepository | None = None,
        series: MeetingSeriesRepository | None = None,
        occurrences: MeetingOccurrenceRepository | None = None,
        attendees: MeetingOccurrenceAttendeeRepository | None = None,
        agenda_items: AgendaItemRepository | None = None,
        tasks: TaskRepository | None = None,
    ) -> None:
        self.session = session
        self.settings = settings
        self.users = users or UserRepository(session)
        self.series = series or MeetingSeriesRepository(session)
        self.occurrences = occurrences or MeetingOccurrenceRepository(session)
        self.attendees = attendees or MeetingOccurrenceAttendeeRepository(session)
        self.agenda_items = agenda_items or AgendaItemRepository(session)
        self.tasks = tasks or TaskRepository(session)
        self.series_service = SeriesService(
            session=session,
            users=self.users,
            attendees=self.attendees,
            series=self.series,
            occurrences=self.occurrences,
        )

    async def seed(
        self,
        *,
        user_specs: Sequence[SeedUserSpec],
        series_specs: Sequence[SeedSeriesSpec],
        password: str,
    ) -> SeedSummary:
        counters = _SeedCounters()
        user_by_email, counters.users_created = await self._get_or_create_users(
            user_specs=user_specs,
            password=password,
        )

        for series_spec in series_specs:
            owner = user_by_email[series_spec.owner_email]
            (
                occurrences,
                series_created,
                occurrences_created,
            ) = await self._get_or_create_occurrences(
                series_spec=series_spec,
                owner=owner,
            )
            counters.series_created += series_created
            counters.occurrences_created += occurrences_created

            attendee_users = [user_by_email[email] for email in series_spec.attendee_emails]
            attendees_added, agenda_items_created, tasks_created = await self._seed_occurrences(
                owner=owner,
                occurrences=occurrences,
                attendee_users=attendee_users,
            )
            counters.attendees_added += attendees_added
            counters.agenda_items_created += agenda_items_created
            counters.tasks_created += tasks_created

        await self.session.commit()
        return SeedSummary(
            users_created=counters.users_created,
            series_created=counters.series_created,
            occurrences_created=counters.occurrences_created,
            attendees_added=counters.attendees_added,
            agenda_items_created=counters.agenda_items_created,
            tasks_created=counters.tasks_created,
            reset_applied=False,
        )

    async def _get_or_create_users(
        self,
        *,
        user_specs: Sequence[SeedUserSpec],
        password: str,
    ) -> tuple[dict[str, User], int]:
        user_by_email: dict[str, User] = {}
        users_created = 0

        for spec in user_specs:
            existing_user = await self.users.get_by_email(spec.email)
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
            await self.users.add(created_user)
            user_by_email[spec.email] = created_user
            users_created += 1

        return user_by_email, users_created

    async def _get_or_create_occurrences(
        self,
        *,
        series_spec: SeedSeriesSpec,
        owner: User,
    ) -> tuple[list[MeetingOccurrence], int, int]:
        existing_series = await self.series.first_where(
            MeetingSeries.owner_user_id == owner.id,
            MeetingSeries.title == series_spec.title,
        )

        if existing_series is None:
            _, created_occurrences = await self.series_service.create_series_with_occurrences(
                owner_user_id=owner.id,
                title=series_spec.title,
                reminder_minutes_before=series_spec.reminder_minutes_before,
                recurrence_rrule=series_spec.recurrence_rrule,
                recurrence_dtstart=series_spec.recurrence_dtstart,
                recurrence_timezone=series_spec.recurrence_timezone,
                generate_count=series_spec.generate_count,
                settings=self.settings,
            )
            return created_occurrences, 1, len(created_occurrences)

        existing_occurrences = await self.occurrences.list_for_series(existing_series.id)
        return existing_occurrences, 0, 0

    async def _seed_occurrences(
        self,
        *,
        owner: User,
        occurrences: Sequence[MeetingOccurrence],
        attendee_users: Sequence[User],
    ) -> tuple[int, int, int]:
        attendees_added = 0
        agenda_items_created = 0
        tasks_created = 0

        for occurrence_index, occurrence in enumerate(occurrences):
            occurrence.is_completed = occurrence_index < max(0, len(occurrences) - 2)
            attendees_added += await self._ensure_attendees(
                occurrence=occurrence,
                attendee_users=attendee_users,
            )
            agenda_items_created += await self._ensure_agenda_items(
                occurrence=occurrence,
                occurrence_index=occurrence_index,
            )
            tasks_created += await self._ensure_tasks(
                occurrence=occurrence,
                occurrence_index=occurrence_index,
                owner=owner,
                attendee_users=attendee_users,
            )

        return attendees_added, agenda_items_created, tasks_created

    async def _ensure_attendees(
        self,
        *,
        occurrence: MeetingOccurrence,
        attendee_users: Sequence[User],
    ) -> int:
        attendees_added = 0
        for attendee in attendee_users:
            existing = await self.attendees.get_by_occurrence_and_user(occurrence.id, attendee.id)
            if existing is not None:
                continue
            await self.attendees.add_link(
                occurrence_id=occurrence.id,
                user_id=attendee.id,
                flush=False,
            )
            attendees_added += 1
        return attendees_added

    async def _ensure_agenda_items(
        self,
        *,
        occurrence: MeetingOccurrence,
        occurrence_index: int,
    ) -> int:
        agenda_items_created = 0
        for agenda_index, agenda_title in enumerate(
            ("Wins since last check-in", "Blockers and risks")
        ):
            existing = await self.agenda_items.first_where(
                AgendaItem.occurrence_id == occurrence.id,
                AgendaItem.body == agenda_title,
            )
            if existing is not None:
                continue

            await self.agenda_items.add(
                AgendaItem(
                    occurrence_id=occurrence.id,
                    body=agenda_title,
                    description="Seeded item for layout/dev testing.",
                    is_done=((occurrence_index + agenda_index) % 2 == 0),
                ),
                flush=False,
            )
            agenda_items_created += 1

        return agenda_items_created

    async def _ensure_tasks(
        self,
        *,
        occurrence: MeetingOccurrence,
        occurrence_index: int,
        owner: User,
        attendee_users: Sequence[User],
    ) -> int:
        tasks_created = 0
        assignees = list(attendee_users) if attendee_users else [owner]

        for task_index, (task_title, day_offset) in enumerate(
            (("Prepare updates", 0), ("Follow up action items", 1))
        ):
            existing = await self.tasks.first_where(
                Task.occurrence_id == occurrence.id,
                Task.title == task_title,
            )
            if existing is not None:
                continue

            assignee = assignees[(occurrence_index + task_index) % len(assignees)]
            await self.tasks.add(
                Task(
                    occurrence_id=occurrence.id,
                    assigned_user_id=assignee.id,
                    title=task_title,
                    description="Seeded task for local UX iteration.",
                    due_at=occurrence.scheduled_at + timedelta(days=day_offset),
                    is_done=((occurrence_index + task_index) % 3 == 0),
                ),
                flush=False,
            )
            tasks_created += 1

        return tasks_created


async def seed_dev_data(
    *,
    session_maker: async_sessionmaker[AsyncSession],
    settings: Settings,
    user_specs: Sequence[SeedUserSpec],
    series_specs: Sequence[SeedSeriesSpec],
    password: str,
) -> SeedSummary:
    async with session_maker() as session:
        service = DevSeedService(session=session, settings=settings)
        return await service.seed(
            user_specs=user_specs,
            series_specs=series_specs,
            password=password,
        )
