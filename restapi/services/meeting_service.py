from django.utils import timezone
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta
import calendar


def create_next_meeting(meeting):
    from restapi.tasks import create_or_update_record

    next_occurrence_time = meeting.recurrence.get_next_occurrence(meeting.start_date)
    if next_occurrence_time and (
        not meeting.recurrence.end_recurrence
        or next_occurrence_time <= meeting.recurrence.end_recurrence
    ):
        duration = meeting.end_date - meeting.start_date
        meeting_data = {
            "recurrence": meeting.recurrence,
            "title": meeting.title,
            "start_date": next_occurrence_time,
            "end_date": next_occurrence_time + duration,
            "notes": meeting.notes,
            "num_reschedules": meeting.num_reschedules,
            "created_at": timezone.now(),
        }
        create_or_update_record.delay(meeting_data, "Meeting", create=True)


def get_next_occurrence_date(recurrence, source_datetime):
    if recurrence.frequency == "daily":
        return source_datetime + timedelta(days=recurrence.interval)
    elif recurrence.frequency == "weekly":
        return source_datetime + timedelta(weeks=recurrence.interval)
    elif recurrence.frequency == "monthly":
        next_date = source_datetime + relativedelta(months=recurrence.interval)
        if recurrence.week_day is not None:
            days_in_month = calendar.monthrange(next_date.year, next_date.month)[1]
            week_day_occurrences = [
                day
                for day in range(1, days_in_month + 1)
                if date(next_date.year, next_date.month, day).weekday()
                == recurrence.week_day
            ]
            if recurrence.month_week <= len(week_day_occurrences):
                day = week_day_occurrences[recurrence.month_week - 1]
            else:
                day = week_day_occurrences[-1]
            next_date = next_date.replace(day=day)
        return next_date
    else:
        # Custom recurrence logic to be added later
        return None


def complete_meeting(meeting_id):
    from restapi.models import Meeting, MeetingTask
    from restapi.tasks import create_or_update_batch

    meeting = Meeting.objects.get(pk=meeting_id)
    next_occurrence = meeting.get_next_occurrence()

    if next_occurrence:
        tasks_data = []
        meeting_tasks = MeetingTask.objects.filter(meeting__id=meeting_id)

        for meeting_task in meeting_tasks:
            task_data = {
                "id": meeting_task.id,  # Include the ID for updating
                "meeting": next_occurrence.id,  # Set the new meeting ID
            }
            tasks_data.append(task_data)

        # Enqueue a single task for batch updating MeetingTasks
        if tasks_data:
            create_or_update_batch.delay(tasks_data, "MeetingTask")


def handle_next_meeting_creation(meeting):
    if not meeting.get_next_occurrence() and meeting.recurrence:
        create_next_meeting(meeting)


def generate_reminder(meeting_id, user_id):
    from restapi.models import Meeting, MeetingTask

    open_tasks = MeetingTask.objects.filter(meeting__id=meeting_id, completed=False)
    meeting = Meeting.objects.get(pk=meeting_id)
    notes = meeting.notes
