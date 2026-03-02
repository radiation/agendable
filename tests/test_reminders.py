from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import agendable.cli as reminder_cli
import agendable.db as db
from agendable.cli import _run_due_reminders
from agendable.db.models import (
    MeetingOccurrence,
    MeetingSeries,
    Reminder,
    ReminderChannel,
    ReminderDeliveryStatus,
    Task,
    User,
)
from agendable.reminders import (
    ReminderEmail,
    ReminderSender,
    TerminalReminderDeliveryError,
    TransientReminderDeliveryError,
)


@dataclass
class CapturingSender(ReminderSender):
    sent: list[ReminderEmail]

    async def send_email_reminder(self, reminder: ReminderEmail) -> None:
        self.sent.append(reminder)


@dataclass
class TransientFailingSender(ReminderSender):
    reason_code: str

    async def send_email_reminder(self, reminder: ReminderEmail) -> None:
        _ = reminder
        raise TransientReminderDeliveryError(self.reason_code)


@dataclass
class TerminalFailingSender(ReminderSender):
    reason_code: str

    async def send_email_reminder(self, reminder: ReminderEmail) -> None:
        _ = reminder
        raise TerminalReminderDeliveryError(self.reason_code)


async def _create_occurrence(
    db_session: AsyncSession, *, email: str, title: str
) -> MeetingOccurrence:
    owner = User(
        email=email,
        first_name="Test",
        last_name="Owner",
        display_name="Test Owner",
        timezone="UTC",
        password_hash=None,
    )
    db_session.add(owner)
    await db_session.flush()

    series = MeetingSeries(owner_user_id=owner.id, title=title, default_interval_days=7)
    db_session.add(series)
    await db_session.flush()

    occurrence = MeetingOccurrence(
        series_id=series.id,
        scheduled_at=datetime.now(UTC) + timedelta(days=1),
        notes="",
        is_completed=False,
    )
    db_session.add(occurrence)
    await db_session.commit()
    await db_session.refresh(occurrence)
    return occurrence


@pytest.mark.asyncio
async def test_run_due_reminders_sends_due_email_and_marks_sent(db_session: AsyncSession) -> None:
    occurrence = await _create_occurrence(
        db_session,
        email="owner-reminder@example.com",
        title="Weekly 1:1",
    )

    due_reminder = Reminder(
        occurrence_id=occurrence.id,
        channel=ReminderChannel.email,
        send_at=datetime.now(UTC) - timedelta(minutes=1),
        sent_at=None,
    )
    future_reminder = Reminder(
        occurrence_id=occurrence.id,
        channel=ReminderChannel.email,
        send_at=datetime.now(UTC) + timedelta(hours=1),
        sent_at=None,
    )
    db_session.add_all([due_reminder, future_reminder])
    series = (
        await db_session.execute(
            select(MeetingSeries).where(MeetingSeries.id == occurrence.series_id)
        )
    ).scalar_one()
    db_session.add_all(
        [
            Task(
                occurrence_id=occurrence.id,
                assigned_user_id=series.owner_user_id,
                due_at=occurrence.scheduled_at,
                title="Prepare agenda",
                is_done=False,
            ),
            Task(
                occurrence_id=occurrence.id,
                assigned_user_id=series.owner_user_id,
                due_at=occurrence.scheduled_at,
                title="Already complete",
                is_done=True,
            ),
        ]
    )
    await db_session.commit()

    sender = CapturingSender(sent=[])
    await _run_due_reminders(sender=sender)

    assert len(sender.sent) == 1
    sent_payload = sender.sent[0]
    assert sent_payload.recipient_email == "owner-reminder@example.com"
    assert sent_payload.meeting_title == "Weekly 1:1"
    assert sent_payload.incomplete_tasks == ["Prepare agenda"]

    async with db.SessionMaker() as verify_session:
        refreshed_due = (
            await verify_session.execute(select(Reminder).where(Reminder.id == due_reminder.id))
        ).scalar_one()
        refreshed_future = (
            await verify_session.execute(select(Reminder).where(Reminder.id == future_reminder.id))
        ).scalar_one()

        assert refreshed_due.sent_at is not None
        assert refreshed_due.delivery_status == ReminderDeliveryStatus.sent
        assert refreshed_due.failure_reason_code is None
        assert refreshed_future.sent_at is None


@pytest.mark.asyncio
async def test_run_due_reminders_skips_non_email_channels(db_session: AsyncSession) -> None:
    occurrence = await _create_occurrence(
        db_session,
        email="owner-slack@example.com",
        title="Standup",
    )

    slack_reminder = Reminder(
        occurrence_id=occurrence.id,
        channel=ReminderChannel.slack,
        send_at=datetime.now(UTC) - timedelta(minutes=1),
        sent_at=None,
    )
    db_session.add(slack_reminder)
    await db_session.commit()

    sender = CapturingSender(sent=[])
    await _run_due_reminders(sender=sender)

    assert sender.sent == []

    async with db.SessionMaker() as verify_session:
        refreshed = (
            await verify_session.execute(select(Reminder).where(Reminder.id == slack_reminder.id))
        ).scalar_one()
        assert refreshed.sent_at is None
        assert refreshed.delivery_status == ReminderDeliveryStatus.skipped
        assert refreshed.failure_reason_code == "unsupported_channel"


@pytest.mark.asyncio
async def test_run_due_reminders_transient_failure_schedules_retry(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENDABLE_REMINDER_RETRY_MAX_ATTEMPTS", "3")
    monkeypatch.setenv("AGENDABLE_REMINDER_RETRY_BACKOFF_SECONDS", "30")

    occurrence = await _create_occurrence(
        db_session,
        email="owner-retry@example.com",
        title="Retry Meeting",
    )

    retry_reminder = Reminder(
        occurrence_id=occurrence.id,
        channel=ReminderChannel.email,
        send_at=datetime.now(UTC) - timedelta(minutes=2),
        next_attempt_at=datetime.now(UTC) - timedelta(minutes=1),
        sent_at=None,
    )
    db_session.add(retry_reminder)
    await db_session.commit()

    await _run_due_reminders(sender=TransientFailingSender(reason_code="smtp_unavailable"))

    async with db.SessionMaker() as verify_session:
        refreshed = (
            await verify_session.execute(select(Reminder).where(Reminder.id == retry_reminder.id))
        ).scalar_one()

        assert refreshed.sent_at is None
        assert refreshed.delivery_status == ReminderDeliveryStatus.retry_scheduled
        assert refreshed.failure_reason_code == "smtp_unavailable"
        assert refreshed.attempt_count == 1
        assert refreshed.last_attempted_at is not None
        assert refreshed.next_attempt_at is not None
        assert refreshed.next_attempt_at > refreshed.last_attempted_at
        retry_delay = (refreshed.next_attempt_at - refreshed.last_attempted_at).total_seconds()
        assert retry_delay == pytest.approx(30, rel=0, abs=1)


@pytest.mark.asyncio
async def test_run_due_reminders_terminal_failure_marks_failed(
    db_session: AsyncSession,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level("INFO", logger="agendable.cli")
    occurrence = await _create_occurrence(
        db_session,
        email="owner-failed@example.com",
        title="Failure Meeting",
    )

    failed_reminder = Reminder(
        occurrence_id=occurrence.id,
        channel=ReminderChannel.email,
        send_at=datetime.now(UTC) - timedelta(minutes=1),
        next_attempt_at=datetime.now(UTC) - timedelta(minutes=1),
        sent_at=None,
    )
    db_session.add(failed_reminder)
    await db_session.commit()

    await _run_due_reminders(sender=TerminalFailingSender(reason_code="smtp_auth_failed"))

    async with db.SessionMaker() as verify_session:
        refreshed = (
            await verify_session.execute(select(Reminder).where(Reminder.id == failed_reminder.id))
        ).scalar_one()

        assert refreshed.delivery_status == ReminderDeliveryStatus.failed_terminal
        assert refreshed.failure_reason_code == "smtp_auth_failed"
        assert refreshed.attempt_count == 1

    messages = [record.getMessage() for record in caplog.records]
    assert any("reminder run complete" in message for message in messages)
    assert any("attempted=1" in message for message in messages)
    assert any("failed=1" in message for message in messages)
    assert any("reminder run failure reason" in message for message in messages)
    assert any("reason_code=smtp_auth_failed" in message for message in messages)


@pytest.mark.asyncio
async def test_run_due_reminders_stops_retrying_at_max_attempts(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENDABLE_REMINDER_RETRY_MAX_ATTEMPTS", "2")
    monkeypatch.setenv("AGENDABLE_REMINDER_RETRY_BACKOFF_SECONDS", "15")

    occurrence = await _create_occurrence(
        db_session,
        email="owner-max@example.com",
        title="Max Attempts Meeting",
    )

    maxed_reminder = Reminder(
        occurrence_id=occurrence.id,
        channel=ReminderChannel.email,
        send_at=datetime.now(UTC) - timedelta(minutes=2),
        next_attempt_at=datetime.now(UTC) - timedelta(minutes=1),
        sent_at=None,
        attempt_count=1,
        delivery_status=ReminderDeliveryStatus.retry_scheduled,
    )
    db_session.add(maxed_reminder)
    await db_session.commit()

    await _run_due_reminders(sender=TransientFailingSender(reason_code="smtp_unavailable"))

    async with db.SessionMaker() as verify_session:
        refreshed = (
            await verify_session.execute(select(Reminder).where(Reminder.id == maxed_reminder.id))
        ).scalar_one()

        assert refreshed.delivery_status == ReminderDeliveryStatus.failed_terminal
        assert refreshed.attempt_count == 2
        assert refreshed.failure_reason_code == "smtp_unavailable"


@pytest.mark.asyncio
async def test_run_due_reminders_skips_send_when_claim_not_acquired(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    occurrence = await _create_occurrence(
        db_session,
        email="owner-claim@example.com",
        title="Claimed Elsewhere Meeting",
    )

    reminder = Reminder(
        occurrence_id=occurrence.id,
        channel=ReminderChannel.email,
        send_at=datetime.now(UTC) - timedelta(minutes=1),
        next_attempt_at=datetime.now(UTC) - timedelta(minutes=1),
        sent_at=None,
    )
    db_session.add(reminder)
    await db_session.commit()

    async def fake_claim(*, reminder: Reminder, now: datetime) -> bool:
        _ = reminder
        _ = now
        return False

    monkeypatch.setattr(reminder_cli, "_claim_reminder_attempt", fake_claim)

    sender = CapturingSender(sent=[])
    await _run_due_reminders(sender=sender)

    assert sender.sent == []

    async with db.SessionMaker() as verify_session:
        refreshed = (
            await verify_session.execute(select(Reminder).where(Reminder.id == reminder.id))
        ).scalar_one()
        assert refreshed.sent_at is None
        assert refreshed.attempt_count == 0
