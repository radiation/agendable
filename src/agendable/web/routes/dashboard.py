from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from agendable.auth import require_user
from agendable.db import get_session
from agendable.db.models import User
from agendable.services.dashboard_service import DashboardService
from agendable.web.routes.common import templates

router = APIRouter()


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_user),
) -> HTMLResponse:
    now = datetime.now(UTC)
    dashboard_service = DashboardService.from_session(session)

    upcoming_meetings = await dashboard_service.list_upcoming_meetings(
        user_id=current_user.id,
        now=now,
        limit=20,
    )

    outstanding_tasks = await dashboard_service.list_outstanding_tasks(
        user_id=current_user.id,
        limit=200,
    )

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "upcoming_meetings": upcoming_meetings,
            "outstanding_tasks": outstanding_tasks,
            "current_user": current_user,
        },
    )
