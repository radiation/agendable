from __future__ import annotations

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from agendable.auth import require_admin, require_user
from agendable.db import get_session
from agendable.db.models import User
from agendable.db.repos import (
    AgendaItemRepository,
    DashboardRepository,
    ExternalCalendarConnectionRepository,
    ExternalCalendarEventMirrorRepository,
    ExternalIdentityRepository,
    MeetingOccurrenceAttendeeRepository,
    MeetingOccurrenceRepository,
    MeetingSeriesRepository,
    TaskRepository,
    UserRepository,
)
from agendable.services.admin_service import AdminService
from agendable.services.auth_service import AuthService
from agendable.services.calendar_event_mapping_service import CalendarEventMappingService
from agendable.services.dashboard_service import DashboardService
from agendable.services.google_calendar_client import GoogleCalendarHttpClient
from agendable.services.google_calendar_sync_service import GoogleCalendarSyncService
from agendable.services.google_imported_series_service import GoogleImportedSeriesService
from agendable.services.occurrence_service import OccurrenceService
from agendable.services.series_service import SeriesService
from agendable.settings import Settings, get_settings


async def get_current_user(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> User:
    return await require_user(request, session)


async def get_admin_user(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> User:
    return await require_admin(request, session)


def get_dashboard_repo(
    session: AsyncSession = Depends(get_session),
) -> DashboardRepository:
    return DashboardRepository(session)


def get_meeting_series_repo(
    session: AsyncSession = Depends(get_session),
) -> MeetingSeriesRepository:
    return MeetingSeriesRepository(session)


def get_meeting_occurrence_repo(
    session: AsyncSession = Depends(get_session),
) -> MeetingOccurrenceRepository:
    return MeetingOccurrenceRepository(session)


def get_meeting_occurrence_attendee_repo(
    session: AsyncSession = Depends(get_session),
) -> MeetingOccurrenceAttendeeRepository:
    return MeetingOccurrenceAttendeeRepository(session)


def get_user_repo(
    session: AsyncSession = Depends(get_session),
) -> UserRepository:
    return UserRepository(session)


def get_external_identity_repo(
    session: AsyncSession = Depends(get_session),
) -> ExternalIdentityRepository:
    return ExternalIdentityRepository(session)


def get_external_calendar_connection_repo(
    session: AsyncSession = Depends(get_session),
) -> ExternalCalendarConnectionRepository:
    return ExternalCalendarConnectionRepository(session)


def get_external_calendar_event_mirror_repo(
    session: AsyncSession = Depends(get_session),
) -> ExternalCalendarEventMirrorRepository:
    return ExternalCalendarEventMirrorRepository(session)


def get_calendar_event_mapping_service(
    session: AsyncSession = Depends(get_session),
    occurrence_repo: MeetingOccurrenceRepository = Depends(get_meeting_occurrence_repo),
    series_repo: MeetingSeriesRepository = Depends(get_meeting_series_repo),
) -> CalendarEventMappingService:
    return CalendarEventMappingService(
        session=session,
        occurrence_repo=occurrence_repo,
        series_repo=series_repo,
    )


def get_google_calendar_client(
    settings: Settings = Depends(get_settings),
) -> GoogleCalendarHttpClient:
    return GoogleCalendarHttpClient(
        api_base_url=settings.google_calendar_api_base_url,
        initial_sync_days_back=settings.google_calendar_initial_sync_days_back,
    )


def get_dashboard_service(
    dashboard_repo: DashboardRepository = Depends(get_dashboard_repo),
) -> DashboardService:
    return DashboardService(dashboard_repo=dashboard_repo)


def get_admin_service(
    users: UserRepository = Depends(get_user_repo),
    external_identities: ExternalIdentityRepository = Depends(get_external_identity_repo),
) -> AdminService:
    return AdminService(users=users, external_identities=external_identities)


def get_auth_service(
    session: AsyncSession = Depends(get_session),
    users: UserRepository = Depends(get_user_repo),
    external_identities: ExternalIdentityRepository = Depends(get_external_identity_repo),
    calendar_connections: ExternalCalendarConnectionRepository = Depends(
        get_external_calendar_connection_repo
    ),
    series: MeetingSeriesRepository = Depends(get_meeting_series_repo),
) -> AuthService:
    return AuthService(
        session=session,
        users=users,
        external_identities=external_identities,
        calendar_connections=calendar_connections,
        series=series,
    )


def get_series_service(
    session: AsyncSession = Depends(get_session),
    users: UserRepository = Depends(get_user_repo),
    attendees: MeetingOccurrenceAttendeeRepository = Depends(get_meeting_occurrence_attendee_repo),
    series: MeetingSeriesRepository = Depends(get_meeting_series_repo),
    occurrences: MeetingOccurrenceRepository = Depends(get_meeting_occurrence_repo),
) -> SeriesService:
    return SeriesService(
        session=session,
        users=users,
        attendees=attendees,
        series=series,
        occurrences=occurrences,
    )


def get_occurrence_service(
    session: AsyncSession = Depends(get_session),
    users: UserRepository = Depends(get_user_repo),
    attendees: MeetingOccurrenceAttendeeRepository = Depends(get_meeting_occurrence_attendee_repo),
    occurrences: MeetingOccurrenceRepository = Depends(get_meeting_occurrence_repo),
    series: MeetingSeriesRepository = Depends(get_meeting_series_repo),
) -> OccurrenceService:
    return OccurrenceService(
        session=session,
        users=users,
        attendees=attendees,
        occurrences=occurrences,
        series=series,
        tasks=TaskRepository(session),
        agenda_items=AgendaItemRepository(session),
    )


def get_google_imported_series_service(
    session: AsyncSession = Depends(get_session),
    series_repo: MeetingSeriesRepository = Depends(get_meeting_series_repo),
    mirror_repo: ExternalCalendarEventMirrorRepository = Depends(
        get_external_calendar_event_mirror_repo
    ),
    occurrence_repo: MeetingOccurrenceRepository = Depends(get_meeting_occurrence_repo),
    connection_repo: ExternalCalendarConnectionRepository = Depends(
        get_external_calendar_connection_repo
    ),
    event_mapper: CalendarEventMappingService = Depends(get_calendar_event_mapping_service),
) -> GoogleImportedSeriesService:
    return GoogleImportedSeriesService(
        session=session,
        series_repo=series_repo,
        mirror_repo=mirror_repo,
        occurrence_repo=occurrence_repo,
        connection_repo=connection_repo,
        event_mapper=event_mapper,
    )


def get_google_calendar_sync_service(
    connection_repo: ExternalCalendarConnectionRepository = Depends(
        get_external_calendar_connection_repo
    ),
    event_mirror_repo: ExternalCalendarEventMirrorRepository = Depends(
        get_external_calendar_event_mirror_repo
    ),
    calendar_client: GoogleCalendarHttpClient = Depends(get_google_calendar_client),
    event_mapper: CalendarEventMappingService = Depends(get_calendar_event_mapping_service),
    settings: Settings = Depends(get_settings),
) -> GoogleCalendarSyncService:
    return GoogleCalendarSyncService(
        connection_repo=connection_repo,
        event_mirror_repo=event_mirror_repo,
        calendar_client=calendar_client,
        event_mapper=event_mapper,
        settings=settings,
    )


__all__ = [
    "get_admin_service",
    "get_admin_user",
    "get_auth_service",
    "get_calendar_event_mapping_service",
    "get_current_user",
    "get_dashboard_repo",
    "get_dashboard_service",
    "get_external_calendar_connection_repo",
    "get_external_calendar_event_mirror_repo",
    "get_external_identity_repo",
    "get_google_calendar_client",
    "get_google_calendar_sync_service",
    "get_google_imported_series_service",
    "get_meeting_occurrence_attendee_repo",
    "get_meeting_occurrence_repo",
    "get_meeting_series_repo",
    "get_occurrence_service",
    "get_series_service",
    "get_session",
    "get_user_repo",
]
