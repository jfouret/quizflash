from typing import Any

from fastapi.testclient import TestClient

from app.teacher.base import TeacherError
from tests.conftest import FakeTeacher, response_dict


def test_explain_uses_deck_and_card_context(
    client: TestClient, card: dict[str, Any], fake_teacher: FakeTeacher
) -> None:
    client.patch("/api/settings", json={"eval_mode": "ai_assess", "judge_language": "fr"})
    answered = response_dict(
        client.post(
            "/api/study/answer",
            json={
                "card_id": card["id"],
                "answer_text": "Paris",
                "input_method": "text",
                "response_time_ms": 1500,
            },
        )
    )
    assert answered["status"] == "reviewed"

    result = response_dict(client.post("/api/study/explain", json={"card_id": card["id"]}))
    assert result == {
        "explanation": "Paris is the capital of France.",
        "model": "fake-teacher",
    }
    assert len(fake_teacher.calls) == 1
    call = fake_teacher.calls[0]
    assert call["deck_context"] == "Upper-secondary geography course"
    assert call["card_context"] == "Capitals are seated in the city proper, not the metro area."
    assert call["question"] == "Capital of France?"
    assert call["expected_answer"] == "Paris"
    assert call["user_answer"] == "Paris"
    assert call["is_correct"] is True
    assert call["language"] == "fr"


def test_explain_without_prior_answer(
    client: TestClient, card: dict[str, Any], fake_teacher: FakeTeacher
) -> None:
    result = response_dict(client.post("/api/study/explain", json={"card_id": card["id"]}))
    assert result["explanation"] == "Paris is the capital of France."
    assert fake_teacher.calls[0]["user_answer"] == ""
    assert fake_teacher.calls[0]["is_correct"] is None


def test_explain_unknown_card(client: TestClient) -> None:
    assert client.post("/api/study/explain", json={"card_id": 999}).status_code == 404


def test_explain_teacher_failure(
    client: TestClient, card: dict[str, Any], fake_teacher: FakeTeacher
) -> None:
    fake_teacher.error = TeacherError("timeout")
    response = client.post("/api/study/explain", json={"card_id": card["id"]})
    assert response.status_code == 502
    assert "Teacher explanation failed" in response_dict(response)["detail"]
