from __future__ import annotations

import asyncio

from sqlalchemy import text

import agendable.db as db
from agendable.db.models import Base


async def init_db() -> None:
    async with db.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def check_db(*, timeout_seconds: float) -> None:
    async def _ping() -> None:
        async with db.engine.connect() as conn:
            await conn.execute(text("SELECT 1"))

    await asyncio.wait_for(_ping(), timeout=timeout_seconds)
