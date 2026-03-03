from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agendable.db.models import ExternalCalendarEventMirror
from agendable.db.repos.base import BaseRepository


class ExternalCalendarEventMirrorRepository(BaseRepository[ExternalCalendarEventMirror]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, ExternalCalendarEventMirror)

    async def get_for_connection_event(
        self,
        *,
        connection_id: uuid.UUID,
        external_event_id: str,
    ) -> ExternalCalendarEventMirror | None:
        result = await self.session.execute(
            select(ExternalCalendarEventMirror).where(
                ExternalCalendarEventMirror.connection_id == connection_id,
                ExternalCalendarEventMirror.external_event_id == external_event_id,
            )
        )
        return result.scalar_one_or_none()

    async def touch_seen(self, mirror: ExternalCalendarEventMirror) -> ExternalCalendarEventMirror:
        mirror.last_seen_at = datetime.now(UTC)
        await self.session.flush()
        return mirror
