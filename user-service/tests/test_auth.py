from httpx import AsyncClient
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import verify_password
from app.repositories.user import UserRepository


@pytest.mark.asyncio
async def test_user_registration_and_login(
    test_client: AsyncClient, db_session: AsyncSession
) -> None:
    # Registration payload
    user_data = {"email": "test_auth@example.com", "password": "securepassword"}

    # Register a new user
    response = await test_client.post("/auth/register", json=user_data)
    assert response.status_code == 200

    # Check response contains a valid token
    token_data = response.json()
    assert "access_token" in token_data
    assert "token_type" in token_data
    assert token_data["token_type"] == "bearer"

    # Verify user exists in the database
    user_repo = UserRepository(db_session)
    user = await user_repo.get_by_field("email", user_data["email"])
    assert user is not None
    assert len(user) > 0
    assert user[0].email == user_data["email"]
    assert verify_password(user_data["password"], user[0].hashed_password)

    # Login with the same credentials
    response = await test_client.post("/auth/login", json=user_data)
    assert response.status_code == 200

    # Check response contains a valid token
    login_token_data = response.json()
    assert "access_token" in login_token_data
    assert "token_type" in login_token_data
    assert login_token_data["token_type"] == "bearer"
