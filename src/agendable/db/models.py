from __future__ import annotations

import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class ReminderChannel(enum.StrEnum):
    email = "email"
    slack = "slack"


class ReminderDeliveryStatus(enum.StrEnum):
    pending = "pending"
    retry_scheduled = "retry_scheduled"
    sent = "sent"
    failed_terminal = "failed_terminal"
    skipped = "skipped"


class UserRole(enum.StrEnum):
    user = "user"
    admin = "admin"


class CalendarProvider(enum.StrEnum):
    google = "google"


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    first_name: Mapped[str] = mapped_column(String(120))
    last_name: Mapped[str] = mapped_column(String(120))
    display_name: Mapped[str] = mapped_column(String(200))
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.user)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    prefers_dark_mode: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    meeting_series: Mapped[list[MeetingSeries]] = relationship(back_populates="owner")
    assigned_tasks: Mapped[list[Task]] = relationship(back_populates="assignee")
    attendance: Mapped[list[MeetingOccurrenceAttendee]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    external_identities: Mapped[list[ExternalIdentity]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    calendar_connections: Mapped[list[ExternalCalendarConnection]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()


class ExternalIdentity(Base):
    __tablename__ = "external_identities"
    __table_args__ = (
        UniqueConstraint("provider", "subject", name="uq_external_identity_provider_subject"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)

    # Identity provider (e.g. "google", "okta", "azuread", "saml")
    provider: Mapped[str] = mapped_column(String(50), index=True)
    # Provider subject / NameID / sub
    subject: Mapped[str] = mapped_column(String(255))

    # Optional cached attributes
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    user: Mapped[User] = relationship(back_populates="external_identities")


class MeetingSeries(Base):
    __tablename__ = "meeting_series"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)

    title: Mapped[str] = mapped_column(String(200))
    default_interval_days: Mapped[int] = mapped_column(Integer, default=7)
    reminder_minutes_before: Mapped[int] = mapped_column(Integer, default=60)

    # RRULE recurrence (optional; preferred over default_interval_days when present).
    recurrence_rrule: Mapped[str | None] = mapped_column(Text, nullable=True)
    recurrence_dtstart: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    recurrence_timezone: Mapped[str | None] = mapped_column(String(64), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    owner: Mapped[User] = relationship(back_populates="meeting_series")
    occurrences: Mapped[list[MeetingOccurrence]] = relationship(
        back_populates="series", cascade="all, delete-orphan"
    )


class MeetingOccurrence(Base):
    __tablename__ = "meeting_occurrence"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    series_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("meeting_series.id"), index=True)

    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    is_completed: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    series: Mapped[MeetingSeries] = relationship(back_populates="occurrences")
    agenda_items: Mapped[list[AgendaItem]] = relationship(
        back_populates="occurrence", cascade="all, delete-orphan"
    )
    tasks: Mapped[list[Task]] = relationship(
        back_populates="occurrence", cascade="all, delete-orphan"
    )
    attendees: Mapped[list[MeetingOccurrenceAttendee]] = relationship(
        back_populates="occurrence", cascade="all, delete-orphan"
    )
    reminders: Mapped[list[Reminder]] = relationship(
        back_populates="occurrence", cascade="all, delete-orphan"
    )
    external_event_mirrors: Mapped[list[ExternalCalendarEventMirror]] = relationship(
        back_populates="linked_occurrence"
    )


class ExternalCalendarConnection(Base):
    __tablename__ = "external_calendar_connection"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "provider",
            "external_calendar_id",
            name="uq_external_calendar_connection_user_provider_calendar",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)

    provider: Mapped[CalendarProvider] = mapped_column(
        Enum(CalendarProvider, name="calendar_provider"),
        default=CalendarProvider.google,
    )
    external_calendar_id: Mapped[str] = mapped_column(String(255))
    calendar_display_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    scope: Mapped[str | None] = mapped_column(Text, nullable=True)

    access_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    refresh_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    access_token_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    sync_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    watch_channel_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    watch_resource_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    watch_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_sync_error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_sync_error_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    user: Mapped[User] = relationship(back_populates="calendar_connections")
    event_mirrors: Mapped[list[ExternalCalendarEventMirror]] = relationship(
        back_populates="connection", cascade="all, delete-orphan"
    )


class ExternalCalendarEventMirror(Base):
    __tablename__ = "external_calendar_event_mirror"
    __table_args__ = (
        UniqueConstraint(
            "connection_id",
            "external_event_id",
            name="uq_external_calendar_event_mirror_connection_event",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    connection_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("external_calendar_connection.id"), index=True
    )
    linked_occurrence_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("meeting_occurrence.id"), index=True, nullable=True
    )

    external_event_id: Mapped[str] = mapped_column(String(255))
    external_recurring_event_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    external_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    etag: Mapped[str | None] = mapped_column(String(255), nullable=True)

    summary: Mapped[str | None] = mapped_column(String(500), nullable=True)
    start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_all_day: Mapped[bool] = mapped_column(Boolean, default=False)

    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    external_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    connection: Mapped[ExternalCalendarConnection] = relationship(back_populates="event_mirrors")
    linked_occurrence: Mapped[MeetingOccurrence | None] = relationship(
        back_populates="external_event_mirrors"
    )


class MeetingOccurrenceAttendee(Base):
    __tablename__ = "meeting_occurrence_attendee"
    __table_args__ = (
        UniqueConstraint(
            "occurrence_id",
            "user_id",
            name="uq_meeting_occurrence_attendee_occurrence_user",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    occurrence_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("meeting_occurrence.id"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    occurrence: Mapped[MeetingOccurrence] = relationship(back_populates="attendees")
    user: Mapped[User] = relationship(back_populates="attendance")


class AgendaItem(Base):
    __tablename__ = "agenda_item"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    occurrence_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("meeting_occurrence.id"), index=True
    )

    body: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_done: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    occurrence: Mapped[MeetingOccurrence] = relationship(back_populates="agenda_items")


class Task(Base):
    __tablename__ = "task"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    occurrence_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("meeting_occurrence.id"), index=True
    )
    assigned_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)

    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    is_done: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    occurrence: Mapped[MeetingOccurrence] = relationship(back_populates="tasks")
    assignee: Mapped[User] = relationship(back_populates="assigned_tasks")


class Reminder(Base):
    __tablename__ = "reminder"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    occurrence_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("meeting_occurrence.id"), index=True
    )

    channel: Mapped[ReminderChannel] = mapped_column(Enum(ReminderChannel, name="reminder_channel"))
    send_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_attempted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    delivery_status: Mapped[ReminderDeliveryStatus] = mapped_column(
        Enum(ReminderDeliveryStatus, name="reminder_delivery_status"),
        default=ReminderDeliveryStatus.pending,
    )
    failure_reason_code: Mapped[str | None] = mapped_column(String(64), nullable=True)

    occurrence: Mapped[MeetingOccurrence] = relationship(back_populates="reminders")
