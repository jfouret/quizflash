import os
from typing import Any

import httpx
from jinja2 import TemplateError
from pydantic import ValidationError

from app.agents import (
    DEFAULT_AGENT_CONFIGS,
    agent_api_key,
    agent_base_url,
    agent_model,
    api_key_env_name,
    render_prompt,
)
from app.config import api_key_env, base_url_env
from app.models import AgentConfig
from app.retry import send_with_retries
from app.teacher.base import TeacherError, TeacherResult


class OpenRouterTeacher:
    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str = "",
        vocal_model: str = "",
        timeout: float = 30.0,
        transport: httpx.BaseTransport | None = None,
        *,
        system_prompt: str | None = None,
        prompt_template: str | None = None,
        vocal_base_url: str = "",
        vocal_api_key: str = "",
        vocal_system_prompt: str | None = None,
        vocal_prompt_template: str | None = None,
        api_key_env: str = "OPENROUTER_API_KEY",
        vocal_api_key_env: str = "OPENROUTER_API_KEY",
    ) -> None:
        defaults = DEFAULT_AGENT_CONFIGS
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.vocal_model = vocal_model or model
        self.timeout = timeout
        self.transport = transport
        self.system_prompt = (
            defaults["teacher"]["system_prompt"] if system_prompt is None else system_prompt
        )
        self.prompt_template = (
            defaults["teacher"]["prompt_template"] if prompt_template is None else prompt_template
        )
        self.vocal_base_url = (vocal_base_url or base_url).rstrip("/")
        self.vocal_api_key = vocal_api_key or api_key
        self.vocal_system_prompt = (
            defaults["verbalizer"]["system_prompt"]
            if vocal_system_prompt is None
            else vocal_system_prompt
        )
        self.vocal_prompt_template = (
            defaults["verbalizer"]["prompt_template"]
            if vocal_prompt_template is None
            else vocal_prompt_template
        )
        self.api_key_env = api_key_env
        self.vocal_api_key_env = vocal_api_key_env

    @classmethod
    def from_env(cls) -> "OpenRouterTeacher":
        return cls(
            base_url=base_url_env("TEACHER_BASE_URL", "JUDGE_BASE_URL"),
            model=os.getenv("TEACHER_MODEL", ""),
            api_key=api_key_env("TEACHER_API_KEY", "JUDGE_API_KEY"),
            vocal_model=os.getenv("VOCAL_MODEL", ""),
        )

    @classmethod
    def from_config(cls, config: AgentConfig, verbalizer: AgentConfig) -> "OpenRouterTeacher":
        base_url = agent_base_url(config, "TEACHER_BASE_URL", "JUDGE_BASE_URL")
        model = agent_model(config, "TEACHER_MODEL")
        vocal_base_url = agent_base_url(verbalizer, "TEACHER_BASE_URL", "JUDGE_BASE_URL")
        if not verbalizer.base_url:
            vocal_base_url = base_url
        return cls(
            base_url=base_url,
            model=model,
            api_key=agent_api_key(config),
            vocal_model=agent_model(verbalizer, "VOCAL_MODEL") or model,
            system_prompt=config.system_prompt,
            prompt_template=config.prompt_template,
            vocal_base_url=vocal_base_url,
            vocal_api_key=agent_api_key(verbalizer),
            vocal_system_prompt=verbalizer.system_prompt,
            vocal_prompt_template=verbalizer.prompt_template,
            api_key_env=api_key_env_name(config),
            vocal_api_key_env=api_key_env_name(verbalizer),
        )

    def explain(
        self,
        *,
        deck_context: str,
        card_context: str,
        question: str,
        expected_answer: str,
        user_answer: str,
        is_correct: bool | None,
        language: str,
        rating: int | None = None,
        max_level: int = 0,
        rating_label: str = "",
    ) -> TeacherResult:
        if not self.base_url or not self.model:
            raise TeacherError("TEACHER_BASE_URL and TEACHER_MODEL must be configured")
        if not self.api_key:
            raise TeacherError(
                f"Teacher API key is not set; define {self.api_key_env} "
                "or OPENROUTER_API_KEY in the environment"
            )

        correctness = (
            "not yet assessed" if is_correct is None else ("correct" if is_correct else "incorrect")
        )
        context = {
            "deck": {"context": deck_context},
            "card": {
                "context": card_context,
                "question": question,
                "answer": expected_answer,
            },
            "deck_context": deck_context,
            "card_context": card_context,
            "question": question,
            "expected_answer": expected_answer,
            "user_answer": user_answer,
            "is_correct": is_correct,
            "correctness": correctness,
            "rating": rating,
            "max_level": max_level,
            "rating_label": rating_label,
            "language": language,
        }
        try:
            system_message = render_prompt(self.system_prompt, context)
            user_message = render_prompt(self.prompt_template, context)
        except TemplateError as exc:
            raise TeacherError(f"Teacher prompt template is invalid: {exc}") from exc
        language_instruction = (
            "Use the language of the card." if language == "auto" else f"Answer in {language}."
        )
        system_message = "\n\n".join(
            part for part in (system_message, language_instruction) if part
        )

        response = self._chat(
            self.base_url,
            self.api_key,
            self.model,
            system_message,
            user_message,
        )
        return self._parse_response(response)

    def to_vocal(self, text: str, *, language: str) -> str:
        """Rewrite a text so it reads well when spoken aloud (no markdown, lists, symbols)."""
        if not self.vocal_base_url or not self.vocal_model:
            raise TeacherError("TEACHER_BASE_URL and VOCAL_MODEL must be configured")
        if not self.vocal_api_key:
            raise TeacherError(
                f"Verbalizer API key is not set; define {self.vocal_api_key_env} "
                "or OPENROUTER_API_KEY in the environment"
            )
        if not text.strip():
            raise TeacherError("Nothing to rewrite")
        context = {"text": text, "language": language}
        try:
            system_message = render_prompt(self.vocal_system_prompt, context)
            user_message = render_prompt(self.vocal_prompt_template, context) or text
        except TemplateError as exc:
            raise TeacherError(f"Verbalizer prompt template is invalid: {exc}") from exc
        language_instruction = (
            "Rewrite in the language of the text."
            if language == "auto"
            else f"Rewrite in {language}."
        )
        system_message = "\n\n".join(
            part for part in (system_message, language_instruction) if part
        )
        response = self._chat(
            self.vocal_base_url,
            self.vocal_api_key,
            self.vocal_model,
            system_message,
            user_message,
        )
        return self._parse_response(response).explanation

    def _chat(
        self,
        base_url: str,
        api_key: str,
        model: str,
        system_message: str,
        user_message: str,
    ) -> httpx.Response:
        headers = {"Authorization": f"Bearer {api_key}"}
        endpoint = base_url
        if not endpoint.endswith("/api/v1/chat/completions"):
            endpoint += "/api/v1/chat/completions"
        with httpx.Client(timeout=self.timeout, transport=self.transport) as client:
            try:
                request = client.build_request(
                    "POST",
                    endpoint,
                    headers=headers,
                    json={
                        "model": model,
                        "messages": [
                            {"role": "system", "content": system_message},
                            {"role": "user", "content": user_message},
                        ],
                    },
                )
                response = send_with_retries(client, request)
                response.raise_for_status()
            except httpx.HTTPError as exc:
                raise TeacherError(f"Teacher request failed: {exc}") from exc
        return response

    @staticmethod
    def _parse_response(response: httpx.Response) -> TeacherResult:
        try:
            payload: dict[str, Any] = response.json()
            content = payload["choices"][0]["message"]["content"]
            if not isinstance(content, str) or not content.strip():
                raise ValueError("empty teacher explanation")
            return TeacherResult(explanation=content.strip())
        except (KeyError, IndexError, TypeError, ValueError, ValidationError) as exc:
            raise TeacherError("Teacher returned an invalid response") from exc
