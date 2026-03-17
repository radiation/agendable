from __future__ import annotations

from agendable.services.google_calendar_client import GoogleCalendarHttpClient
from agendable.settings import get_settings
from agendable.sso.oidc.client import OidcClient
from agendable.web.routes import auth as auth_routes


def oidc_enabled() -> bool:
    return auth_routes.oidc_enabled()


def oidc_oauth_client() -> OidcClient:
    return auth_routes.oidc_oauth_client()


def keycloak_oidc_enabled() -> bool:
    return auth_routes.keycloak_oidc_enabled()


def keycloak_oidc_oauth_client() -> OidcClient:
    return auth_routes.keycloak_oidc_oauth_client()


def build_google_calendar_client() -> GoogleCalendarHttpClient:
    settings = get_settings()
    return GoogleCalendarHttpClient(
        api_base_url=settings.google_calendar_api_base_url,
        initial_sync_days_back=settings.google_calendar_initial_sync_days_back,
    )
