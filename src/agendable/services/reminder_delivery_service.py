from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import agendable.db as db
from agendable.db.models import Reminder, ReminderChannel, ReminderDeliveryStatus
from agendable.db.repos import ReminderRepository
from agendable.logging_config import log_with_fields
from agendable.reminders import ReminderDeliveryError, ReminderEmail, ReminderSender, as_utc
from agendable.settings import Settings, get_settings


@dataclass(slots=True)
class ReminderRunStats:
    attempted: int = 0
    sent: int = 0
    failed: int = 0
    skipped: int = 0
    retried: int = 0
    failure_reason_counts: Counter[str] = field(default_factory=Counter)


def _is_reminder_due(reminder: Reminder, now: datetime) -> bool:
    next_attempt_at = reminder.next_attempt_at if reminder.next_attempt_at else reminder.send_at
    return as_utc(next_attempt_at) <= now


async def claim_reminder_attempt(*, reminder: Reminder, now: datetime) -> bool:
    settings = get_settings()
    async with db.SessionMaker() as claim_session:
        reminder_repo = ReminderRepository(claim_session)
        was_claimed = await reminder_repo.try_claim_attempt(
            reminder_id=reminder.id,
            expected_attempt_count=reminder.attempt_count,
            now=now,
            claim_lease_seconds=settings.reminder_claim_lease_seconds,
        )
        if not was_claimed:
            return False

        await claim_session.commit()

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


def _log_run_summary(
    *, logger: logging.Logger, started_at: datetime, stats: ReminderRunStats
) -> None:
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


async def run_due_reminders(
    *,
    sender: ReminderSender,
    logger: logging.Logger,
    settings: Settings | None = None,
    claim_attempt: Callable[..., Awaitable[bool]] | None = None,
) -> None:
    selected_settings = settings if settings is not None else get_settings()
    started_at = datetime.now(UTC)
    now = started_at
    stats = ReminderRunStats()
    selected_claim_attempt = claim_attempt if claim_attempt is not None else claim_reminder_attempt

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

            was_claimed = await selected_claim_attempt(reminder=reminder, now=now)
            if not was_claimed:
                continue

            stats.attempted += 1

            try:
                await sender.send_email_reminder(_build_reminder_email(reminder))
            except ReminderDeliveryError as exc:
                reminder.failure_reason_code = exc.reason_code
                stats.failure_reason_counts[exc.reason_code] += 1
                if (
                    exc.is_transient
                    and reminder.attempt_count < selected_settings.reminder_retry_max_attempts
                ):
                    backoff_seconds = selected_settings.reminder_retry_backoff_seconds * (
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

    _log_run_summary(logger=logger, started_at=started_at, stats=stats)
