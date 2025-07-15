from typing import Optional

from common_lib.redis_client import redis_client
from fastapi import Depends, HTTPException, status
from jose import JWTError, jwt
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import oauth2_scheme
from app.db.session import get_db
from app.repositories.group import GroupRepository
from app.repositories.role import RoleRepository
from app.repositories.user import UserRepository
from app.services.auth import AuthService
from app.services.group import GroupService
from app.services.role import RoleService
from app.services.user import UserService


def get_user_repository(db: AsyncSession = Depends(get_db)) -> UserRepository:
    return UserRepository(db)


def get_user_service(
    repo: UserRepository = Depends(get_user_repository),
    redis: Redis = Depends(lambda: redis_client),
) -> UserService:
    return UserService(repo, redis)


def get_group_repository(db: AsyncSession = Depends(get_db)) -> GroupRepository:
    return GroupRepository(db)


def get_group_service(
    repo: GroupRepository = Depends(get_group_repository),
    redis: Redis = Depends(lambda: redis_client),
) -> GroupService:
    return GroupService(repo, redis)


def get_role_repository(db: AsyncSession = Depends(get_db)) -> RoleRepository:
    return RoleRepository(db)


def get_role_service(
    repo: RoleRepository = Depends(get_role_repository),
    redis: Redis = Depends(lambda: redis_client),
) -> RoleService:
    return RoleService(repo, redis)


def get_auth_service(
    repo: UserRepository = Depends(get_user_repository),
) -> AuthService:
    return AuthService(repo)


async def get_current_user(
    token: str = Depends(oauth2_scheme),
) -> str:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        email: Optional[str] = payload.get("sub")
        if email is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return email
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
