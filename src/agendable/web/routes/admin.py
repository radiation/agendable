from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.responses import Response

from agendable.auth import require_admin
from agendable.db.models import User, UserRole
from agendable.dependencies import get_admin_service
from agendable.logging_config import log_with_fields
from agendable.security.audit import audit_admin_denied, audit_admin_success
from agendable.security.audit_constants import (
    ADMIN_EVENT_USER_ACTIVE_UPDATE,
    ADMIN_EVENT_USER_ROLE_UPDATE,
    ADMIN_REASON_INVALID_ROLE,
    ADMIN_REASON_SELF_DEACTIVATION_BLOCKED,
    ADMIN_REASON_SELF_DEMOTION_BLOCKED,
)
from agendable.services.admin_service import AdminService, AdminUserNotFoundError
from agendable.web.routes.common import templates

router = APIRouter()
logger = logging.getLogger("agendable.admin")


def _parse_bool(raw: str) -> bool:
    return raw.strip().lower() in {"1", "true", "yes", "on"}


async def _load_user_or_404(admin_service: AdminService, user_id: uuid.UUID) -> User:
    try:
        return await admin_service.get_user_or_404(user_id)
    except AdminUserNotFoundError as exc:
        raise HTTPException(status_code=404) from exc


async def _render_admin_users_template(
    request: Request,
    *,
    admin_service: AdminService,
    current_user: User,
    error: str | None,
    status_code: int = 200,
) -> HTMLResponse:
    (
        users,
        identity_counts,
        identity_providers,
    ) = await admin_service.list_users_with_identity_summary(limit=1000)

    return templates.TemplateResponse(
        request,
        "admin_users.html",
        {
            "users": users,
            "current_user": current_user,
            "error": error,
            "identity_counts": identity_counts,
            "identity_providers": identity_providers,
        },
        status_code=status_code,
    )


@router.get("/admin/users", response_class=HTMLResponse)
async def admin_users(
    request: Request,
    current_user: User = Depends(require_admin),
    admin_service: AdminService = Depends(get_admin_service),
) -> HTMLResponse:
    log_with_fields(
        logger,
        logging.INFO,
        "admin users viewed",
        admin_user_id=current_user.id,
    )
    return await _render_admin_users_template(
        request,
        admin_service=admin_service,
        current_user=current_user,
        error=None,
    )


@router.post("/admin/users/{user_id}/role", response_class=RedirectResponse)
async def admin_update_user_role(
    request: Request,
    user_id: uuid.UUID,
    role: str = Form(...),
    current_user: User = Depends(require_admin),
    admin_service: AdminService = Depends(get_admin_service),
) -> Response:
    user = await _load_user_or_404(admin_service, user_id)

    try:
        new_role = UserRole(role.strip().lower())
    except ValueError:
        audit_admin_denied(
            event=ADMIN_EVENT_USER_ROLE_UPDATE,
            reason=ADMIN_REASON_INVALID_ROLE,
            actor=current_user,
            target_user_id=user_id,
            requested_role=role,
        )
        log_with_fields(
            logger,
            logging.WARNING,
            "admin role update rejected invalid role",
            admin_user_id=current_user.id,
            target_user_id=user_id,
            requested_role=role,
        )
        raise HTTPException(status_code=400, detail="Invalid role") from None

    if user.id == current_user.id and new_role != UserRole.admin:
        audit_admin_denied(
            event=ADMIN_EVENT_USER_ROLE_UPDATE,
            reason=ADMIN_REASON_SELF_DEMOTION_BLOCKED,
            actor=current_user,
            target_user_id=user.id,
            previous_role=user.role.value,
            requested_role=new_role.value,
        )
        log_with_fields(
            logger,
            logging.WARNING,
            "admin role update rejected self-demotion",
            admin_user_id=current_user.id,
            target_user_id=user.id,
            requested_role=new_role.value,
        )
        return await _render_admin_users_template(
            request,
            admin_service=admin_service,
            current_user=current_user,
            error="You cannot remove your own admin role.",
            status_code=400,
        )

    previous_role = user.role.value
    await admin_service.update_user_role(user=user, role=new_role.value)
    audit_admin_success(
        event=ADMIN_EVENT_USER_ROLE_UPDATE,
        actor=current_user,
        target_user_id=user.id,
        previous_role=previous_role,
        new_role=new_role.value,
    )
    log_with_fields(
        logger,
        logging.INFO,
        "admin role updated",
        admin_user_id=current_user.id,
        target_user_id=user.id,
        previous_role=previous_role,
        new_role=new_role.value,
    )
    return RedirectResponse(url="/admin/users", status_code=303)


@router.post("/admin/users/{user_id}/active", response_class=RedirectResponse)
async def admin_update_user_active(
    request: Request,
    user_id: uuid.UUID,
    is_active: str = Form(...),
    current_user: User = Depends(require_admin),
    admin_service: AdminService = Depends(get_admin_service),
) -> Response:
    user = await _load_user_or_404(admin_service, user_id)

    new_is_active = _parse_bool(is_active)
    if user.id == current_user.id and not new_is_active:
        audit_admin_denied(
            event=ADMIN_EVENT_USER_ACTIVE_UPDATE,
            reason=ADMIN_REASON_SELF_DEACTIVATION_BLOCKED,
            actor=current_user,
            target_user_id=user.id,
            previous_is_active=user.is_active,
            requested_is_active=new_is_active,
        )
        log_with_fields(
            logger,
            logging.WARNING,
            "admin active update rejected self-deactivation",
            admin_user_id=current_user.id,
            target_user_id=user.id,
            requested_is_active=new_is_active,
        )
        return await _render_admin_users_template(
            request,
            admin_service=admin_service,
            current_user=current_user,
            error="You cannot deactivate your own account.",
            status_code=400,
        )

    previous_is_active = user.is_active
    await admin_service.update_user_active(user=user, is_active=new_is_active)
    audit_admin_success(
        event=ADMIN_EVENT_USER_ACTIVE_UPDATE,
        actor=current_user,
        target_user_id=user.id,
        previous_is_active=previous_is_active,
        new_is_active=new_is_active,
    )
    log_with_fields(
        logger,
        logging.INFO,
        "admin active updated",
        admin_user_id=current_user.id,
        target_user_id=user.id,
        previous_is_active=previous_is_active,
        new_is_active=new_is_active,
    )
    return RedirectResponse(url="/admin/users", status_code=303)
