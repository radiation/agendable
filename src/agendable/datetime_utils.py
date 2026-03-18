from __future__ import annotations

from datetime import UTC, datetime, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def format_datetime_local_value(value: datetime, timezone_name: str | None) -> str:
    dt_utc = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)

    tz_name = (timezone_name or "UTC").strip() or "UTC"
    target_zone: tzinfo
    try:
        target_zone = ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        target_zone = UTC

    return dt_utc.astimezone(target_zone).strftime("%Y-%m-%dT%H:%M")
