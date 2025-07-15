from typing import Optional
from uuid import UUID

from common_lib.exceptions import ForbiddenError, NotFoundError, ValidationError
from common_lib.logging_config import logger
from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, EmailStr

from app.core.dependencies import get_auth_service, get_user_service
from app.core.security import create_access_token, decode_access_token, verify_password
from app.db.models.user import User
from app.schemas.auth import Token
from app.schemas.user import UserRegistration, UserRetrieve
from app.services.auth import AuthService
from app.services.user import UserService

router = APIRouter()


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


@router.post("/register", response_model=Token)
async def register_user(
    registration_data: UserRegistration,
    service: UserService = Depends(get_user_service),
) -> Token:
    logger.info(f"Registering user with data: {registration_data.model_dump()}")
    existing_user: list[User] = await service.get_by_field(
        field_name="email", value=registration_data.email
    )
    if existing_user:
        logger.warning(f"User with email {registration_data.email} already exists")
        raise ValidationError("User with this email already exists")
    try:
        new_user: User = await service.register_user(registration_data)
        logger.info(f"User created successfully with ID: {new_user.id}")
        token = create_access_token(data={"sub": new_user.email, "id": new_user.id})
        logger.debug(f"Token: {token}")
        return Token(access_token=token, token_type="bearer")
    except Exception as exc:
        logger.exception("Unexpected error while creating user")
        raise ValidationError(
            "An unexpected error occurred. Please try again."
        ) from exc


@router.post("/login", response_model=Token)
async def login_user(
    login_request: LoginRequest,
    service: AuthService = Depends(get_auth_service),
) -> Token:
    user: Optional[User] = await service.authenticate_user(
        email=login_request.email, password=login_request.password
    )
    if not user:
        raise NotFoundError(f"User with email {login_request.email} not found")
    if not verify_password(login_request.password, user.hashed_password):
        raise ForbiddenError(f"Invalid password for user {login_request.email}")
    token = create_access_token(data={"sub": user.email})
    return Token(access_token=token, token_type="bearer")


@router.get("/protected-route", response_model=UserRetrieve)
async def protected_route(authorization: str = Header(...)) -> UserRetrieve:
    STUB_UUID = UUID("00000000-0000-0000-0000-000000000001")
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token format"
        )

    token = authorization.split(" ")[1]
    try:
        payload = decode_access_token(token)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)
        ) from exc

    return UserRetrieve(id=STUB_UUID, email=payload["sub"])
