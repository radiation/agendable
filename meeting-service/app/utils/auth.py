from typing import Optional

from common_lib.exceptions import ForbiddenError
from fastapi import Request


def get_user_metadata(request: Request) -> dict[str, Optional[str]]:
    """Extracts user metadata from request headers."""
    user_id = request.headers.get("X-User-ID")
    user_email = request.headers.get("X-User-Email")
    if not user_id:
        raise ForbiddenError(detail=f"User not {user_email} authenticated")
    return {"id": user_id, "email": user_email}
