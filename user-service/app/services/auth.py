from datetime import timedelta
from typing import Optional

from app.core.security import create_access_token, verify_password
from app.db.models.user import User
from app.repositories.user import UserRepository

ACCESS_TOKEN_EXPIRE_MINUTES = 30


class AuthService:
    def __init__(self, repo: UserRepository):
        self.repo = repo

    async def authenticate_user(self, email: str, password: str) -> Optional[User]:
        user = await self.repo.get_by_field("email", email)
        if (
            len(user) == 0
            or not user[0]
            or not verify_password(password, user[0].hashed_password)
        ):
            return None
        return user[0]

    def create_token(self, user: User) -> str:
        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        return create_access_token(
            {"sub": user.email}, expires_delta=access_token_expires
        )
