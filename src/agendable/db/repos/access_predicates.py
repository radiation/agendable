from __future__ import annotations

import uuid

from sqlalchemy import or_
from sqlalchemy.sql.elements import ColumnElement

from agendable.db.models import ImportedSeriesDecision, MeetingOccurrenceAttendee, MeetingSeries


def visible_occurrence_for_user_predicate(
    *,
    user_id: uuid.UUID,
    attendee_user_match: ColumnElement[bool],
) -> ColumnElement[bool]:
    return or_(
        MeetingSeries.owner_user_id == user_id,
        attendee_user_match,
    )


def kept_or_local_series_predicate() -> ColumnElement[bool]:
    return or_(
        MeetingSeries.import_decision.is_(None),
        MeetingSeries.import_decision == ImportedSeriesDecision.kept,
    )


def attendee_matches_user_predicate(*, user_id: uuid.UUID) -> ColumnElement[bool]:
    return MeetingOccurrenceAttendee.user_id == user_id
