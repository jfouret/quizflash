"""Per-card and per-tag statistics, normalized across deck scales."""

from typing import Any

from fastapi.testclient import TestClient

from tests.conftest import response_dict
from tests.test_scale import make_card, make_scaled_deck
from tests.test_study import answer_payload


def record(client: TestClient, card_id: int, rating: int, correct: bool = True) -> None:
    response = client.post(
        "/api/study/answer",
        json=answer_payload(card_id, confirmed=True, rating=rating, is_correct=correct),
    )
    assert response.status_code == 200, response.text


def test_breakdown_by_card_normalizes_the_mean(client: TestClient) -> None:
    deck = make_scaled_deck(client)  # 0..10 scale
    first = make_card(client, deck["id"], "First")
    second = make_card(client, deck["id"], "Second")
    record(client, first["id"], 7)
    record(client, first["id"], 3)
    record(client, second["id"], 10, correct=False)

    body = response_dict(client.get(f"/api/stats/breakdown?group=card&deck_id={deck['id']}"))

    assert body["group"] == "card"
    by_key = {item["key"]: item for item in body["items"]}
    assert by_key[str(first["id"])]["avg_rating"] == 5.0
    assert by_key[str(first["id"])]["avg_normalized"] == 5.0
    assert by_key[str(first["id"])]["correct_rate"] == 1.0
    assert by_key[str(second["id"])]["avg_normalized"] == 10.0
    assert by_key[str(second["id"])]["correct_rate"] == 0.0


def test_breakdown_by_tag(client: TestClient) -> None:
    deck = make_scaled_deck(client)
    card = response_dict(
        client.post(
            "/api/cards",
            json={
                "deck_id": deck["id"],
                "question": "Q",
                "answer": "A",
                "tags": ["europe", "capitals"],
            },
        )
    )
    record(client, card["id"], 8)

    body = response_dict(client.get(f"/api/stats/breakdown?group=tag&deck_id={deck['id']}"))

    labels = {item["key"]: item for item in body["items"]}
    assert set(labels) == {"europe", "capitals"}
    assert labels["europe"]["avg_normalized"] == 8.0
    assert labels["europe"]["total"] == 1


def test_breakdown_without_answers_is_empty(client: TestClient, deck: dict[str, Any]) -> None:
    body = response_dict(client.get(f"/api/stats/breakdown?group=card&deck_id={deck['id']}"))
    assert body["items"] == []


def test_stats_page_renders_with_data(client: TestClient) -> None:
    deck = make_scaled_deck(client)
    card = make_card(client, deck["id"], "Chart me")
    record(client, card["id"], 9)

    response = client.get(f"/stats?deck_id={deck['id']}")

    assert response.status_code == 200
    assert "Chart me" in response.text
    assert 'id="chart-card"' in response.text
