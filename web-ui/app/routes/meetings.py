from typing import Any

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
import httpx

from app.core.config import settings
from app.core.templating import templates

router = APIRouter(tags=["meetings"])


@router.get("/list", response_class=HTMLResponse)
async def show_meetings(request: Request) -> Any:
    return templates.TemplateResponse("meetings/list.html", {"request": request})


@router.get("/create", response_class=HTMLResponse)
async def create_meeting(request: Request) -> Any:
    return templates.TemplateResponse("meetings/create.html", {"request": request})


@router.post("/create", response_class=HTMLResponse)
async def submit_meeting(
    request: Request,
    title: str = Form(...),
    description: str = Form(...),
    notes: str = Form(...),
    recurrence: int = Form(...),
) -> Any:
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{settings.MEETING_API_BASE}/meetings",
            json={
                "title": title,
                "description": description,
                "notes": notes,
                "recurrence_id": recurrence,
            },
        )

    if resp.status_code not in (200, 201):
        return templates.TemplateResponse(
            "meetings/create.html",
            {"request": request, "error": "Failed to create meeting"},
            status_code=400,
        )

    return RedirectResponse(url=request.url_for("show_meetings"), status_code=303)
