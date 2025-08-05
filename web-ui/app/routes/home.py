from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.core.templating import templates

router = APIRouter(tags=["meetings"])


@router.get("/", response_class=HTMLResponse, name="home")
async def home(request: Request) -> Any:
    return templates.TemplateResponse("home.html", {"request": request})
