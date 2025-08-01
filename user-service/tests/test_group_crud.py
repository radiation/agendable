import json
from unittest.mock import AsyncMock

from httpx import AsyncClient
import pytest


@pytest.mark.asyncio
async def test_group_crud_operations(
    test_client: AsyncClient, mock_redis_client: AsyncMock
) -> None:
    group_data = {
        "name": "crudgroup",
        "description": "Group for CRUD operations",
    }

    # Create a group
    response = await test_client.post(
        "/groups/",
        json=group_data,
    )
    assert response.status_code == 200
    group_data = response.json()
    assert group_data["name"] == "crudgroup"

    mock_redis_client.publish.assert_awaited_with(
        "group-events",
        json.dumps(
            {
                "event_type": "create",
                "model": "Group",
                "payload": {
                    "id": group_data["id"],
                    "name": "crudgroup",
                    "description": "Group for CRUD operations",
                },
            }
        ),
    )

    # Read a group by name
    response = await test_client.get("/groups/by-name?name=crudgroup")
    assert response.status_code == 200
    group_data = response.json()
    assert group_data["name"] == "crudgroup"

    # Update the group
    response = await test_client.put(
        f"/groups/{group_data['id']}",
        json={"id": group_data["id"], "name": "updatedgroup"},
    )
    assert response.status_code == 200
    updated_data = response.json()
    assert updated_data["name"] == "updatedgroup"

    mock_redis_client.publish.assert_awaited_with(
        "group-events",
        json.dumps(
            {
                "event_type": "update",
                "model": "Group",
                "payload": {"name": "updatedgroup", "id": int(group_data["id"])},
            }
        ),
    )

    # Delete the group
    response = await test_client.delete(
        f"/groups/{group_data['id']}",
    )
    assert response.status_code == 204

    mock_redis_client.publish.assert_awaited_with(
        "group-events",
        json.dumps(
            {
                "event_type": "delete",
                "model": "Group",
                "payload": {"id": int(group_data["id"])},
            }
        ),
    )
