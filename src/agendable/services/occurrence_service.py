from __future__ import annotations

from datetime import UTC
from zoneinfo import ZoneInfo

from dateutil.rrule import rrulestr
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from agendable.db.models import AgendaItem, MeetingOccurrence, MeetingSeries, Task
from agendable.db.repos import MeetingOccurrenceRepository
from agendable.recurrence import normalize_rrule


async def _ensure_next_occurrence_from_rrule(
    session: AsyncSession,
    *,
    occurrence: MeetingOccurrence,
) -> MeetingOccurrence | None:
    series = await session.get(MeetingSeries, occurrence.series_id)
    if series is None:
        return None

    rrule = (series.recurrence_rrule or "").strip()
    dtstart = series.recurrence_dtstart
    if not rrule or dtstart is None:
        return None

    if dtstart.tzinfo is None:
        dtstart = dtstart.replace(tzinfo=UTC)

    timezone_name = (series.recurrence_timezone or "").strip()
    tzinfo = dtstart.tzinfo
    if timezone_name:
        try:
            tzinfo = ZoneInfo(timezone_name)
        except Exception:
            tzinfo = dtstart.tzinfo

    after_dt = occurrence.scheduled_at
    if after_dt.tzinfo is None:
        after_dt = after_dt.replace(tzinfo=UTC)

    local_dtstart = dtstart.astimezone(tzinfo)
    local_after = after_dt.astimezone(tzinfo)

    rule = rrulestr(normalize_rrule(rrule), dtstart=local_dtstart)
    next_local = rule.after(local_after, inc=False)
    if next_local is None:
        return None

    if next_local.tzinfo is None:
        next_local = next_local.replace(tzinfo=tzinfo)

    next_utc = next_local.astimezone(UTC)
    existing = (
        await session.execute(
            select(MeetingOccurrence)
            .where(
                MeetingOccurrence.series_id == occurrence.series_id,
                MeetingOccurrence.scheduled_at == next_utc,
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    next_occurrence = MeetingOccurrence(
        series_id=occurrence.series_id,
        scheduled_at=next_utc,
        notes="",
        is_completed=False,
    )
    session.add(next_occurrence)
    await session.flush()
    return next_occurrence


async def complete_occurrence_and_roll_forward(
    session: AsyncSession,
    *,
    occurrence: MeetingOccurrence,
    commit: bool = True,
    create_next_if_missing: bool = False,
) -> MeetingOccurrence | None:
    occ_repo = MeetingOccurrenceRepository(session)
    next_occurrence = await occ_repo.get_next_for_series(
        occurrence.series_id,
        occurrence.scheduled_at,
    )

    if next_occurrence is None and create_next_if_missing:
        next_occurrence = await _ensure_next_occurrence_from_rrule(
            session,
            occurrence=occurrence,
        )

    if next_occurrence is not None:
        await session.execute(
            update(Task)
            .where(Task.occurrence_id == occurrence.id, Task.is_done.is_(False))
            .values(occurrence_id=next_occurrence.id, due_at=next_occurrence.scheduled_at)
        )
        await session.execute(
            update(AgendaItem)
            .where(AgendaItem.occurrence_id == occurrence.id, AgendaItem.is_done.is_(False))
            .values(occurrence_id=next_occurrence.id)
        )

    occurrence.is_completed = True
    if commit:
        await session.commit()
    else:
        await session.flush()
    return next_occurrence
