"""Shared history building, used by the HTTP API and the history page."""

from sqlmodel import Session

from app import crud, grading
from app.models import AnswerLog, Card, Deck, User
from app.schemas import HistoryItem, HistoryPage


def build_item(log: AnswerLog, card: Card, deck: Deck) -> HistoryItem:
    scale = grading.normalize(deck.grading_scale)
    return HistoryItem(
        id=log.id or 0,
        card_id=card.id or 0,
        deck_id=deck.id or 0,
        deck_name=deck.name,
        question=card.question,
        answer=card.answer,
        answer_text=log.answer_text,
        input_method=log.input_method,
        mode=log.mode,
        rating=log.rating,
        max_level=scale["max"],
        rating_label=grading.label(scale, log.rating),
        is_correct=log.is_correct,
        judge_feedback=log.judge_feedback,
        judge_model=log.judge_model,
        explanation=log.explanation,
        response_time_ms=log.response_time_ms,
        reviewed_at=log.reviewed_at,
    )


def history_page(
    session: Session,
    user: User,
    deck_id: int | None = None,
    limit: int = 50,
    offset: int = 0,
) -> HistoryPage:
    if deck_id is not None:
        crud.get_deck(session, user, deck_id)
    rows = crud.list_history(session, user, deck_id, limit, offset)
    return HistoryPage(
        total=crud.count_history(session, user, deck_id),
        items=[build_item(log, card, deck) for log, card, deck in rows],
    )


__all__ = ["build_item", "history_page"]
