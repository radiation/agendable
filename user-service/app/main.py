from common_lib.exceptions import (
    ForbiddenError,
    NotFoundError,
    ValidationError,
    forbidden_exception_handler,
    generic_exception_handler,
    not_found_exception_handler,
    validation_exception_handler,
)
from fastapi import FastAPI

from app.api.v1.routes import auth, group, role, user

app = FastAPI(title="User Service", version="1.0.0")

# Register exception handlers
app.add_exception_handler(ForbiddenError, forbidden_exception_handler)
app.add_exception_handler(NotFoundError, not_found_exception_handler)
app.add_exception_handler(ValidationError, validation_exception_handler)
app.add_exception_handler(Exception, generic_exception_handler)

# Include routers
app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(group.router, prefix="/groups", tags=["groups"])
app.include_router(role.router, prefix="/roles", tags=["roles"])
app.include_router(user.router, prefix="/users", tags=["users"])


@app.get("/")
async def root() -> dict[str, str]:
    return {"message": "User Service is running"}
