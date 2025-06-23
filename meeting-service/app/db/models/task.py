from datetime import datetime

from common_lib.models import Base
from sqlalchemy import Boolean, DateTime, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
import sqlalchemy.sql.functions as func

from .relationships import meeting_tasks


class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = (
        Index("ix_task_assignee_id", "assignee_id"),
        Index("ix_task_due_date", "due_date"),
        Index("ix_task_completed", "completed"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    assignee_id: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(100), default="")
    description: Mapped[str] = mapped_column(String(1000), default="")
    due_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    completed: Mapped[bool] = mapped_column(Boolean, default=False)
    completed_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    meetings = relationship("Meeting", secondary=meeting_tasks, back_populates="tasks")
