from __future__ import annotations

import argparse
import asyncio
import logging
from datetime import datetime

import agendable.db as db
from agendable.db.models import Base, Reminder
from agendable.db.repos import (
    ExternalCalendarConnectionRepository,
    ExternalCalendarEventMirrorRepository,
    ReminderRepository,
)
from agendable.db.repos.reminders import claim_reminder_attempt as claim_reminder_attempt_in_repo
from agendable.logging_config import configure_logging
from agendable.reminders import ReminderSender, build_reminder_sender
from agendable.services.calendar_event_mapping_service import CalendarEventMappingService
from agendable.services.google_calendar_client import GoogleCalendarHttpClient
from agendable.services.google_calendar_sync_service import GoogleCalendarSyncService
from agendable.services.reminder_delivery_service import run_due_reminders
from agendable.settings import get_settings

logger = logging.getLogger(__name__)


async def _init_db() -> None:
    async with db.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def _claim_reminder_attempt(*, reminder: Reminder, now: datetime) -> bool:
    settings = get_settings()
    return await claim_reminder_attempt_in_repo(
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
        await _run_due_reminders()
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
            event_mapper=CalendarEventMappingService(session=session),
        )
        synced_event_count = await sync_service.sync_all_enabled_connections()

    logger.info("google calendar sync complete: synced_event_count=%s", synced_event_count)
    return synced_event_count


async def _run_google_calendar_sync_worker(poll_seconds: int) -> None:
    while True:
        await _run_google_calendar_sync()
        await asyncio.sleep(poll_seconds)


def main() -> None:
    parser = argparse.ArgumentParser(prog="agendable")
    sub = parser.add_subparsers(dest="cmd", required=True)
    settings = get_settings()
    configure_logging(settings)

    sub.add_parser("init-db")
    sub.add_parser("run-reminders")
    sub.add_parser("run-google-calendar-sync")
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
    elif args.cmd == "run-reminders":
        asyncio.run(_run_due_reminders())
    elif args.cmd == "run-reminders-worker":
        poll_seconds = max(1, int(args.poll_seconds))
        asyncio.run(_run_reminders_worker(poll_seconds))
    elif args.cmd == "run-google-calendar-sync":
        asyncio.run(_run_google_calendar_sync())
    elif args.cmd == "run-google-calendar-sync-worker":
        poll_seconds = max(1, int(args.poll_seconds))
        asyncio.run(_run_google_calendar_sync_worker(poll_seconds))
    else:
        raise SystemExit(2)
