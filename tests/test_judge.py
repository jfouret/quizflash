import json
from typing import Any

import httpx
import pytest

from app.judge.base import JudgeError, JudgeResult
from app.judge.openai_compat import OpenAICompatibleJudge


def _valid_content(rating: int = 4) -> str:
    return json.dumps({"rating": rating, "is_correct": True, "feedback": "Bonne réponse."})


def _judge_response(content: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={"choices": [{"message": {"content": content}}]},
    )


def _make_judge(transport: httpx.MockTransport) -> OpenAICompatibleJudge:
    return OpenAICompatibleJudge(
        base_url="https://judge.test/v1",
        model="judge-model",
        api_key="test-key",
        transport=transport,
    )


def _evaluate(judge: OpenAICompatibleJudge) -> JudgeResult:
    return judge.evaluate(
        question="Quelle est la capitale de la France ?",
        expected_answer="Paris",
        user_answer="Paris",
        expected_time_s=15,
        response_time_ms=2345,
        language="fr",
    )


def test_valid_structured_output_and_request_context() -> None:
    request_bodies: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        request_bodies.append(json.loads(request.content))
        assert request.headers["Authorization"] == "Bearer test-key"
        return _judge_response(_valid_content())

    judge = _make_judge(httpx.MockTransport(handler))

    result = _evaluate(judge)

    assert result == JudgeResult(rating=4, is_correct=True, feedback="Bonne réponse.")
    assert len(request_bodies) == 1
    body = request_bodies[0]
    assert body["model"] == "judge-model"
    assert body["response_format"]["type"] == "json_schema"
    assert body["response_format"]["json_schema"]["strict"] is True
    context: dict[str, Any] = json.loads(body["messages"][1]["content"])
    assert context == {
        "question": "Quelle est la capitale de la France ?",
        "expected_answer": "Paris",
        "user_answer": "Paris",
        "expected_time_s": 15,
        "response_time_ms": 2345,
        "feedback_language": "fr",
        "language_instruction": "Write feedback in language code fr",
    }


def test_parse_failure_retries_once_with_original_context() -> None:
    request_bodies: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        request_bodies.append(json.loads(request.content))
        content = "not JSON" if len(request_bodies) == 1 else _valid_content()
        return _judge_response(content)

    result = _evaluate(_make_judge(httpx.MockTransport(handler)))

    assert result.rating == 4
    assert len(request_bodies) == 2
    first_messages = request_bodies[0]["messages"]
    second_messages = request_bodies[1]["messages"]
    assert second_messages[: len(first_messages)] == first_messages
    assert len(second_messages) == len(first_messages) + 1
    assert second_messages[-1]["role"] == "user"
    assert "invalid" in second_messages[-1]["content"]


def test_persistent_invalid_output_fails_after_two_attempts() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return _judge_response('{"rating": 3}')

    judge = _make_judge(httpx.MockTransport(handler))

    with pytest.raises(JudgeError, match="invalid structured response"):
        _evaluate(judge)
    assert calls == 2


def test_http_error_is_wrapped_without_retry() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503, json={"error": "unavailable"})

    judge = _make_judge(httpx.MockTransport(handler))

    with pytest.raises(JudgeError, match="Judge request failed"):
        _evaluate(judge)
    assert calls == 1


def test_timeout_is_wrapped_without_retry() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.TimeoutException("timed out", request=request)

    judge = _make_judge(httpx.MockTransport(handler))

    with pytest.raises(JudgeError, match="Judge request failed"):
        _evaluate(judge)
    assert calls == 1


@pytest.mark.parametrize("rating", [0, 5])
def test_out_of_range_rating_is_rejected(rating: int) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return _judge_response(_valid_content(rating))

    judge = _make_judge(httpx.MockTransport(handler))

    with pytest.raises(JudgeError, match="invalid structured response"):
        _evaluate(judge)
    assert calls == 2
