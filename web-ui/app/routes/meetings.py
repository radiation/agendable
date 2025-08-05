from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.core.templating import templates

router = APIRouter(tags=["meetings"])


@router.get("/show_meetings", response_class=HTMLResponse)
async def show_meetings(request: Request) -> Any:
    return templates.TemplateResponse(
        "meetings/show_meetings.html", {"request": request}
    )
