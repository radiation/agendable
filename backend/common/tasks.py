import logging

from celery import Celery, shared_task
from celery.signals import task_postrun
from common.consumers import notify_channel_layer
from django.apps import apps
from meetings.serializers import (
    EventTimeSerializer,
    MeetingAttendeeSerializer,
    MeetingRecurrenceSerializer,
    MeetingSerializer,
    MeetingTaskSerializer,
    TaskSerializer,
)
from users.serializers import UserPreferencesSerializer, UserSerializer

logger = logging.getLogger(__name__)

serializers_dict = {
    "User": UserSerializer,
    "UserPreferences": UserPreferencesSerializer,
    "EventTime": EventTimeSerializer,
    "Meeting": MeetingSerializer,
    "MeetingRecurrence": MeetingRecurrenceSerializer,
    "Task": TaskSerializer,
    "MeetingTask": MeetingTaskSerializer,
    "MeetingAttendee": MeetingAttendeeSerializer,
}

app = Celery()


@shared_task(name="high_priority:create_or_update_record")
def create_or_update_record(validated_data, model_name, create=True):
    logger.debug(
        f"Creating/Updating record for model {model_name} with data: {validated_data}"
    )

    Model = apps.get_model("meetings", model_name)
    SerializerClass = serializers_dict[model_name]

    if create:
        serializer = SerializerClass(data=validated_data)
    else:
        instance = Model.objects.get(pk=validated_data["id"])
        serializer = SerializerClass(instance, data=validated_data)

    if serializer.is_valid():
        serializer.save()
        return serializer.data
    else:
        logger.error(f"Serializer errors: {serializer.errors}")
        return serializer.errors


@shared_task(name="high_priority:create_or_update_batch")
def create_or_update_batch(tasks_data, model_name):
    Model = apps.get_model("meetings", model_name)
    SerializerClass = serializers_dict[model_name]

    for data in tasks_data:
        instance = Model.objects.get(pk=data["id"])
        serializer = SerializerClass(instance, data=data)

        if serializer.is_valid():
            serializer.save()
        else:
            logger.error(
                f"Serializer errors for {model_name} ID {data['id']}: "
                f"{serializer.errors}"
            )

    return "Batch update completed"


@shared_task()
def task_test_logger():
    logger.info("test")


@task_postrun.connect
def task_postrun_handler(task_id, **kwargs):
    notify_channel_layer(task_id)
