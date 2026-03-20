from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from agendable.db.models import ExternalCalendarConnection, ExternalIdentity, User
from agendable.db.repos import ExternalCalendarConnectionRepository, ExternalIdentityRepository
from agendable.services.calendar_connection_service import (
    should_capture_google_calendar_token,
    upsert_google_primary_calendar_connection,
)
from agendable.settings import Settings
from agendable.sso.oidc.flow import OidcTokenCapture


async def stage_oidc_identity_if_needed(
    session: AsyncSession,
    *,
    user: User,
    create_identity: bool,
    identity_provider: str,
    sub: str,
    email: str,
) -> None:
    if not create_identity:
        return

    ext = ExternalIdentity(user_id=user.id, provider=identity_provider, subject=sub, email=email)
    session.add(ext)
    await session.flush()


async def get_identity_for_provider_subject(
    session: AsyncSession,
    *,
    identity_provider: str,
    subject: str,
) -> ExternalIdentity | None:
    repo = ExternalIdentityRepository(session)
    return await repo.get_by_provider_subject(identity_provider, subject)


async def stage_google_primary_connection_upsert(
    session: AsyncSession,
    *,
    user: User,
    allow_google_calendar_token_capture: bool,
    token_capture: OidcTokenCapture,
    settings: Settings,
) -> ExternalCalendarConnection | None:
    if not allow_google_calendar_token_capture:
        return None
    if not should_capture_google_calendar_token(settings=settings, token_capture=token_capture):
        return None

    connection_repo = ExternalCalendarConnectionRepository(session)
    return await upsert_google_primary_calendar_connection(
        connection_repo=connection_repo,
        user=user,
        token_capture=token_capture,
    )


async def commit_staged_oidc_changes(session: AsyncSession) -> None:
    await session.commit()


async def create_oidc_identity_if_needed(
    session: AsyncSession,
    *,
    user: User,
    create_identity: bool,
    identity_provider: str,
    sub: str,
    email: str,
) -> None:
    await stage_oidc_identity_if_needed(
        session,
        user=user,
        create_identity=create_identity,
        identity_provider=identity_provider,
        sub=sub,
        email=email,
    )


async def maybe_upsert_google_primary_connection(
    session: AsyncSession,
    *,
    user: User,
    allow_google_calendar_token_capture: bool,
    token_capture: OidcTokenCapture,
    settings: Settings,
) -> ExternalCalendarConnection | None:
    return await stage_google_primary_connection_upsert(
        session,
        user=user,
        allow_google_calendar_token_capture=allow_google_calendar_token_capture,
        token_capture=token_capture,
        settings=settings,
    )


async def commit_oidc_session(session: AsyncSession) -> None:
    await commit_staged_oidc_changes(session)
