from typing import Any, Union

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
import httpx

from app.core.config import settings
from app.core.templating import templates

router = APIRouter(tags=["users"])


@router.get("/login", response_class=HTMLResponse, name="login")
async def login_page(request: Request, next_url: str | None = None) -> Any:
    return templates.TemplateResponse(
        "users/login.html", {"request": request, "next": next_url or ""}
    )


@router.post(
    "/login", response_class=HTMLResponse, response_model=None, name="login_post"
)
async def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    next_url: str | None = Form(None),
) -> Union[Any, RedirectResponse]:
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{settings.USER_API_BASE}/auth/login",
            json={"email": email, "password": password},
        )

    if resp.status_code != 200:
        # invalid credentials
        return templates.TemplateResponse(
            "users/login.html",
            {"request": request, "error": "Invalid email or password"},
            status_code=400,
        )

    token = resp.json().get("access_token")

    # set cookie, then redirect to previous page or profile
    response = RedirectResponse(
        url=next_url or request.url_for("profile"), status_code=303
    )
    response.set_cookie(
        key="token",
        value=token,
        httponly=True,
        max_age=3600,
        samesite="lax",
        path="/",
    )
    return response


@router.get("/logout", name="logout")
async def logout() -> RedirectResponse:
    resp = RedirectResponse(url=router.url_path_for("login"))
    resp.delete_cookie("token")
    return resp


@router.get("/register", response_class=HTMLResponse, name="register")
async def register_form(request: Request) -> Any:
    return templates.TemplateResponse(
        "users/register.html",
        {
            "request": request,
            "USER_API_BASE": settings.USER_API_BASE,
            "MEETING_API_BASE": settings.MEETING_API_BASE,
        },
    )


@router.post(
    "/register", response_class=HTMLResponse, response_model=None, name="register_post"
)
async def register_post(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    first_name: str = Form(...),
    last_name: str = Form(...),
) -> Union[Any, RedirectResponse]:
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

    if resp.status_code not in (200, 201):
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
    return RedirectResponse(url=request.url_for("login"), status_code=303)


@router.get(
    "/profile", response_class=HTMLResponse, response_model=None, name="profile"
)
async def profile(request: Request) -> Union[Any, RedirectResponse]:
    token = request.cookies.get("token")
    if not token:
        return RedirectResponse(url=router.url_path_for("login"), status_code=303)

    async with httpx.AsyncClient() as client:
        user_resp = await client.get(
            f"{settings.USER_API_BASE}/users/me",
            headers={"Authorization": f"Bearer {token}"},
        )

    if user_resp.status_code != 200:
        # token expired or invalid, redirect to login
        return RedirectResponse(url=router.url_path_for("login"), status_code=303)

    user = user_resp.json()
    return templates.TemplateResponse(
        "users/profile.html", {"request": request, "user": user}
    )


@router.get("/list", response_class=HTMLResponse, response_model=None, name="user_list")
async def user_list(request: Request) -> Union[Any, RedirectResponse]:
    token = request.cookies.get("token")
    if not token:
        return RedirectResponse(url=request.url_for("login"), status_code=303)

    async with httpx.AsyncClient() as client:
        user_resp = await client.get(
            f"{settings.USER_API_BASE}/users/",
            headers={"Authorization": f"Bearer {token}"},
        )

    # token expired or invalid
    if user_resp.status_code != 200:
        return RedirectResponse(url=request.url_for("login"), status_code=303)

    users = user_resp.json()
    return templates.TemplateResponse(
        "users/list.html", {"request": request, "users": users}
    )
