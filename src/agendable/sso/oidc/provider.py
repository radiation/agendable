from __future__ import annotations

from dataclasses import dataclass

from authlib.integrations.starlette_client import OAuth

from agendable.settings import get_settings


@dataclass(frozen=True)
class OidcConfig:
    client_id: str
    client_secret: str
    metadata_url: str


def get_oidc_config() -> OidcConfig | None:
    settings = get_settings()
    if (
        settings.oidc_client_id is None
        or settings.oidc_client_secret is None
        or settings.oidc_metadata_url is None
    ):
        return None

    metadata_url = settings.oidc_metadata_url.strip()
    if not metadata_url:
        return None

    return OidcConfig(
        client_id=settings.oidc_client_id,
        client_secret=settings.oidc_client_secret.get_secret_value(),
        metadata_url=metadata_url,
    )


def get_keycloak_oidc_config() -> OidcConfig | None:
    settings = get_settings()
    if (
        settings.keycloak_oidc_client_id is None
        or settings.keycloak_oidc_client_secret is None
        or settings.keycloak_oidc_metadata_url is None
    ):
        return None

    metadata_url = settings.keycloak_oidc_metadata_url.strip()
    if not metadata_url:
        return None

    return OidcConfig(
        client_id=settings.keycloak_oidc_client_id,
        client_secret=settings.keycloak_oidc_client_secret.get_secret_value(),
        metadata_url=metadata_url,
    )


def oidc_enabled() -> bool:
    return get_oidc_config() is not None


def keycloak_oidc_enabled() -> bool:
    cfg = get_keycloak_oidc_config()
    if cfg is None:
        return False

    settings = get_settings()
    return settings.environment == "production" or settings.keycloak_oidc_allow_non_production


def build_oauth() -> OAuth:
    oauth = OAuth()
    cfg = get_oidc_config()
    keycloak_cfg = get_keycloak_oidc_config()
    settings = get_settings()

    if cfg is None and keycloak_cfg is None:
        return oauth

    if cfg is not None:
        scope_parts = [part for part in settings.oidc_scope.split() if part]
        if settings.google_calendar_sync_enabled:
            additional_scope = settings.google_calendar_oidc_additional_scope.strip()
            if additional_scope and additional_scope not in scope_parts:
                scope_parts.append(additional_scope)
        scope_value = " ".join(scope_parts)

        oauth.register(
            name="oidc",
            client_id=cfg.client_id,
            client_secret=cfg.client_secret,
            server_metadata_url=cfg.metadata_url,
            client_kwargs={"scope": scope_value},
        )

    if keycloak_cfg is not None:
        keycloak_scope_value = " ".join(
            [part for part in settings.keycloak_oidc_scope.split() if part]
        )
        oauth.register(
            name="oidc_keycloak",
            client_id=keycloak_cfg.client_id,
            client_secret=keycloak_cfg.client_secret,
            server_metadata_url=keycloak_cfg.metadata_url,
            client_kwargs={"scope": keycloak_scope_value},
        )
    return oauth
