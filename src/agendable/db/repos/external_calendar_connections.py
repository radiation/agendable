from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agendable.db.models import CalendarProvider, ExternalCalendarConnection
from agendable.db.repos.base import BaseRepository


class ExternalCalendarConnectionRepository(BaseRepository[ExternalCalendarConnection]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, ExternalCalendarConnection)

    async def get_for_user_provider_calendar(
        self,
        *,
        user_id: uuid.UUID,
        provider: CalendarProvider,
        external_calendar_id: str,
    ) -> ExternalCalendarConnection | None:
        result = await self.session.execute(
            select(ExternalCalendarConnection).where(
                ExternalCalendarConnection.user_id == user_id,
                ExternalCalendarConnection.provider == provider,
                ExternalCalendarConnection.external_calendar_id == external_calendar_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_enabled_for_provider(
        self,
        provider: CalendarProvider,
    ) -> list[ExternalCalendarConnection]:
        result = await self.session.execute(
            select(ExternalCalendarConnection)
            .where(
                ExternalCalendarConnection.provider == provider,
                ExternalCalendarConnection.is_enabled,
            )
            .order_by(ExternalCalendarConnection.created_at.asc())
        )
        return list(result.scalars().all())
