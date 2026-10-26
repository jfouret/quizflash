from typing import Any

from fastapi.testclient import TestClient

from app.judge.base import JudgeResult
from tests.conftest import FakeJudge, response_dict, response_list
from tests.test_study import answer_payload, enable_ai_assess


def test_stats_aggregates_by_deck_card_and_tag(
    client: TestClient, card: dict[str, Any], fake_judge: FakeJudge
) -> None:
    enable_ai_assess(client)
    second = response_dict(
        client.post(
            "/api/cards",
            json={
                "deck_id": card["deck_id"],
                "question": "Second",
                "answer": "Answer",
                "tags": ["europe"],
            },
        )
    )
    fake_judge.result = JudgeResult(rating=3, is_correct=True, feedback="yes")
    client.post(
        "/api/study/answer", json=answer_payload(card["id"], response_time_ms=1000)
    )
    fake_judge.result = JudgeResult(rating=1, is_correct=False, feedback="no")
    client.post(
        "/api/study/answer", json=answer_payload(second["id"], response_time_ms=3000)
    )

    deck_stats = response_dict(
        client.get("/api/stats", params={"scope": "deck", "id": card["deck_id"]})
    )
    assert deck_stats == {
        "total": 2,
        "correct": 1,
        "incorrect": 1,
        "correct_rate": 0.5,
        "avg_response_time_ms": 2000.0,
        "by_mode": {"ai_assess": 2},
    }
    card_stats = response_dict(
        client.get("/api/stats", params={"scope": "card", "id": second["id"]})
    )
    assert card_stats["total"] == 1
    assert card_stats["correct"] == 0
    assert card_stats["incorrect"] == 1
    assert card_stats["avg_response_time_ms"] == 3000.0

    tags = response_list(client.get("/api/tags"))
    europe_id = next(tag["id"] for tag in tags if tag["name"] == "europe")
    tag_stats = response_dict(
        client.get("/api/stats", params={"scope": "tag", "id": europe_id})
    )
    assert tag_stats["total"] == 2
    assert tag_stats["correct_rate"] == 0.5


def test_empty_and_missing_stats(client: TestClient, card: dict[str, Any]) -> None:
    empty = response_dict(
        client.get("/api/stats", params={"scope": "card", "id": card["id"]})
    )
    assert empty["total"] == 0
    assert empty["correct_rate"] == 0.0
    assert empty["avg_response_time_ms"] is None
    assert empty["by_mode"] == {}
    assert client.get("/api/stats", params={"scope": "deck", "id": 999}).status_code == 404
