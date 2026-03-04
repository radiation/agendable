from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agendable.db.models import ExternalCalendarConnection, ExternalIdentity, User, UserRole
from agendable.web.routes import auth as auth_routes
from agendable.web.routes.auth import oidc_callback_flow


@dataclass
class _FakeOidcClient:
    userinfo_payload: dict[str, object]
    token_payload: dict[str, object] | None = None

    async def authorize_access_token(self, request: object) -> dict[str, object]:
        if self.token_payload is not None:
            return self.token_payload
        return {"access_token": "test-token"}

    async def parse_id_token(self, request: object, token: object) -> dict[str, object]:
        return self.userinfo_payload

    async def userinfo(self, token: object) -> dict[str, object]:
        return self.userinfo_payload


class _FakeAutoSyncService:
    def __init__(self) -> None:
        self.synced_connection_ids: list[object] = []

    async def sync_connection(self, connection: object) -> int:
        self.synced_connection_ids.append(getattr(connection, "id", None))
        return 0


@pytest.mark.asyncio
async def test_oidc_callback_autoprovisions_user_and_links_identity(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="agendable.security.audit")

    monkeypatch.setenv("AGENDABLE_OIDC_CLIENT_ID", "test-client")
    monkeypatch.setenv("AGENDABLE_OIDC_CLIENT_SECRET", "test-secret")
    monkeypatch.setenv(
        "AGENDABLE_OIDC_METADATA_URL", "https://example.com/.well-known/openid-configuration"
    )
    monkeypatch.setattr(
        auth_routes,
        "_oidc_oauth_client",
        lambda: _FakeOidcClient(
            {
                "sub": "sub-123",
                "email": "alice@example.com",
                "email_verified": True,
                "given_name": "Alice",
                "family_name": "Example",
            }
        ),
    )

    response = await client.get("/auth/oidc/callback", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/dashboard"

    user = (
        await db_session.execute(select(User).where(User.email == "alice@example.com"))
    ).scalar_one()
    assert user.first_name == "Alice"
    assert user.last_name == "Example"
    assert user.password_hash is None

    identity = (
        await db_session.execute(
            select(ExternalIdentity).where(
                ExternalIdentity.provider == "oidc",
                ExternalIdentity.subject == "sub-123",
            )
        )
    ).scalar_one()
    assert identity.user_id == user.id

    messages = [record.getMessage() for record in caplog.records]
    assert any(
        "audit_event=auth.oidc.callback_login" in message and "outcome=success" in message
        for message in messages
    )


@pytest.mark.asyncio
async def test_oidc_callback_rejects_link_to_existing_password_account(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENDABLE_OIDC_CLIENT_ID", "test-client")
    monkeypatch.setenv("AGENDABLE_OIDC_CLIENT_SECRET", "test-secret")
    monkeypatch.setenv(
        "AGENDABLE_OIDC_METADATA_URL", "https://example.com/.well-known/openid-configuration"
    )

    signup = await client.post(
        "/signup",
        data={
            "first_name": "Bob",
            "last_name": "Example",
            "timezone": "UTC",
            "email": "bob@example.com",
            "password": "pw-bob",
        },
        follow_redirects=True,
    )
    assert signup.status_code == 200
    await client.post("/logout", follow_redirects=True)

    monkeypatch.setattr(
        auth_routes,
        "_oidc_oauth_client",
        lambda: _FakeOidcClient(
            {
                "sub": "sub-bob",
                "email": "bob@example.com",
                "email_verified": True,
                "given_name": "Bob",
                "family_name": "Example",
            }
        ),
    )

    response = await client.get("/auth/oidc/callback", follow_redirects=False)
    assert response.status_code == 403
    assert "Sign in with password first to link SSO" in response.text

    user_count = (await db_session.execute(select(func.count(User.id)))).scalar_one()
    assert user_count == 1

    identity = (
        await db_session.execute(
            select(ExternalIdentity).where(
                ExternalIdentity.provider == "oidc",
                ExternalIdentity.subject == "sub-bob",
            )
        )
    ).scalar_one_or_none()
    bob = (
        await db_session.execute(select(User).where(User.email == "bob@example.com"))
    ).scalar_one()
    assert identity is None
    assert bob.password_hash is not None


@pytest.mark.asyncio
async def test_oidc_callback_links_existing_passwordless_account(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENDABLE_OIDC_CLIENT_ID", "test-client")
    monkeypatch.setenv("AGENDABLE_OIDC_CLIENT_SECRET", "test-secret")
    monkeypatch.setenv(
        "AGENDABLE_OIDC_METADATA_URL", "https://example.com/.well-known/openid-configuration"
    )

    existing_user = User(
        email="dana@example.com",
        first_name="Dana",
        last_name="Example",
        display_name="Dana Example",
        timezone="UTC",
        role=UserRole.user,
        password_hash=None,
    )
    db_session.add(existing_user)
    await db_session.commit()

    monkeypatch.setattr(
        auth_routes,
        "_oidc_oauth_client",
        lambda: _FakeOidcClient(
            {
                "sub": "sub-dana",
                "email": "dana@example.com",
                "email_verified": True,
                "given_name": "Dana",
                "family_name": "Example",
            }
        ),
    )

    response = await client.get("/auth/oidc/callback", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/dashboard"

    user_count = (await db_session.execute(select(func.count(User.id)))).scalar_one()
    assert user_count == 1

    identity = (
        await db_session.execute(
            select(ExternalIdentity).where(
                ExternalIdentity.provider == "oidc",
                ExternalIdentity.subject == "sub-dana",
            )
        )
    ).scalar_one()
    dana = (
        await db_session.execute(select(User).where(User.email == "dana@example.com"))
    ).scalar_one()
    assert identity.user_id == dana.id


@pytest.mark.asyncio
async def test_oidc_autoprovision_name_fallback_uses_email_localpart(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENDABLE_OIDC_CLIENT_ID", "test-client")
    monkeypatch.setenv("AGENDABLE_OIDC_CLIENT_SECRET", "test-secret")
    monkeypatch.setenv(
        "AGENDABLE_OIDC_METADATA_URL", "https://example.com/.well-known/openid-configuration"
    )
    monkeypatch.setattr(
        auth_routes,
        "_oidc_oauth_client",
        lambda: _FakeOidcClient(
            {
                "sub": "sub-charlie",
                "email": "charlie@example.com",
                "email_verified": True,
            }
        ),
    )

    response = await client.get("/auth/oidc/callback", follow_redirects=False)
    assert response.status_code == 303

    user = (
        await db_session.execute(select(User).where(User.email == "charlie@example.com"))
    ).scalar_one()
    assert user.first_name == "charlie"
    assert user.last_name == ""
    assert user.display_name == "charlie"


@pytest.mark.asyncio
async def test_oidc_callback_rate_limit_blocks_repeated_attempts(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENDABLE_OIDC_CLIENT_ID", "test-client")
    monkeypatch.setenv("AGENDABLE_OIDC_CLIENT_SECRET", "test-secret")
    monkeypatch.setenv(
        "AGENDABLE_OIDC_METADATA_URL", "https://example.com/.well-known/openid-configuration"
    )
    monkeypatch.setenv("AGENDABLE_OIDC_CALLBACK_RATE_LIMIT_IP_ATTEMPTS", "1")
    monkeypatch.setenv("AGENDABLE_OIDC_CALLBACK_RATE_LIMIT_ACCOUNT_ATTEMPTS", "99")
    monkeypatch.setattr(
        auth_routes,
        "_oidc_oauth_client",
        lambda: _FakeOidcClient(
            {
                "sub": "sub-rate-oidc",
                "email": "rate-oidc@example.com",
                "email_verified": True,
            }
        ),
    )

    first = await client.get("/auth/oidc/callback", follow_redirects=False)
    second = await client.get("/auth/oidc/callback", follow_redirects=False)

    assert first.status_code == 303
    assert second.status_code == 429
    assert "Too many SSO attempts" in second.text


@pytest.mark.asyncio
async def test_oidc_callback_denies_disallowed_email_domain(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENDABLE_OIDC_CLIENT_ID", "test-client")
    monkeypatch.setenv("AGENDABLE_OIDC_CLIENT_SECRET", "test-secret")
    monkeypatch.setenv(
        "AGENDABLE_OIDC_METADATA_URL", "https://example.com/.well-known/openid-configuration"
    )
    monkeypatch.setenv("AGENDABLE_ALLOWED_EMAIL_DOMAIN", "example.com")
    monkeypatch.setenv("AGENDABLE_OIDC_DEBUG_LOGGING", "true")
    monkeypatch.setattr(
        auth_routes,
        "_oidc_oauth_client",
        lambda: _FakeOidcClient(
            {
                "sub": "sub-domain-denied",
                "email": "not-allowed@other.com",
                "email_verified": True,
            }
        ),
    )

    response = await client.get("/auth/oidc/callback", follow_redirects=False)

    assert response.status_code == 403
    assert "Email domain not allowed" in response.text


@pytest.mark.asyncio
async def test_oidc_callback_returns_404_when_provider_disabled(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(auth_routes, "oidc_enabled", lambda: False)

    response = await client.get("/auth/oidc/callback", follow_redirects=False)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_oidc_callback_creates_google_calendar_connection_when_scope_granted(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_auto_sync_service = _FakeAutoSyncService()
    monkeypatch.setattr(
        oidc_callback_flow,
        "build_google_calendar_sync_service",
        lambda session, settings: fake_auto_sync_service,
    )

    monkeypatch.setenv("AGENDABLE_OIDC_CLIENT_ID", "test-client")
    monkeypatch.setenv("AGENDABLE_OIDC_CLIENT_SECRET", "test-secret")
    monkeypatch.setenv(
        "AGENDABLE_OIDC_METADATA_URL",
        "https://accounts.google.com/.well-known/openid-configuration",
    )
    monkeypatch.setenv("AGENDABLE_GOOGLE_CALENDAR_SYNC_ENABLED", "true")
    monkeypatch.setattr(
        auth_routes,
        "_oidc_oauth_client",
        lambda: _FakeOidcClient(
            {
                "sub": "sub-calendar-create",
                "email": "calendar-create@example.com",
                "email_verified": True,
            },
            token_payload={
                "access_token": "google-access-token-1",
                "refresh_token": "google-refresh-token-1",
                "scope": "openid email profile https://www.googleapis.com/auth/calendar.readonly",
                "expires_at": 1_900_000_000,
            },
        ),
    )

    response = await client.get("/auth/oidc/callback", follow_redirects=False)
    assert response.status_code == 303

    user = (
        await db_session.execute(select(User).where(User.email == "calendar-create@example.com"))
    ).scalar_one()
    connection = (
        await db_session.execute(
            select(ExternalCalendarConnection).where(
                ExternalCalendarConnection.user_id == user.id,
                ExternalCalendarConnection.external_calendar_id == "primary",
            )
        )
    ).scalar_one()

    assert connection.access_token == "google-access-token-1"
    assert connection.refresh_token == "google-refresh-token-1"
    assert connection.scope is not None
    assert "calendar.readonly" in connection.scope
    assert connection.access_token_expires_at is not None
    assert connection.access_token_expires_at.replace(tzinfo=UTC) == datetime.fromtimestamp(
        1_900_000_000,
        tz=UTC,
    )
    assert fake_auto_sync_service.synced_connection_ids == [connection.id]


@pytest.mark.asyncio
async def test_oidc_callback_updates_google_calendar_connection_and_preserves_refresh_token(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENDABLE_OIDC_CLIENT_ID", "test-client")
    monkeypatch.setenv("AGENDABLE_OIDC_CLIENT_SECRET", "test-secret")
    monkeypatch.setenv(
        "AGENDABLE_OIDC_METADATA_URL",
        "https://accounts.google.com/.well-known/openid-configuration",
    )
    monkeypatch.setenv("AGENDABLE_GOOGLE_CALENDAR_SYNC_ENABLED", "true")

    existing_user = User(
        email="calendar-update@example.com",
        first_name="Cal",
        last_name="Update",
        display_name="Cal Update",
        timezone="UTC",
        role=UserRole.user,
        password_hash=None,
    )
    db_session.add(existing_user)
    await db_session.flush()

    db_session.add(
        ExternalIdentity(
            user_id=existing_user.id,
            provider="oidc",
            subject="sub-calendar-update",
            email=existing_user.email,
        )
    )
    db_session.add(
        ExternalCalendarConnection(
            user_id=existing_user.id,
            provider="google",
            external_calendar_id="primary",
            access_token="old-access-token",
            refresh_token="stored-refresh-token",
            scope="openid email profile https://www.googleapis.com/auth/calendar.readonly",
        )
    )
    await db_session.commit()

    monkeypatch.setattr(
        auth_routes,
        "_oidc_oauth_client",
        lambda: _FakeOidcClient(
            {
                "sub": "sub-calendar-update",
                "email": "calendar-update@example.com",
                "email_verified": True,
            },
            token_payload={
                "access_token": "new-access-token",
                "scope": "openid email profile https://www.googleapis.com/auth/calendar.readonly",
                "expires_at": 1_950_000_000,
            },
        ),
    )

    response = await client.get("/auth/oidc/callback", follow_redirects=False)
    assert response.status_code == 303

    connection = (
        await db_session.execute(
            select(ExternalCalendarConnection).where(
                ExternalCalendarConnection.user_id == existing_user.id,
                ExternalCalendarConnection.external_calendar_id == "primary",
            )
        )
    ).scalar_one()

    assert connection.access_token == "new-access-token"
    assert connection.refresh_token == "stored-refresh-token"
    assert connection.access_token_expires_at is not None
    assert connection.access_token_expires_at.replace(tzinfo=UTC) == datetime.fromtimestamp(
        1_950_000_000,
        tz=UTC,
    )
