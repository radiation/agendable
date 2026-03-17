from __future__ import annotations

from agendable.sso.oidc.client import OidcClient
from agendable.web.routes.auth import seams as auth_seams
from agendable.web.routes.auth.oidc_callback_flow import (
    domain_block_response,
    extract_oidc_identity_or_response,
    handle_login_callback,
    rate_limit_block_response,
)
from agendable.web.routes.auth.oidc_link_flow import handle_link_callback


def auth_oidc_enabled() -> bool:
    return auth_seams.oidc_enabled()


def auth_oidc_oauth_client() -> OidcClient:
    return auth_seams.oidc_oauth_client()


__all__ = [
    "auth_oidc_enabled",
    "auth_oidc_oauth_client",
    "domain_block_response",
    "extract_oidc_identity_or_response",
    "handle_link_callback",
    "handle_login_callback",
    "rate_limit_block_response",
]
