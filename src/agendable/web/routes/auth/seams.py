from __future__ import annotations

from agendable.sso.oidc.client import OidcClient
from agendable.web.routes import auth as auth_routes


def oidc_enabled() -> bool:
    enabled_fn = getattr(auth_routes, "_oidc_enabled", auth_routes.oidc_enabled)
    return enabled_fn()


def oidc_oauth_client() -> OidcClient:
    client_fn = getattr(auth_routes, "_oidc_oauth_client", auth_routes.oidc_oauth_client)
    return client_fn()


def keycloak_oidc_oauth_client() -> OidcClient:
    client_fn = getattr(
        auth_routes,
        "_keycloak_oidc_oauth_client",
        auth_routes.keycloak_oidc_oauth_client,
    )
    return client_fn()
