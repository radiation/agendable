from __future__ import annotations

import logging
import uuid
from typing import cast
from urllib.parse import unquote

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import Response

from agendable.auth import hash_password, require_user, verify_password
from agendable.db.models import MeetingSeries, User, UserRole
from agendable.dependencies import get_auth_service, get_session
from agendable.security.audit import audit_auth_denied, audit_auth_success
from agendable.security.audit_constants import (
    AUTH_EVENT_LOGOUT,
    AUTH_EVENT_PASSWORD_LOGIN,
    AUTH_EVENT_SIGNUP,
    AUTH_REASON_ACCOUNT_EXISTS,
    AUTH_REASON_ACCOUNT_NOT_FOUND,
    AUTH_REASON_INACTIVE_USER,
    AUTH_REASON_INVALID_CREDENTIALS,
    AUTH_REASON_RATE_LIMITED,
)
from agendable.services.auth_service import (
    AuthService,
    AuthUserNotFoundError,
)
from agendable.services.auth_service import (
    maybe_promote_bootstrap_admin_flush_only as maybe_promote_bootstrap_admin_flush_only_service,
)
from agendable.settings import get_settings
from agendable.sso.oidc.client import OidcClient
from agendable.web.routes.auth.oidc import router as auth_oidc_router
from agendable.web.routes.auth.rate_limits import is_login_rate_limited, record_login_failure
from agendable.web.routes.common import oauth, parse_timezone, recurrence_label, templates

router = APIRouter()
logger = logging.getLogger("uvicorn.error")


def _auth_oidc_enabled() -> bool:
    from agendable.web.routes.auth import seams as auth_seams

    return auth_seams.oidc_enabled()


def _auth_keycloak_oidc_enabled() -> bool:
    from agendable.web.routes.auth import seams as auth_seams

    return auth_seams.keycloak_oidc_enabled()


def is_bootstrap_admin_email(email: str) -> bool:
    configured = get_settings().bootstrap_admin_email
    if configured is None:
        return False
    return configured.strip().lower() == email.strip().lower()


async def maybe_promote_bootstrap_admin_flush_only(user: User, session: AsyncSession) -> bool:
    return await maybe_promote_bootstrap_admin_flush_only_service(
        session=session,
        user=user,
        bootstrap_admin_email=get_settings().bootstrap_admin_email,
    )


def render_login_template(
    request: Request,
    *,
    error: str | None,
    status_code: int = 200,
) -> Response:
    return templates.TemplateResponse(
        request,
        "login.html",
        {
            "error": error,
            "current_user": None,
            "oidc_enabled": _auth_oidc_enabled(),
            "keycloak_oidc_enabled": _auth_keycloak_oidc_enabled(),
        },
        status_code=status_code,
    )


def _signup_form_context(
    *,
    first_name: str = "",
    last_name: str = "",
    timezone: str = "UTC",
    email: str = "",
) -> dict[str, str]:
    return {
        "first_name": first_name,
        "last_name": last_name,
        "timezone": timezone,
        "email": email,
    }


def _default_timezone_from_cookie(request: Request) -> str:
    raw = (request.cookies.get("agendable_tz") or "").strip()
    if not raw:
        return "UTC"
    try:
        decoded = unquote(raw).strip()
        return parse_timezone(decoded).key
    except HTTPException:
        return "UTC"


def _render_signup_template(
    request: Request,
    *,
    error: str | None,
    form: dict[str, str] | None = None,
    status_code: int = 200,
) -> Response:
    return templates.TemplateResponse(
        request,
        "signup.html",
        {
            "error": error,
            "current_user": None,
            "form": form or _signup_form_context(),
        },
        status_code=status_code,
    )


async def _redirect_if_authenticated(
    request: Request,
    session: AsyncSession,
) -> RedirectResponse | None:
    try:
        _ = await require_user(request, session)
        return RedirectResponse(url="/dashboard", status_code=303)
    except HTTPException:
        return None


async def get_user_or_404(auth_service: AuthService, user_id: uuid.UUID) -> User:
    try:
        return await auth_service.get_user_or_404(user_id)
    except AuthUserNotFoundError as exc:
        raise HTTPException(status_code=404) from exc


def oidc_oauth_client() -> OidcClient:
    client = oauth.create_client("oidc")
    if client is None:
        raise RuntimeError("OIDC OAuth client is not configured")
    return cast(OidcClient, client)


def keycloak_oidc_oauth_client() -> OidcClient:
    client = oauth.create_client("oidc_keycloak")
    if client is None:
        raise RuntimeError("Keycloak OIDC OAuth client is not configured")
    return cast(OidcClient, client)


async def render_profile_template(
    request: Request,
    *,
    auth_service: AuthService,
    user: User,
    identity_error: str | None,
    status_code: int = 200,
) -> Response:
    settings = get_settings()
    profile_data = await auth_service.get_profile_view_data(
        user_id=user.id,
        google_sync_enabled=settings.google_calendar_sync_enabled,
    )
    pending_import_series: list[MeetingSeries] = profile_data.pending_import_series
    pending_import_recurrence: dict[uuid.UUID, str] = {
        series.id: recurrence_label(
            recurrence_rrule=series.recurrence_rrule,
            recurrence_dtstart=series.recurrence_dtstart,
            recurrence_timezone=series.recurrence_timezone,
            default_interval_days=series.default_interval_days,
        )
        for series in pending_import_series
    }

    return templates.TemplateResponse(
        request,
        "profile.html",
        {
            "user": user,
            "current_user": user,
            "identities": profile_data.identities,
            "identity_error": identity_error,
            "oidc_enabled": _auth_oidc_enabled(),
            "keycloak_oidc_enabled": _auth_keycloak_oidc_enabled(),
            "any_oidc_enabled": _auth_oidc_enabled() or _auth_keycloak_oidc_enabled(),
            "google_calendar_sync_enabled": settings.google_calendar_sync_enabled,
            "google_calendar_connected": profile_data.google_calendar_connected,
            "pending_import_series": pending_import_series,
            "pending_import_recurrence": pending_import_recurrence,
        },
        status_code=status_code,
    )


@router.get("/login", response_class=Response)
async def login_form(request: Request, session: AsyncSession = Depends(get_session)) -> Response:
    redirect_response = await _redirect_if_authenticated(request, session)
    if redirect_response is not None:
        return redirect_response

    return render_login_template(request, error=None)


@router.post("/login", response_class=HTMLResponse)
async def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    auth_service: AuthService = Depends(get_auth_service),
) -> Response:
    normalized_email = email.strip().lower()

    if is_login_rate_limited(request, normalized_email):
        audit_auth_denied(
            event=AUTH_EVENT_PASSWORD_LOGIN,
            reason=AUTH_REASON_RATE_LIMITED,
            actor_email=normalized_email,
        )
        return render_login_template(
            request,
            error="Too many login attempts. Try again in a minute.",
            status_code=429,
        )

    user = await auth_service.get_by_email(normalized_email)

    if user is None:
        record_login_failure(request, normalized_email)
        audit_auth_denied(
            event=AUTH_EVENT_PASSWORD_LOGIN,
            reason=AUTH_REASON_ACCOUNT_NOT_FOUND,
            actor_email=normalized_email,
        )
        return render_login_template(
            request,
            error="Account not found. Create one first.",
            status_code=401,
        )

    if not user.is_active:
        record_login_failure(request, normalized_email)
        audit_auth_denied(
            event=AUTH_EVENT_PASSWORD_LOGIN,
            reason=AUTH_REASON_INACTIVE_USER,
            actor=user,
        )
        return render_login_template(
            request,
            error="This account is deactivated. Contact an admin.",
            status_code=403,
        )

    if user.password_hash is None or not verify_password(password, user.password_hash):
        record_login_failure(request, normalized_email)
        audit_auth_denied(
            event=AUTH_EVENT_PASSWORD_LOGIN,
            reason=AUTH_REASON_INVALID_CREDENTIALS,
            actor=user,
        )
        return render_login_template(
            request,
            error="Invalid email or password",
            status_code=401,
        )

    await auth_service.promote_bootstrap_admin_if_needed(
        user=user,
        bootstrap_admin_email=get_settings().bootstrap_admin_email,
    )

    request.session["user_id"] = str(user.id)
    audit_auth_success(event=AUTH_EVENT_PASSWORD_LOGIN, actor=user)
    return RedirectResponse(url="/dashboard", status_code=303)


@router.get("/signup", response_class=Response)
async def signup_form(request: Request, session: AsyncSession = Depends(get_session)) -> Response:
    redirect_response = await _redirect_if_authenticated(request, session)
    if redirect_response is not None:
        return redirect_response

    return _render_signup_template(
        request,
        error=None,
        form=_signup_form_context(timezone=_default_timezone_from_cookie(request)),
    )


@router.post("/signup", response_class=HTMLResponse)
async def signup(
    request: Request,
    first_name: str = Form(...),
    last_name: str = Form(""),
    timezone: str = Form("UTC"),
    email: str = Form(...),
    password: str = Form(...),
    auth_service: AuthService = Depends(get_auth_service),
) -> Response:
    normalized_first_name = first_name.strip()
    normalized_last_name = last_name.strip()
    timezone_input = timezone.strip() or "UTC"
    normalized_timezone = parse_timezone(timezone_input).key
    normalized_email = email.strip().lower()
    if not normalized_first_name:
        raise HTTPException(status_code=400, detail="First name is required")
    if not normalized_email:
        raise HTTPException(status_code=400, detail="Email is required")

    existing = await auth_service.get_by_email(normalized_email)
    if existing is not None:
        audit_auth_denied(
            event=AUTH_EVENT_SIGNUP,
            reason=AUTH_REASON_ACCOUNT_EXISTS,
            actor_email=normalized_email,
        )
        return _render_signup_template(
            request,
            error="Account already exists. Sign in instead.",
            form=_signup_form_context(
                first_name=normalized_first_name,
                last_name=normalized_last_name,
                timezone=normalized_timezone,
                email=normalized_email,
            ),
            status_code=400,
        )

    user = await auth_service.create_local_user(
        email=normalized_email,
        first_name=normalized_first_name,
        last_name=normalized_last_name,
        timezone=normalized_timezone,
        role=(UserRole.admin if is_bootstrap_admin_email(normalized_email) else UserRole.user),
        password_hash=hash_password(password),
    )

    request.session["user_id"] = str(user.id)
    audit_auth_success(event=AUTH_EVENT_SIGNUP, actor=user, role=user.role.value)
    return RedirectResponse(url="/dashboard", status_code=303)


@router.post("/logout", response_class=RedirectResponse)
async def logout(request: Request) -> RedirectResponse:
    user_id = request.session.get("user_id")
    audit_auth_success(event=AUTH_EVENT_LOGOUT, actor_user_id=user_id)
    request.session.clear()
    return RedirectResponse(url="/", status_code=303)


@router.get("/profile", response_class=HTMLResponse)
async def profile(
    request: Request,
    current_user: User = Depends(require_user),
    auth_service: AuthService = Depends(get_auth_service),
) -> HTMLResponse:
    user = await get_user_or_404(auth_service, current_user.id)
    return cast(
        HTMLResponse,
        await render_profile_template(
            request,
            auth_service=auth_service,
            user=user,
            identity_error=None,
        ),
    )


@router.post("/profile", response_class=RedirectResponse)
async def update_profile(
    request: Request,
    first_name: str = Form(...),
    last_name: str = Form(""),
    timezone: str = Form("UTC"),
    prefers_dark_mode: str | None = Form(None),
    current_user: User = Depends(require_user),
    auth_service: AuthService = Depends(get_auth_service),
) -> RedirectResponse:
    user = await get_user_or_404(auth_service, current_user.id)

    normalized_first_name = first_name.strip()
    normalized_last_name = last_name.strip()
    timezone_input = timezone.strip() or "UTC"
    normalized_timezone = parse_timezone(timezone_input).key
    if not normalized_first_name:
        raise HTTPException(status_code=400, detail="First name is required")

    await auth_service.update_profile(
        user=user,
        first_name=normalized_first_name,
        last_name=normalized_last_name,
        timezone=normalized_timezone,
        prefers_dark_mode=prefers_dark_mode is not None,
    )

    return RedirectResponse(url="/profile", status_code=303)


router.include_router(auth_oidc_router)
