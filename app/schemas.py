from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

EvalMode = Literal["ai_preselect", "ai_assess"]
SchedulerName = Literal["fsrs", "sm2"]
InputMethod = Literal["text", "voice"]
StatsScope = Literal["deck", "card", "tag"]


class TagRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class DeckCreate(BaseModel):
    name: str = Field(min_length=1)
    description: str = ""
    context: str = ""
    scheduler: SchedulerName = "fsrs"
    scheduler_params: dict[str, Any] = Field(default_factory=dict)
    eval_mode: EvalMode | None = None


class DeckUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    description: str | None = None
    context: str | None = None
    scheduler: SchedulerName | None = None
    scheduler_params: dict[str, Any] | None = None
    eval_mode: EvalMode | None = None


class DeckRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str
    context: str
    scheduler: str
    scheduler_params: dict[str, Any]
    eval_mode: str | None
    created_at: datetime


class CardCreate(BaseModel):
    deck_id: int
    question: str = Field(min_length=1)
    answer: str = Field(min_length=1)
    details: str = ""
    context: str = ""
    expected_time_s: int | None = Field(default=None, ge=1)
    tags: list[str] = Field(default_factory=list)


class CardUpdate(BaseModel):
    deck_id: int | None = None
    question: str | None = Field(default=None, min_length=1)
    answer: str | None = Field(default=None, min_length=1)
    details: str | None = None
    context: str | None = None
    expected_time_s: int | None = Field(default=None, ge=1)
    tags: list[str] | None = None


class CardRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    deck_id: int
    question: str
    answer: str
    details: str
    context: str
    expected_time_s: int | None
    created_at: datetime
    tags: list[TagRead]


class DueCard(BaseModel):
    card: CardRead
    due: datetime
    is_new: bool


class SettingsRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    eval_mode: str
    judge_language: str
    stt_language: str
    voice_auto_judge: bool
    auto_confirm: bool
    teacher_enabled: bool
    daily_new_limit: int
    daily_review_limit: int


class SettingsUpdate(BaseModel):
    eval_mode: EvalMode | None = None
    judge_language: str | None = Field(default=None, min_length=1)
    stt_language: str | None = Field(default=None, min_length=1)
    voice_auto_judge: bool | None = None
    auto_confirm: bool | None = None
    teacher_enabled: bool | None = None
    daily_new_limit: int | None = Field(default=None, ge=0)
    daily_review_limit: int | None = Field(default=None, ge=0)


class TranscribeResponse(BaseModel):
    text: str
    stt_duration_ms: int
    audio_duration_ms: int


class AnswerRequest(BaseModel):
    card_id: int
    answer_text: str = ""
    input_method: InputMethod
    response_time_ms: int = Field(ge=0)
    stt_duration_ms: int | None = Field(default=None, ge=0)
    audio_duration_ms: int | None = Field(default=None, ge=0)
    preview: bool = False
    confirmed: bool = False
    self_fallback: bool = False
    fallback_token: str | None = None
    rating: int | None = Field(default=None, ge=1, le=4)
    is_correct: bool | None = None
    judge_feedback: str = ""
    judge_model: str = ""


class ExplainRequest(BaseModel):
    card_id: int


class ExplainResponse(BaseModel):
    explanation: str
    model: str


class AnswerResponse(BaseModel):
    status: Literal["pending", "reviewed", "fallback_required"]
    mode: str
    rating: int | None = None
    is_correct: bool | None = None
    feedback: str = ""
    judge_model: str = ""
    fallback_token: str | None = None
    due: datetime | None = None
    log_id: int | None = None


class StatsResponse(BaseModel):
    total: int
    correct: int
    incorrect: int
    correct_rate: float
    avg_response_time_ms: float | None
    by_mode: dict[str, int]
