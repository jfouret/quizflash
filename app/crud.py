from datetime import datetime

from sqlalchemy import func, or_
from sqlmodel import Session, col, delete, select
from sqlmodel.sql.expression import SelectOfScalar

from app.models import (
    AnswerLog,
    ApiToken,
    AppSettings,
    AuthSession,
    Card,
    CardState,
    CardTag,
    Deck,
    DeckFollow,
    Settings,
    Tag,
    User,
    utc_now,
)
from app.schemas import (
    AppSettingsUpdate,
    CardCreate,
    CardUpdate,
    DeckCreate,
    DeckUpdate,
    SettingsUpdate,
)
from app.srs import get_scheduler


class NotFoundError(LookupError):
    pass


class PermissionDeniedError(PermissionError):
    pass


def uid(user: User) -> int:
    if user.id is None:
        raise ValueError("User has no ID")
    return user.id


# --- Perimeter ----------------------------------------------------------------
# Every deck access goes through these helpers. Private decks of other users are
# reported as missing (404) so IDs cannot be probed.


def trainable_deck_ids(user_id: int) -> SelectOfScalar[int] | SelectOfScalar[None]:
    """Decks the user owns, plus public decks they follow."""
    followed = (
        select(DeckFollow.deck_id)
        .join(Deck, col(Deck.id) == col(DeckFollow.deck_id))
        .where(DeckFollow.user_id == user_id, Deck.visibility == "public")
    )
    return select(Deck.id).where(
        or_(col(Deck.owner_id) == user_id, col(Deck.id).in_(followed))
    )


def get_deck(session: Session, user: User, deck_id: int) -> Deck:
    """Readable deck: owned or public."""
    deck = session.get(Deck, deck_id)
    if deck is None or (deck.owner_id != uid(user) and deck.visibility != "public"):
        raise NotFoundError(f"Deck {deck_id} not found")
    return deck


def _writable_deck(session: Session, user: User, deck_id: int) -> Deck:
    deck = get_deck(session, user, deck_id)
    if deck.owner_id != uid(user):
        raise PermissionDeniedError("Only the deck owner can modify it")
    return deck


def is_following(session: Session, user: User, deck_id: int) -> bool:
    return session.get(DeckFollow, (uid(user), deck_id)) is not None


def _trainable_deck(session: Session, user: User, deck_id: int) -> Deck:
    deck = get_deck(session, user, deck_id)
    if deck.owner_id != uid(user) and not is_following(session, user, deck_id):
        raise PermissionDeniedError("Follow this deck to train on it")
    return deck


# --- Decks --------------------------------------------------------------------


def list_decks(session: Session, user: User) -> list[Deck]:
    statement = (
        select(Deck)
        .where(col(Deck.id).in_(trainable_deck_ids(uid(user))))
        .order_by(col(Deck.id))
    )
    return list(session.exec(statement).all())


def deck_overview(session: Session, user: User) -> dict[int, tuple[int, int]]:
    """Card and due counts per trainable deck, for the deck list."""
    counts = session.exec(
        select(Card.deck_id, func.count(col(Card.id)))
        .where(col(Card.deck_id).in_(trainable_deck_ids(uid(user))))
        .group_by(col(Card.deck_id))
    ).all()
    due: dict[int, int] = {}
    for card, _ in get_due(session, user):
        due[card.deck_id] = due.get(card.deck_id, 0) + 1
    return {deck_id: (int(total), due.get(deck_id, 0)) for deck_id, total in counts}


def _check_visibility(session: Session, visibility: str | None) -> None:
    if visibility == "public" and not get_app_settings(session).allow_public_decks:
        raise PermissionDeniedError("Public decks are disabled by the administrator")


def create_deck(session: Session, user: User, data: DeckCreate) -> Deck:
    _check_visibility(session, data.visibility)
    deck = Deck(**data.model_dump(), owner_id=uid(user))
    session.add(deck)
    session.commit()
    session.refresh(deck)
    return deck


def update_deck(session: Session, user: User, deck_id: int, data: DeckUpdate) -> Deck:
    deck = _writable_deck(session, user, deck_id)
    values = data.model_dump(exclude_unset=True)
    for field in ("name", "description", "context", "scheduler", "scheduler_params", "visibility"):
        if field in values and values[field] is None:
            raise ValueError(f"{field} cannot be null")
    _check_visibility(session, values.get("visibility"))
    for key, value in values.items():
        setattr(deck, key, value)
    session.add(deck)
    session.commit()
    session.refresh(deck)
    return deck


def _delete_card(session: Session, card: Card) -> None:
    if card.id is None:
        raise ValueError("Card has no ID")
    # Every learner's state and logs go with the card.
    session.exec(delete(AnswerLog).where(col(AnswerLog.card_id) == card.id))
    session.exec(delete(CardTag).where(col(CardTag.card_id) == card.id))
    session.exec(delete(CardState).where(col(CardState.card_id) == card.id))
    session.flush()
    session.delete(card)


def _delete_deck(session: Session, deck: Deck) -> None:
    for card in list(session.exec(select(Card).where(Card.deck_id == deck.id)).all()):
        _delete_card(session, card)
    session.exec(delete(DeckFollow).where(col(DeckFollow.deck_id) == deck.id))
    session.flush()
    session.delete(deck)


def delete_deck(session: Session, user: User, deck_id: int) -> None:
    _delete_deck(session, _writable_deck(session, user, deck_id))
    session.commit()


# --- Public space -------------------------------------------------------------


def list_public_decks(session: Session) -> list[tuple[Deck, str, int]]:
    card_count = (
        select(func.count(col(Card.id)))
        .where(col(Card.deck_id) == col(Deck.id))
        .scalar_subquery()
    )
    statement = (
        select(Deck, User.display_name, card_count)
        .join(User, col(User.id) == col(Deck.owner_id))
        .where(Deck.visibility == "public")
        .order_by(col(Deck.id))
    )
    return [(deck, name, int(count)) for deck, name, count in session.exec(statement).all()]


def follow_deck(session: Session, user: User, deck_id: int) -> Deck:
    deck = get_deck(session, user, deck_id)
    if deck.owner_id == uid(user):
        raise ValueError("You already own this deck")
    if not is_following(session, user, deck_id):
        session.add(DeckFollow(user_id=uid(user), deck_id=deck_id))
        session.commit()
    return deck


def unfollow_deck(session: Session, user: User, deck_id: int) -> None:
    follow = session.get(DeckFollow, (uid(user), deck_id))
    if follow is None:
        raise NotFoundError(f"Deck {deck_id} is not followed")
    # Progress rows stay so a later re-follow resumes the schedule.
    session.delete(follow)
    session.commit()


def copy_deck(session: Session, user: User, deck_id: int) -> Deck:
    source = get_deck(session, user, deck_id)
    copy = Deck(
        owner_id=uid(user),
        name=source.name,
        description=source.description,
        context=source.context,
        scheduler=source.scheduler,
        scheduler_params=dict(source.scheduler_params),
        eval_mode=source.eval_mode,
        visibility="private",
        source_deck_id=source.id,
    )
    session.add(copy)
    session.flush()
    if copy.id is None:
        raise RuntimeError("Deck ID was not generated")
    for card in session.exec(select(Card).where(Card.deck_id == deck_id).order_by(col(Card.id))):
        _add_card(
            session,
            user,
            copy,
            CardCreate(
                deck_id=copy.id,
                question=card.question,
                answer=card.answer,
                details=card.details,
                context=card.context,
                expected_time_s=card.expected_time_s,
                tags=[tag.name for tag in card.tags],
            ),
        )
    session.commit()
    session.refresh(copy)
    return copy


# --- Cards and tags -----------------------------------------------------------


def _tags_by_name(session: Session, owner_id: int, names: list[str]) -> list[Tag]:
    tags: list[Tag] = []
    for raw_name in dict.fromkeys(names):
        name = raw_name.strip()
        if not name:
            raise ValueError("Tag names cannot be empty")
        tag = session.exec(select(Tag).where(Tag.owner_id == owner_id, Tag.name == name)).first()
        if tag is None:
            tag = Tag(owner_id=owner_id, name=name)
            session.add(tag)
            session.flush()
        tags.append(tag)
    return tags


def list_cards(
    session: Session, user: User, deck_id: int | None = None, tag: str | None = None
) -> list[Card]:
    statement = select(Card).order_by(col(Card.id))
    if deck_id is not None:
        get_deck(session, user, deck_id)
        statement = statement.where(Card.deck_id == deck_id)
    else:
        statement = statement.where(col(Card.deck_id).in_(trainable_deck_ids(uid(user))))
    if tag is not None:
        statement = statement.join(CardTag).join(Tag).where(Tag.name == tag)
    return list(session.exec(statement).all())


def get_card(session: Session, user: User, card_id: int) -> Card:
    card = session.get(Card, card_id)
    if card is None:
        raise NotFoundError(f"Card {card_id} not found")
    try:
        get_deck(session, user, card.deck_id)
    except NotFoundError:
        raise NotFoundError(f"Card {card_id} not found") from None
    return card


def _writable_card(session: Session, user: User, card_id: int) -> Card:
    card = get_card(session, user, card_id)
    _writable_deck(session, user, card.deck_id)
    return card


def _new_state(user_id: int, card_id: int, scheduler_name: str) -> CardState:
    now = utc_now()
    return CardState(
        user_id=user_id,
        card_id=card_id,
        scheduler=scheduler_name,
        state=get_scheduler(scheduler_name).init_state(now),
        due=now,
        introduced_at=now,
    )


def _add_card(session: Session, user: User, deck: Deck, data: CardCreate) -> Card:
    card = Card(**data.model_dump(exclude={"tags"}))
    card.tags = _tags_by_name(session, uid(user), data.tags)
    session.add(card)
    session.flush()
    if card.id is None:
        raise RuntimeError("Card ID was not generated")
    session.add(_new_state(uid(user), card.id, deck.scheduler))
    return card


def create_card(session: Session, user: User, data: CardCreate) -> Card:
    deck = _writable_deck(session, user, data.deck_id)
    card = _add_card(session, user, deck, data)
    session.commit()
    session.refresh(card)
    return card


def update_card(session: Session, user: User, card_id: int, data: CardUpdate) -> Card:
    card = _writable_card(session, user, card_id)
    values = data.model_dump(exclude_unset=True)
    for field in ("deck_id", "question", "answer", "details", "context"):
        if field in values and values[field] is None:
            raise ValueError(f"{field} cannot be null")
    if "deck_id" in values:
        _writable_deck(session, user, values["deck_id"])
    if "tags" in values:
        raw_tags = values.pop("tags")
        if raw_tags is None:
            raise ValueError("tags cannot be null")
        card.tags = _tags_by_name(session, uid(user), raw_tags)
    for key, value in values.items():
        setattr(card, key, value)
    session.add(card)
    session.commit()
    session.refresh(card)
    return card


def delete_card(session: Session, user: User, card_id: int) -> None:
    _delete_card(session, _writable_card(session, user, card_id))
    session.commit()


def list_tags(session: Session, user: User) -> list[Tag]:
    statement = select(Tag).where(Tag.owner_id == uid(user)).order_by(col(Tag.name))
    return list(session.exec(statement).all())


def delete_tag(session: Session, user: User, tag_id: int) -> None:
    tag = session.get(Tag, tag_id)
    if tag is None or tag.owner_id != uid(user):
        raise NotFoundError(f"Tag {tag_id} not found")
    session.exec(delete(CardTag).where(col(CardTag.tag_id) == tag_id))
    session.delete(tag)
    session.commit()


# --- Settings -----------------------------------------------------------------


def get_app_settings(session: Session) -> AppSettings:
    app_settings = session.get(AppSettings, 1)
    if app_settings is None:
        app_settings = AppSettings()
        session.add(app_settings)
        session.commit()
        session.refresh(app_settings)
    return app_settings


def update_app_settings(session: Session, data: AppSettingsUpdate) -> AppSettings:
    app_settings = get_app_settings(session)
    values = data.model_dump(exclude_unset=True)
    for field in ("registration", "allow_public_decks", "teacher_allowed", "voice_allowed"):
        if field in values and values[field] is None:
            raise ValueError(f"{field} cannot be null")
    if "default_settings" in values:
        defaults = data.default_settings
        values["default_settings"] = (
            defaults.model_dump(exclude_none=True) if defaults is not None else {}
        )
    for key, value in values.items():
        setattr(app_settings, key, value)
    session.add(app_settings)
    session.commit()
    session.refresh(app_settings)
    return app_settings


def get_settings(session: Session, user: User) -> Settings:
    settings = session.get(Settings, uid(user))
    if settings is None:
        defaults = SettingsUpdate.model_validate(get_app_settings(session).default_settings)
        settings = Settings(user_id=uid(user), **defaults.model_dump(exclude_none=True))
        session.add(settings)
        session.commit()
        session.refresh(settings)
    return settings


def effective_settings(session: Session, user: User) -> Settings:
    """User settings with admin-level switches applied (not persisted)."""
    settings = get_settings(session, user)
    effective = Settings.model_validate(settings.model_dump())
    if not get_app_settings(session).teacher_allowed:
        effective.teacher_enabled = False
    return effective


def update_settings(session: Session, user: User, data: SettingsUpdate) -> Settings:
    settings = get_settings(session, user)
    values = data.model_dump(exclude_unset=True)
    fields = (
        "eval_mode",
        "judge_language",
        "stt_language",
        "voice_auto_judge",
        "auto_confirm",
        "teacher_enabled",
        "daily_new_limit",
        "daily_review_limit",
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


# --- Study --------------------------------------------------------------------


def _ensure_states(session: Session, user_id: int) -> None:
    """Followed decks get scheduling state lazily, on first queue lookup."""
    missing = (
        select(Card.id, Deck.scheduler)
        .join(Deck, col(Deck.id) == col(Card.deck_id))
        .where(col(Card.deck_id).in_(trainable_deck_ids(user_id)))
        .where(
            ~select(CardState.card_id)
            .where(CardState.user_id == user_id, col(CardState.card_id) == col(Card.id))
            .exists()
        )
    )
    rows = list(session.exec(missing).all())
    for card_id, scheduler_name in rows:
        if card_id is not None:
            session.add(_new_state(user_id, card_id, scheduler_name))
    if rows:
        session.commit()


def _daily_usage(session: Session, user_id: int, now: datetime) -> tuple[int, int]:
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    new_count = session.exec(
        select(func.count(col(CardState.card_id))).where(
            CardState.user_id == user_id,
            col(CardState.introduced_at) >= start,
            col(CardState.last_review).is_not(None),
        )
    ).one()
    review_count = session.exec(
        select(func.count(col(AnswerLog.id)))
        .join(
            CardState,
            (col(AnswerLog.card_id) == col(CardState.card_id))
            & (col(AnswerLog.user_id) == col(CardState.user_id)),
        )
        .where(
            AnswerLog.user_id == user_id,
            col(AnswerLog.reviewed_at) >= start,
            col(AnswerLog.reviewed_at) != col(CardState.introduced_at),
        )
    ).one()
    return int(new_count), int(review_count)


def get_due(
    session: Session, user: User, deck_id: int | None = None, now: datetime | None = None
) -> list[tuple[Card, CardState]]:
    user_id = uid(user)
    _ensure_states(session, user_id)
    current = now or utc_now()
    statement = (
        select(Card, CardState)
        .join(CardState, col(Card.id) == col(CardState.card_id))
        .where(CardState.user_id == user_id)
        .where(col(Card.deck_id).in_(trainable_deck_ids(user_id)))
        .where(col(CardState.due) <= current)
        .order_by(col(CardState.due), col(Card.id))
    )
    if deck_id is not None:
        _trainable_deck(session, user, deck_id)
        statement = statement.where(Card.deck_id == deck_id)
    rows = list(session.exec(statement).all())
    settings = get_settings(session, user)
    new_used, review_used = _daily_usage(session, user_id, current)
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


def get_trainable_card(session: Session, user: User, card_id: int) -> tuple[Card, Deck]:
    card = get_card(session, user, card_id)
    return card, _trainable_deck(session, user, card.deck_id)


def get_last_answer_log(session: Session, user: User, card_id: int) -> AnswerLog | None:
    statement = (
        select(AnswerLog)
        .where(AnswerLog.card_id == card_id, AnswerLog.user_id == uid(user))
        .order_by(col(AnswerLog.reviewed_at).desc(), col(AnswerLog.id).desc())
    )
    return session.exec(statement).first()


def record_review(
    session: Session,
    user: User,
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
    user_id = uid(user)
    _, deck = get_trainable_card(session, user, card_id)
    state = session.get(CardState, (user_id, card_id)) or _new_state(
        user_id, card_id, deck.scheduler
    )
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
        user_id=user_id,
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


# --- Users (admin) ------------------------------------------------------------


def list_users(session: Session) -> list[User]:
    return list(session.exec(select(User).order_by(col(User.id))).all())


def get_user(session: Session, user_id: int) -> User:
    user = session.get(User, user_id)
    if user is None:
        raise NotFoundError(f"User {user_id} not found")
    return user


def revoke_sessions(session: Session, user_id: int) -> None:
    session.exec(delete(AuthSession).where(col(AuthSession.user_id) == user_id))


def _active_admin_count(session: Session) -> int:
    return int(
        session.exec(
            select(func.count(col(User.id))).where(User.role == "admin", User.status == "active")
        ).one()
    )


def admin_update_user(
    session: Session,
    admin: User,
    user_id: int,
    *,
    status: str | None = None,
    role: str | None = None,
    oidc_enabled: bool = False,
) -> User:
    target = get_user(session, user_id)
    if target.id == admin.id:
        raise PermissionDeniedError("Administrators cannot change their own account")
    if role is not None and oidc_enabled:
        raise PermissionDeniedError("Roles are managed by the identity provider")
    removes_admin = target.role == "admin" and target.status == "active" and (
        (status is not None and status != "active") or role == "user"
    )
    if removes_admin and _active_admin_count(session) <= 1:
        raise PermissionDeniedError("Cannot remove the last active administrator")
    if status is not None:
        target.status = status
    if role is not None:
        target.role = role
    if (status is not None and status != "active") or role is not None:
        revoke_sessions(session, user_id)
    session.add(target)
    session.commit()
    session.refresh(target)
    return target


def delete_user(session: Session, admin: User, user_id: int) -> None:
    target = get_user(session, user_id)
    if target.id == admin.id:
        raise PermissionDeniedError("Administrators cannot delete their own account")
    if target.role == "admin" and target.status == "active" and _active_admin_count(session) <= 1:
        raise PermissionDeniedError("Cannot remove the last active administrator")
    for deck in list(session.exec(select(Deck).where(Deck.owner_id == user_id)).all()):
        _delete_deck(session, deck)
    session.exec(delete(AnswerLog).where(col(AnswerLog.user_id) == user_id))
    session.exec(delete(CardState).where(col(CardState.user_id) == user_id))
    session.exec(delete(DeckFollow).where(col(DeckFollow.user_id) == user_id))
    session.exec(delete(AuthSession).where(col(AuthSession.user_id) == user_id))
    session.exec(delete(ApiToken).where(col(ApiToken.user_id) == user_id))
    session.exec(delete(Settings).where(col(Settings.user_id) == user_id))
    session.exec(delete(Tag).where(col(Tag.owner_id) == user_id))
    session.flush()
    session.delete(target)
    session.commit()


def unpublish_deck(session: Session, deck_id: int) -> Deck:
    deck = session.get(Deck, deck_id)
    if deck is None or deck.visibility != "public":
        raise NotFoundError(f"Public deck {deck_id} not found")
    deck.visibility = "private"
    session.add(deck)
    session.commit()
    session.refresh(deck)
    return deck
