import os

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import httpx

from .config import settings

app = FastAPI(
    title="Web UI",
    version="1.0.0",
    debug=(os.getenv("ENV", "dev") == "dev"),
)
templates = Jinja2Templates(directory="templates")

if app.debug:
    # clear jinja cache so template files are re-read on each render
    templates.env.auto_reload = True
    templates.env.cache = {}

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/", response_class=HTMLResponse, name="home")
async def home(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("home.html", {"request": request})


@app.get("/login", response_class=HTMLResponse, name="login")
async def login_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("users/login.html", {"request": request})


@app.post("/login", response_class=HTMLResponse, name="login_post")
async def login(
    request: Request, email: str = Form(...), password: str = Form(...)
) -> Response:
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{settings.USER_API_BASE}/auth/login",
            json={"email": email, "password": password},
        )

    if resp.status_code != 200:
        # invalid credentials → re-render form + error
        return templates.TemplateResponse(
            "users/login.html",
            {"request": request, "error": "Invalid email or password"},
            status_code=400,
        )

    token = resp.json().get("access_token")

    # set cookie, then redirect to profile
    response = RedirectResponse(url=app.url_path_for("profile"), status_code=303)
    response.set_cookie(
        key="token",
        value=token,
        httponly=True,
        max_age=3600,
        samesite="lax",
    )
    return response


@app.get("/logout", name="logout")
async def logout() -> RedirectResponse:
    resp = RedirectResponse(app.url_path_for("login"))
    resp.delete_cookie("token")
    return resp


@app.get("/register", response_class=HTMLResponse, name="register")
async def register_form(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        "users/register.html",
        {
            "request": request,
            "USER_API_BASE": settings.USER_API_BASE,
            "MEETING_API_BASE": settings.MEETING_API_BASE,
        },
    )


@app.post("/register", response_class=HTMLResponse, name="register_post")
async def register(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    first_name: str = Form(...),
    last_name: str = Form(...),
) -> Response:
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{settings.USER_API_BASE}/auth/register",
            json={
                "email": email,
                "password": password,
                "first_name": first_name,
                "last_name": last_name,
            },
        )

    if resp.status_code != 201:
        # registration failed
        return templates.TemplateResponse(
            "users/register.html",
            {
                "request": request,
                "error": resp.json().get("detail", "Registration failed"),
                "USER_API_BASE": settings.USER_API_BASE,
                "MEETING_API_BASE": settings.MEETING_API_BASE,
            },
            status_code=resp.status_code,
        )

    # redirect to login
    return RedirectResponse(url=app.url_path_for("login"), status_code=303)


@app.get("/profile", response_class=HTMLResponse, name="profile")
async def profile(request: Request) -> Response:
    token = request.cookies.get("token")
    if not token:
        return RedirectResponse(url=app.url_path_for("login"), status_code=303)

    # fetch the “/me” endpoint on your user-service
    async with httpx.AsyncClient() as client:
        user_resp = await client.get(
            f"{settings.USER_API_BASE}/users/me",
            headers={"Authorization": f"Bearer {token}"},
        )

    if user_resp.status_code != 200:
        # token expired or invalid → back to login
        return RedirectResponse(url=app.url_path_for("login"), status_code=303)

    user = user_resp.json()
    return templates.TemplateResponse(
        "users/profile.html", {"request": request, "user": user}
    )


@app.get("/show_meetings", response_class=HTMLResponse)
async def show_meetings(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        "meetings/show_meetings.html", {"request": request}
    )
