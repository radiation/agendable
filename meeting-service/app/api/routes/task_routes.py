from uuid import UUID

from fastapi import APIRouter, Depends

from app.core.decorators import log_execution_time
from app.core.dependencies import get_task_service
from app.core.logging_config import logger
from app.exceptions import NotFoundError, handle_service_exceptions
from app.schemas.task_schemas import TaskCreate, TaskRetrieve, TaskUpdate
from app.services.task_service import TaskService

router = APIRouter()


@router.post("/", response_model=TaskRetrieve)
@handle_service_exceptions
@log_execution_time
async def create_task(
    task: TaskCreate, service: TaskService = Depends(get_task_service)
) -> TaskRetrieve:
    logger.info(f"Creating task with data: {task.model_dump()}")
    return TaskRetrieve.model_validate(await service.create(task))


@router.get("/", response_model=list[TaskRetrieve])
@log_execution_time
async def get_tasks(
    service: TaskService = Depends(get_task_service),
) -> list[TaskRetrieve]:
    logger.info("Fetching all tasks assigned to no specific assignee.")
    result = await service.get_by_field(field_name="assignee_id", value=None)
    logger.info(f"Retrieved {len(result)} tasks.")
    return [TaskRetrieve.model_validate(task) for task in result]


@router.get("/{task_id}", response_model=TaskRetrieve)
@log_execution_time
async def get_task(
    task_id: int, service: TaskService = Depends(get_task_service)
) -> TaskRetrieve:
    logger.info(f"Fetching task with ID: {task_id}")
    result = await service.get_by_id(task_id)
    if result is None:
        logger.warning(f"Task with ID {task_id} not found")
        raise NotFoundError(f"Task with ID {task_id} not found")
    logger.info(f"Task retrieved: {result}")
    return TaskRetrieve.model_validate(result)


@router.put("/{task_id}", response_model=TaskRetrieve)
@log_execution_time
async def update_task(
    task_id: int,
    task: TaskUpdate,
    service: TaskService = Depends(get_task_service),
) -> TaskRetrieve:
    logger.info(f"Updating task with ID: {task_id} with data: {task.model_dump()}")
    result = await service.update(task_id, task)
    if result is None:
        logger.warning(f"Task with ID {task_id} not found")
        raise NotFoundError(f"Task with ID {task_id} not found")
    logger.info(f"Task updated successfully: {result}")
    return TaskRetrieve.model_validate(result)


@router.delete("/{task_id}", status_code=204)
@log_execution_time
async def delete_task(
    task_id: int, service: TaskService = Depends(get_task_service)
) -> None:
    logger.info(f"Deleting task with ID: {task_id}")
    success = await service.delete(task_id)
    if not success:
        logger.warning(f"Task with ID {task_id} not found")
        raise NotFoundError(f"Task with ID {task_id} not found")
    logger.info(f"Task with ID {task_id} deleted successfully.")


@router.get("/user/{user_id}", response_model=list[TaskRetrieve])
@log_execution_time
async def get_tasks_by_user(
    user_id: UUID, service: TaskService = Depends(get_task_service)
) -> list[TaskRetrieve]:
    logger.info(f"Fetching tasks assigned to user with ID: {user_id}")
    result = await service.get_tasks_by_user(user_id)
    logger.info(f"Retrieved {len(result)} tasks for user ID: {user_id}")
    return [TaskRetrieve.model_validate(task) for task in result]


@router.post("/{task_id}/complete", response_model=TaskRetrieve)
@log_execution_time
async def complete_task(
    task_id: int, service: TaskService = Depends(get_task_service)
) -> TaskRetrieve:
    logger.info(f"Marking task with ID {task_id} as complete.")
    result = await service.mark_task_complete(task_id)
    if result is None:
        logger.warning(f"Task with ID {task_id} not found")
        raise NotFoundError(f"Task with ID {task_id} not found")
    logger.info(f"Task with ID {task_id} marked as complete.")
    return TaskRetrieve.model_validate(result)
