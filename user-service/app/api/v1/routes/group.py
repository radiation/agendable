from common_lib.exceptions import handle_service_exceptions
from fastapi import APIRouter, Depends, status

from app.core.dependencies import get_group_service
from app.schemas.group import GroupCreate, GroupRetrieve, GroupUpdate
from app.services.group import GroupService

router = APIRouter()


@router.post("/", response_model=GroupRetrieve)
@handle_service_exceptions
async def create_group(
    group: GroupCreate, service: GroupService = Depends(get_group_service)
) -> GroupRetrieve:
    return GroupRetrieve.model_validate(await service.create(group))


@router.get("/by-name", response_model=GroupRetrieve)
async def get_group_by_name(
    name: str, service: GroupService = Depends(get_group_service)
) -> GroupRetrieve:
    group = await service.get_by_field("name", name)
    return GroupRetrieve.model_validate(group[0])


@router.get("/{group_id}", response_model=GroupRetrieve)
async def get_group(
    group_id: int, service: GroupService = Depends(get_group_service)
) -> GroupRetrieve:
    result = await service.get_by_id(group_id)
    return GroupRetrieve.model_validate(result)


@router.get("/", response_model=list[GroupRetrieve])
async def get_groups(
    service: GroupService = Depends(get_group_service),
) -> list[GroupRetrieve]:
    result = await service.get_all()
    return [GroupRetrieve.model_validate(group) for group in result]


@router.put("/{group_id}", response_model=GroupRetrieve)
async def update_group(
    group_id: int,
    group_update: GroupUpdate,
    service: GroupService = Depends(get_group_service),
) -> GroupRetrieve:
    result = await service.update(group_id, group_update)
    return GroupRetrieve.model_validate(result)


@router.delete("/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_group(
    group_id: int, service: GroupService = Depends(get_group_service)
) -> None:
    await service.delete(group_id)
