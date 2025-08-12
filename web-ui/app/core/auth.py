from typing import Any, Awaitable, Callable
from urllib.parse import quote

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import RedirectResponse

PUBLIC_PATHS = {
    "/users/login",
    "/users/register",
    "/favicon.ico",
    "/static",
}

RequestHandler = Callable[[Request], Awaitable[Response]]


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestHandler) -> Any:
        url_path = request.url.path

        # Skip public paths
        if any(url_path == p or url_path.startswith(p + "/") for p in PUBLIC_PATHS):
            return await call_next(request)

        # Check for token
        token = request.cookies.get("token")

        if not token:
            print("[AUTH] No token found, redirecting to login")
            # remember where we wanted to go
            next_url = request.url.path
            if request.url.query:
                next_url += "?" + request.url.query

            login_url = request.url_for("login")
            return RedirectResponse(
                f"{login_url}?next={quote(next_url, safe='/:?&=')}", status_code=303
            )

        return await call_next(request)
