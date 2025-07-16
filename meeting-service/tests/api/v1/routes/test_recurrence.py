from httpx import AsyncClient
import pytest


@pytest.mark.asyncio
async def test_get_recurrences(test_client: AsyncClient) -> None:
    response = await test_client.get("/recurrences/")
    assert response.status_code == 200
    recurrences = response.json()
    assert isinstance(recurrences, list)
