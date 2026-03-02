"""Add reminder delivery status, attempts, and failure reason tracking.

Revision ID: 0016
Revises: 0015
Create Date: 2026-03-02
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    delivery_status_enum = sa.Enum(
        "pending",
        "retry_scheduled",
        "sent",
        "failed_terminal",
        "skipped",
        name="reminder_delivery_status",
    )
    delivery_status_enum.create(op.get_bind(), checkfirst=True)

    with op.batch_alter_table("reminder") as batch:
        batch.add_column(sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("last_attempted_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(
            sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0")
        )
        batch.add_column(
            sa.Column(
                "delivery_status",
                delivery_status_enum,
                nullable=False,
                server_default="pending",
            )
        )
        batch.add_column(sa.Column("failure_reason_code", sa.String(length=64), nullable=True))

    op.execute("UPDATE reminder SET next_attempt_at = send_at WHERE next_attempt_at IS NULL")


def downgrade() -> None:
    with op.batch_alter_table("reminder") as batch:
        batch.drop_column("failure_reason_code")
        batch.drop_column("delivery_status")
        batch.drop_column("attempt_count")
        batch.drop_column("last_attempted_at")
        batch.drop_column("next_attempt_at")

    delivery_status_enum = sa.Enum(name="reminder_delivery_status")
    delivery_status_enum.drop(op.get_bind(), checkfirst=True)
