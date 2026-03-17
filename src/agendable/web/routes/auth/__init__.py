from __future__ import annotations

from agendable.sso.oidc.client import OidcClient
from agendable.sso.oidc.provider import keycloak_oidc_enabled, oidc_enabled
from agendable.web.routes.auth.router import (
    get_user_or_404,
    is_bootstrap_admin_email,
    keycloak_oidc_oauth_client,
    maybe_promote_bootstrap_admin,
    oidc_oauth_client,
    render_login_template,
    render_profile_template,
    router,
)


def _oidc_oauth_client() -> OidcClient:
    return oidc_oauth_client()


def _keycloak_oidc_oauth_client() -> OidcClient:
    return keycloak_oidc_oauth_client()


__all__ = [
    "get_user_or_404",
    "is_bootstrap_admin_email",
    "keycloak_oidc_enabled",
    "keycloak_oidc_oauth_client",
    "maybe_promote_bootstrap_admin",
    "oidc_enabled",
    "oidc_oauth_client",
    "render_login_template",
    "render_profile_template",
    "router",
]
