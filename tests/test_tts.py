from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app.teacher.base import TeacherError
from app.tts.base import TTSError
from app.tts.openrouter import OpenRouterTTS
from tests.conftest import FakeTeacher, FakeTTS, response_dict


def _make_tts(transport: httpx.MockTransport) -> OpenRouterTTS:
    return OpenRouterTTS(
        base_url="https://tts.test",
        model="tts-model",
        api_key="test-key",
        voice="nova",
        transport=transport,
    )


def test_speak_posts_to_audio_speech_endpoint() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, content=b"MP3DATA", headers={"Content-Type": "audio/mpeg"})

    result = _make_tts(httpx.MockTransport(handler)).speak("Bonjour", "fr")

    assert result.audio == b"MP3DATA"
    assert result.content_type == "audio/mpeg"
    assert len(requests) == 1
    request = requests[0]
    assert str(request.url) == "https://tts.test/api/v1/audio/speech"
    assert request.headers["Authorization"] == "Bearer test-key"
    body = request.read()
    assert b'"model":"tts-model"' in body
    assert b'"voice":"nova"' in body
    assert b'"input":"Bonjour"' in body


def test_speak_requires_model_and_base_url() -> None:
    transport = httpx.MockTransport(lambda r: httpx.Response(200))
    tts = OpenRouterTTS(base_url="", model="", transport=transport)
    with pytest.raises(TTSError, match="must be configured"):
        tts.speak("hello", "auto")


@pytest.mark.parametrize("text", ["", "   "])
def test_speak_rejects_empty_text_before_http(text: str) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, content=b"x")

    with pytest.raises(TTSError, match="Nothing to speak"):
        _make_tts(httpx.MockTransport(handler)).speak(text, "auto")
    assert calls == 0


def test_speak_rejects_empty_response() -> None:
    body = b""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=body)

    with pytest.raises(TTSError, match="empty response"):
        _make_tts(httpx.MockTransport(handler)).speak("hello", "auto")


@pytest.mark.parametrize("status_code", [400, 500])
def test_speak_http_error_is_wrapped(status_code: int) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json={"error": "nope"})

    with pytest.raises(TTSError, match="TTS request failed"):
        _make_tts(httpx.MockTransport(handler)).speak("hello", "auto")


def _enable_tts(client: TestClient, **extra: Any) -> None:
    payload: dict[str, Any] = {"tts_enabled": True}
    payload.update(extra)
    response = client.patch("/api/settings", json=payload)
    assert response.status_code == 200, response.text


def test_speak_question_disabled_by_default(client: TestClient, card: dict[str, Any]) -> None:
    response = client.post("/api/study/speak-question", json={"card_id": card["id"]})
    assert response.status_code == 403
    assert "off in your settings" in response_dict(response)["detail"]


def test_speak_question_returns_audio(
    client: TestClient, card: dict[str, Any], fake_tts: FakeTTS, fake_teacher: FakeTeacher
) -> None:
    _enable_tts(client)
    response = client.post("/api/study/speak-question", json={"card_id": card["id"]})
    assert response.status_code == 200
    assert response.content == b"FAKEAUDIO"
    assert response.headers["Content-Type"].startswith("audio/mpeg")
    assert fake_tts.calls == [("Capital of France?", "auto")]
    assert fake_teacher.vocal_calls == []


def test_speak_question_with_vocal_pass(
    client: TestClient, card: dict[str, Any], fake_tts: FakeTTS, fake_teacher: FakeTeacher
) -> None:
    _enable_tts(client, question_vocal=True, judge_language="fr")
    response = client.post("/api/study/speak-question", json={"card_id": card["id"]})
    assert response.status_code == 200
    assert fake_teacher.vocal_calls == [{"text": "Capital of France?", "language": "fr"}]
    assert fake_tts.calls == [("Vocal: Capital of France?", "fr")]


def test_speak_explanation_returns_audio(
    client: TestClient, card: dict[str, Any], fake_tts: FakeTTS, fake_teacher: FakeTeacher
) -> None:
    _enable_tts(client, teacher_vocal=True)
    client.patch("/api/settings", json={"eval_mode": "ai_assess"})
    answered = client.post(
        "/api/study/answer",
        json={
            "card_id": card["id"],
            "answer_text": "Paris",
            "input_method": "text",
            "response_time_ms": 1500,
        },
    )
    assert response_dict(answered)["status"] == "reviewed"

    response = client.post("/api/study/speak-explanation", json={"card_id": card["id"]})
    assert response.status_code == 200
    assert response.content == b"FAKEAUDIO"
    assert fake_teacher.vocal_calls == [
        {"text": "Paris is the capital of France.", "language": "auto"}
    ]
    assert fake_tts.calls == [("Vocal: Paris is the capital of France.", "auto")]


def test_speak_explanation_teacher_failure(
    client: TestClient, card: dict[str, Any], fake_teacher: FakeTeacher
) -> None:
    _enable_tts(client)
    fake_teacher.error = TeacherError("timeout")
    response = client.post("/api/study/speak-explanation", json={"card_id": card["id"]})
    assert response.status_code == 502
    assert "Teacher explanation failed" in response_dict(response)["detail"]


def test_speak_tts_failure(client: TestClient, card: dict[str, Any], fake_tts: FakeTTS) -> None:
    _enable_tts(client)
    fake_tts.error = TTSError("boom")
    response = client.post("/api/study/speak-question", json={"card_id": card["id"]})
    assert response.status_code == 502
    assert "Speech synthesis failed" in response_dict(response)["detail"]


def test_speak_blocked_when_admin_disables_tts(
    admin_client: TestClient, client: TestClient, card: dict[str, Any]
) -> None:
    _enable_tts(client)
    response = admin_client.patch("/api/admin/settings", json={"tts_allowed": False})
    assert response.status_code == 200, response.text
    response = client.post("/api/study/speak-question", json={"card_id": card["id"]})
    assert response.status_code == 403
    assert "disabled" in response_dict(response)["detail"]


def test_speak_unknown_card(client: TestClient, card: dict[str, Any]) -> None:
    _enable_tts(client)
    assert client.post("/api/study/speak-question", json={"card_id": 999}).status_code == 404
