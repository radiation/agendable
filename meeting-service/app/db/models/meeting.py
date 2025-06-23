from datetime import datetime
from typing import cast

from common_lib.models import Base
from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, event
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Mapped, Mapper, mapped_column, relationship
import sqlalchemy.sql.functions as func

from .relationships import meeting_tasks, meeting_users


class Meeting(Base):
    __tablename__ = "meetings"
    __table_args__ = (
        Index("ix_recurrence_id", "recurrence_id"),
        Index("ix_meeting_start_date", "start_date"),
        Index("ix_meeting_completed", "completed"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    recurrence_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("recurrences.id"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(100), default="")
    start_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    duration: Mapped[int] = mapped_column(Integer, default=30)
    location: Mapped[str] = mapped_column(String(100), default="")
    notes: Mapped[str] = mapped_column(String)
    num_reschedules: Mapped[int] = mapped_column(Integer, default=0)
    reminder_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    completed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

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
        target.title = cast(Mapped[str], new_title)
