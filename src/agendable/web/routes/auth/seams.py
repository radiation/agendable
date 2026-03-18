from __future__ import annotations

from typing import cast

from agendable.services.google_calendar_client import GoogleCalendarHttpClient
from agendable.settings import get_settings
from agendable.sso.oidc.client import OidcClient
from agendable.sso.oidc.provider import keycloak_oidc_enabled as provider_keycloak_oidc_enabled
from agendable.sso.oidc.provider import oidc_enabled as provider_oidc_enabled
from agendable.web.routes.common import oauth


def oidc_enabled() -> bool:
    return provider_oidc_enabled()


def oidc_oauth_client() -> OidcClient:
    client = oauth.create_client("oidc")
    if client is None:
        raise RuntimeError("OIDC OAuth client is not configured")
    return cast(OidcClient, client)


def keycloak_oidc_enabled() -> bool:
    return provider_keycloak_oidc_enabled()


def keycloak_oidc_oauth_client() -> OidcClient:
    client = oauth.create_client("oidc_keycloak")
    if client is None:
        raise RuntimeError("Keycloak OIDC OAuth client is not configured")
    return cast(OidcClient, client)


def build_google_calendar_client() -> GoogleCalendarHttpClient:
    settings = get_settings()
    return GoogleCalendarHttpClient(
        api_base_url=settings.google_calendar_api_base_url,
        initial_sync_days_back=settings.google_calendar_initial_sync_days_back,
    )
