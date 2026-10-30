from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, Column, UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel


def utc_now() -> datetime:
    """Return aware UTC for consistent storage and scheduler input."""
    return datetime.now(UTC)


def as_utc(value: datetime) -> datetime:
    """SQLite returns naive datetimes; treat them as UTC."""
    return value if value.tzinfo else value.replace(tzinfo=UTC)


class User(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("oidc_issuer", "oidc_subject"),)

    id: int | None = Field(default=None, primary_key=True)
    email: str = Field(unique=True, index=True)
    display_name: str = ""
    password_hash: str | None = None
    role: str = "user"
    status: str = "pending"
    oidc_issuer: str | None = None
    oidc_subject: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    last_login_at: datetime | None = None


class AuthSession(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    token_hash: str = Field(unique=True, index=True)
    csrf_token: str
    user_agent: str = ""
    created_at: datetime = Field(default_factory=utc_now)
    last_seen_at: datetime = Field(default_factory=utc_now)
    expires_at: datetime


class ApiToken(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    name: str
    prefix: str
    token_hash: str = Field(unique=True, index=True)
    created_at: datetime = Field(default_factory=utc_now)
    last_used_at: datetime | None = None
    revoked_at: datetime | None = None


class Deck(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    owner_id: int = Field(foreign_key="user.id", index=True)
    name: str
    description: str = ""
    context: str = ""
    scheduler: str = "fsrs"
    scheduler_params: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSON)
    )
    eval_mode: str | None = None
    visibility: str = "private"
    source_deck_id: int | None = None
    created_at: datetime = Field(default_factory=utc_now)


class DeckFollow(SQLModel, table=True):
    user_id: int = Field(foreign_key="user.id", primary_key=True)
    deck_id: int = Field(foreign_key="deck.id", primary_key=True)
    created_at: datetime = Field(default_factory=utc_now)


class Tag(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("owner_id", "name"),)

    id: int | None = Field(default=None, primary_key=True)
    owner_id: int = Field(foreign_key="user.id", index=True)
    name: str = Field(index=True)


class CardTag(SQLModel, table=True):
    card_id: int = Field(foreign_key="card.id", primary_key=True)
    tag_id: int = Field(foreign_key="tag.id", primary_key=True)


class Card(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    deck_id: int = Field(foreign_key="deck.id", index=True)
    question: str
    answer: str
    details: str = ""
    context: str = ""
    expected_time_s: int | None = None
    created_at: datetime = Field(default_factory=utc_now)
    tags: list[Tag] = Relationship(link_model=CardTag)


class CardState(SQLModel, table=True):
    user_id: int = Field(foreign_key="user.id", primary_key=True)
    card_id: int = Field(foreign_key="card.id", primary_key=True)
    scheduler: str
    state: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    due: datetime = Field(index=True)
    last_review: datetime | None = None
    introduced_at: datetime


class AnswerLog(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
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
    user_id: int = Field(foreign_key="user.id", primary_key=True)
    eval_mode: str = "ai_preselect"
    judge_language: str = "auto"
    stt_language: str = "auto"
    voice_auto_judge: bool = False
    auto_confirm: bool = False
    teacher_enabled: bool = True
    daily_new_limit: int = 0
    daily_review_limit: int = 0


class AppSettings(SQLModel, table=True):
    id: int = Field(default=1, primary_key=True)
    registration: str = "approval"
    allow_public_decks: bool = True
    teacher_allowed: bool = True
    voice_allowed: bool = True
    default_settings: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
