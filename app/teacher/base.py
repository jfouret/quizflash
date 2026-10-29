from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field


class TeacherResult(BaseModel):
    model_config = ConfigDict(strict=True)

    explanation: str = Field(min_length=1)


class Teacher(Protocol):
    model: str

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
    ) -> TeacherResult: ...


class TeacherError(RuntimeError):
    pass
