import os

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.responses import HTMLResponse

from .config import settings

app = FastAPI(
    title="Web UI",
    version="1.0.0",
    debug=(os.getenv("ENV", "dev") == "dev"),
)
templates = Jinja2Templates(directory="templates")

if app.debug:
    # clear Jinja’s cache so template files are re-read on each render
    templates.env.auto_reload = True
    templates.env.cache = {}

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/", response_class=HTMLResponse, name="home")
async def home(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("home.html", {"request": request})


@app.get("/register", response_class=HTMLResponse)
async def register_form(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        "users/register.html",
        {
            "request": request,
            "USER_API_BASE": settings.USER_API_BASE,
            "MEETING_API_BASE": settings.MEETING_API_BASE,
        },
    )


@app.get("/profile", response_class=HTMLResponse)
async def profile(
    request: Request,
    email: str,
    first_name: str,
    last_name: str,
) -> HTMLResponse:
    user = {"email": email, "first_name": first_name, "last_name": last_name}
    return templates.TemplateResponse(
        "users/profile.html", {"request": request, "user": user}
    )


@app.get("/show_meetings", response_class=HTMLResponse)
async def show_meetings(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        "meetings/show_meetings.html", {"request": request}
    )
