from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncEngine

import agendable.db as db
from agendable.recurrence import build_rrule
from agendable.services.dev_seed_service import (
    SeedSeriesSpec,
    SeedSummary,
    SeedUserSpec,
    reset_database,
)
from agendable.services.dev_seed_service import (
    seed_dev_data as seed_dev_data_with_service,
)
from agendable.settings import get_settings


def _seed_users() -> tuple[SeedUserSpec, ...]:
    return (
        SeedUserSpec(
            email="alex.manager+seed@example.com",
            first_name="Alex",
            last_name="Manager",
            timezone="America/Chicago",
        ),
        SeedUserSpec(
            email="jamie.engineer+seed@example.com",
            first_name="Jamie",
            last_name="Engineer",
            timezone="America/New_York",
        ),
        SeedUserSpec(
            email="riley.designer+seed@example.com",
            first_name="Riley",
            last_name="Designer",
            timezone="America/Los_Angeles",
        ),
    )


def _seed_series() -> tuple[SeedSeriesSpec, ...]:
    now_utc = datetime.now(UTC)

    one_on_one_tz = ZoneInfo("America/Chicago")
    one_on_one_start = (
        (now_utc - timedelta(days=28))
        .astimezone(one_on_one_tz)
        .replace(
            hour=10,
            minute=0,
            second=0,
            microsecond=0,
        )
    )

    design_sync_tz = ZoneInfo("America/Los_Angeles")
    design_sync_start = (
        (now_utc - timedelta(days=21))
        .astimezone(design_sync_tz)
        .replace(
            hour=14,
            minute=30,
            second=0,
            microsecond=0,
        )
    )

    planning_tz = ZoneInfo("America/New_York")
    planning_start = (
        (now_utc - timedelta(days=12))
        .astimezone(planning_tz)
        .replace(
            hour=9,
            minute=15,
            second=0,
            microsecond=0,
        )
    )

    return (
        SeedSeriesSpec(
            owner_email="alex.manager+seed@example.com",
            title="[Seed] 1:1 Alex <> Jamie",
            recurrence_rrule=build_rrule(
                freq="WEEKLY",
                interval=1,
                dtstart=one_on_one_start,
                weekly_byday=["MO"],
            ),
            recurrence_dtstart=one_on_one_start,
            recurrence_timezone="America/Chicago",
            reminder_minutes_before=30,
            generate_count=10,
            attendee_emails=(
                "alex.manager+seed@example.com",
                "jamie.engineer+seed@example.com",
            ),
        ),
        SeedSeriesSpec(
            owner_email="riley.designer+seed@example.com",
            title="[Seed] Product Design Sync",
            recurrence_rrule=build_rrule(
                freq="WEEKLY",
                interval=1,
                dtstart=design_sync_start,
                weekly_byday=["WE"],
            ),
            recurrence_dtstart=design_sync_start,
            recurrence_timezone="America/Los_Angeles",
            reminder_minutes_before=45,
            generate_count=12,
            attendee_emails=(
                "riley.designer+seed@example.com",
                "alex.manager+seed@example.com",
                "jamie.engineer+seed@example.com",
            ),
        ),
        SeedSeriesSpec(
            owner_email="jamie.engineer+seed@example.com",
            title="[Seed] Engineering Planning",
            recurrence_rrule=build_rrule(
                freq="DAILY",
                interval=2,
                dtstart=planning_start,
            ),
            recurrence_dtstart=planning_start,
            recurrence_timezone="America/New_York",
            reminder_minutes_before=20,
            generate_count=14,
            attendee_emails=(
                "jamie.engineer+seed@example.com",
                "alex.manager+seed@example.com",
            ),
        ),
    )


async def seed_dev_data(*, reset: bool, password: str) -> SeedSummary:
    settings = get_settings()

    if reset:
        bind = db.SessionMaker.kw.get("bind")
        if bind is None or not isinstance(bind, AsyncEngine):
            raise RuntimeError("SessionMaker is not bound to an async engine")
        await reset_database(bind)

    summary = await seed_dev_data_with_service(
        session_maker=db.SessionMaker,
        settings=settings,
        user_specs=_seed_users(),
        series_specs=_seed_series(),
        password=password,
    )

    return SeedSummary(
        users_created=summary.users_created,
        series_created=summary.series_created,
        occurrences_created=summary.occurrences_created,
        attendees_added=summary.attendees_added,
        agenda_items_created=summary.agenda_items_created,
        tasks_created=summary.tasks_created,
        reset_applied=reset,
    )


__all__ = ["seed_dev_data"]
