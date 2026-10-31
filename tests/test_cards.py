from typing import Any

from fastapi.testclient import TestClient

from tests.conftest import response_dict, response_list


def test_card_crud_and_filters(client: TestClient, card: dict[str, Any]) -> None:
    assert [tag["name"] for tag in card["tags"]] == ["geography", "europe"]
    assert card["details"].startswith("https://")
    assert card["context"].startswith("Capitals")

    by_deck = response_list(client.get("/api/cards", params={"deck_id": card["deck_id"]}))
    assert [item["id"] for item in by_deck] == [card["id"]]
    by_tag = response_list(client.get("/api/cards", params={"tag": "europe"}))
    assert [item["id"] for item in by_tag] == [card["id"]]
    assert response_list(client.get("/api/cards", params={"tag": "missing"})) == []

    updated = response_dict(
        client.patch(
            f"/api/cards/{card['id']}",
            json={
                "question": "Updated question",
                "context": "Updated context",
                "expected_time_s": None,
                "tags": ["updated"],
            },
        )
    )
    assert updated["question"] == "Updated question"
    assert updated["context"] == "Updated context"
    assert updated["expected_time_s"] is None
    assert [tag["name"] for tag in updated["tags"]] == ["updated"]

    assert client.patch(f"/api/cards/{card['id']}", json={"context": None}).status_code == 400

    assert client.delete(f"/api/cards/{card['id']}").status_code == 204
    assert client.get(f"/api/cards/{card['id']}").status_code == 404


def test_card_validation_and_initial_state(client: TestClient, deck: dict[str, Any]) -> None:
    missing_deck = client.post("/api/cards", json={"deck_id": 999, "question": "Q", "answer": "A"})
    assert missing_deck.status_code == 404
    blank_tag = client.post(
        "/api/cards",
        json={"deck_id": deck["id"], "question": "Q", "answer": "A", "tags": [" "]},
    )
    assert blank_tag.status_code == 400

    created = client.post(
        "/api/cards",
        json={"deck_id": deck["id"], "question": "Q", "answer": "A"},
    )
    card_id = response_dict(created)["id"]
    due = response_dict(client.get("/api/study/next"))
    assert due["card"]["id"] == card_id
    assert due["is_new"] is True
    assert client.patch(f"/api/cards/{card_id}", json={"tags": None}).status_code == 400
