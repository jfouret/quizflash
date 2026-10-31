"""Per-deck grading scale: API round trip, judging, and the change guard."""

import re
from typing import Any

from fastapi.testclient import TestClient

from tests.conftest import FakeJudge, response_dict
from tests.test_study import answer_payload


def make_scaled_deck(client: TestClient, **overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": "Scaled",
        "grading_scale": {"max": 10, "labels": {"3": "Bad", "7": "Good", "10": "Perfect"}},
    }
    payload.update(overrides)
    return response_dict(client.post("/api/decks", json=payload))


def make_card(client: TestClient, deck_id: int, question: str = "Q") -> dict[str, Any]:
    return response_dict(
        client.post("/api/cards", json={"deck_id": deck_id, "question": question, "answer": "A"})
    )


def record(
    client: TestClient, card_id: int, rating: int = 7, correct: bool = True
) -> dict[str, Any]:
    return response_dict(
        client.post(
            "/api/study/answer",
            json=answer_payload(card_id, confirmed=True, rating=rating, is_correct=correct),
        )
    )


def test_deck_scale_round_trips(client: TestClient) -> None:
    deck = make_scaled_deck(client)
    stored = response_dict(client.get(f"/api/decks/{deck['id']}"))["grading_scale"]
    assert stored["max"] == 10
    assert stored["labels"]["7"] == "Good"


def test_default_scale_is_the_five_level_notation(client: TestClient) -> None:
    deck = response_dict(client.post("/api/decks", json={"name": "Plain"}))

    assert deck["grading_scale"]["max"] == 5
    assert deck["grading_scale"]["labels"] == {
        "0": "False or absent",
        "1": "Bad",
        "2": "Average",
        "3": "Better than average",
        "4": "Good",
        "5": "Perfect",
    }


def test_default_notation_reaches_the_deck_page(client: TestClient) -> None:
    deck = response_dict(client.post("/api/decks", json={"name": "Plain"}))

    page = client.get(f"/decks/{deck['id']}").text

    assert re.search(r'name="grading_max"[^>]*value="5"', page)
    assert "0=False or absent" in page
    assert "5=Perfect" in page


def test_default_notation_is_what_the_rating_list_receives(
    client: TestClient, fake_judge: FakeJudge
) -> None:
    """The study view builds its rating list from the scale the batch reports."""
    deck = response_dict(client.post("/api/decks", json={"name": "Plain"}))
    card = make_card(client, deck["id"])

    client.post("/api/study/answer", json=answer_payload(card["id"]))

    assert fake_judge.calls[-1]["max_level"] == 5
    assert fake_judge.calls[-1]["labels"] == {
        0: "False or absent",
        1: "Bad",
        2: "Average",
        3: "Better than average",
        4: "Good",
        5: "Perfect",
    }


def test_judge_receives_the_deck_scale(client: TestClient, fake_judge: FakeJudge) -> None:
    deck = make_scaled_deck(client)
    card = make_card(client, deck["id"])

    client.post("/api/study/answer", json=answer_payload(card["id"]))

    assert fake_judge.calls[-1]["max_level"] == 10
    assert fake_judge.calls[-1]["labels"] == {3: "Bad", 7: "Good", 10: "Perfect"}


def test_rating_above_the_scale_is_rejected(client: TestClient) -> None:
    deck = make_scaled_deck(client)
    card = make_card(client, deck["id"])

    response = client.post(
        "/api/study/answer",
        json=answer_payload(card["id"], confirmed=True, rating=11, is_correct=True),
    )

    assert response.status_code == 400, response.text


def test_stored_rating_uses_the_deck_scale(client: TestClient) -> None:
    deck = make_scaled_deck(client)
    card = make_card(client, deck["id"])

    saved = record(client, card["id"], rating=7)

    assert saved["rating"] == 7
    item = response_dict(client.get("/api/history"))["items"][0]
    assert item["rating"] == 7
    assert item["max_level"] == 10
    assert item["rating_label"] == "Good"


def test_scale_change_is_blocked_once_the_deck_has_answers(client: TestClient) -> None:
    deck = make_scaled_deck(client)
    card = make_card(client, deck["id"])
    record(client, card["id"], rating=7)

    blocked = client.patch(f"/api/decks/{deck['id']}", json={"grading_scale": {"max": 5}})

    assert blocked.status_code == 400
    assert "Copy the deck" in response_dict(blocked)["detail"]


def test_scale_change_is_allowed_without_history(client: TestClient) -> None:
    deck = make_scaled_deck(client)

    updated = client.patch(f"/api/decks/{deck['id']}", json={"grading_scale": {"max": 5}})

    assert updated.status_code == 200
    assert response_dict(updated)["grading_scale"]["max"] == 5


def test_copy_keeps_the_scale(client: TestClient) -> None:
    deck = make_scaled_deck(client)

    copy = response_dict(client.post(f"/api/decks/{deck['id']}/copy"))

    assert copy["grading_scale"]["max"] == 10
    assert copy["grading_scale"]["labels"]["7"] == "Good"
