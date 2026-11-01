from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app.teacher.base import TeacherError
from app.teacher.openrouter import OpenRouterTeacher
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
    # The rating and the deck scale reach the prompt, so the teacher can say what
    # a stronger answer would have added.
    assert call["rating"] == 3
    assert call["max_level"] == 5
    assert call["rating_label"] == "Better than average"


def test_explain_without_prior_answer(
    client: TestClient, card: dict[str, Any], fake_teacher: FakeTeacher
) -> None:
    result = response_dict(client.post("/api/study/explain", json={"card_id": card["id"]}))
    assert result["explanation"] == "Paris is the capital of France."
    assert fake_teacher.calls[0]["user_answer"] == ""
    assert fake_teacher.calls[0]["is_correct"] is None
    assert fake_teacher.calls[0]["rating"] is None


def test_explain_unknown_card(client: TestClient) -> None:
    assert client.post("/api/study/explain", json={"card_id": 999}).status_code == 404


def test_explain_teacher_failure(
    client: TestClient, card: dict[str, Any], fake_teacher: FakeTeacher
) -> None:
    fake_teacher.error = TeacherError("timeout")
    response = client.post("/api/study/explain", json={"card_id": card["id"]})
    assert response.status_code == 502
    assert "Teacher explanation failed" in response_dict(response)["detail"]


def _make_teacher(transport: httpx.MockTransport, **kwargs: Any) -> OpenRouterTeacher:
    return OpenRouterTeacher(
        base_url="https://teacher.test",
        model="teacher-model",
        api_key="test-key",
        transport=transport,
        **kwargs,
    )


def test_to_vocal_uses_vocal_model_and_spoken_prompt() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": " What is the capital of France?"}}]},
        )

    teacher = _make_teacher(httpx.MockTransport(handler), vocal_model="cheap-model")
    result = teacher.to_vocal("**Capital** of France?", language="en")

    assert result == "What is the capital of France?"
    assert len(requests) == 1
    request = requests[0]
    assert str(request.url) == "https://teacher.test/api/v1/chat/completions"
    body = request.read()
    assert b'"model":"cheap-model"' in body
    assert b"text-to-speech" in body


def test_to_vocal_defaults_to_teacher_model() -> None:
    bodies: list[bytes] = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(request.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": "spoken"}}]})

    teacher = _make_teacher(httpx.MockTransport(handler))
    assert teacher.to_vocal("hi", language="auto") == "spoken"
    assert b'"model":"teacher-model"' in bodies[0]


def test_to_vocal_rejects_empty_text() -> None:
    teacher = _make_teacher(httpx.MockTransport(lambda r: httpx.Response(200)))
    with pytest.raises(TeacherError, match="Nothing to rewrite"):
        teacher.to_vocal("  ", language="auto")
