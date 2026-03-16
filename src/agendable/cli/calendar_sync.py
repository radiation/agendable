from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

import agendable.db as db
from agendable.db.repos import (
    ExternalCalendarConnectionRepository,
    ExternalCalendarEventMirrorRepository,
)
from agendable.logging_config import log_with_fields
from agendable.services.calendar_event_mapping_service import CalendarEventMappingService
from agendable.services.google_calendar_client import GoogleCalendarHttpClient
from agendable.services.google_calendar_sync_service import GoogleCalendarSyncService
from agendable.settings import get_settings

logger = logging.getLogger(__name__)


async def run_google_calendar_sync() -> int:
    settings = get_settings()
    if not settings.google_calendar_sync_enabled:
        logger.info("google calendar sync skipped: feature disabled")
        return 0

    async with db.SessionMaker() as session:
        sync_service = GoogleCalendarSyncService(
            connection_repo=ExternalCalendarConnectionRepository(session),
            event_mirror_repo=ExternalCalendarEventMirrorRepository(session),
            calendar_client=GoogleCalendarHttpClient(
                api_base_url=settings.google_calendar_api_base_url,
                initial_sync_days_back=settings.google_calendar_initial_sync_days_back,
            ),
            event_mapper=CalendarEventMappingService.from_session(session),
            settings=settings,
        )
        synced_event_count = await sync_service.sync_all_enabled_connections()

    logger.info("google calendar sync complete: synced_event_count=%s", synced_event_count)
    return synced_event_count


async def run_google_calendar_sync_worker(poll_seconds: int) -> None:
    while True:
        started_at = datetime.now(UTC)
        synced_event_count: int | None = None
        try:
            synced_event_count = await run_google_calendar_sync()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("google calendar sync worker iteration failed")
        finally:
            duration_ms = int((datetime.now(UTC) - started_at).total_seconds() * 1000)
            log_with_fields(
                logger,
                logging.INFO,
                "google calendar sync worker iteration complete",
                duration_ms=duration_ms,
                synced_event_count=synced_event_count,
            )
        await asyncio.sleep(poll_seconds)
