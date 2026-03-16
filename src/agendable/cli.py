from __future__ import annotations

import argparse
import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine

import agendable.db as db
from agendable.auth import hash_password
from agendable.db.models import (
    AgendaItem,
    Base,
    MeetingOccurrence,
    MeetingSeries,
    Reminder,
    Task,
    User,
)
from agendable.db.repos import (
    ExternalCalendarConnectionRepository,
    ExternalCalendarEventMirrorRepository,
    MeetingOccurrenceAttendeeRepository,
    ReminderRepository,
)
from agendable.logging_config import configure_logging, log_with_fields
from agendable.recurrence import build_rrule
from agendable.reminders import ReminderSender, build_reminder_sender
from agendable.services.calendar_event_mapping_service import CalendarEventMappingService
from agendable.services.google_calendar_client import GoogleCalendarHttpClient
from agendable.services.google_calendar_sync_service import GoogleCalendarSyncService
from agendable.services.reminder_claim_service import (
    claim_reminder_attempt as claim_reminder_attempt_in_service,
)
from agendable.services.reminder_delivery_service import run_due_reminders
from agendable.services.series_service import create_series_with_occurrences
from agendable.settings import get_settings

logger = logging.getLogger(__name__)


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


async def _init_db() -> None:
    async with db.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


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


async def seed_dev_data(*, reset: bool, password: str) -> _SeedSummary:
    settings = get_settings()
    summary = _SeedSummary(reset_applied=reset)

    if reset:
        await _reset_database()

    users_created = 0
    series_created = 0
    occurrences_created = 0
    attendees_added = 0
    agenda_items_created = 0
    tasks_created = 0

    async with db.SessionMaker() as session:
        user_by_email: dict[str, User] = {}

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

        attendee_repo = MeetingOccurrenceAttendeeRepository(session)

        for series_spec in _seed_series():
            owner = user_by_email[series_spec.owner_email]
            existing_series = (
                await session.execute(
                    select(MeetingSeries).where(
                        MeetingSeries.owner_user_id == owner.id,
                        MeetingSeries.title == series_spec.title,
                    )
                )
            ).scalar_one_or_none()

            if existing_series is None:
                series, occurrences = await create_series_with_occurrences(
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
                series_created += 1
                occurrences_created += len(occurrences)
            else:
                series = existing_series
                occurrences = list(
                    (
                        await session.execute(
                            select(MeetingOccurrence)
                            .where(MeetingOccurrence.series_id == series.id)
                            .order_by(MeetingOccurrence.scheduled_at.asc())
                        )
                    )
                    .scalars()
                    .all()
                )

            attendee_users = [user_by_email[email] for email in series_spec.attendee_emails]

            for occurrence_index, occurrence in enumerate(occurrences):
                occurrence.is_completed = occurrence_index < max(0, len(occurrences) - 2)

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

        await session.commit()

    return _SeedSummary(
        users_created=users_created,
        series_created=series_created,
        occurrences_created=occurrences_created,
        attendees_added=attendees_added,
        agenda_items_created=agenda_items_created,
        tasks_created=tasks_created,
        reset_applied=summary.reset_applied,
    )


async def _claim_reminder_attempt(*, reminder: Reminder, now: datetime) -> bool:
    settings = get_settings()
    return await claim_reminder_attempt_in_service(
        reminder=reminder,
        now=now,
        claim_lease_seconds=settings.reminder_claim_lease_seconds,
    )


async def _run_due_reminders(sender: ReminderSender | None = None) -> None:
    settings = get_settings()
    selected_sender = sender if sender is not None else build_reminder_sender(settings)
    async with db.SessionMaker() as session:
        reminder_repo = ReminderRepository(session)
        await run_due_reminders(
            reminder_repo=reminder_repo,
            sender=selected_sender,
            logger=logger,
            settings=settings,
            claim_attempt=_claim_reminder_attempt,
        )


async def _run_reminders_worker(poll_seconds: int) -> None:
    while True:
        started_at = datetime.now(UTC)
        try:
            await _run_due_reminders()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("reminders worker iteration failed")
        finally:
            duration_ms = int((datetime.now(UTC) - started_at).total_seconds() * 1000)
            log_with_fields(
                logger,
                logging.INFO,
                "reminders worker iteration complete",
                duration_ms=duration_ms,
            )
        await asyncio.sleep(poll_seconds)


async def _run_google_calendar_sync() -> int:
    settings = get_settings()
    if not settings.google_calendar_sync_enabled:
        logger.info("google calendar sync skipped: feature disabled")
        return 0

    async with db.SessionMaker() as session:
        sync_service = GoogleCalendarSyncService(
            connection_repo=ExternalCalendarConnectionRepository(session),
            event_mirror_repo=ExternalCalendarEventMirrorRepository(session),
            calendar_client=GoogleCalendarHttpClient(
                api_base_url=settings.google_calendar_api_base_url,
                initial_sync_days_back=settings.google_calendar_initial_sync_days_back,
            ),
            event_mapper=CalendarEventMappingService.from_session(session),
            settings=settings,
        )
        synced_event_count = await sync_service.sync_all_enabled_connections()

    logger.info("google calendar sync complete: synced_event_count=%s", synced_event_count)
    return synced_event_count


async def _run_google_calendar_sync_worker(poll_seconds: int) -> None:
    while True:
        started_at = datetime.now(UTC)
        synced_event_count: int | None = None
        try:
            synced_event_count = await _run_google_calendar_sync()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("google calendar sync worker iteration failed")
        finally:
            duration_ms = int((datetime.now(UTC) - started_at).total_seconds() * 1000)
            log_with_fields(
                logger,
                logging.INFO,
                "google calendar sync worker iteration complete",
                duration_ms=duration_ms,
                synced_event_count=synced_event_count,
            )
        await asyncio.sleep(poll_seconds)


async def _check_db(*, timeout_seconds: float) -> None:
    async def _ping() -> None:
        async with db.engine.connect() as conn:
            await conn.execute(text("SELECT 1"))

    await asyncio.wait_for(_ping(), timeout=timeout_seconds)


def main() -> None:
    parser = argparse.ArgumentParser(prog="agendable")
    sub = parser.add_subparsers(dest="cmd", required=True)
    settings = get_settings()
    configure_logging(settings)

    sub.add_parser("init-db")
    check_db = sub.add_parser("check-db")
    check_db.add_argument(
        "--timeout-seconds",
        type=float,
        default=5.0,
        help="Fail if the DB ping exceeds this timeout.",
    )
    sub.add_parser("run-reminders")
    sub.add_parser("run-google-calendar-sync")
    seed = sub.add_parser(
        "seed-dev-data",
        help="Create deterministic local sample data for recurring meetings, tasks, and agenda items.",
    )
    seed.add_argument(
        "--reset",
        action="store_true",
        help="Drop and recreate all tables before seeding.",
    )
    seed.add_argument(
        "--password",
        type=str,
        default="Password123!",
        help="Password applied to seeded users.",
    )
    worker = sub.add_parser("run-reminders-worker")
    worker.add_argument(
        "--poll-seconds",
        type=int,
        default=settings.reminder_worker_poll_seconds,
    )
    google_worker = sub.add_parser("run-google-calendar-sync-worker")
    google_worker.add_argument(
        "--poll-seconds",
        type=int,
        default=settings.google_calendar_sync_worker_poll_seconds,
    )

    args = parser.parse_args()

    if args.cmd == "init-db":
        asyncio.run(_init_db())
    elif args.cmd == "check-db":
        timeout_seconds = max(0.1, float(args.timeout_seconds))
        try:
            asyncio.run(_check_db(timeout_seconds=timeout_seconds))
        except Exception:
            logger.exception("db healthcheck failed")
            raise SystemExit(1) from None
    elif args.cmd == "run-reminders":
        asyncio.run(_run_due_reminders())
    elif args.cmd == "run-reminders-worker":
        poll_seconds = max(1, int(args.poll_seconds))
        asyncio.run(_run_reminders_worker(poll_seconds))
    elif args.cmd == "run-google-calendar-sync":
        asyncio.run(_run_google_calendar_sync())
    elif args.cmd == "seed-dev-data":
        summary = asyncio.run(seed_dev_data(reset=bool(args.reset), password=str(args.password)))
        logger.info(
            "seed-dev-data complete: reset=%s users_created=%s series_created=%s occurrences_created=%s attendees_added=%s agenda_items_created=%s tasks_created=%s",
            summary.reset_applied,
            summary.users_created,
            summary.series_created,
            summary.occurrences_created,
            summary.attendees_added,
            summary.agenda_items_created,
            summary.tasks_created,
        )
    elif args.cmd == "run-google-calendar-sync-worker":
        poll_seconds = max(1, int(args.poll_seconds))
        asyncio.run(_run_google_calendar_sync_worker(poll_seconds))
    else:
        raise SystemExit(2)
