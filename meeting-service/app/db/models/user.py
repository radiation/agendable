import uuid

from sqlalchemy import Column, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from common_lib.models import Base


class User(Base):
    __tablename__ = "users"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)  # type: ignore
    email = Column(String, unique=True)
    first_name = Column(String)
    last_name = Column(String)

    meetings = relationship(
        "Meeting", secondary="meeting_users", back_populates="users"
    )

    def __repr__(self) -> str:
        return f"<User {self.email}>"
