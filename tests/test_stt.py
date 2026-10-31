import io
import wave

import httpx
import pytest

from app.stt.base import STTError
from app.stt.openai_compat import OpenAICompatibleSTT


def _wav_bytes(frame_count: int = 800, sample_rate: int = 8000) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(b"\x00\x00" * frame_count)
    return buffer.getvalue()


def _make_stt(transport: httpx.MockTransport) -> OpenAICompatibleSTT:
    return OpenAICompatibleSTT(
        base_url="https://stt.test/v1",
        model="stt-model",
        api_key="test-key",
        transport=transport,
    )


def test_openrouter_root_gets_the_api_v1_prefix() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"text": "Bonjour"})

    stt = OpenAICompatibleSTT(
        base_url="https://openrouter.ai",
        model="stt-model",
        api_key="test-key",
        transport=httpx.MockTransport(handler),
    )
    stt.transcribe(_wav_bytes(), "fr")

    assert str(requests[0].url) == "https://openrouter.ai/api/v1/audio/transcriptions"


def test_valid_transcription_measures_wav_duration_server_side() -> None:
    audio = _wav_bytes()
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"text": "Bonjour"})

    result = _make_stt(httpx.MockTransport(handler)).transcribe(audio, "fr")

    assert result.text == "Bonjour"
    assert result.audio_duration_ms == 100
    assert result.stt_duration_ms >= 0
    assert len(requests) == 1
    request = requests[0]
    assert str(request.url) == "https://stt.test/v1/audio/transcriptions"
    assert request.headers["Authorization"] == "Bearer test-key"
    assert request.headers["Content-Type"].startswith("multipart/form-data;")
    assert b"\r\n\r\nstt-model\r\n" in request.content
    assert audio in request.content


@pytest.mark.parametrize(("language", "language_sent"), [("fr", True), ("auto", False)])
def test_stt_language_behavior(language: str, language_sent: bool) -> None:
    request_bodies: list[bytes] = []

    def handler(request: httpx.Request) -> httpx.Response:
        request_bodies.append(request.content)
        return httpx.Response(200, json={"text": "transcript"})

    result = _make_stt(httpx.MockTransport(handler)).transcribe(_wav_bytes(), language)

    assert result.text == "transcript"
    assert len(request_bodies) == 1
    body = request_bodies[0]
    assert (b'name="language"' in body) is language_sent
    if language_sent:
        assert b"\r\n\r\nfr\r\n" in body


@pytest.mark.parametrize("audio", [b"", b"not an audio container"])
def test_invalid_audio_fails_before_http_request(audio: bytes) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"text": "should not be used"})

    stt = _make_stt(httpx.MockTransport(handler))

    with pytest.raises(STTError):
        stt.transcribe(audio, "auto")
    assert calls == 0


@pytest.mark.parametrize("body", [b"not JSON", b"{}", b'{"text": 42}'])
def test_malformed_api_response_is_rejected(body: bytes) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=body,
            headers={"Content-Type": "application/json"},
        )

    stt = _make_stt(httpx.MockTransport(handler))

    with pytest.raises(STTError, match="STT returned an invalid response"):
        stt.transcribe(_wav_bytes(), "auto")


@pytest.mark.parametrize("status_code", [400, 500])
def test_http_api_error_is_wrapped(status_code: int) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json={"error": "request failed"})

    stt = _make_stt(httpx.MockTransport(handler))

    with pytest.raises(STTError, match="STT request failed"):
        stt.transcribe(_wav_bytes(), "auto")
