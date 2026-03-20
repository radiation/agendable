from __future__ import annotations

import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.ext.asyncio import AsyncSession

from agendable.db.models import User, UserRole
from agendable.db.repos import ExternalIdentityRepository, UserRepository
from agendable.security.audit_constants import (
    OIDC_REASON_ALREADY_LINKED_OTHER_USER,
    OIDC_REASON_EMAIL_MISMATCH,
    OIDC_REASON_INACTIVE_USER,
    OIDC_REASON_PASSWORD_USER_REQUIRES_LINK,
)
from agendable.sso.oidc.flow import userinfo_name_parts


@dataclass(frozen=True)
class OidcResolution:
    user: User | None
    create_identity: bool
    error: str | None = None
    should_redirect_login: bool = False


class OidcLinkResolution(OidcResolution):
    pass


class OidcLoginResolution(OidcResolution):
    pass


class OidcIdentityNotFoundError(LookupError):
    pass


class OidcOnlySignInMethodError(ValueError):
    pass


def oidc_login_error_message(error: str | None) -> str | None:
    if error == OIDC_REASON_INACTIVE_USER:
        return "This account is deactivated. Contact an admin."
    if error == OIDC_REASON_PASSWORD_USER_REQUIRES_LINK:
        return "An account with this email already exists. Sign in with password first to link SSO."
    return None


def is_email_allowed_for_domain(email: str, allowed_email_domain: str | None) -> bool:
    if allowed_email_domain is None:
        return True

    allowed = allowed_email_domain.strip().lower().lstrip("@")
    return email.endswith(f"@{allowed}")


async def stage_user_provision_for_oidc(
    session: AsyncSession,
    *,
    email: str,
    userinfo: Mapping[str, object],
    is_bootstrap_admin_email: Callable[[str], bool],
    timezone: str | None = None,
) -> User:
    first_name, last_name = userinfo_name_parts(userinfo, email)
    normalized_timezone = _normalize_provision_timezone(timezone)
    user = User(
        email=email,
        first_name=first_name,
        last_name=last_name,
        display_name=f"{first_name} {last_name}".strip(),
        timezone=normalized_timezone,
        role=(UserRole.admin if is_bootstrap_admin_email(email) else UserRole.user),
        password_hash=None,
    )
    session.add(user)
    await session.flush()
    return user


async def provision_user_for_oidc(
    session: AsyncSession,
    *,
    email: str,
    userinfo: Mapping[str, object],
    is_bootstrap_admin_email: Callable[[str], bool],
    timezone: str | None = None,
) -> User:
    return await stage_user_provision_for_oidc(
        session,
        email=email,
        userinfo=userinfo,
        is_bootstrap_admin_email=is_bootstrap_admin_email,
        timezone=timezone,
    )


def _normalize_provision_timezone(value: str | None) -> str:
    if value is None:
        return "UTC"
    name = value.strip()
    if not name:
        return "UTC"
    try:
        _ = ZoneInfo(name)
    except ZoneInfoNotFoundError:
        return "UTC"
    return name


async def resolve_oidc_link_resolution(
    session: AsyncSession,
    *,
    provider: str,
    link_user: User,
    sub: str,
    email: str,
) -> OidcLinkResolution:
    if not link_user.is_active:
        return OidcLinkResolution(
            user=None,
            create_identity=False,
            should_redirect_login=True,
        )

    ext_repo = ExternalIdentityRepository(session)
    ext = await ext_repo.get_by_provider_subject(provider, sub)
    if ext is not None and ext.user_id != link_user.id:
        return OidcLinkResolution(
            user=link_user,
            create_identity=False,
            error=OIDC_REASON_ALREADY_LINKED_OTHER_USER,
        )

    if email != link_user.email:
        return OidcLinkResolution(
            user=link_user,
            create_identity=False,
            error=OIDC_REASON_EMAIL_MISMATCH,
        )

    return OidcLinkResolution(
        user=link_user,
        create_identity=(ext is None),
    )


async def resolve_oidc_login_resolution(
    session: AsyncSession,
    *,
    provider: str,
    sub: str,
    email: str,
    userinfo: Mapping[str, object],
    is_bootstrap_admin_email: Callable[[str], bool],
    default_timezone: str | None = None,
) -> OidcLoginResolution:
    ext_repo = ExternalIdentityRepository(session)
    users = UserRepository(session)

    ext = await ext_repo.get_by_provider_subject(provider, sub)
    if ext is not None:
        user = await users.get_by_id(ext.user_id)
        if user is None:
            return OidcLoginResolution(user=None, create_identity=False, should_redirect_login=True)
        if not user.is_active:
            return OidcLoginResolution(
                user=user,
                create_identity=False,
                error=OIDC_REASON_INACTIVE_USER,
            )
        return OidcLoginResolution(user=user, create_identity=False)

    user = await users.get_by_email(email)
    if user is None:
        user = await stage_user_provision_for_oidc(
            session,
            email=email,
            userinfo=userinfo,
            is_bootstrap_admin_email=is_bootstrap_admin_email,
            timezone=default_timezone,
        )
        return OidcLoginResolution(user=user, create_identity=True)

    if not user.is_active:
        return OidcLoginResolution(
            user=user,
            create_identity=False,
            error=OIDC_REASON_INACTIVE_USER,
        )
    if user.password_hash is not None:
        return OidcLoginResolution(
            user=user,
            create_identity=False,
            error=OIDC_REASON_PASSWORD_USER_REQUIRES_LINK,
        )

    return OidcLoginResolution(user=user, create_identity=True)


async def unlink_oidc_identity_for_user(
    session: AsyncSession,
    *,
    user: User,
    identity_id: uuid.UUID,
) -> uuid.UUID:
    ext_repo = ExternalIdentityRepository(session)

    identity = await ext_repo.get(identity_id)
    if identity is None or identity.user_id != user.id:
        raise OidcIdentityNotFoundError

    identities = await ext_repo.list_by_user_id(user.id)
    if user.password_hash is None and len(identities) <= 1:
        raise OidcOnlySignInMethodError

    await ext_repo.delete(identity, flush=False)
    await session.commit()
    return identity.id
