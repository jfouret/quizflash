from typing import Literal

from sqlalchemy import case, func
from sqlmodel import Session, col, or_, select
from sqlmodel.sql.expression import SelectOfScalar

from app import crud
from app.crud import NotFoundError
from app.models import AnswerLog, Card, CardTag, Tag, User
from app.schemas import StatsResponse


def _visible_tag_ids(user: User) -> SelectOfScalar[int] | SelectOfScalar[None]:
    """Tags the user owns or that sit on cards they can train on."""
    trainable_cards = select(Card.id).where(
        col(Card.deck_id).in_(crud.trainable_deck_ids(crud.uid(user)))
    )
    linked = select(CardTag.tag_id).where(col(CardTag.card_id).in_(trainable_cards))
    return select(Tag.id).where(
        or_(col(Tag.owner_id) == crud.uid(user), col(Tag.id).in_(linked))
    )


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
            col(Card.id).in_(
                select(CardTag.card_id).where(col(CardTag.tag_id).in_(target_ids))
            )
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
