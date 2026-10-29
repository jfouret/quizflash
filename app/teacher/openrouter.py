import os
from typing import Any

import httpx
from pydantic import ValidationError

from app.teacher.base import TeacherError, TeacherResult


class OpenRouterTeacher:
    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str = "",
        timeout: float = 30.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout
        self.transport = transport

    @classmethod
    def from_env(cls) -> "OpenRouterTeacher":
        return cls(
            base_url=os.getenv("TEACHER_BASE_URL")
            or os.getenv("JUDGE_BASE_URL")
            or "https://openrouter.ai",
            model=os.getenv("TEACHER_MODEL", ""),
            api_key=(
                os.getenv("TEACHER_API_KEY")
                or os.getenv("JUDGE_API_KEY")
                or os.getenv("OPENROUTER_API_KEY")
                or ""
            ),
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
    ) -> TeacherResult:
        if not self.base_url or not self.model:
            raise TeacherError("TEACHER_BASE_URL and TEACHER_MODEL must be configured")
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        endpoint = self.base_url
        if not endpoint.endswith("/api/v1/chat/completions"):
            endpoint += "/api/v1/chat/completions"

        language_instruction = (
            "auto" if language == "auto" else f"Answer in {language}."
        )
        correctness = (
            "not yet assessed"
            if is_correct is None
            else ("correct" if is_correct else "incorrect")
        )
        sections = [
            f"Deck context:\n{deck_context}" if deck_context else None,
            f"Card context:\n{card_context}" if card_context else None,
            f"Question:\n{question}",
            f"Expected answer:\n{expected_answer}",
            f"User answer ({correctness}):\n{user_answer or '(empty)'}",
        ]
        user_message = "\n\n".join(section for section in sections if section)
        system_message = (
            "You are a teacher explaining a quiz card to its author. Use the deck and card "
            "context when given. Explain why the expected answer is right, point out what is "
            "missing or wrong in the user's answer when one was given, and add one useful "
            "detail for remembering it. Be concise. " + language_instruction
        )

        with httpx.Client(timeout=self.timeout, transport=self.transport) as client:
            try:
                response = client.post(
                    endpoint,
                    headers=headers,
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": system_message},
                            {"role": "user", "content": user_message},
                        ],
                    },
                )
                response.raise_for_status()
            except httpx.HTTPError as exc:
                raise TeacherError(f"Teacher request failed: {exc}") from exc
        return self._parse_response(response)

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
