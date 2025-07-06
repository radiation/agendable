from common_lib.exceptions import handle_service_exceptions
from fastapi import APIRouter, Depends, status

from app.api.dependencies import get_role_service
from app.schemas.roles import RoleCreate, RoleRetrieve, RoleUpdate
from app.services.role_service import RoleService

router = APIRouter()


@router.post("/", response_model=RoleRetrieve)
@handle_service_exceptions
async def create_role(
    role: RoleCreate, service: RoleService = Depends(get_role_service)
) -> RoleRetrieve:
    return RoleRetrieve.model_validate(await service.create(role))


@router.get("/by-name", response_model=RoleRetrieve)
async def get_role_by_name(
    name: str, service: RoleService = Depends(get_role_service)
) -> RoleRetrieve:
    result = await service.get_by_field("name", name)
    return RoleRetrieve.model_validate(result[0])


@router.get("/{role_id}", response_model=RoleRetrieve)
async def get_role(
    role_id: int, service: RoleService = Depends(get_role_service)
) -> RoleRetrieve:
    result = await service.get_by_id(role_id)
    return RoleRetrieve.model_validate(result)


@router.get("/", response_model=list[RoleRetrieve])
async def get_roles(
    service: RoleService = Depends(get_role_service),
) -> list[RoleRetrieve]:
    result = await service.get_all()
    return [RoleRetrieve.model_validate(role) for role in result]


@router.put("/{role_id}", response_model=RoleRetrieve)
async def update_role(
    role_id: int,
    role_update: RoleUpdate,
    service: RoleService = Depends(get_role_service),
) -> RoleRetrieve:
    result = await service.update(role_id, role_update)
    return RoleRetrieve.model_validate(result)


@router.delete("/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_role(
    role_id: int, service: RoleService = Depends(get_role_service)
) -> None:
    await service.delete(role_id)
