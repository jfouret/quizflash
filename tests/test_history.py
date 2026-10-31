"""History of past answers: listing, deck filter, stored explanation, clearing."""

from typing import Any

from fastapi.testclient import TestClient

from tests.conftest import FakeTeacher, response_dict
from tests.test_study import answer_payload


def record(
    client: TestClient, card_id: int, rating: int = 3, correct: bool = True
) -> dict[str, Any]:
    return response_dict(
        client.post(
            "/api/study/answer",
            json=answer_payload(card_id, confirmed=True, rating=rating, is_correct=correct),
        )
    )


def test_history_lists_then_clears(
    client: TestClient, deck: dict[str, Any], card: dict[str, Any]
) -> None:
    record(client, card["id"])

    page = response_dict(client.get("/api/history"))
    assert page["total"] == 1
    item = page["items"][0]
    assert item["question"] == card["question"]
    assert item["answer_text"] == "Paris"
    assert item["deck_name"] == deck["name"]
    assert item["is_correct"] is True

    cleared = response_dict(client.request("DELETE", "/api/history"))
    assert cleared["deleted"] == 1
    assert response_dict(client.get("/api/history"))["total"] == 0


def test_history_can_be_cleared_for_one_deck(
    client: TestClient, deck: dict[str, Any], card: dict[str, Any]
) -> None:
    other = response_dict(client.post("/api/decks", json={"name": "Other"}))
    other_card = response_dict(
        client.post("/api/cards", json={"deck_id": other["id"], "question": "Q", "answer": "A"})
    )
    record(client, card["id"])
    record(client, other_card["id"])

    cleared = response_dict(client.request("DELETE", f"/api/history?deck_id={deck['id']}"))

    assert cleared["deleted"] == 1
    remaining = response_dict(client.get("/api/history"))
    assert remaining["total"] == 1
    assert remaining["items"][0]["deck_id"] == other["id"]


def test_teacher_explanation_is_stored_with_the_answer(
    client: TestClient, card: dict[str, Any], fake_teacher: FakeTeacher
) -> None:
    saved = record(client, card["id"])

    response = client.post(
        "/api/study/explain", json={"card_id": card["id"], "log_id": saved["log_id"]}
    )
    assert response.status_code == 200

    item = response_dict(client.get("/api/history"))["items"][0]
    assert item["explanation"] == fake_teacher.result.explanation


def test_explanation_without_a_log_id_is_not_stored(
    client: TestClient, card: dict[str, Any]
) -> None:
    record(client, card["id"])

    client.post("/api/study/explain", json={"card_id": card["id"]})

    assert response_dict(client.get("/api/history"))["items"][0]["explanation"] == ""


def test_history_filter_by_a_foreign_deck_is_not_found(
    client: TestClient, client_b: TestClient, deck: dict[str, Any]
) -> None:
    assert client_b.get(f"/api/history?deck_id={deck['id']}").status_code == 404


def test_history_page_renders(
    client: TestClient, deck: dict[str, Any], card: dict[str, Any]
) -> None:
    record(client, card["id"])

    response = client.get(f"/history?deck_id={deck['id']}")

    assert response.status_code == 200
    assert card["question"] in response.text
