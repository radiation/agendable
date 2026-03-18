from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from agendable.db.models import CalendarProvider, ExternalIdentity, MeetingSeries, User, UserRole
from agendable.db.repos import (
    ExternalCalendarConnectionRepository,
    ExternalIdentityRepository,
    MeetingSeriesRepository,
    UserRepository,
)


class AuthUserNotFoundError(Exception):
    pass


@dataclass(slots=True)
class ProfileViewData:
    user: User
    identities: list[ExternalIdentity]
    google_calendar_connected: bool
    pending_import_series: list[MeetingSeries]


class AuthService:
    def __init__(
        self,
        *,
        session: AsyncSession,
        users: UserRepository,
        external_identities: ExternalIdentityRepository,
        calendar_connections: ExternalCalendarConnectionRepository,
        series: MeetingSeriesRepository,
    ) -> None:
        self._session = session
        self._users = users
        self._external_identities = external_identities
        self._calendar_connections = calendar_connections
        self._series = series

    async def get_user_or_404(self, user_id: uuid.UUID) -> User:
        user = await self._users.get_by_id(user_id)
        if user is None:
            raise AuthUserNotFoundError
        return user

    async def get_by_email(self, email: str) -> User | None:
        return await self._users.get_by_email(email)

    async def promote_bootstrap_admin_if_needed(
        self,
        *,
        user: User,
        bootstrap_admin_email: str | None,
    ) -> bool:
        if not _should_promote_bootstrap_admin(
            user=user,
            bootstrap_admin_email=bootstrap_admin_email,
        ):
            return False

        user.role = UserRole.admin
        await self._session.commit()
        return True

    async def create_local_user(
        self,
        *,
        email: str,
        first_name: str,
        last_name: str,
        timezone: str,
        role: UserRole,
        password_hash: str,
    ) -> User:
        user = User(
            email=email,
            first_name=first_name,
            last_name=last_name,
            timezone=timezone,
            display_name=f"{first_name} {last_name}".strip(),
            role=role,
            password_hash=password_hash,
        )
        self._session.add(user)
        await self._session.commit()
        await self._session.refresh(user)
        return user

    async def update_profile(
        self,
        *,
        user: User,
        first_name: str,
        last_name: str,
        timezone: str,
        prefers_dark_mode: bool,
    ) -> None:
        user.first_name = first_name
        user.last_name = last_name
        user.timezone = timezone
        user.display_name = f"{first_name} {last_name}".strip()
        user.prefers_dark_mode = prefers_dark_mode
        await self._session.commit()

    async def get_profile_view_data(
        self,
        *,
        user_id: uuid.UUID,
        google_sync_enabled: bool,
    ) -> ProfileViewData:
        user = await self.get_user_or_404(user_id)
        identities = await self._external_identities.list_by_user_id(user.id)
        google_calendar_connection = (
            await self._calendar_connections.get_for_user_provider_calendar(
                user_id=user.id,
                provider=CalendarProvider.google,
                external_calendar_id="primary",
            )
        )
        pending_import_series: list[MeetingSeries] = []
        if google_sync_enabled:
            pending_import_series = await self._series.list_pending_google_import_for_owner(
                owner_user_id=user.id
            )

        return ProfileViewData(
            user=user,
            identities=identities,
            google_calendar_connected=google_calendar_connection is not None,
            pending_import_series=pending_import_series,
        )


def _should_promote_bootstrap_admin(
    *,
    user: User,
    bootstrap_admin_email: str | None,
) -> bool:
    if user.role == UserRole.admin:
        return False
    if bootstrap_admin_email is None:
        return False
    return bootstrap_admin_email.strip().lower() == user.email.strip().lower()


async def maybe_promote_bootstrap_admin_flush_only(
    *,
    session: AsyncSession,
    user: User,
    bootstrap_admin_email: str | None,
) -> bool:
    if not _should_promote_bootstrap_admin(
        user=user,
        bootstrap_admin_email=bootstrap_admin_email,
    ):
        return False

    user.role = UserRole.admin
    await session.flush()
    return True
