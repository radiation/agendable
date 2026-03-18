from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from agendable.auth import require_user
from agendable.db.models import User
from agendable.dependencies import get_dashboard_service
from agendable.services.dashboard_service import DashboardService
from agendable.web.routes.common import templates

router = APIRouter()


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    dashboard_service: DashboardService = Depends(get_dashboard_service),
    current_user: User = Depends(require_user),
) -> HTMLResponse:
    now = datetime.now(UTC)

    dashboard_view = await dashboard_service.get_dashboard_view(
        user_id=current_user.id,
        now=now,
    )

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "dashboard_view": dashboard_view,
            "current_user": current_user,
        },
    )
