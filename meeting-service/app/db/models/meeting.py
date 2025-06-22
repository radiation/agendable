from typing import cast

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    event,
)
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Mapper, relationship
import sqlalchemy.sql.functions as func

from . import Base
from .relationships import meeting_tasks, meeting_users


class Meeting(Base):
    __tablename__ = "meetings"
    __table_args__ = (
        Index("ix_recurrence_id", "recurrence_id"),
        Index("ix_meeting_start_date", "start_date"),
        Index("ix_meeting_completed", "completed"),
    )

    id = Column(Integer, primary_key=True)
    recurrence_id = Column(Integer, ForeignKey("recurrences.id"), nullable=True)
    title = Column(String(100), default="")
    start_date = Column(DateTime(timezone=True))
    duration = Column(Integer, default=30)
    location = Column(String(100), default="")
    notes = Column(String)
    num_reschedules = Column(Integer, default=0)
    reminder_sent = Column(Boolean, default=False)
    completed = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    recurrence = relationship("Recurrence", back_populates="meetings", lazy="joined")
    tasks = relationship("Task", secondary=meeting_tasks, back_populates="meetings")
    users = relationship("User", secondary=meeting_users, back_populates="meetings")


@event.listens_for(Meeting, "before_insert")
@event.listens_for(Meeting, "before_update")
def receive_before_save(
    _mapper: Mapper[Meeting], _connection: Connection, target: Meeting
) -> None:
    """Set the title based on recurrence if the title is empty"""
    if not target.title and target.recurrence:
        new_title = f"{target.recurrence.title} on "
        new_title += f"{target.start_date.strftime('%Y-%m-%d')}"
        target.title = cast(Column[str], new_title)
