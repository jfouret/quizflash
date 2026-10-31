"""Teacher explanations shared by the HTTP API and the MCP server."""

from sqlmodel import Session

from app import crud
from app.models import User
from app.teacher.base import Teacher, TeacherError


def explain_card(session: Session, user: User, card_id: int, teacher: Teacher) -> str:
    """Explain a trainable card using its deck and card context and the last answer.

    Raises `crud.NotFoundError` when the card is out of the user's perimeter and
    `TeacherError` when the model call fails; callers map those to their own errors.
    """
    card, deck = crud.get_trainable_card(session, user, card_id)
    settings = crud.get_settings(session, user)
    log = crud.get_last_answer_log(session, user, card_id)
    result = teacher.explain(
        deck_context=deck.context,
        card_context=card.context,
        question=card.question,
        expected_answer=card.answer,
        user_answer=log.answer_text if log else "",
        is_correct=log.is_correct if log else None,
        language=settings.judge_language,
    )
    return result.explanation


__all__ = ["TeacherError", "explain_card"]
