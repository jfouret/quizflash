from typing import Any

from fastapi.testclient import TestClient

from tests.conftest import response_dict, response_list


def test_tag_list_and_delete(client: TestClient, card: dict[str, Any]) -> None:
    tags = response_list(client.get("/api/tags"))
    assert [tag["name"] for tag in tags] == ["europe", "geography"]

    europe = next(tag for tag in tags if tag["name"] == "europe")
    assert client.delete(f"/api/tags/{europe['id']}").status_code == 204
    remaining = response_dict(client.get(f"/api/cards/{card['id']}"))
    assert [tag["name"] for tag in remaining["tags"]] == ["geography"]
    assert client.delete(f"/api/tags/{europe['id']}").status_code == 404
