from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from app.grading import DEFAULT_MAX


class JudgeResult(BaseModel):
    model_config = ConfigDict(strict=True)

    rating: int = Field(ge=0, le=100)
    is_correct: bool
    feedback: str


class Judge(Protocol):
    model: str

    def evaluate(
        self,
        *,
        question: str,
        expected_answer: str,
        user_answer: str,
        expected_time_s: int | None,
        response_time_ms: int,
        language: str,
        max_level: int = DEFAULT_MAX,
        labels: dict[int, str] | None = None,
    ) -> JudgeResult: ...


class JudgeError(RuntimeError):
    pass
