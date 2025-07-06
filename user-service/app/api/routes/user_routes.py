from uuid import UUID

from common_lib.exceptions import handle_service_exceptions
from fastapi import APIRouter, Depends, status

from app.api.dependencies import get_current_user, get_user_service
from app.schemas.user import UserCreate, UserRetrieve, UserUpdate
from app.services.user_service import UserService

router = APIRouter()


@router.get("/me", response_model=UserRetrieve)
async def get_current_user_profile(
    email: str = Depends(get_current_user),
    service: UserService = Depends(get_user_service),
) -> UserRetrieve:
    user = await service.get_by_field(field_name="email", value=email)
    return UserRetrieve.model_validate(user[0])


@router.post("/", response_model=UserRetrieve)
@handle_service_exceptions
async def create_user(
    user: UserCreate, service: UserService = Depends(get_user_service)
) -> UserRetrieve:
    return UserRetrieve.model_validate(await service.create(user))


@router.get("/by-email", response_model=UserRetrieve)
async def get_user_by_email(
    email: str, service: UserService = Depends(get_user_service)
) -> UserRetrieve:
    result = await service.get_by_field(field_name="email", value=email)
    return UserRetrieve.model_validate(result[0])


@router.get("/{user_id}", response_model=UserRetrieve)
async def get_user(
    user_id: UUID, service: UserService = Depends(get_user_service)
) -> UserRetrieve:
    result = await service.get_by_id(user_id)
    return UserRetrieve.model_validate(result)


@router.get("/", response_model=list[UserRetrieve])
async def get_users(
    service: UserService = Depends(get_user_service),
) -> list[UserRetrieve]:
    result = await service.get_all()
    return [UserRetrieve.model_validate(user) for user in result]


@router.put("/{user_id}", response_model=UserRetrieve)
async def update_user(
    user_id: UUID,
    user_update: UserUpdate,
    service: UserService = Depends(get_user_service),
) -> UserRetrieve:
    result = await service.update(user_id, user_update)
    return UserRetrieve.model_validate(result)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: UUID, service: UserService = Depends(get_user_service)
) -> None:
    await service.delete(user_id)
