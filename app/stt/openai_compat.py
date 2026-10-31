import os
from time import perf_counter
from typing import Any

import httpx

from app.agents import agent_api_key, agent_base_url, agent_model, api_key_env_name
from app.config import api_key_env, base_url_env
from app.models import AgentConfig
from app.retry import send_with_retries
from app.stt.base import STTError, STTResult, measure_audio_duration


class OpenAICompatibleSTT:
    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str = "",
        timeout: float = 30.0,
        transport: httpx.BaseTransport | None = None,
        *,
        api_key_env: str = "OPENROUTER_API_KEY",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout
        self.transport = transport
        self.api_key_env = api_key_env

    @classmethod
    def from_env(cls) -> "OpenAICompatibleSTT":
        return cls(
            base_url=os.getenv("STT_BASE_URL") or base_url_env(),
            model=os.getenv("STT_MODEL", ""),
            api_key=api_key_env("STT_API_KEY"),
        )

    @classmethod
    def from_config(cls, config: AgentConfig) -> "OpenAICompatibleSTT":
        return cls(
            base_url=agent_base_url(config, "STT_BASE_URL"),
            model=agent_model(config, "STT_MODEL"),
            api_key=agent_api_key(config),
            api_key_env=api_key_env_name(config),
        )

    def transcribe(self, audio: bytes, language: str) -> STTResult:
        if not self.base_url or not self.model:
            raise STTError("STT_BASE_URL and STT_MODEL must be configured")
        if not self.api_key:
            raise STTError(
                f"STT API key is not set; define {self.api_key_env} "
                "or OPENROUTER_API_KEY in the environment"
            )
        audio_duration_ms = measure_audio_duration(audio)
        endpoint = self.base_url
        if not endpoint.endswith("/audio/transcriptions"):
            if endpoint.endswith(("/api/v1", "/v1")):
                endpoint += "/audio/transcriptions"
            else:
                endpoint += "/api/v1/audio/transcriptions"
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        data = {"model": self.model}
        if language != "auto":
            data["language"] = language

        start = perf_counter()
        try:
            with httpx.Client(timeout=self.timeout, transport=self.transport) as client:
                request = client.build_request(
                    "POST",
                    endpoint,
                    headers=headers,
                    data=data,
                    files={"file": ("audio.webm", audio, "audio/webm")},
                )
                response = send_with_retries(client, request)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise STTError(f"STT request failed: {exc}") from exc
        stt_duration_ms = round((perf_counter() - start) * 1000)

        try:
            payload: dict[str, Any] = response.json()
            text = payload["text"]
            if not isinstance(text, str):
                raise TypeError("transcript is not text")
        except (KeyError, TypeError, ValueError) as exc:
            raise STTError("STT returned an invalid response") from exc
        return STTResult(
            text=text,
            audio_duration_ms=audio_duration_ms,
            stt_duration_ms=stt_duration_ms,
        )
