from datetime import datetime

from sqlalchemy import func
from sqlmodel import Session, col, select

from app.models import AnswerLog, Card, CardState, CardTag, Deck, Settings, Tag, utc_now
from app.schemas import (
    CardCreate,
    CardUpdate,
    DeckCreate,
    DeckUpdate,
    SettingsUpdate,
)
from app.srs import get_scheduler


class NotFoundError(LookupError):
    pass


def list_decks(session: Session) -> list[Deck]:
    return list(session.exec(select(Deck).order_by(col(Deck.id))).all())


def get_deck(session: Session, deck_id: int) -> Deck:
    deck = session.get(Deck, deck_id)
    if deck is None:
        raise NotFoundError(f"Deck {deck_id} not found")
    return deck


def create_deck(session: Session, data: DeckCreate) -> Deck:
    deck = Deck(**data.model_dump())
    session.add(deck)
    session.commit()
    session.refresh(deck)
    return deck


def update_deck(session: Session, deck_id: int, data: DeckUpdate) -> Deck:
    deck = get_deck(session, deck_id)
    values = data.model_dump(exclude_unset=True)
    for field in ("name", "description", "context", "scheduler", "scheduler_params"):
        if field in values and values[field] is None:
            raise ValueError(f"{field} cannot be null")
    for key, value in values.items():
        setattr(deck, key, value)
    session.add(deck)
    session.commit()
    session.refresh(deck)
    return deck


def _delete_card(session: Session, card: Card) -> None:
    if card.id is None:
        raise ValueError("Card has no ID")
    for log in session.exec(select(AnswerLog).where(AnswerLog.card_id == card.id)):
        session.delete(log)
    for link in session.exec(select(CardTag).where(CardTag.card_id == card.id)):
        session.delete(link)
    state = session.get(CardState, card.id)
    if state is not None:
        session.delete(state)
    session.flush()
    session.delete(card)


def delete_deck(session: Session, deck_id: int) -> None:
    deck = get_deck(session, deck_id)
    for card in list(session.exec(select(Card).where(Card.deck_id == deck_id)).all()):
        _delete_card(session, card)
    session.delete(deck)
    session.commit()


def _tags_by_name(session: Session, names: list[str]) -> list[Tag]:
    tags: list[Tag] = []
    for raw_name in dict.fromkeys(names):
        name = raw_name.strip()
        if not name:
            raise ValueError("Tag names cannot be empty")
        tag = session.exec(select(Tag).where(Tag.name == name)).first()
        if tag is None:
            tag = Tag(name=name)
            session.add(tag)
            session.flush()
        tags.append(tag)
    return tags


def list_cards(
    session: Session, deck_id: int | None = None, tag: str | None = None
) -> list[Card]:
    statement = select(Card).order_by(col(Card.id))
    if deck_id is not None:
        statement = statement.where(Card.deck_id == deck_id)
    if tag is not None:
        statement = statement.join(CardTag).join(Tag).where(Tag.name == tag)
    return list(session.exec(statement).all())


def get_card(session: Session, card_id: int) -> Card:
    card = session.get(Card, card_id)
    if card is None:
        raise NotFoundError(f"Card {card_id} not found")
    return card


def create_card(session: Session, data: CardCreate) -> Card:
    get_deck(session, data.deck_id)
    values = data.model_dump(exclude={"tags"})
    card = Card(**values)
    card.tags = _tags_by_name(session, data.tags)
    session.add(card)
    session.flush()
    if card.id is None:
        raise RuntimeError("Card ID was not generated")
    now = utc_now()
    deck = get_deck(session, data.deck_id)
    scheduler = get_scheduler(deck.scheduler)
    session.add(
        CardState(
            card_id=card.id,
            scheduler=deck.scheduler,
            state=scheduler.init_state(now),
            due=now,
            introduced_at=now,
        )
    )
    session.commit()
    session.refresh(card)
    return card


def update_card(session: Session, card_id: int, data: CardUpdate) -> Card:
    card = get_card(session, card_id)
    values = data.model_dump(exclude_unset=True)
    for field in ("deck_id", "question", "answer", "details", "context"):
        if field in values and values[field] is None:
            raise ValueError(f"{field} cannot be null")
    if "deck_id" in values:
        get_deck(session, values["deck_id"])
    if "tags" in values:
        raw_tags = values.pop("tags")
        if raw_tags is None:
            raise ValueError("tags cannot be null")
        card.tags = _tags_by_name(session, raw_tags)
    for key, value in values.items():
        setattr(card, key, value)
    session.add(card)
    session.commit()
    session.refresh(card)
    return card


def delete_card(session: Session, card_id: int) -> None:
    card = get_card(session, card_id)
    _delete_card(session, card)
    session.commit()


def list_tags(session: Session) -> list[Tag]:
    return list(session.exec(select(Tag).order_by(col(Tag.name))).all())


def delete_tag(session: Session, tag_id: int) -> None:
    tag = session.get(Tag, tag_id)
    if tag is None:
        raise NotFoundError(f"Tag {tag_id} not found")
    for link in session.exec(select(CardTag).where(CardTag.tag_id == tag_id)):
        session.delete(link)
    session.delete(tag)
    session.commit()


def get_settings(session: Session) -> Settings:
    settings = session.get(Settings, 1)
    if settings is None:
        settings = Settings()
        session.add(settings)
        session.commit()
        session.refresh(settings)
    return settings


def update_settings(session: Session, data: SettingsUpdate) -> Settings:
    settings = get_settings(session)
    values = data.model_dump(exclude_unset=True)
    fields = (
        "eval_mode",
        "judge_language",
        "stt_language",
        "voice_auto_judge",
        "auto_confirm",
        "teacher_enabled",
    )
    for field in fields:
        if field in values and values[field] is None:
            raise ValueError(f"{field} cannot be null")
    for key, value in values.items():
        setattr(settings, key, value)
    session.add(settings)
    session.commit()
    session.refresh(settings)
    return settings


def _daily_usage(session: Session, now: datetime) -> tuple[int, int]:
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    new_count = session.exec(
        select(func.count(col(CardState.card_id))).where(
            col(CardState.introduced_at) >= start,
            col(CardState.last_review).is_not(None),
        )
    ).one()
    review_count = session.exec(
        select(func.count(col(AnswerLog.id)))
        .join(CardState, col(AnswerLog.card_id) == col(CardState.card_id))
        .where(
            col(AnswerLog.reviewed_at) >= start,
            col(AnswerLog.reviewed_at) != col(CardState.introduced_at),
        )
    ).one()
    return int(new_count), int(review_count)


def get_due(
    session: Session, deck_id: int | None = None, now: datetime | None = None
) -> list[tuple[Card, CardState]]:
    current = now or utc_now()
    statement = (
        select(Card, CardState)
        .join(CardState, col(Card.id) == col(CardState.card_id))
        .where(col(CardState.due) <= current)
        .order_by(col(CardState.due), col(Card.id))
    )
    if deck_id is not None:
        get_deck(session, deck_id)
        statement = statement.where(Card.deck_id == deck_id)
    rows = list(session.exec(statement).all())
    settings = get_settings(session)
    new_used, review_used = _daily_usage(session, current)
    new_remaining = (
        None
        if settings.daily_new_limit == 0
        else max(0, settings.daily_new_limit - new_used)
    )
    review_remaining = (
        None
        if settings.daily_review_limit == 0
        else max(0, settings.daily_review_limit - review_used)
    )

    due: list[tuple[Card, CardState]] = []
    for card, state in rows:
        is_new = state.last_review is None
        if is_new and new_remaining is not None:
            if new_remaining == 0:
                continue
            new_remaining -= 1
        if not is_new and review_remaining is not None:
            if review_remaining == 0:
                continue
            review_remaining -= 1
        due.append((card, state))
    return due


def get_last_answer_log(session: Session, card_id: int) -> AnswerLog | None:
    statement = (
        select(AnswerLog)
        .where(AnswerLog.card_id == card_id)
        .order_by(col(AnswerLog.reviewed_at).desc(), col(AnswerLog.id).desc())
    )
    return session.exec(statement).first()


def record_review(
    session: Session,
    *,
    card_id: int,
    mode: str,
    input_method: str,
    answer_text: str,
    response_time_ms: int,
    stt_duration_ms: int | None,
    audio_duration_ms: int | None,
    rating: int,
    is_correct: bool,
    judge_feedback: str,
    judge_model: str,
) -> tuple[AnswerLog, CardState]:
    card = get_card(session, card_id)
    deck = get_deck(session, card.deck_id)
    state = session.get(CardState, card_id)
    if state is None:
        raise NotFoundError(f"Card state {card_id} not found")
    scheduler = get_scheduler(deck.scheduler)
    if state.scheduler != deck.scheduler:
        state.state = scheduler.init_state(utc_now())
    now = utc_now()
    new_state, due = scheduler.review(state.state, rating, now, deck.scheduler_params)
    if state.last_review is None:
        state.introduced_at = now
    state.scheduler = deck.scheduler
    state.state = new_state
    state.due = due
    state.last_review = now
    log = AnswerLog(
        card_id=card_id,
        mode=mode,
        input_method=input_method,
        answer_text=answer_text,
        response_time_ms=response_time_ms,
        stt_duration_ms=stt_duration_ms,
        audio_duration_ms=audio_duration_ms,
        rating=rating,
        is_correct=is_correct,
        judge_feedback=judge_feedback,
        judge_model=judge_model,
        reviewed_at=now,
    )
    session.add(state)
    session.add(log)
    session.commit()
    session.refresh(log)
    session.refresh(state)
    return log, state
