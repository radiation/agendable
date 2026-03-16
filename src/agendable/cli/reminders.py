from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

import agendable.db as db
from agendable.db.models import Reminder
from agendable.db.repos import ReminderRepository
from agendable.logging_config import log_with_fields
from agendable.reminders import ReminderSender, build_reminder_sender
from agendable.services.reminder_claim_service import (
    claim_reminder_attempt as claim_reminder_attempt_in_service,
)
from agendable.services.reminder_delivery_service import run_due_reminders as run_due_reminders_impl
from agendable.settings import get_settings

logger = logging.getLogger(__name__)


async def claim_reminder_attempt(*, reminder: Reminder, now: datetime) -> bool:
    settings = get_settings()
    return await claim_reminder_attempt_in_service(
        reminder=reminder,
        now=now,
        claim_lease_seconds=settings.reminder_claim_lease_seconds,
    )


async def run_due_reminders(sender: ReminderSender | None = None) -> None:
    settings = get_settings()
    selected_sender = sender if sender is not None else build_reminder_sender(settings)
    async with db.SessionMaker() as session:
        reminder_repo = ReminderRepository(session)
        await run_due_reminders_impl(
            reminder_repo=reminder_repo,
            sender=selected_sender,
            logger=logger,
            settings=settings,
            claim_attempt=claim_reminder_attempt,
        )


async def run_reminders_worker(poll_seconds: int) -> None:
    while True:
        started_at = datetime.now(UTC)
        try:
            await run_due_reminders()
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
