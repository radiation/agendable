import uuid
from uuid import UUID as PyUUID

from common_lib.models import Base
from sqlalchemy import String
from sqlalchemy import UUID as SQLUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship


class User(Base):
    __tablename__ = "users"
    id: Mapped[PyUUID] = mapped_column(
        SQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(String, unique=True)
    first_name: Mapped[str] = mapped_column(String)
    last_name: Mapped[str] = mapped_column(String)

    meetings = relationship(
        "Meeting", secondary="meeting_users", back_populates="users"
    )

    def __repr__(self) -> str:
        return f"<User {self.email}>"
