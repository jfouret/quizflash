from typing import Any

from fastapi.testclient import TestClient

from tests.conftest import response_dict, response_list


def test_deck_crud(client: TestClient, deck: dict[str, Any]) -> None:
    assert deck["scheduler"] == "fsrs"
    assert deck["scheduler_params"] == {"desired_retention": 0.85}
    assert deck["context"] == "Upper-secondary geography course"

    listed = response_list(client.get("/api/decks"))
    assert [item["id"] for item in listed] == [deck["id"]]
    assert response_dict(client.get(f"/api/decks/{deck['id']}"))["name"] == "Geography"

    updated = response_dict(
        client.patch(
            f"/api/decks/{deck['id']}",
            json={
                "name": "Updated",
                "context": "New context",
                "scheduler": "sm2",
                "scheduler_params": {"ease_start": 2.7},
                "eval_mode": "ai_assess",
            },
        )
    )
    assert updated["name"] == "Updated"
    assert updated["context"] == "New context"
    assert updated["scheduler"] == "sm2"
    assert updated["eval_mode"] == "ai_assess"

    assert client.patch(f"/api/decks/{deck['id']}", json={"context": None}).status_code == 400

    form = client.post(
        f"/decks/{deck['id']}/update",
        data={"description": "Form description", "context": "Form context"},
        follow_redirects=False,
    )
    assert form.status_code == 303
    saved = response_dict(client.get(f"/api/decks/{deck['id']}"))
    assert saved["description"] == "Form description"
    assert saved["context"] == "Form context"

    cleared = response_dict(
        client.patch(f"/api/decks/{deck['id']}", json={"eval_mode": None})
    )
    assert cleared["eval_mode"] is None

    assert client.delete(f"/api/decks/{deck['id']}").status_code == 204
    assert client.get(f"/api/decks/{deck['id']}").status_code == 404


def test_deck_validation_and_cascade(client: TestClient, deck: dict[str, Any]) -> None:
    assert client.post("/api/decks", json={"name": "bad", "scheduler": "other"}).status_code == 422
    created = client.post(
        "/api/cards",
        json={"deck_id": deck["id"], "question": "Q", "answer": "A"},
    )
    card_id = response_dict(created)["id"]
    assert client.delete(f"/api/decks/{deck['id']}").status_code == 204
    assert client.get(f"/api/cards/{card_id}").status_code == 404
    assert client.get("/api/study/next").json() is None


def test_management_pages(client: TestClient, card: dict[str, Any]) -> None:
    assert client.get("/").status_code == 200
    detail = client.get(f"/decks/{card['deck_id']}")
    assert detail.status_code == 200
    assert "Capital of France?" in detail.text
    assert client.get("/study").status_code == 200
    assert client.get("/settings").status_code == 200
