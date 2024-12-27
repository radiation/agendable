from app.errors import NotFoundError
from app.repositories.meeting_attendee_repository import MeetingAttendeeRepository
from app.schemas.meeting_attendee_schemas import (
    MeetingAttendeeCreate,
    MeetingAttendeeRetrieve,
    MeetingAttendeeUpdate,
)


class MeetingAttendeeService:
    def __init__(self, attendee_repo: MeetingAttendeeRepository):
        self.attendee_repo = attendee_repo

    async def create_meeting_attendee(
        self, attendee_data: MeetingAttendeeCreate
    ) -> MeetingAttendeeRetrieve:
        attendee = await self.attendee_repo.create(attendee_data.model_dump())
        return MeetingAttendeeRetrieve.model_validate(attendee)

    async def get_meeting_attendees(
        self, skip: int = 0, limit: int = 10
    ) -> list[MeetingAttendeeRetrieve]:
        attendees = await self.attendee_repo.get_all(skip=skip, limit=limit)
        return [
            MeetingAttendeeRetrieve.model_validate(attendee) for attendee in attendees
        ]

    async def get_meeting_attendee(
        self, meeting_attendee_id: int
    ) -> MeetingAttendeeRetrieve:
        attendee = await self.attendee_repo.get_by_id(meeting_attendee_id)
        if not attendee:
            raise NotFoundError(
                detail=f"Meeting attendee with ID {meeting_attendee_id} not found"
            )
        return MeetingAttendeeRetrieve.model_validate(attendee)

    async def update_meeting_attendee(
        self, meeting_attendee_id: int, update_data: MeetingAttendeeUpdate
    ) -> MeetingAttendeeRetrieve:
        attendee = await self.attendee_repo.update(
            meeting_attendee_id, update_data.model_dump(exclude_unset=True)
        )
        if not attendee:
            raise NotFoundError(
                detail=f"Meeting attendee with ID {meeting_attendee_id} not found"
            )
        return MeetingAttendeeRetrieve.model_validate(attendee)

    async def delete_meeting_attendee(self, meeting_attendee_id: int) -> bool:
        success = await self.attendee_repo.delete(meeting_attendee_id)
        if not success:
            raise NotFoundError(
                detail=f"Meeting attendee with ID {meeting_attendee_id} not found"
            )
        return success

    async def get_attendees_by_meeting(
        self, meeting_id: int
    ) -> list[MeetingAttendeeRetrieve]:
        attendees = await self.attendee_repo.get_attendees_by_meeting(meeting_id)
        return [
            MeetingAttendeeRetrieve.model_validate(attendee) for attendee in attendees
        ]

    async def get_meetings_by_user(self, user_id: int) -> list[MeetingAttendeeRetrieve]:
        meetings = await self.attendee_repo.get_meetings_by_user(user_id)
        return [MeetingAttendeeRetrieve.model_validate(meeting) for meeting in meetings]
