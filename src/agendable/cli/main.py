from __future__ import annotations

import argparse
import asyncio
import logging

from agendable.cli.calendar_sync import run_google_calendar_sync, run_google_calendar_sync_worker
from agendable.cli.db import check_db, init_db
from agendable.cli.reminders import run_due_reminders, run_reminders_worker
from agendable.cli.seed import seed_dev_data
from agendable.logging_config import configure_logging
from agendable.settings import get_settings

logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(prog="agendable")
    sub = parser.add_subparsers(dest="cmd", required=True)
    settings = get_settings()
    configure_logging(settings)

    sub.add_parser("init-db")
    check_db_parser = sub.add_parser("check-db")
    check_db_parser.add_argument(
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
        asyncio.run(init_db())
    elif args.cmd == "check-db":
        timeout_seconds = max(0.1, float(args.timeout_seconds))
        try:
            asyncio.run(check_db(timeout_seconds=timeout_seconds))
        except Exception:
            logger.exception("db healthcheck failed")
            raise SystemExit(1) from None
    elif args.cmd == "run-reminders":
        asyncio.run(run_due_reminders())
    elif args.cmd == "run-reminders-worker":
        poll_seconds = max(1, int(args.poll_seconds))
        asyncio.run(run_reminders_worker(poll_seconds))
    elif args.cmd == "run-google-calendar-sync":
        asyncio.run(run_google_calendar_sync())
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
        asyncio.run(run_google_calendar_sync_worker(poll_seconds))
    else:
        raise SystemExit(2)
