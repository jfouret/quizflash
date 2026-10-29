from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from app import crud
from app.dependencies import SessionDep
from app.schemas import CardCreate, DeckCreate, SettingsUpdate

router = APIRouter(include_in_schema=False)
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))
EvalModeForm = Literal["ai_preselect", "ai_assess"]
SchedulerForm = Literal["fsrs", "sm2"]


@router.get("/", response_class=HTMLResponse)
def index(request: Request, session: SessionDep) -> Response:
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"decks": crud.list_decks(session)},
    )


@router.post("/decks")
def create_deck_form(
    session: SessionDep,
    name: Annotated[str, Form()],
    description: Annotated[str, Form()] = "",
    scheduler: Annotated[SchedulerForm, Form()] = "fsrs",
) -> RedirectResponse:
    crud.create_deck(
        session,
        DeckCreate(name=name, description=description, scheduler=scheduler),
    )
    return RedirectResponse("/", status_code=303)


@router.get("/decks/{deck_id}", response_class=HTMLResponse)
def deck_detail(request: Request, deck_id: int, session: SessionDep) -> Response:
    return templates.TemplateResponse(
        request=request,
        name="deck_detail.html",
        context={
            "deck": crud.get_deck(session, deck_id),
            "cards": crud.list_cards(session, deck_id),
        },
    )


@router.post("/decks/{deck_id}/delete")
def delete_deck_form(deck_id: int, session: SessionDep) -> RedirectResponse:
    crud.delete_deck(session, deck_id)
    return RedirectResponse("/", status_code=303)


@router.post("/decks/{deck_id}/cards")
def create_card_form(
    deck_id: int,
    session: SessionDep,
    question: Annotated[str, Form()],
    answer: Annotated[str, Form()],
    details: Annotated[str, Form()] = "",
    expected_time_s: Annotated[str, Form()] = "",
    tags: Annotated[str, Form()] = "",
) -> RedirectResponse:
    crud.create_card(
        session,
        CardCreate(
            deck_id=deck_id,
            question=question,
            answer=answer,
            details=details,
            expected_time_s=int(expected_time_s) if expected_time_s.strip() else None,
            tags=[tag.strip() for tag in tags.split(",") if tag.strip()],
        ),
    )
    return RedirectResponse(f"/decks/{deck_id}", status_code=303)


@router.post("/cards/{card_id}/delete")
def delete_card_form(
    card_id: int,
    session: SessionDep,
    deck_id: Annotated[int, Form()],
) -> RedirectResponse:
    crud.delete_card(session, card_id)
    return RedirectResponse(f"/decks/{deck_id}", status_code=303)


@router.get("/study", response_class=HTMLResponse)
def study_page(
    request: Request, session: SessionDep, deck_id: int | None = None
) -> Response:
    return templates.TemplateResponse(
        request=request,
        name="study.html",
        context={
            "decks": crud.list_decks(session),
            "deck_id": deck_id,
            "settings": crud.get_settings(session),
            "due_count": len(crud.get_due(session, deck_id)),
        },
    )


@router.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request, session: SessionDep) -> Response:
    return templates.TemplateResponse(
        request=request,
        name="settings.html",
        context={"settings": crud.get_settings(session)},
    )


@router.post("/settings")
def update_settings_form(
    session: SessionDep,
    eval_mode: Annotated[EvalModeForm, Form()],
    judge_language: Annotated[str, Form()],
    stt_language: Annotated[str, Form()],
    daily_new_limit: Annotated[int, Form()],
    daily_review_limit: Annotated[int, Form()],
    voice_auto_judge: Annotated[bool, Form()] = False,
    auto_confirm: Annotated[bool, Form()] = False,
) -> RedirectResponse:
    crud.update_settings(
        session,
        SettingsUpdate(
            eval_mode=eval_mode,
            judge_language=judge_language,
            stt_language=stt_language,
            voice_auto_judge=voice_auto_judge,
            auto_confirm=auto_confirm,
            daily_new_limit=daily_new_limit,
            daily_review_limit=daily_review_limit,
        ),
    )
    return RedirectResponse("/settings", status_code=303)
