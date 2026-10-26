from typing import Literal

from sqlalchemy import case, func
from sqlmodel import Session, col, select

from app.crud import NotFoundError
from app.models import AnswerLog, Card, CardTag, Deck, Tag
from app.schemas import StatsResponse


def _target_id(
    session: Session, scope: Literal["deck", "card", "tag"], target: str
) -> int:
    if scope == "tag" and not target.isdigit():
        tag = session.exec(select(Tag).where(Tag.name == target)).first()
        if tag is None or tag.id is None:
            raise NotFoundError(f"Tag {target!r} not found")
        return tag.id
    try:
        target_id = int(target)
    except ValueError as exc:
        raise NotFoundError(f"Invalid {scope} target: {target}") from exc
    model = Deck if scope == "deck" else Card if scope == "card" else Tag
    if session.get(model, target_id) is None:
        raise NotFoundError(f"{scope.title()} {target_id} not found")
    return target_id


def get_stats(
    session: Session, scope: Literal["deck", "card", "tag"], target: str
) -> StatsResponse:
    target_id = _target_id(session, scope, target)
    filters = []
    if scope == "deck":
        filters.append(Card.deck_id == target_id)
    elif scope == "card":
        filters.append(Card.id == target_id)

    statement = select(
        func.count(col(AnswerLog.id)),
        func.coalesce(func.sum(case((col(AnswerLog.is_correct), 1), else_=0)), 0),
        func.avg(col(AnswerLog.response_time_ms)),
    ).join(Card, col(AnswerLog.card_id) == col(Card.id))
    mode_statement = (
        select(AnswerLog.mode, func.count(col(AnswerLog.id)))
        .join(Card, col(AnswerLog.card_id) == col(Card.id))
        .group_by(col(AnswerLog.mode))
    )
    if scope == "tag":
        statement = statement.join(CardTag, col(Card.id) == col(CardTag.card_id)).where(
            col(CardTag.tag_id) == target_id
        )
        mode_statement = mode_statement.join(
            CardTag, col(Card.id) == col(CardTag.card_id)
        ).where(col(CardTag.tag_id) == target_id)
    statement = statement.where(*filters)
    mode_statement = mode_statement.where(*filters)

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
