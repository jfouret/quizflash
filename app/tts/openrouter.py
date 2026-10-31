import os

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
from app.tts.base import TTSError, TTSResult


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
        if not self.base_url or not self.model:
            raise TTSError("TTS_BASE_URL and TTS_MODEL must be configured")
        if not self.api_key:
            raise TTSError(
                f"TTS API key is not set; define {self.api_key_env} "
                "or OPENROUTER_API_KEY in the environment"
            )
        if not text.strip():
            raise TTSError("Nothing to speak")
        headers = {"Authorization": f"Bearer {self.api_key}"}
        endpoint = self.base_url
        if not endpoint.endswith("/audio/speech"):
            if endpoint.endswith(("/api/v1", "/v1")):
                endpoint += "/audio/speech"
            else:
                endpoint += "/api/v1/audio/speech"
        # The speech endpoint takes no language parameter; the vocal pass already
        # rewrites the text in the target language, so `language` is unused here.
        payload: dict[str, object] = {
            "model": self.model,
            "voice": self.voice,
            "input": text,
            "response_format": "mp3",
        }

        with httpx.Client(timeout=self.timeout, transport=self.transport) as client:
            try:
                response = client.post(endpoint, headers=headers, json=payload)
                response.raise_for_status()
            except httpx.HTTPError as exc:
                raise TTSError(f"TTS request failed: {exc}") from exc
        if not response.content:
            raise TTSError("TTS returned an empty response")
        return TTSResult(
            audio=response.content,
            content_type=response.headers.get("Content-Type", "audio/mpeg").split(";")[0].strip(),
        )
