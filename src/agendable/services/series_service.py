from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from agendable.db.models import MeetingOccurrence, MeetingSeries, User
from agendable.db.repos import MeetingOccurrenceAttendeeRepository, UserRepository
from agendable.recurrence import generate_datetimes
from agendable.reminders import build_default_email_reminder
from agendable.settings import Settings


class UnknownAttendeeEmailsError(ValueError):
    def __init__(self, emails: list[str]) -> None:
        self.emails = emails
        super().__init__("Unknown attendee email(s): " + ", ".join(emails))


class SeriesService:
    def __init__(
        self,
        *,
        users: UserRepository,
        attendees: MeetingOccurrenceAttendeeRepository,
    ) -> None:
        self.users = users
        self.attendees = attendees

    async def list_attendee_suggestions(
        self,
        *,
        needle: str,
        current_user_id: uuid.UUID,
    ) -> list[User]:
        return await self.users.list_active_suggestions(
            needle=needle,
            exclude_user_id=current_user_id,
            limit=8,
        )

    async def resolve_attendee_user_ids(
        self,
        *,
        attendee_emails: Sequence[str],
        owner_user_id: uuid.UUID,
    ) -> set[uuid.UUID]:
        attendee_user_ids: set[uuid.UUID] = {owner_user_id}
        if not attendee_emails:
            return attendee_user_ids

        attendee_users = await self.users.list_by_emails(attendee_emails)
        attendee_users_by_email = {user.email.lower(): user for user in attendee_users}
        unknown_attendee_emails = [
            email for email in attendee_emails if email not in attendee_users_by_email
        ]
        if unknown_attendee_emails:
            raise UnknownAttendeeEmailsError(unknown_attendee_emails)

        attendee_user_ids.update(user.id for user in attendee_users)
        return attendee_user_ids

    async def link_attendees_to_occurrences(
        self,
        *,
        occurrences: Sequence[MeetingOccurrence],
        attendee_user_ids: set[uuid.UUID],
    ) -> None:
        for occurrence in occurrences:
            for attendee_user_id in attendee_user_ids:
                await self.attendees.add_link(
                    occurrence_id=occurrence.id,
                    user_id=attendee_user_id,
                    flush=False,
                )


async def create_series_with_occurrences(
    session: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    title: str,
    reminder_minutes_before: int,
    recurrence_rrule: str,
    recurrence_dtstart: datetime,
    recurrence_timezone: str,
    generate_count: int,
    settings: Settings,
) -> tuple[MeetingSeries, list[MeetingOccurrence]]:
    series = MeetingSeries(
        owner_user_id=owner_user_id,
        title=title,
        default_interval_days=7,
        reminder_minutes_before=reminder_minutes_before,
        recurrence_rrule=recurrence_rrule,
        recurrence_dtstart=recurrence_dtstart,
        recurrence_timezone=recurrence_timezone.strip(),
    )
    session.add(series)
    await session.flush()

    scheduled: Sequence[datetime] = generate_datetimes(
        rrule=recurrence_rrule,
        dtstart=recurrence_dtstart,
        count=generate_count,
    )
    if not scheduled:
        raise ValueError("RRULE produced no occurrences")

    occurrences = [
        MeetingOccurrence(
            series_id=series.id,
            scheduled_at=dt.astimezone(UTC),
            notes="",
        )
        for dt in scheduled
    ]
    session.add_all(occurrences)
    await session.flush()

    if settings.enable_default_email_reminders:
        session.add_all(
            [
                build_default_email_reminder(
                    occurrence_id=occ.id,
                    occurrence_scheduled_at=occ.scheduled_at,
                    settings=settings,
                    lead_minutes_before=series.reminder_minutes_before,
                )
                for occ in occurrences
            ]
        )

    return series, occurrences
