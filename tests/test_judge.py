import json
from typing import Any

import httpx
import pytest

from app.judge.base import JudgeError, JudgeResult
from app.judge.openrouter import OpenRouterJudge


def _judge_response(noul: Any = 0.96, choice: Any = "4") -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "model": "inception/mercury-decide",
            "answers": {
                "is_correct": {"type": "noul", "noul": noul},
                "rating": {"type": "choice", "choice": choice},
            },
            "usage": {"input_tokens": 100, "output_tokens": 0},
        },
    )


def _make_judge(transport: httpx.MockTransport) -> OpenRouterJudge:
    return OpenRouterJudge(
        base_url="https://openrouter.ai",
        model="inception/mercury-decide",
        api_key="test-key",
        transport=transport,
    )


def _evaluate(judge: OpenRouterJudge) -> JudgeResult:
    return judge.evaluate(
        question="Quelle est la capitale de la France ?",
        expected_answer="Paris",
        user_answer="Paris",
        expected_time_s=15,
        response_time_ms=2345,
        language="fr",
    )


def test_decisions_endpoint_and_request_context() -> None:
    request_bodies: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/alpha/decisions"
        assert request.headers["Authorization"] == "Bearer test-key"
        request_bodies.append(json.loads(request.content))
        return _judge_response()

    result = _evaluate(_make_judge(httpx.MockTransport(handler)))

    assert result == JudgeResult(rating=4, is_correct=True, feedback="")
    assert len(request_bodies) == 1
    body = request_bodies[0]
    assert body["model"] == "inception/mercury-decide"
    assert body["state"] == {
        "question": "Quelle est la capitale de la France ?",
        "expected_answer": "Paris",
        "user_answer": "Paris",
        "expected_time_s": 15,
        "response_time_ms": 2345,
        "language": "fr",
    }
    assert body["questions"]["is_correct"]["type"] == "noul"
    assert body["questions"]["rating"]["type"] == "choice"
    assert set(body["questions"]["rating"]["criteria"]) == {"0", "1", "2", "3", "4"}
    assert "messages" not in body


def test_rating_criteria_follow_the_deck_scale() -> None:
    request_bodies: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        request_bodies.append(json.loads(request.content))
        return _judge_response(choice="7")

    judge = _make_judge(httpx.MockTransport(handler))
    result = judge.evaluate(
        question="Q",
        expected_answer="A",
        user_answer="A",
        expected_time_s=None,
        response_time_ms=1000,
        language="en",
        max_level=10,
        labels={3: "Bad", 5: "Average", 7: "Good"},
    )

    assert result.rating == 7
    criteria = request_bodies[0]["questions"]["rating"]["criteria"]
    assert set(criteria) == {str(level) for level in range(11)}
    assert criteria["3"].startswith("Bad")
    assert criteria["7"].startswith("Good")


@pytest.mark.parametrize(
    ("probability", "expected"),
    [(0.49, False), (0.5, True), (1, True)],
)
def test_correctness_uses_noul_probability(probability: float, expected: bool) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return _judge_response(noul=probability)

    result = _evaluate(_make_judge(httpx.MockTransport(handler)))

    assert result.is_correct is expected


def test_invalid_output_fails_without_retry() -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"answers": {}})

    judge = _make_judge(httpx.MockTransport(handler))

    with pytest.raises(JudgeError, match="invalid structured response"):
        _evaluate(judge)
    assert calls == 1


def test_http_error_is_wrapped_without_retry() -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
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


@pytest.mark.parametrize("choice", ["5", 4, None, "-1", "1.5"])
def test_invalid_rating_choice_is_rejected(choice: Any) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return _judge_response(choice=choice)

    judge = _make_judge(httpx.MockTransport(handler))

    with pytest.raises(JudgeError, match="invalid structured response"):
        _evaluate(judge)


@pytest.mark.parametrize("probability", [-0.1, 1.1, True, "0.5"])
def test_invalid_correctness_probability_is_rejected(probability: Any) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return _judge_response(noul=probability)

    judge = _make_judge(httpx.MockTransport(handler))

    with pytest.raises(JudgeError, match="invalid structured response"):
        _evaluate(judge)
