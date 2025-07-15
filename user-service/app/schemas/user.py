from typing import Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr

from app.core.security import get_password_hash


class UserBase(BaseModel):
    email: EmailStr
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    is_active: Optional[bool] = True
    is_superuser: Optional[bool] = False


class UserCreate(UserBase):
    hashed_password: str


class UserRegistration(UserBase):
    password: str

    def to_create(self) -> UserCreate:
        data = self.model_dump(exclude_none=True)
        raw = data.pop("password")
        data["hashed_password"] = get_password_hash(raw)
        return UserCreate(**data)


class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    is_active: Optional[bool] = None
    is_superuser: Optional[bool] = None


class UserRetrieve(UserBase):
    id: UUID

    model_config = {"from_attributes": True}

    def model_dump(self, **kwargs):  # type: ignore
        kwargs.setdefault("exclude", {"hashed_password"})
        return super().model_dump(**kwargs)
