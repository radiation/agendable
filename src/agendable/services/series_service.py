from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from agendable.db.models import MeetingOccurrence, MeetingSeries, User
from agendable.db.repos import (
    MeetingOccurrenceAttendeeRepository,
    MeetingOccurrenceRepository,
    MeetingSeriesRepository,
    UserRepository,
)
from agendable.recurrence import generate_datetimes
from agendable.reminders import build_default_email_reminder
from agendable.settings import Settings


class UnknownAttendeeEmailsError(ValueError):
    def __init__(self, emails: list[str]) -> None:
        self.emails = emails
        super().__init__("Unknown attendee email(s): " + ", ".join(emails))


class SeriesNotFoundError(LookupError):
    pass


class SeriesService:
    def __init__(
        self,
        *,
        session: AsyncSession,
        users: UserRepository,
        attendees: MeetingOccurrenceAttendeeRepository,
        series: MeetingSeriesRepository,
        occurrences: MeetingOccurrenceRepository,
    ) -> None:
        self.session = session
        self.users = users
        self.attendees = attendees
        self.series = series
        self.occurrences = occurrences

    async def list_series_for_owner(self, owner_user_id: uuid.UUID) -> list[MeetingSeries]:
        return await self.series.list_for_owner(owner_user_id)

    async def create_series_with_occurrences(
        self,
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
        await self.series.add(series)

        scheduled: Sequence[datetime] = generate_datetimes(
            rrule=recurrence_rrule,
            dtstart=recurrence_dtstart,
            count=generate_count,
        )
        if not scheduled:
            raise ValueError("RRULE produced no occurrences")

        occurrences: list[MeetingOccurrence] = []
        for dt in scheduled:
            occurrence = MeetingOccurrence(
                series_id=series.id,
                scheduled_at=dt.astimezone(UTC),
                notes="",
            )
            await self.occurrences.add(occurrence, flush=False)
            occurrences.append(occurrence)
        await self.session.flush()

        if settings.enable_default_email_reminders:
            self.session.add_all(
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

    async def create_series_for_owner(
        self,
        *,
        owner_user_id: uuid.UUID,
        title: str,
        reminder_minutes_before: int,
        recurrence_rrule: str,
        recurrence_dtstart: datetime,
        recurrence_timezone: str,
        generate_count: int,
        attendee_emails: Sequence[str],
        settings: Settings,
    ) -> tuple[MeetingSeries, list[MeetingOccurrence], set[uuid.UUID]]:
        series, occurrences = await self.create_series_with_occurrences(
            owner_user_id=owner_user_id,
            title=title,
            reminder_minutes_before=reminder_minutes_before,
            recurrence_rrule=recurrence_rrule,
            recurrence_dtstart=recurrence_dtstart,
            recurrence_timezone=recurrence_timezone,
            generate_count=generate_count,
            settings=settings,
        )
        attendee_user_ids = await self.resolve_attendee_user_ids(
            attendee_emails=attendee_emails,
            owner_user_id=owner_user_id,
        )
        await self.link_attendees_to_occurrences(
            occurrences=occurrences,
            attendee_user_ids=attendee_user_ids,
        )
        await self.session.commit()
        return series, occurrences, attendee_user_ids

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

    async def add_attendee_to_series_occurrences(
        self,
        *,
        series_id: uuid.UUID,
        attendee_user_id: uuid.UUID,
    ) -> int:
        occurrences = await self.occurrences.list_for_series(series_id)
        occurrence_ids = [occ.id for occ in occurrences]
        existing_occurrence_ids = await self.attendees.list_occurrence_ids_for_user(
            user_id=attendee_user_id,
            occurrence_ids=occurrence_ids,
        )
        return await self.attendees.add_missing_links(
            user_id=attendee_user_id,
            occurrence_ids=occurrence_ids,
            existing_occurrence_ids=existing_occurrence_ids,
        )

    async def create_occurrence_for_owner(
        self,
        *,
        owner_user_id: uuid.UUID,
        series_id: uuid.UUID,
        scheduled_at: datetime,
        settings: Settings,
    ) -> MeetingOccurrence:
        series = await self.series.get_for_owner(series_id, owner_user_id)
        if series is None:
            raise SeriesNotFoundError

        occurrence = MeetingOccurrence(
            series_id=series_id,
            scheduled_at=scheduled_at,
            notes="",
        )
        await self.occurrences.add(occurrence)

        if settings.enable_default_email_reminders:
            self.session.add(
                build_default_email_reminder(
                    occurrence_id=occurrence.id,
                    occurrence_scheduled_at=occurrence.scheduled_at,
                    settings=settings,
                    lead_minutes_before=series.reminder_minutes_before,
                )
            )

        await self.session.commit()
        return occurrence
