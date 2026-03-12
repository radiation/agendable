from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agendable.db.models import (
    CalendarProvider,
    ExternalCalendarEventMirror,
    ImportedSeriesDecision,
    MeetingOccurrence,
    MeetingSeries,
)
from agendable.db.repos import ExternalCalendarConnectionRepository
from agendable.services.calendar_event_mapping_service import CalendarEventMappingService


class ImportedSeriesNotFoundError(Exception):
    pass


class MissingGoogleCalendarConnectionError(Exception):
    pass


class GoogleImportedSeriesService:
    def __init__(self, *, session: AsyncSession) -> None:
        self.session = session

    async def keep_pending_google_series(self, *, user_id: uuid.UUID, series_id: uuid.UUID) -> None:
        series = await self._get_pending_google_series_for_user(
            user_id=user_id, series_id=series_id
        )

        connection_repo = ExternalCalendarConnectionRepository(self.session)
        connection = await connection_repo.get_for_user_provider_calendar(
            user_id=user_id,
            provider=CalendarProvider.google,
            external_calendar_id="primary",
        )
        if connection is None:
            raise MissingGoogleCalendarConnectionError

        series.import_decision = ImportedSeriesDecision.kept

        import_series_id = series.import_external_series_id
        if import_series_id:
            mirrors = list(
                (
                    await self.session.execute(
                        select(ExternalCalendarEventMirror)
                        .where(
                            ExternalCalendarEventMirror.connection_id == connection.id,
                            ExternalCalendarEventMirror.external_recurring_event_id
                            == import_series_id,
                        )
                        .order_by(ExternalCalendarEventMirror.created_at.asc())
                    )
                )
                .scalars()
                .all()
            )
            if mirrors:
                await CalendarEventMappingService(session=self.session).map_mirrors(
                    connection=connection,
                    mirrors=mirrors,
                    recurring_event_details_by_id=None,
                )

        await self.session.commit()

    async def reject_pending_google_series(
        self,
        *,
        user_id: uuid.UUID,
        series_id: uuid.UUID,
    ) -> None:
        series = await self._get_pending_google_series_for_user(
            user_id=user_id, series_id=series_id
        )

        # Keep the series row as a tombstone so this external recurring ID stays rejected.
        series.import_decision = ImportedSeriesDecision.rejected

        mirrors = list(
            (
                await self.session.execute(
                    select(ExternalCalendarEventMirror)
                    .join(
                        MeetingOccurrence,
                        ExternalCalendarEventMirror.linked_occurrence_id == MeetingOccurrence.id,
                    )
                    .where(MeetingOccurrence.series_id == series.id)
                )
            )
            .scalars()
            .all()
        )
        for mirror in mirrors:
            mirror.linked_occurrence_id = None

        occurrences = list(
            (
                await self.session.execute(
                    select(MeetingOccurrence).where(MeetingOccurrence.series_id == series.id)
                )
            )
            .scalars()
            .all()
        )
        for occurrence in occurrences:
            await self.session.delete(occurrence)

        await self.session.commit()

    async def _get_pending_google_series_for_user(
        self,
        *,
        user_id: uuid.UUID,
        series_id: uuid.UUID,
    ) -> MeetingSeries:
        series = await self.session.get(MeetingSeries, series_id)
        if series is None or series.owner_user_id != user_id:
            raise ImportedSeriesNotFoundError

        if (
            series.imported_from_provider != CalendarProvider.google
            or series.import_decision != ImportedSeriesDecision.pending
        ):
            raise ImportedSeriesNotFoundError

        return series
