"""Add imported-series review decision fields.

Revision ID: 0018
Revises: 0017
Create Date: 2026-03-11
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()

    import_decision_enum = sa.Enum(
        "pending",
        "kept",
        "rejected",
        name="imported_series_decision",
    )

    if bind.dialect.name == "postgresql":
        op.execute(
            """
            DO $$
            BEGIN
                CREATE TYPE imported_series_decision AS ENUM ('pending', 'kept', 'rejected');
            EXCEPTION
                WHEN duplicate_object THEN NULL;
            END
            $$;
            """
        )
        import_decision_column_type = postgresql.ENUM(
            "pending",
            "kept",
            "rejected",
            name="imported_series_decision",
            create_type=False,
        )
        provider_column_type = postgresql.ENUM(
            "google",
            name="calendar_provider",
            create_type=False,
        )
    else:
        import_decision_enum.create(bind, checkfirst=True)
        import_decision_column_type = import_decision_enum
        provider_column_type = sa.Enum("google", name="calendar_provider")

    op.add_column(
        "meeting_series",
        sa.Column(
            "imported_from_provider",
            provider_column_type,
            nullable=True,
        ),
    )
    op.add_column(
        "meeting_series",
        sa.Column("import_external_series_id", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "meeting_series",
        sa.Column("import_decision", import_decision_column_type, nullable=True),
    )
    op.create_index(
        op.f("ix_meeting_series_import_external_series_id"),
        "meeting_series",
        ["import_external_series_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_meeting_series_import_external_series_id"),
        table_name="meeting_series",
    )
    op.drop_column("meeting_series", "import_decision")
    op.drop_column("meeting_series", "import_external_series_id")
    op.drop_column("meeting_series", "imported_from_provider")

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP TYPE IF EXISTS imported_series_decision")
    else:
        import_decision_enum = sa.Enum(name="imported_series_decision")
        import_decision_enum.drop(bind, checkfirst=True)
