"""Studying one or many decks at once."""

from fastapi.testclient import TestClient

from tests.conftest import response_dict, response_list


def _deck_with_card(client: TestClient, name: str, tag: str) -> tuple[int, int]:
    deck = response_dict(
        client.post("/api/decks", json={"name": name, "grading_scale": {"max": 6}})
    )
    card = response_dict(
        client.post(
            "/api/cards",
            json={"deck_id": deck["id"], "question": name, "answer": "A", "tags": [tag]},
        )
    )
    return deck["id"], card["id"]


def test_batch_accepts_several_decks(client: TestClient) -> None:
    first, _ = _deck_with_card(client, "First", "one")
    second, _ = _deck_with_card(client, "Second", "two")
    _deck_with_card(client, "Third", "three")

    batch = response_list(
        client.get(
            "/api/study/batch",
            params=[("size", "10"), ("deck_id", str(first)), ("deck_id", str(second))],
        )
    )

    assert sorted(item["card"]["deck_id"] for item in batch) == sorted([first, second])


def test_tags_and_due_follow_the_deck_selection(client: TestClient) -> None:
    first, _ = _deck_with_card(client, "First", "one")
    second, _ = _deck_with_card(client, "Second", "two")

    assert client.get(
        "/api/study/tags", params=[("deck_id", str(first)), ("deck_id", str(second))]
    ).json() == ["one", "two"]
    assert client.get(
        "/api/study/due", params=[("deck_id", str(first)), ("deck_id", str(second))]
    ).json() == {"count": 2}
    assert client.get("/api/study/due", params=[("deck_id", str(first))]).json() == {"count": 1}


def test_next_card_carries_the_deck_scale(client: TestClient) -> None:
    deck_id, _ = _deck_with_card(client, "First", "one")

    card = response_dict(client.get("/api/study/next", params={"deck_id": str(deck_id)}))

    assert card["grading_scale"]["max"] == 6
