from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from agendable.db.models import ExternalIdentity, User, UserRole
from agendable.security.audit_constants import OIDC_REASON_INACTIVE_USER
from agendable.services.oidc_service import (
    provision_user_for_oidc,
    resolve_oidc_link_resolution,
    resolve_oidc_login_resolution,
)


@pytest.mark.asyncio
async def test_provision_user_for_oidc_normalizes_blank_timezone_to_utc(
    db_session: AsyncSession,
) -> None:
    user = await provision_user_for_oidc(
        db_session,
        email=f"tz-blank-{uuid.uuid4()}@example.com",
        userinfo={},
        is_bootstrap_admin_email=lambda _email: False,
        timezone="   ",
    )
    assert user.timezone == "UTC"


@pytest.mark.asyncio
async def test_resolve_oidc_link_resolution_redirects_when_link_user_inactive(
    db_session: AsyncSession,
) -> None:
    link_user = User(
        email=f"inactive-link-{uuid.uuid4()}@example.com",
        first_name="Inactive",
        last_name="Link",
        display_name="Inactive Link",
        timezone="UTC",
        role=UserRole.user,
        password_hash=None,
    )
    link_user.is_active = False
    db_session.add(link_user)
    await db_session.commit()

    resolution = await resolve_oidc_link_resolution(
        db_session,
        provider="oidc",
        link_user=link_user,
        sub="sub-inactive-link",
        email=link_user.email,
    )

    assert resolution.user is None
    assert resolution.create_identity is False
    assert resolution.should_redirect_login is True


@pytest.mark.asyncio
async def test_resolve_oidc_login_resolution_redirects_when_identity_user_missing(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = User(
        email=f"dangling-user-{uuid.uuid4()}@example.com",
        first_name="Dangling",
        last_name="User",
        display_name="Dangling User",
        timezone="UTC",
        role=UserRole.user,
        password_hash=None,
    )
    db_session.add(user)
    await db_session.flush()

    identity = ExternalIdentity(
        user_id=user.id,
        provider="oidc",
        subject="sub-dangling",
        email=user.email,
    )
    db_session.add(identity)
    await db_session.commit()

    async def _missing_user(self: object, user_id: object) -> None:
        return None

    monkeypatch.setattr(
        "agendable.services.oidc_service.UserRepository.get_by_id",
        _missing_user,
    )

    resolution = await resolve_oidc_login_resolution(
        db_session,
        provider="oidc",
        sub="sub-dangling",
        email=user.email,
        userinfo={},
        is_bootstrap_admin_email=lambda _email: False,
    )

    assert resolution.user is None
    assert resolution.create_identity is False
    assert resolution.should_redirect_login is True


@pytest.mark.asyncio
async def test_resolve_oidc_login_resolution_returns_inactive_error_for_identity_user(
    db_session: AsyncSession,
) -> None:
    user = User(
        email=f"inactive-identity-{uuid.uuid4()}@example.com",
        first_name="Inactive",
        last_name="Identity",
        display_name="Inactive Identity",
        timezone="UTC",
        role=UserRole.user,
        password_hash=None,
    )
    user.is_active = False
    db_session.add(user)
    await db_session.flush()

    db_session.add(
        ExternalIdentity(
            user_id=user.id,
            provider="oidc",
            subject="sub-inactive-identity",
            email=user.email,
        )
    )
    await db_session.commit()

    resolution = await resolve_oidc_login_resolution(
        db_session,
        provider="oidc",
        sub="sub-inactive-identity",
        email=user.email,
        userinfo={},
        is_bootstrap_admin_email=lambda _email: False,
    )

    assert resolution.user is not None
    assert resolution.user.id == user.id
    assert resolution.create_identity is False
    assert resolution.error == OIDC_REASON_INACTIVE_USER


@pytest.mark.asyncio
async def test_resolve_oidc_login_resolution_provisions_user_when_missing(
    db_session: AsyncSession,
) -> None:
    email = f"new-oidc-{uuid.uuid4()}@example.com"
    resolution = await resolve_oidc_login_resolution(
        db_session,
        provider="oidc",
        sub="sub-new",
        email=email,
        userinfo={},
        is_bootstrap_admin_email=lambda _email: False,
        default_timezone="",
    )

    assert resolution.user is not None
    assert resolution.user.email == email
    assert resolution.user.timezone == "UTC"
    assert resolution.create_identity is True


@pytest.mark.asyncio
async def test_resolve_oidc_login_resolution_returns_inactive_error_for_email_match(
    db_session: AsyncSession,
) -> None:
    existing = User(
        email=f"inactive-email-match-{uuid.uuid4()}@example.com",
        first_name="Inactive",
        last_name="EmailMatch",
        display_name="Inactive EmailMatch",
        timezone="UTC",
        role=UserRole.user,
        password_hash=None,
    )
    existing.is_active = False
    db_session.add(existing)
    await db_session.commit()

    resolution = await resolve_oidc_login_resolution(
        db_session,
        provider="oidc",
        sub="sub-someone-else",
        email=existing.email,
        userinfo={},
        is_bootstrap_admin_email=lambda _email: False,
    )

    assert resolution.user is not None
    assert resolution.user.id == existing.id
    assert resolution.create_identity is False
    assert resolution.error == OIDC_REASON_INACTIVE_USER
