import logging
import secrets
import time
from typing import Annotated, Any

from fastapi import APIRouter, File, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import StreamingResponse

from app import crud, grading
from app.dependencies import CurrentUser, JudgeDep, SessionDep, STTDep, TeacherDep, TTSDep
from app.judge.base import JudgeError
from app.models import Settings
from app.schemas import (
    AnswerRequest,
    AnswerResponse,
    CardRead,
    DueCard,
    ExplainRequest,
    ExplainResponse,
    SpeakTextRequest,
    TranscribeResponse,
)
from app.stt.base import STTError
from app.teacher.base import TeacherError
from app.teacher.service import explain_card
from app.tts.base import TTSError

router = APIRouter(prefix="/api/study", tags=["study"])
logger = logging.getLogger(__name__)
MAX_AUDIO_BYTES = 25 * 1024 * 1024


def _scale(
    session: SessionDep, user: CurrentUser, deck_id: int, cache: dict[int, dict[str, Any]]
) -> dict[str, Any]:
    """Normalized grading scale for a deck, cached within one request."""
    if deck_id not in cache:
        cache[deck_id] = grading.normalize(crud.get_deck(session, user, deck_id).grading_scale)
    return cache[deck_id]


@router.get("/next", response_model=DueCard | None)
def next_card(
    session: SessionDep,
    user: CurrentUser,
    deck_id: Annotated[list[int] | None, Query()] = None,
    tag: Annotated[list[str] | None, Query()] = None,
) -> DueCard | None:
    due = crud.get_due(session, user, deck_id, tags=tag)
    if not due:
        return None
    card, state = due[0]
    return DueCard(
        card=CardRead.model_validate(card),
        due=state.due,
        is_new=state.last_review is None,
        grading_scale=_scale(session, user, card.deck_id, {}),
    )


@router.get("/tags", response_model=list[str])
def study_tags(
    session: SessionDep,
    user: CurrentUser,
    deck_id: Annotated[list[int] | None, Query()] = None,
) -> list[str]:
    """Distinct tag names available in the user's study queue (optionally one or more decks)."""
    return crud.list_study_tags(session, user, deck_id)


@router.get("/due", response_model=dict[str, int])
def due_count(
    session: SessionDep,
    user: CurrentUser,
    deck_id: Annotated[list[int] | None, Query()] = None,
    tag: Annotated[list[str] | None, Query()] = None,
) -> dict[str, int]:
    """How many cards are due under the current deck and tag filters."""
    return {"count": len(crud.get_due(session, user, deck_id, tags=tag))}


@router.get("/batch", response_model=list[DueCard])
def batch_cards(
    session: SessionDep,
    user: CurrentUser,
    size: int = 5,
    deck_id: Annotated[list[int] | None, Query()] = None,
    tag: Annotated[list[str] | None, Query()] = None,
) -> list[DueCard]:
    """Up to `size` due cards, for the batch study flow."""
    size = max(1, min(size, 50))
    due = crud.get_due(session, user, deck_id, tags=tag)[:size]
    cache: dict[int, dict[str, Any]] = {}
    return [
        DueCard(
            card=CardRead.model_validate(card),
            due=state.due,
            is_new=state.last_review is None,
            grading_scale=_scale(session, user, card.deck_id, cache),
        )
        for card, state in due
    ]


@router.post("/transcribe", response_model=TranscribeResponse)
async def transcribe(
    session: SessionDep,
    user: CurrentUser,
    stt: STTDep,
    audio: Annotated[UploadFile, File(...)],
) -> TranscribeResponse:
    if not crud.get_app_settings(session).voice_allowed:
        raise HTTPException(status_code=403, detail="Voice answers are disabled")
    content = await audio.read(MAX_AUDIO_BYTES + 1)
    if not content:
        raise HTTPException(status_code=400, detail="Audio file is empty")
    if len(content) > MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="Audio file exceeds 25 MB")
    try:
        result = stt.transcribe(content, crud.get_settings(session, user).stt_language)
    except STTError as exc:
        logger.warning("Voice transcription attempt failed: %s", exc)
        raise HTTPException(
            status_code=502,
            detail="Speech transcription failed; type the answer instead",
        ) from exc
    return TranscribeResponse(
        text=result.text,
        stt_duration_ms=result.stt_duration_ms,
        audio_duration_ms=result.audio_duration_ms,
    )


@router.post("/explain", response_model=ExplainResponse)
def explain(
    payload: ExplainRequest, session: SessionDep, user: CurrentUser, teacher: TeacherDep
) -> ExplainResponse:
    if not crud.get_app_settings(session).teacher_allowed:
        raise HTTPException(status_code=403, detail="Teacher explanations are disabled")
    try:
        explanation = explain_card(session, user, payload.card_id, teacher, payload.log_id)
    except TeacherError as exc:
        logger.warning("Teacher explanation failed: %s", exc)
        raise HTTPException(
            status_code=502,
            detail="Teacher explanation failed; try again",
        ) from exc
    return ExplainResponse(explanation=explanation, model=teacher.model)


def _check_tts(session: SessionDep, user: CurrentUser) -> Settings:
    """Return effective TTS settings, rejecting when the feature is off."""
    if not crud.get_app_settings(session).tts_allowed:
        raise HTTPException(status_code=403, detail="Text-to-speech is disabled")
    settings = crud.effective_settings(session, user)
    if not settings.tts_enabled:
        raise HTTPException(status_code=403, detail="Text-to-speech is off in your settings")
    return settings


def _speak(text: str, language: str, tts: TTSDep) -> Response:
    try:
        stream = tts.speak_stream(text, language)
    except TTSError as exc:
        logger.warning("TTS request failed: %s", exc)
        raise HTTPException(status_code=502, detail="Speech synthesis failed; try again") from exc
    return StreamingResponse(stream.chunks, media_type=stream.content_type)


def _vocal(text: str, language: str, vocal: bool, teacher: TeacherDep) -> str:
    if not vocal:
        return text
    try:
        return teacher.to_vocal(text, language=language)
    except TeacherError as exc:
        logger.warning("Vocal pass failed: %s", exc)
        raise HTTPException(status_code=502, detail="Vocal rewrite failed; try again") from exc


@router.post("/speak-question")
def speak_question(
    payload: ExplainRequest,
    session: SessionDep,
    user: CurrentUser,
    teacher: TeacherDep,
    tts: TTSDep,
) -> Response:
    card, _ = crud.get_trainable_card(session, user, payload.card_id)
    settings = _check_tts(session, user)
    text = _vocal(card.question, settings.judge_language, settings.question_vocal, teacher)
    return _speak(text, settings.judge_language, tts)


@router.post("/speak-explanation")
def speak_explanation(
    payload: ExplainRequest,
    session: SessionDep,
    user: CurrentUser,
    teacher: TeacherDep,
    tts: TTSDep,
) -> Response:
    # Perimeter first: an outsider must get 404, never a 403 that confirms the ID exists.
    crud.get_trainable_card(session, user, payload.card_id)
    settings = _check_tts(session, user)
    if not crud.get_app_settings(session).teacher_allowed:
        raise HTTPException(status_code=403, detail="Teacher explanations are disabled")
    try:
        explanation = explain_card(session, user, payload.card_id, teacher)
    except TeacherError as exc:
        logger.warning("Teacher explanation failed: %s", exc)
        raise HTTPException(
            status_code=502,
            detail="Teacher explanation failed; try again",
        ) from exc
    text = _vocal(explanation, settings.judge_language, settings.teacher_vocal, teacher)
    return _speak(text, settings.judge_language, tts)


@router.post("/speak")
def speak_text(
    payload: SpeakTextRequest,
    session: SessionDep,
    user: CurrentUser,
    teacher: TeacherDep,
    tts: TTSDep,
) -> Response:
    """Synthesize arbitrary text, so a prefetched explanation is not re-generated."""
    settings = _check_tts(session, user)
    text = _vocal(payload.text, settings.judge_language, payload.vocal, teacher)
    return _speak(text, settings.judge_language, tts)


def _record_answer(
    session: SessionDep,
    user: CurrentUser,
    payload: AnswerRequest,
    *,
    mode: str,
    rating: int,
    is_correct: bool,
    feedback: str,
    judge_model: str,
) -> AnswerResponse:
    log, state = crud.record_review(
        session,
        user,
        card_id=payload.card_id,
        mode=mode,
        input_method=payload.input_method,
        answer_text=payload.answer_text,
        response_time_ms=payload.response_time_ms,
        stt_duration_ms=payload.stt_duration_ms,
        audio_duration_ms=payload.audio_duration_ms,
        rating=rating,
        is_correct=is_correct,
        judge_feedback=feedback,
        judge_model=judge_model,
    )
    return AnswerResponse(
        status="reviewed",
        mode=mode,
        rating=rating,
        is_correct=is_correct,
        feedback=feedback,
        judge_model=judge_model,
        due=state.due,
        log_id=log.id,
    )


def _record_self_fallback(
    request: Request, payload: AnswerRequest, session: SessionDep, user: CurrentUser
) -> AnswerResponse:
    """Save a manual rating after a judge failure, guarded by a one-use token."""
    tokens: dict[str, tuple[int, int, float]] = request.app.state.fallback_tokens
    token = payload.fallback_token or ""
    token_user_id, token_card_id, expires = tokens.get(token, (0, 0, 0.0))
    if token_user_id != user.id or token_card_id != payload.card_id or expires < time.monotonic():
        raise HTTPException(
            status_code=400,
            detail="Self fallback requires a recent AI judge failure",
        )
    if payload.rating is None or payload.is_correct is None:
        raise HTTPException(
            status_code=400,
            detail="Fallback requires both rating and is_correct",
        )
    feedback = "AI judge failed; manual self-assessment fallback used."
    if payload.judge_feedback:
        feedback += f" {payload.judge_feedback}"
    response = _record_answer(
        session,
        user,
        payload,
        mode="self_fallback",
        rating=payload.rating,
        is_correct=payload.is_correct,
        feedback=feedback,
        judge_model=payload.judge_model,
    )
    tokens.pop(token, None)
    return response


@router.post("/answer", response_model=AnswerResponse)
def answer(
    request: Request,
    payload: AnswerRequest,
    session: SessionDep,
    user: CurrentUser,
    judge: JudgeDep,
) -> AnswerResponse:
    card, deck = crud.get_trainable_card(session, user, payload.card_id)
    settings = crud.get_settings(session, user)
    mode = deck.eval_mode or settings.eval_mode
    scale = grading.normalize(deck.grading_scale)

    if payload.rating is not None and payload.rating > scale["max"]:
        raise HTTPException(
            status_code=400,
            detail=f"Rating must be between 0 and {scale['max']} for this deck",
        )

    if payload.self_fallback:
        return _record_self_fallback(request, payload, session, user)

    if payload.confirmed:
        if payload.rating is None or payload.is_correct is None:
            raise HTTPException(
                status_code=400,
                detail="Confirmation requires both rating and is_correct",
            )
        return _record_answer(
            session,
            user,
            payload,
            mode=mode,
            rating=payload.rating,
            is_correct=payload.is_correct,
            feedback=payload.judge_feedback,
            judge_model=payload.judge_model or judge.model,
        )

    try:
        result = judge.evaluate(
            question=card.question,
            expected_answer=card.answer,
            user_answer=payload.answer_text,
            expected_time_s=card.expected_time_s,
            response_time_ms=payload.response_time_ms,
            language=settings.judge_language,
            max_level=scale["max"],
            labels=scale["labels"],
        )
    except JudgeError as exc:
        logger.warning("Judge failed; requiring self-assessment fallback: %s", exc)
        issued_tokens: dict[str, tuple[int, int, float]] = request.app.state.fallback_tokens
        now = time.monotonic()
        for expired_token, (_, _, expires) in list(issued_tokens.items()):
            if expires < now:
                issued_tokens.pop(expired_token, None)
        token = secrets.token_urlsafe(24)
        issued_tokens[token] = (crud.uid(user), payload.card_id, now + 600)
        return AnswerResponse(
            status="fallback_required",
            mode="self_fallback",
            feedback=f"AI judge unavailable: {exc}. Select a manual rating.",
            fallback_token=token,
        )

    if mode == "ai_preselect" or payload.preview:
        return AnswerResponse(
            status="pending",
            mode=mode,
            rating=result.rating,
            is_correct=result.is_correct,
            feedback=result.feedback,
            judge_model=judge.model,
        )
    return _record_answer(
        session,
        user,
        payload,
        mode=mode,
        rating=result.rating,
        is_correct=result.is_correct,
        feedback=result.feedback,
        judge_model=judge.model,
    )
