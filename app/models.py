from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, Column
from sqlmodel import Field, Relationship, SQLModel


def utc_now() -> datetime:
    """Return aware UTC for consistent storage and scheduler input."""
    return datetime.now(UTC)


class Deck(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    description: str = ""
    scheduler: str = "fsrs"
    scheduler_params: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSON)
    )
    eval_mode: str | None = None
    created_at: datetime = Field(default_factory=utc_now)


class Tag(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(unique=True, index=True)


class CardTag(SQLModel, table=True):
    card_id: int = Field(foreign_key="card.id", primary_key=True)
    tag_id: int = Field(foreign_key="tag.id", primary_key=True)


class Card(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    deck_id: int = Field(foreign_key="deck.id")
    question: str
    answer: str
    details: str = ""
    expected_time_s: int | None = None
    created_at: datetime = Field(default_factory=utc_now)
    tags: list[Tag] = Relationship(link_model=CardTag)


class CardState(SQLModel, table=True):
    card_id: int = Field(foreign_key="card.id", primary_key=True)
    scheduler: str
    state: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    due: datetime = Field(index=True)
    last_review: datetime | None = None
    introduced_at: datetime


class AnswerLog(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    card_id: int = Field(foreign_key="card.id", index=True)
    mode: str
    input_method: str
    answer_text: str = ""
    response_time_ms: int
    stt_duration_ms: int | None = None
    audio_duration_ms: int | None = None
    rating: int
    is_correct: bool
    judge_feedback: str = ""
    judge_model: str = ""
    reviewed_at: datetime = Field(index=True)


class Settings(SQLModel, table=True):
    id: int = Field(default=1, primary_key=True)
    eval_mode: str = "ai_preselect"
    judge_language: str = "auto"
    stt_language: str = "auto"
    voice_auto_judge: bool = False
    auto_confirm: bool = False
    daily_new_limit: int = 0
    daily_review_limit: int = 0
