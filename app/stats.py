from typing import Any, Literal

from sqlalchemy import case, func
from sqlmodel import Session, col, or_, select
from sqlmodel.sql.expression import SelectOfScalar

from app import crud, grading
from app.crud import NotFoundError
from app.models import AnswerLog, Card, CardTag, Deck, Tag, User
from app.schemas import StatsBreakdownItem, StatsBreakdownResponse, StatsResponse


def _visible_tag_ids(user: User) -> SelectOfScalar[int] | SelectOfScalar[None]:
    """Tags the user owns or that sit on cards they can train on."""
    trainable_cards = select(Card.id).where(
        col(Card.deck_id).in_(crud.trainable_deck_ids(crud.uid(user)))
    )
    linked = select(CardTag.tag_id).where(col(CardTag.card_id).in_(trainable_cards))
    return select(Tag.id).where(or_(col(Tag.owner_id) == crud.uid(user), col(Tag.id).in_(linked)))


def _target_ids(
    session: Session, user: User, scope: Literal["deck", "card", "tag"], target: str
) -> list[int]:
    if scope == "tag":
        statement = select(Tag.id).where(col(Tag.id).in_(_visible_tag_ids(user)))
        if target.isdigit():
            statement = statement.where(Tag.id == int(target))
        else:
            statement = statement.where(Tag.name == target)
        ids = [tag_id for tag_id in session.exec(statement).all() if tag_id is not None]
        if not ids:
            raise NotFoundError(f"Tag {target!r} not found")
        return ids
    try:
        target_id = int(target)
    except ValueError as exc:
        raise NotFoundError(f"Invalid {scope} target: {target}") from exc
    if scope == "deck":
        crud.get_deck(session, user, target_id)
    else:
        crud.get_card(session, user, target_id)
    return [target_id]


def get_stats(
    session: Session, user: User, scope: Literal["deck", "card", "tag"], target: str
) -> StatsResponse:
    target_ids = _target_ids(session, user, scope, target)
    filters = [col(AnswerLog.user_id) == crud.uid(user)]
    if scope == "deck":
        filters.append(col(Card.deck_id).in_(target_ids))
    elif scope == "card":
        filters.append(col(Card.id).in_(target_ids))
    else:
        filters.append(
            col(Card.id).in_(select(CardTag.card_id).where(col(CardTag.tag_id).in_(target_ids)))
        )

    statement = (
        select(
            func.count(col(AnswerLog.id)),
            func.coalesce(func.sum(case((col(AnswerLog.is_correct), 1), else_=0)), 0),
            func.avg(col(AnswerLog.response_time_ms)),
        )
        .join(Card, col(AnswerLog.card_id) == col(Card.id))
        .where(*filters)
    )
    mode_statement = (
        select(AnswerLog.mode, func.count(col(AnswerLog.id)))
        .join(Card, col(AnswerLog.card_id) == col(Card.id))
        .where(*filters)
        .group_by(col(AnswerLog.mode))
    )

    total, correct, average = session.exec(statement).one()
    by_mode = {mode: int(count) for mode, count in session.exec(mode_statement).all()}
    total_int = int(total)
    correct_int = int(correct)
    return StatsResponse(
        total=total_int,
        correct=correct_int,
        incorrect=total_int - correct_int,
        correct_rate=correct_int / total_int if total_int else 0.0,
        avg_response_time_ms=float(average) if average is not None else None,
        by_mode=by_mode,
    )


def _merge(
    rows: list[tuple[str, str, dict[str, Any], int, int, float | None]],
) -> list[StatsBreakdownItem]:
    """Combine per-deck rows sharing a key into one weighted item.

    `rows` are `(key, label, scale, total, correct, avg_rating)`. The normalized
    mean is rating/max*10, so decks graded on different scales stay comparable.
    """
    merged: dict[str, dict[str, Any]] = {}
    for key, label, scale, total, correct, average in rows:
        maximum = grading.normalize(scale)["max"]
        bucket = merged.setdefault(
            key, {"label": label, "total": 0, "correct": 0, "rating_sum": 0.0, "norm_sum": 0.0}
        )
        bucket["total"] += total
        bucket["correct"] += correct
        if average is not None:
            bucket["rating_sum"] += float(average) * total
            bucket["norm_sum"] += (float(average) / maximum * 10) * total
    items: list[StatsBreakdownItem] = []
    for key, bucket in merged.items():
        total = int(bucket["total"])
        items.append(
            StatsBreakdownItem(
                key=key,
                label=str(bucket["label"]),
                total=total,
                correct=int(bucket["correct"]),
                correct_rate=int(bucket["correct"]) / total if total else 0.0,
                avg_rating=bucket["rating_sum"] / total if total else None,
                avg_normalized=bucket["norm_sum"] / total if total else None,
            )
        )
    return items


def get_breakdown(
    session: Session,
    user: User,
    group: Literal["card", "tag"],
    deck_id: int | None = None,
) -> StatsBreakdownResponse:
    """Mean rating and correct rate per card or per tag, for one deck or all."""
    if deck_id is not None:
        crud.get_deck(session, user, deck_id)
    base = [col(AnswerLog.user_id) == crud.uid(user)]
    if deck_id is not None:
        base.append(col(Card.deck_id) == deck_id)

    if group == "card":
        statement = (
            select(  # type: ignore[call-overload]
                Card.id,
                Card.question,
                Deck.grading_scale,
                func.count(col(AnswerLog.id)),
                func.coalesce(func.sum(case((col(AnswerLog.is_correct), 1), else_=0)), 0),
                func.avg(col(AnswerLog.rating)),
            )
            .join(Card, col(Card.id) == col(AnswerLog.card_id))
            .join(Deck, col(Deck.id) == col(Card.deck_id))
            .where(*base)
            .group_by(Card.id, Card.question)
            .order_by(Card.id)
        )
        rows = [
            (str(card_id), str(question), scale, int(total), int(correct), average)
            for card_id, question, scale, total, correct, average in session.exec(statement).all()
        ]
    else:
        statement = (
            select(  # type: ignore[call-overload]
                Tag.name,
                Deck.grading_scale,
                func.count(col(AnswerLog.id)),
                func.coalesce(func.sum(case((col(AnswerLog.is_correct), 1), else_=0)), 0),
                func.avg(col(AnswerLog.rating)),
            )
            .join(Card, col(Card.id) == col(AnswerLog.card_id))
            .join(Deck, col(Deck.id) == col(Card.deck_id))
            .join(CardTag, col(CardTag.card_id) == col(Card.id))
            .join(Tag, col(Tag.id) == col(CardTag.tag_id))
            .where(*base)
            .group_by(Tag.name, Card.deck_id)
            .order_by(Tag.name)
        )
        rows = [
            (str(tag), str(tag), scale, int(total), int(correct), average)
            for tag, scale, total, correct, average in session.exec(statement).all()
        ]
    return StatsBreakdownResponse(group=group, items=_merge(rows))
