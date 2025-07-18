from datetime import datetime
from typing import Any, ClassVar
import uuid

import factory
from factory import Faker, Iterator, LazyFunction, Sequence

from app.db.models.meeting import Meeting
from app.db.models.recurrence import Recurrence
from app.db.models.task import Task
from app.db.models.user import User
from app.schemas.meeting import MeetingCreate
from app.schemas.recurrence import RecurrenceCreate
from app.schemas.task import TaskCreate
from app.schemas.user import UserCreate


class BaseFactory(factory.alchemy.SQLAlchemyModelFactory):
    @classmethod
    def as_dict(cls, **kwargs: Any) -> dict[str, Any]:
        """Convert factory object to dict & serialize UUID / datetime fields"""
        obj = cls.build(**kwargs)
        return {
            key: (
                str(value)
                if isinstance(value, uuid.UUID)
                else value.isoformat()
                if isinstance(value, datetime)
                else value
            )
            for key, value in obj.__dict__.items()
            if not key.startswith("_")
        }

    class Meta:
        abstract = True


class MeetingFactory(BaseFactory):
    class Meta:
        model = Meeting

    id: ClassVar[Sequence] = factory.Sequence(lambda n: n + 1)
    title: ClassVar[Faker] = factory.Faker("sentence", nb_words=3)
    start_date: ClassVar[LazyFunction] = factory.LazyFunction(
        staticmethod(datetime.now)
    )
    duration: ClassVar[Faker] = factory.Faker("random_int", min=15, max=120)
    location: ClassVar[Faker] = factory.Faker("address")
    notes: ClassVar[Faker] = factory.Faker("text")
    num_reschedules: ClassVar[Faker] = factory.Faker("random_int", min=0, max=5)
    reminder_sent: ClassVar[Faker] = factory.Faker("boolean")
    completed: ClassVar[Faker] = factory.Faker("boolean")


class MeetingCreateFactory(factory.Factory):
    class Meta:
        model = MeetingCreate

    title: ClassVar[Faker] = factory.Faker("sentence", nb_words=3)
    start_date: ClassVar[LazyFunction] = factory.LazyFunction(
        staticmethod(datetime.now)
    )
    duration: ClassVar[Faker] = factory.Faker("random_int", min=15, max=120)
    location: ClassVar[Faker] = factory.Faker("address")


class RecurrenceFactory(BaseFactory):
    class Meta:
        model = Recurrence

    id: ClassVar[Sequence] = factory.Sequence(lambda n: n + 1)
    title: ClassVar[Faker] = factory.Faker("sentence", nb_words=3)
    rrule: ClassVar[Iterator] = factory.Iterator(
        [
            "FREQ=DAILY;INTERVAL=1;BYHOUR=14;BYMINUTE=30",
            "FREQ=WEEKLY;BYDAY=MO,WE,FR;BYHOUR=10;BYMINUTE=00",
            "FREQ=MONTHLY;BYMONTHDAY=15;BYHOUR=17;BYMINUTE=00",
            "FREQ=YEARLY;BYMONTH=12;BYMONTHDAY=25;BYHOUR=00;BYMINUTE=00",
        ]
    )
    created_at: ClassVar[Faker] = factory.Faker("date_time")


class RecurrenceCreateFactory(factory.Factory):
    class Meta:
        model = RecurrenceCreate

    title: ClassVar[Faker] = factory.Faker("sentence", nb_words=3)
    rrule: ClassVar[Iterator] = factory.Iterator(
        [
            "FREQ=DAILY;INTERVAL=1;BYHOUR=14;BYMINUTE=30",
            "FREQ=WEEKLY;BYDAY=MO,WE,FR;BYHOUR=10;BYMINUTE=00",
            "FREQ=MONTHLY;BYMONTHDAY=15;BYHOUR=17;BYMINUTE=00",
            "FREQ=YEARLY;BYMONTH=12;BYMONTHDAY=25;BYHOUR=00;BYMINUTE=00",
        ]
    )


class TaskFactory(BaseFactory):
    class Meta:
        model = Task

    id: ClassVar[Sequence] = factory.Sequence(lambda n: n + 1)
    assignee_id: ClassVar[Faker] = factory.Faker("random_int", min=1, max=10)
    title: ClassVar[Faker] = factory.Faker("sentence", nb_words=3)
    description: ClassVar[Faker] = factory.Faker("text")
    due_date: ClassVar[Faker] = factory.Faker("date_time")
    completed: ClassVar[Faker] = factory.Faker("boolean")
    completed_date: ClassVar[Faker] = factory.Faker("date_time")
    created_at: ClassVar[Faker] = factory.Faker("date_time")


class TaskCreateFactory(factory.Factory):
    class Meta:
        model = TaskCreate

    assignee_id: ClassVar[Faker] = factory.Faker("random_int", min=1, max=10)
    title: ClassVar[Faker] = factory.Faker("sentence", nb_words=3)
    description: ClassVar[Faker] = factory.Faker("text")
    due_date: ClassVar[Faker] = factory.Faker("date_time")


class UserFactory(BaseFactory):
    class Meta:
        model = User

    id: ClassVar[LazyFunction] = factory.LazyFunction(uuid.uuid4)
    email: ClassVar[Faker] = factory.Faker("email")
    first_name: ClassVar[Faker] = factory.Faker("first_name")
    last_name: ClassVar[Faker] = factory.Faker("last_name")


class UserCreateFactory(factory.Factory):
    class Meta:
        model = UserCreate

    id: ClassVar[LazyFunction] = factory.LazyFunction(uuid.uuid4)
    email: ClassVar[Faker] = factory.Faker("email")
    first_name: ClassVar[Faker] = factory.Faker("first_name")
    last_name: ClassVar[Faker] = factory.Faker("last_name")
