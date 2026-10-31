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
from app.judge.base import JudgeError, JudgeResult
from app.models import AgentConfig

RATING_INSTRUCTIONS = (
    "Rate recall quality independently of correctness, using the response time and "
    "expected time when available. Pick the level from the deck's scale."
)

# Fallback wording when a deck level has no label of its own.
LEVEL_HINTS = {
    0: "no useful recall or a wrong answer",
    1: "difficult or partial recall",
    2: "correct recall with minor difficulty or omissions",
    3: "complete, correct and prompt recall",
}


def _rating_criteria(max_level: int, labels: dict[int, str]) -> dict[str, str]:
    criteria: dict[str, str] = {}
    for level in range(max(0, max_level) + 1):
        name = labels.get(level) or f"Level {level}"
        criteria[str(level)] = f"{name}: {LEVEL_HINTS.get(level, 'a point on the scale')}"
    return criteria


class OpenRouterJudge:
    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str = "",
        timeout: float = 5.0,
        transport: httpx.BaseTransport | None = None,
        *,
        system_prompt: str | None = None,
        prompt_template: str | None = None,
        api_key_env: str = "OPENROUTER_API_KEY",
    ) -> None:
        defaults = DEFAULT_AGENT_CONFIGS["judge"]
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout
        self.transport = transport
        self.system_prompt = defaults["system_prompt"] if system_prompt is None else system_prompt
        self.prompt_template = (
            defaults["prompt_template"] if prompt_template is None else prompt_template
        )
        self.api_key_env = api_key_env

    @classmethod
    def from_env(cls) -> "OpenRouterJudge":
        return cls(
            base_url=base_url_env("JUDGE_BASE_URL"),
            model=os.getenv("JUDGE_MODEL", "inception/mercury-decide"),
            api_key=api_key_env("JUDGE_API_KEY"),
        )

    @classmethod
    def from_config(cls, config: AgentConfig) -> "OpenRouterJudge":
        return cls(
            base_url=agent_base_url(config, "JUDGE_BASE_URL"),
            model=agent_model(config, "JUDGE_MODEL", "inception/mercury-decide"),
            api_key=agent_api_key(config),
            system_prompt=config.system_prompt,
            prompt_template=config.prompt_template,
            api_key_env=api_key_env_name(config),
        )

    def evaluate(
        self,
        *,
        question: str,
        expected_answer: str,
        user_answer: str,
        expected_time_s: int | None,
        response_time_ms: int,
        language: str,
        max_level: int = 4,
        labels: dict[int, str] | None = None,
    ) -> JudgeResult:
        if not self.base_url or not self.model:
            raise JudgeError("JUDGE_BASE_URL and JUDGE_MODEL must be configured")
        if not self.api_key:
            raise JudgeError(
                f"Judge API key is not set; define {self.api_key_env} "
                "or OPENROUTER_API_KEY in the environment"
            )
        context = {
            "card": {"question": question, "answer": expected_answer},
            "question": question,
            "expected_answer": expected_answer,
            "user_answer": user_answer,
            "expected_time_s": expected_time_s,
            "response_time_ms": response_time_ms,
            "language": language,
        }
        try:
            guidelines = render_prompt(self.system_prompt, context)
            instructions = render_prompt(self.prompt_template, context)
        except TemplateError as exc:
            raise JudgeError(f"Judge prompt template is invalid: {exc}") from exc
        instructions = "\n\n".join(part for part in (guidelines, instructions) if part)
        rating_instructions = "\n\n".join(
            part for part in (guidelines, RATING_INSTRUCTIONS) if part
        )
        headers = {"Authorization": f"Bearer {self.api_key}"}
        endpoint = self.base_url
        if not endpoint.endswith("/api/alpha/decisions"):
            endpoint += "/api/alpha/decisions"

        with httpx.Client(timeout=self.timeout, transport=self.transport) as client:
            try:
                response = client.post(
                    endpoint,
                    headers=headers,
                    json={
                        "model": self.model,
                        "state": {
                            "question": question,
                            "expected_answer": expected_answer,
                            "user_answer": user_answer,
                            "expected_time_s": expected_time_s,
                            "response_time_ms": response_time_ms,
                            "language": language,
                        },
                        "questions": {
                            "is_correct": {
                                "type": "noul",
                                "instructions": instructions,
                                "criteria": {
                                    "true": "The answer matches the expected answer semantically.",
                                    "false": (
                                        "The answer is missing, wrong, or substantively incomplete."
                                    ),
                                },
                            },
                            "rating": {
                                "type": "choice",
                                "instructions": rating_instructions,
                                "criteria": _rating_criteria(max_level, labels or {}),
                            },
                        },
                    },
                )
                response.raise_for_status()
            except httpx.HTTPError as exc:
                raise JudgeError(f"Judge request failed: {exc}") from exc
        return self._parse_response(response, max_level)

    @staticmethod
    def _parse_response(response: httpx.Response, max_level: int = 4) -> JudgeResult:
        try:
            payload: dict[str, Any] = response.json()
            correctness = payload["answers"]["is_correct"]
            rating = payload["answers"]["rating"]
            if correctness["type"] != "noul" or rating["type"] != "choice":
                raise TypeError("unexpected decision types")
            probability = correctness["noul"]
            choice = rating["choice"]
            if (
                isinstance(probability, bool)
                or not isinstance(probability, (int, float))
                or not 0 <= probability <= 1
            ):
                raise ValueError("invalid correctness probability")
            if not isinstance(choice, str) or not choice.isdigit():
                raise ValueError("invalid rating choice")
            if not 0 <= int(choice) <= max_level:
                raise ValueError("rating choice is outside the deck scale")
            return JudgeResult(
                rating=int(choice),
                is_correct=probability >= 0.5,
                feedback="",
            )
        except (KeyError, IndexError, TypeError, ValueError, ValidationError) as exc:
            raise JudgeError("Judge returned an invalid structured response") from exc
