from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# Bounds on free text: the database is user-writable and LLM calls are billed per token.
MAX_TEXT = 10_000
MAX_ANSWER = 20_000
MAX_TAG = 50
MAX_TAGS = 50
TAG = Annotated[str, Field(min_length=1, max_length=MAX_TAG)]

EvalMode = Literal["ai_preselect", "ai_assess"]
SchedulerName = Literal["fsrs", "sm2"]
InputMethod = Literal["text", "voice"]
StatsScope = Literal["deck", "card", "tag"]
Visibility = Literal["private", "public"]
Registration = Literal["open", "approval", "closed"]
UserStatus = Literal["pending", "active", "disabled"]
Role = Literal["admin", "user"]


class TagRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class DeckCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=MAX_TEXT)
    context: str = Field(default="", max_length=MAX_TEXT)
    scheduler: SchedulerName = "fsrs"
    scheduler_params: dict[str, Any] = Field(default_factory=dict)
    eval_mode: EvalMode | None = None
    visibility: Visibility = "private"


class DeckUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=MAX_TEXT)
    context: str | None = Field(default=None, max_length=MAX_TEXT)
    scheduler: SchedulerName | None = None
    scheduler_params: dict[str, Any] | None = None
    eval_mode: EvalMode | None = None
    visibility: Visibility | None = None


class DeckRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str
    context: str
    scheduler: str
    scheduler_params: dict[str, Any]
    eval_mode: str | None
    owner_id: int
    visibility: str
    source_deck_id: int | None
    created_at: datetime


class PublicDeckRead(DeckRead):
    owner_name: str
    card_count: int
    following: bool


class CardCreate(BaseModel):
    deck_id: int
    question: str = Field(min_length=1, max_length=MAX_TEXT)
    answer: str = Field(min_length=1, max_length=MAX_TEXT)
    details: str = Field(default="", max_length=MAX_TEXT)
    context: str = Field(default="", max_length=MAX_TEXT)
    expected_time_s: int | None = Field(default=None, ge=1)
    tags: list[TAG] = Field(default_factory=list, max_length=MAX_TAGS)


class CardUpdate(BaseModel):
    deck_id: int | None = None
    question: str | None = Field(default=None, min_length=1, max_length=MAX_TEXT)
    answer: str | None = Field(default=None, min_length=1, max_length=MAX_TEXT)
    details: str | None = Field(default=None, max_length=MAX_TEXT)
    context: str | None = Field(default=None, max_length=MAX_TEXT)
    expected_time_s: int | None = Field(default=None, ge=1)
    tags: list[TAG] | None = Field(default=None, max_length=MAX_TAGS)


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

    eval_mode: str
    judge_language: str
    stt_language: str
    voice_auto_judge: bool
    auto_confirm: bool
    teacher_enabled: bool
    tts_enabled: bool
    question_vocal: bool
    teacher_vocal: bool
    daily_new_limit: int
    daily_review_limit: int


class SettingsUpdate(BaseModel):
    eval_mode: EvalMode | None = None
    judge_language: str | None = Field(default=None, min_length=1, max_length=35)
    stt_language: str | None = Field(default=None, min_length=1, max_length=35)
    voice_auto_judge: bool | None = None
    auto_confirm: bool | None = None
    teacher_enabled: bool | None = None
    tts_enabled: bool | None = None
    question_vocal: bool | None = None
    teacher_vocal: bool | None = None
    daily_new_limit: int | None = Field(default=None, ge=0)
    daily_review_limit: int | None = Field(default=None, ge=0)


class TranscribeResponse(BaseModel):
    text: str
    stt_duration_ms: int
    audio_duration_ms: int


class AnswerRequest(BaseModel):
    card_id: int
    answer_text: str = Field(default="", max_length=MAX_ANSWER)
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
    judge_feedback: str = Field(default="", max_length=MAX_TEXT)
    judge_model: str = Field(default="", max_length=200)


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


class AppSettingsRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    registration: str
    allow_public_decks: bool
    teacher_allowed: bool
    voice_allowed: bool
    tts_allowed: bool
    default_settings: dict[str, Any]


class AppSettingsUpdate(BaseModel):
    registration: Registration | None = None
    allow_public_decks: bool | None = None
    teacher_allowed: bool | None = None
    voice_allowed: bool | None = None
    tts_allowed: bool | None = None
    default_settings: SettingsUpdate | None = None


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    display_name: str
    role: str
    status: str
    oidc_subject: str | None
    created_at: datetime
    last_login_at: datetime | None


class UserAdminUpdate(BaseModel):
    status: UserStatus | None = None
    role: Role | None = None


class MeResponse(BaseModel):
    user: UserRead
    csrf_token: str


class ApiTokenCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class ApiTokenRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    prefix: str
    created_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None


class ApiTokenCreated(ApiTokenRead):
    token: str


API_KEY_ENV = Annotated[
    str, Field(min_length=1, max_length=100, pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
]


class AgentConfigUpdate(BaseModel):
    model: str | None = Field(default=None, max_length=200)
    base_url: str | None = Field(default=None, max_length=500)
    api_key_env: API_KEY_ENV | None = None
    voice: str | None = Field(default=None, max_length=100)
    system_prompt: str | None = Field(default=None, max_length=MAX_ANSWER)
    prompt_template: str | None = Field(default=None, max_length=MAX_ANSWER)
