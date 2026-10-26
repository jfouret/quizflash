from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field


class JudgeResult(BaseModel):
    model_config = ConfigDict(strict=True)

    rating: int = Field(ge=1, le=4)
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
    ) -> JudgeResult: ...


class JudgeError(RuntimeError):
    pass
