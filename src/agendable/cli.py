from __future__ import annotations

import argparse
import asyncio
import logging
from datetime import datetime

import agendable.db as db
from agendable.db.models import Base, Reminder
from agendable.db.repos import ReminderRepository
from agendable.logging_config import configure_logging
from agendable.reminders import ReminderSender, build_reminder_sender
from agendable.services.reminder_delivery_service import run_due_reminders
from agendable.settings import get_settings

logger = logging.getLogger(__name__)


async def _init_db() -> None:
    async with db.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def _claim_reminder_attempt(*, reminder: Reminder, now: datetime) -> bool:
    async with db.SessionMaker() as claim_session:
        reminder_repo = ReminderRepository(claim_session)
        was_claimed = await reminder_repo.try_claim_attempt(
            reminder_id=reminder.id,
            expected_attempt_count=reminder.attempt_count,
            now=now,
        )
        if not was_claimed:
            return False
        await claim_session.commit()

    reminder.attempt_count += 1
    reminder.last_attempted_at = now
    return True


async def _run_due_reminders(sender: ReminderSender | None = None) -> None:
    settings = get_settings()
    selected_sender = sender if sender is not None else build_reminder_sender(settings)
    await run_due_reminders(
        sender=selected_sender,
        logger=logger,
        settings=settings,
        claim_attempt=_claim_reminder_attempt,
    )


async def _run_reminders_worker(poll_seconds: int) -> None:
    while True:
        await _run_due_reminders()
        await asyncio.sleep(poll_seconds)


def main() -> None:
    parser = argparse.ArgumentParser(prog="agendable")
    sub = parser.add_subparsers(dest="cmd", required=True)
    settings = get_settings()
    configure_logging(settings)

    sub.add_parser("init-db")
    sub.add_parser("run-reminders")
    worker = sub.add_parser("run-reminders-worker")
    worker.add_argument(
        "--poll-seconds",
        type=int,
        default=settings.reminder_worker_poll_seconds,
    )

    args = parser.parse_args()

    if args.cmd == "init-db":
        asyncio.run(_init_db())
    elif args.cmd == "run-reminders":
        asyncio.run(_run_due_reminders())
    elif args.cmd == "run-reminders-worker":
        poll_seconds = max(1, int(args.poll_seconds))
        asyncio.run(_run_reminders_worker(poll_seconds))
    else:
        raise SystemExit(2)
