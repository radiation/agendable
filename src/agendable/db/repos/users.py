from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from agendable.db.models import User
from agendable.db.repos.base import BaseRepository


class UserRepository(BaseRepository[User]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, User)

    async def get_by_email(self, email: str) -> User | None:
        normalized = email.strip().lower()
        result = await self.session.execute(select(User).where(User.email == normalized))
        return result.scalar_one_or_none()

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        return await self.get(user_id)

    async def list_active_suggestions(
        self,
        *,
        needle: str,
        exclude_user_id: uuid.UUID,
        limit: int = 8,
    ) -> list[User]:
        normalized = needle.strip().lower()
        if len(normalized) < 2:
            return []

        pattern = f"%{normalized}%"
        result = await self.session.execute(
            select(User)
            .where(
                User.is_active.is_(True),
                User.id != exclude_user_id,
                or_(
                    func.lower(User.email).like(pattern),
                    func.lower(User.display_name).like(pattern),
                ),
            )
            .order_by(User.display_name.asc(), User.email.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def list_by_emails(self, emails: Sequence[str]) -> list[User]:
        normalized = [email.strip().lower() for email in emails if email.strip()]
        if not normalized:
            return []

        result = await self.session.execute(select(User).where(User.email.in_(normalized)))
        return list(result.scalars().all())
