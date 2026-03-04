"""Add external calendar connection and event mirror tables.

Revision ID: 0017
Revises: 0016
Create Date: 2026-03-03
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    calendar_provider_enum = sa.Enum("google", name="calendar_provider")
    provider_column_type: sa.TypeEngine[object]
    if bind.dialect.name == "postgresql":
        op.execute(
            """
            DO $$
            BEGIN
                CREATE TYPE calendar_provider AS ENUM ('google');
            EXCEPTION
                WHEN duplicate_object THEN NULL;
            END
            $$;
            """
        )
        provider_column_type = postgresql.ENUM(
            "google",
            name="calendar_provider",
            create_type=False,
        )
    else:
        calendar_provider_enum.create(bind, checkfirst=True)
        provider_column_type = calendar_provider_enum

    op.create_table(
        "external_calendar_connection",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("provider", provider_column_type, nullable=False, server_default="google"),
        sa.Column("external_calendar_id", sa.String(length=255), nullable=False),
        sa.Column("calendar_display_name", sa.String(length=300), nullable=True),
        sa.Column("scope", sa.Text(), nullable=True),
        sa.Column("access_token", sa.Text(), nullable=True),
        sa.Column("refresh_token", sa.Text(), nullable=True),
        sa.Column("access_token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sync_token", sa.Text(), nullable=True),
        sa.Column("watch_channel_id", sa.String(length=255), nullable=True),
        sa.Column("watch_resource_id", sa.String(length=255), nullable=True),
        sa.Column("watch_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_sync_error_code", sa.String(length=64), nullable=True),
        sa.Column("last_sync_error_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "provider",
            "external_calendar_id",
            name="uq_external_calendar_connection_user_provider_calendar",
        ),
    )
    op.create_index(
        op.f("ix_external_calendar_connection_user_id"),
        "external_calendar_connection",
        ["user_id"],
        unique=False,
    )

    op.create_table(
        "external_calendar_event_mirror",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("connection_id", sa.Uuid(), nullable=False),
        sa.Column("linked_occurrence_id", sa.Uuid(), nullable=True),
        sa.Column("external_event_id", sa.String(length=255), nullable=False),
        sa.Column("external_recurring_event_id", sa.String(length=255), nullable=True),
        sa.Column("external_status", sa.String(length=32), nullable=True),
        sa.Column("etag", sa.String(length=255), nullable=True),
        sa.Column("summary", sa.String(length=500), nullable=True),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_all_day", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("external_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["connection_id"], ["external_calendar_connection.id"]),
        sa.ForeignKeyConstraint(["linked_occurrence_id"], ["meeting_occurrence.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "connection_id",
            "external_event_id",
            name="uq_external_calendar_event_mirror_connection_event",
        ),
    )
    op.create_index(
        op.f("ix_external_calendar_event_mirror_connection_id"),
        "external_calendar_event_mirror",
        ["connection_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_external_calendar_event_mirror_linked_occurrence_id"),
        "external_calendar_event_mirror",
        ["linked_occurrence_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_external_calendar_event_mirror_linked_occurrence_id"),
        table_name="external_calendar_event_mirror",
    )
    op.drop_index(
        op.f("ix_external_calendar_event_mirror_connection_id"),
        table_name="external_calendar_event_mirror",
    )
    op.drop_table("external_calendar_event_mirror")

    op.drop_index(
        op.f("ix_external_calendar_connection_user_id"),
        table_name="external_calendar_connection",
    )
    op.drop_table("external_calendar_connection")

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP TYPE IF EXISTS calendar_provider")
    else:
        calendar_provider_enum = sa.Enum(name="calendar_provider")
        calendar_provider_enum.drop(bind, checkfirst=True)
