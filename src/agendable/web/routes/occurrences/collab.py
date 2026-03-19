from __future__ import annotations

import uuid
from datetime import UTC, datetime

from agendable.db.models import AgendaItem, MeetingOccurrence, Task

# NOTE: This module keeps collaboration state in-process memory for low-latency
# local development. It is single-instance only: multi-instance deployments need
# a shared backend (for example Redis or a DB table) for consistent presence.
PRESENCE_WINDOW_SECONDS = 30

_occurrence_presence: dict[uuid.UUID, dict[uuid.UUID, datetime]] = {}
_occurrence_last_activity: dict[uuid.UUID, tuple[datetime, str]] = {}


def _prune_stale_occurrence_state(*, now: datetime) -> None:
    cutoff_timestamp = as_utc(now).timestamp() - PRESENCE_WINDOW_SECONDS

    stale_presence_occurrences: list[uuid.UUID] = []
    for occurrence_id, presence_by_user in _occurrence_presence.items():
        # Remove old user entries first, then drop empty occurrence buckets.
        stale_user_ids = [
            user_id
            for user_id, seen_at in presence_by_user.items()
            if seen_at.timestamp() < cutoff_timestamp
        ]
        for user_id in stale_user_ids:
            presence_by_user.pop(user_id, None)
        if not presence_by_user:
            stale_presence_occurrences.append(occurrence_id)

    for occurrence_id in stale_presence_occurrences:
        _occurrence_presence.pop(occurrence_id, None)

    stale_activity_occurrences = [
        occurrence_id
        for occurrence_id, (updated_at, _) in _occurrence_last_activity.items()
        if updated_at.timestamp() < cutoff_timestamp
    ]
    for occurrence_id in stale_activity_occurrences:
        _occurrence_last_activity.pop(occurrence_id, None)


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def relative_time_label(*, then: datetime, now: datetime) -> str:
    normalized_then = as_utc(then)
    normalized_now = as_utc(now)
    delta_seconds = max(0, int((normalized_now - normalized_then).total_seconds()))
    if delta_seconds < 5:
        return "just now"
    if delta_seconds < 60:
        return f"{delta_seconds}s ago"
    if delta_seconds < 3600:
        return f"{delta_seconds // 60}m ago"
    return f"{delta_seconds // 3600}h ago"


def mark_presence(*, occurrence_id: uuid.UUID, user_id: uuid.UUID, now: datetime) -> int:
    _prune_stale_occurrence_state(now=now)
    occurrence_presence = _occurrence_presence.setdefault(occurrence_id, {})
    occurrence_presence[user_id] = now
    return len(occurrence_presence)


def record_occurrence_activity(
    *,
    occurrence_id: uuid.UUID,
    actor_display_name: str,
    now: datetime,
) -> None:
    _prune_stale_occurrence_state(now=now)
    _occurrence_last_activity[occurrence_id] = (as_utc(now), actor_display_name)


def latest_content_activity_at(
    *,
    occurrence: MeetingOccurrence,
    tasks: list[Task],
    agenda_items: list[AgendaItem],
) -> datetime:
    latest = as_utc(occurrence.created_at)
    for task in tasks:
        task_created_at = as_utc(task.created_at)
        if task_created_at > latest:
            latest = task_created_at
    for agenda_item in agenda_items:
        agenda_created_at = as_utc(agenda_item.created_at)
        if agenda_created_at > latest:
            latest = agenda_created_at
    return latest


def get_tracked_occurrence_activity(
    occurrence_id: uuid.UUID,
) -> tuple[datetime, str] | None:
    return _occurrence_last_activity.get(occurrence_id)
