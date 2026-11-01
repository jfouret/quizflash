"""Teacher explanations shared by the HTTP API and the MCP server."""

from sqlmodel import Session

from app import crud, grading
from app.models import User
from app.teacher.base import Teacher, TeacherError


def explain_card(
    session: Session,
    user: User,
    card_id: int,
    teacher: Teacher,
    log_id: int | None = None,
) -> str:
    """Explain a trainable card using its deck and card context and the last answer.

    When `log_id` is given and names one of the caller's answers on this card, the
    explanation is stored with that answer for the history view.

    Raises `crud.NotFoundError` when the card is out of the user's perimeter and
    `TeacherError` when the model call fails; callers map those to their own errors.
    """
    card, deck = crud.get_trainable_card(session, user, card_id)
    settings = crud.get_settings(session, user)
    log = crud.get_last_answer_log(session, user, card_id)
    scale = grading.normalize(deck.grading_scale)
    rating = log.rating if log else None
    result = teacher.explain(
        deck_context=deck.context,
        card_context=card.context,
        question=card.question,
        expected_answer=card.answer,
        user_answer=log.answer_text if log else "",
        is_correct=log.is_correct if log else None,
        rating=rating,
        max_level=scale["max"],
        rating_label=grading.label(scale, rating) if rating is not None else "",
        language=settings.judge_language,
    )
    if log_id is not None and log is not None and log.id == log_id:
        crud.save_explanation(session, log, result.explanation)
    return result.explanation


__all__ = ["TeacherError", "explain_card"]
