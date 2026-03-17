from __future__ import annotations

import uuid
from collections import defaultdict

from agendable.db.models import User
from agendable.db.repos import ExternalIdentityRepository, UserRepository


class AdminUserNotFoundError(LookupError):
    pass


class AdminService:
    def __init__(
        self,
        *,
        users: UserRepository,
        external_identities: ExternalIdentityRepository,
    ) -> None:
        self.users = users
        self.external_identities = external_identities

    async def get_user_or_404(self, user_id: uuid.UUID) -> User:
        user = await self.users.get_by_id(user_id)
        if user is None:
            raise AdminUserNotFoundError
        return user

    async def list_users_with_identity_summary(
        self,
        *,
        limit: int = 1000,
    ) -> tuple[list[User], dict[uuid.UUID, int], dict[uuid.UUID, list[str]]]:
        users = await self.users.list(limit=limit)
        user_ids = [user.id for user in users]
        identities = await self.external_identities.list_by_user_ids(user_ids)

        counts: dict[uuid.UUID, int] = defaultdict(int)
        providers: dict[uuid.UUID, list[str]] = defaultdict(list)
        for identity in identities:
            counts[identity.user_id] += 1
            if identity.provider not in providers[identity.user_id]:
                providers[identity.user_id].append(identity.provider)

        return users, dict(counts), dict(providers)

    async def update_user_role(self, *, user: User, role: str) -> None:
        user.role = user.role.__class__(role.strip().lower())
        await self.users.commit()

    async def update_user_active(self, *, user: User, is_active: bool) -> None:
        user.is_active = is_active
        await self.users.commit()
