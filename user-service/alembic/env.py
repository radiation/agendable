import os

from sqlalchemy import engine_from_config, pool

from alembic import context
from common_lib.models import Base

from app.db.models.group import Group
from app.db.models.role import Role
from app.db.models.user import User
from app.db.models.relationships import group_users, user_roles

config = context.config
target_metadata = Base.metadata

def get_url():
    url = os.getenv("USER_DB_URL", "postgresql://user:password@postgres/user_db")
    return url.replace("+asyncpg", "")  # Alembic doesn't support asyncpg


def run_migrations_online():
    # Run migrations in 'online' mode with an established connection.
    connectable = engine_from_config(
        {"sqlalchemy.url": get_url()},
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    print(f"Online - URL: {get_url()}")

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=Base.metadata)

        with context.begin_transaction():
            context.run_migrations()


def run_migrations_offline():
    # Run migrations in 'offline' mode.
    context.configure(
        url=get_url(),
        target_metadata=Base.metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    print(f"Offline - URL: {get_url()}")

    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
