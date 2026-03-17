from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from agendable.db.models import MeetingOccurrence, Task
from agendable.db.repos import DashboardRepository


@dataclass(slots=True)
class DashboardTaskItem:
    task: Task
    meeting_title: str
    is_overdue: bool
    is_due_soon: bool


@dataclass(slots=True)
class DashboardMeetingItem:
    occurrence: MeetingOccurrence
    participant_count: int
    open_task_count: int
    open_tasks: list[Task]
    has_urgent_tasks: bool


@dataclass(slots=True)
class DashboardView:
    urgent_tasks: list[DashboardTaskItem]
    upcoming_meeting_items: list[DashboardMeetingItem]
    outstanding_task_count: int


class DashboardService:
    def __init__(self, *, dashboard_repo: DashboardRepository) -> None:
        self.dashboard_repo = dashboard_repo

    @classmethod
    def from_session(cls, session: AsyncSession) -> DashboardService:
        return cls(dashboard_repo=DashboardRepository(session))

    async def get_dashboard_view(
        self,
        *,
        user_id: uuid.UUID,
        now: datetime,
        meeting_limit: int = 20,
        task_limit: int = 200,
    ) -> DashboardView:
        upcoming_meetings = await self.list_upcoming_meetings(
            user_id=user_id,
            now=now,
            limit=meeting_limit,
        )
        outstanding_tasks = await self.list_outstanding_tasks(
            user_id=user_id,
            limit=task_limit,
        )

        urgent_cutoff = now + timedelta(days=3)
        normalized_now = _normalize_datetime(now)
        normalized_urgent_cutoff = _normalize_datetime(urgent_cutoff)
        urgent_tasks: list[DashboardTaskItem] = []
        for task in outstanding_tasks:
            if task.assigned_user_id != user_id:
                continue

            due_at = _normalize_datetime(task.due_at)
            is_overdue = due_at < normalized_now
            is_due_soon = normalized_now <= due_at <= normalized_urgent_cutoff
            if not (is_overdue or is_due_soon):
                continue

            urgent_tasks.append(
                DashboardTaskItem(
                    task=task,
                    meeting_title=task.occurrence.series.title,
                    is_overdue=is_overdue,
                    is_due_soon=is_due_soon,
                )
            )

        tasks_by_occurrence: dict[uuid.UUID, list[Task]] = {}
        for task in outstanding_tasks:
            tasks_by_occurrence.setdefault(task.occurrence_id, []).append(task)

        upcoming_meeting_items: list[DashboardMeetingItem] = []
        for occurrence in upcoming_meetings:
            open_tasks = tasks_by_occurrence.get(occurrence.id, [])
            has_urgent_tasks = any(
                _normalize_datetime(task.due_at) <= normalized_urgent_cutoff for task in open_tasks
            )
            upcoming_meeting_items.append(
                DashboardMeetingItem(
                    occurrence=occurrence,
                    participant_count=1 + len(occurrence.attendees),
                    open_task_count=len(open_tasks),
                    open_tasks=open_tasks,
                    has_urgent_tasks=has_urgent_tasks,
                )
            )

        return DashboardView(
            urgent_tasks=urgent_tasks[:8],
            upcoming_meeting_items=upcoming_meeting_items,
            outstanding_task_count=len(outstanding_tasks),
        )

    async def list_upcoming_meetings(
        self,
        *,
        user_id: uuid.UUID,
        now: datetime,
        limit: int = 20,
    ) -> list[MeetingOccurrence]:
        return await self.dashboard_repo.list_upcoming_meetings(
            user_id=user_id,
            now=now,
            limit=limit,
        )

    async def list_outstanding_tasks(
        self,
        *,
        user_id: uuid.UUID,
        limit: int = 200,
    ) -> list[Task]:
        return await self.dashboard_repo.list_outstanding_tasks(
            user_id=user_id,
            limit=limit,
        )


def _normalize_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value
