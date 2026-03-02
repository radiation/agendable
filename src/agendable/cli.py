from __future__ import annotations

import argparse
import asyncio
import logging
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

import agendable.db as db
from agendable.db.models import (
    Base,
    Reminder,
    ReminderChannel,
    ReminderDeliveryStatus,
)
from agendable.db.repos import ReminderRepository
from agendable.logging_config import configure_logging, log_with_fields
from agendable.reminders import (
    ReminderDeliveryError,
    ReminderEmail,
    ReminderSender,
    as_utc,
    build_reminder_sender,
)
from agendable.settings import get_settings

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ReminderRunStats:
    attempted: int = 0
    sent: int = 0
    failed: int = 0
    skipped: int = 0
    retried: int = 0
    failure_reason_counts: Counter[str] = field(default_factory=Counter)


async def _init_db() -> None:
    async with db.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def _is_reminder_due(reminder: Reminder, now: datetime) -> bool:
    next_attempt_at = reminder.next_attempt_at if reminder.next_attempt_at else reminder.send_at
    return as_utc(next_attempt_at) <= now


async def _claim_reminder_attempt(
    *,
    session: AsyncSession,
    reminder: Reminder,
    now: datetime,
) -> bool:
    reminder_repo = ReminderRepository(session)
    was_claimed = await reminder_repo.try_claim_attempt(
        reminder_id=reminder.id,
        expected_attempt_count=reminder.attempt_count,
        now=now,
    )
    if not was_claimed:
        return False

    reminder.attempt_count += 1
    reminder.last_attempted_at = now
    return True


def _build_reminder_email(reminder: Reminder) -> ReminderEmail:
    return ReminderEmail(
        recipient_email=reminder.occurrence.series.owner.email,
        meeting_title=reminder.occurrence.series.title,
        scheduled_at=as_utc(reminder.occurrence.scheduled_at),
        incomplete_tasks=[task.title for task in reminder.occurrence.tasks if not task.is_done],
    )


def _log_run_summary(*, started_at: datetime, stats: ReminderRunStats) -> None:
    duration_ms = int((datetime.now(UTC) - started_at).total_seconds() * 1000)
    log_with_fields(
        logger,
        logging.INFO,
        "reminder run complete",
        attempted=stats.attempted,
        sent=stats.sent,
        failed=stats.failed,
        skipped=stats.skipped,
        retried=stats.retried,
        duration_ms=duration_ms,
    )

    for reason_code, count in sorted(stats.failure_reason_counts.items()):
        log_with_fields(
            logger,
            logging.INFO,
            "reminder run failure reason",
            reason_code=reason_code,
            count=count,
        )


async def _run_due_reminders(sender: ReminderSender | None = None) -> None:
    settings = get_settings()
    selected_sender = sender if sender is not None else build_reminder_sender(settings)
    started_at = datetime.now(UTC)
    now = started_at
    stats = ReminderRunStats()

    async with db.SessionMaker() as session:
        reminder_repo = ReminderRepository(session)
        reminders = await reminder_repo.list_pending_for_delivery()
        for reminder in reminders:
            if not _is_reminder_due(reminder, now):
                continue

            if reminder.channel != ReminderChannel.email:
                reminder.delivery_status = ReminderDeliveryStatus.skipped
                reminder.failure_reason_code = "unsupported_channel"
                stats.skipped += 1
                continue

            was_claimed = await _claim_reminder_attempt(session=session, reminder=reminder, now=now)
            if not was_claimed:
                continue

            stats.attempted += 1

            try:
                await selected_sender.send_email_reminder(_build_reminder_email(reminder))
            except ReminderDeliveryError as exc:
                reminder.failure_reason_code = exc.reason_code
                stats.failure_reason_counts[exc.reason_code] += 1
                if (
                    exc.is_transient
                    and reminder.attempt_count < settings.reminder_retry_max_attempts
                ):
                    backoff_seconds = settings.reminder_retry_backoff_seconds * (
                        2 ** (reminder.attempt_count - 1)
                    )
                    reminder.next_attempt_at = now + timedelta(seconds=backoff_seconds)
                    reminder.delivery_status = ReminderDeliveryStatus.retry_scheduled
                    stats.retried += 1
                    log_with_fields(
                        logger,
                        logging.WARNING,
                        "reminder delivery transient failure",
                        reminder_id=reminder.id,
                        reason_code=exc.reason_code,
                        attempt_count=reminder.attempt_count,
                        next_attempt_at=reminder.next_attempt_at.isoformat(),
                        backoff_seconds=backoff_seconds,
                    )
                else:
                    reminder.delivery_status = ReminderDeliveryStatus.failed_terminal
                    stats.failed += 1
                    log_with_fields(
                        logger,
                        logging.ERROR,
                        "reminder delivery terminal failure",
                        reminder_id=reminder.id,
                        reason_code=exc.reason_code,
                        attempt_count=reminder.attempt_count,
                    )
                continue

            reminder.sent_at = now
            reminder.next_attempt_at = now
            reminder.delivery_status = ReminderDeliveryStatus.sent
            reminder.failure_reason_code = None
            stats.sent += 1

        await session.commit()

    _log_run_summary(started_at=started_at, stats=stats)


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
