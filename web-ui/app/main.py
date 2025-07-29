import os

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.responses import HTMLResponse, Response

app = FastAPI(
    title="Web UI",
    version="1.0.0",
    docs_url="/web_ui_docs",
    redoc_url=None,
    debug=(os.getenv("ENV", "dev") == "dev"),
)
templates = Jinja2Templates(directory="templates")

if app.debug:
    # clear Jinja’s cache so template files are re-read on each render
    templates.env.auto_reload = True
    templates.env.cache = {}

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/register")
async def register_form(request: Request) -> Response:
    return templates.TemplateResponse("register.html", {"request": request})


@app.get("/profile", response_class=HTMLResponse)
async def profile(
    request: Request,
    email: str,
    first_name: str,
    last_name: str,
) -> HTMLResponse:
    user = {"email": email, "first_name": first_name, "last_name": last_name}
    return templates.TemplateResponse(
        "profile.html", {"request": request, "user": user}
    )
