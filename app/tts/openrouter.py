import os
from collections.abc import Iterator

import httpx

from app.agents import (
    agent_api_key,
    agent_base_url,
    agent_model,
    agent_voice,
    api_key_env_name,
)
from app.config import api_key_env, base_url_env
from app.models import AgentConfig
from app.retry import UpstreamGate, send_with_retries
from app.tts.base import TTSError, TTSResult, TTSStream


class OpenRouterTTS:
    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str = "",
        voice: str = "en_paul_neutral",
        timeout: float = 60.0,
        transport: httpx.BaseTransport | None = None,
        *,
        api_key_env: str = "OPENROUTER_API_KEY",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.voice = voice
        self.timeout = timeout
        self.transport = transport
        self.api_key_env = api_key_env
        # A batch prefetches one clip per card at once; the provider rate-limits
        # that burst, so the calls queue and start a second apart.
        self.gate = UpstreamGate(min_interval_seconds=1.0)

    @classmethod
    def from_env(cls) -> "OpenRouterTTS":
        return cls(
            base_url=base_url_env("TTS_BASE_URL", "TEACHER_BASE_URL", "JUDGE_BASE_URL"),
            model=os.getenv("TTS_MODEL", ""),
            api_key=api_key_env("TTS_API_KEY", "TEACHER_API_KEY", "JUDGE_API_KEY"),
            voice=os.getenv("TTS_VOICE", "en_paul_neutral"),
        )

    @classmethod
    def from_config(cls, config: AgentConfig) -> "OpenRouterTTS":
        return cls(
            base_url=agent_base_url(config, "TTS_BASE_URL", "TEACHER_BASE_URL", "JUDGE_BASE_URL"),
            model=agent_model(config, "TTS_MODEL"),
            api_key=agent_api_key(config),
            voice=agent_voice(config),
            api_key_env=api_key_env_name(config),
        )

    def speak(self, text: str, language: str) -> TTSResult:
        stream = self.speak_stream(text, language)
        return TTSResult(audio=b"".join(stream.chunks), content_type=stream.content_type)

    def speak_stream(self, text: str, language: str) -> TTSStream:
        """Open the provider request and read its first chunk, for early playback.

        Every failure (configuration, HTTP status, non-audio answer, empty body)
        happens here, before the caller has committed to a response status.
        """
        if not self.base_url or not self.model:
            raise TTSError("TTS_BASE_URL and TTS_MODEL must be configured")
        if not self.api_key:
            raise TTSError(
                f"TTS API key is not set; define {self.api_key_env} "
                "or OPENROUTER_API_KEY in the environment"
            )
        if not text.strip():
            raise TTSError("Nothing to speak")
        # The speech endpoint takes no language parameter; the vocal pass already
        # rewrites the text in the target language, so `language` is unused here.
        payload: dict[str, object] = {
            "model": self.model,
            "voice": self.voice,
            "input": text,
            "response_format": "mp3",
        }
        return self._open(self._endpoint(), payload)

    def _endpoint(self) -> str:
        endpoint = self.base_url
        if not endpoint.endswith("/audio/speech"):
            if endpoint.endswith(("/api/v1", "/v1")):
                endpoint += "/audio/speech"
            else:
                endpoint += "/api/v1/audio/speech"
        return endpoint

    def _open(self, endpoint: str, payload: dict[str, object]) -> TTSStream:
        headers = {"Authorization": f"Bearer {self.api_key}"}
        client = httpx.Client(timeout=self.timeout, transport=self.transport)
        try:
            request = client.build_request("POST", endpoint, headers=headers, json=payload)
            with self.gate.slot():
                response = send_with_retries(client, request, stream=True)
                response.raise_for_status()
                content_type = response.headers.get("content-type", "").split(";")[0].strip()
                if content_type and not content_type.startswith("audio/"):
                    raise TTSError(f"TTS answered {content_type}, not audio")
                chunks = response.iter_bytes()
                first = next((chunk for chunk in chunks if chunk), b"")
                if not first:
                    raise TTSError("TTS returned an empty response")
        except httpx.HTTPError as exc:
            client.close()
            raise TTSError(f"TTS request failed: {exc}") from exc
        except TTSError:
            client.close()
            raise

        def body() -> Iterator[bytes]:
            try:
                yield first
                for chunk in chunks:
                    if chunk:
                        yield chunk
            finally:
                response.close()
                client.close()

        return TTSStream(content_type=content_type or "audio/mpeg", chunks=body())
