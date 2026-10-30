from typing import Annotated, Literal

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from app import auth, crud
from app.dependencies import AdminUser, AuthConfigDep, CurrentUser, SessionDep
from app.schemas import (
    AppSettingsUpdate,
    CardCreate,
    DeckCreate,
    DeckUpdate,
    Registration,
    SettingsUpdate,
)
from app.templating import templates

router = APIRouter(include_in_schema=False)
EvalModeForm = Literal["ai_preselect", "ai_assess"]
SchedulerForm = Literal["fsrs", "sm2"]
VisibilityForm = Literal["private", "public"]
UserAction = Literal["approve", "suspend", "reactivate", "promote", "demote", "delete"]


@router.get("/", response_class=HTMLResponse)
def index(request: Request, session: SessionDep, user: CurrentUser) -> Response:
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "decks": crud.list_decks(session, user),
            "overview": crud.deck_overview(session, user),
        },
    )


@router.post("/decks")
def create_deck_form(
    session: SessionDep,
    user: CurrentUser,
    name: Annotated[str, Form()],
    description: Annotated[str, Form()] = "",
    context: Annotated[str, Form()] = "",
    scheduler: Annotated[SchedulerForm, Form()] = "fsrs",
) -> RedirectResponse:
    crud.create_deck(
        session,
        user,
        DeckCreate(name=name, description=description, context=context, scheduler=scheduler),
    )
    return RedirectResponse("/?notice=deck-created", status_code=303)


@router.get("/decks/{deck_id}", response_class=HTMLResponse)
def deck_detail(request: Request, deck_id: int, session: SessionDep, user: CurrentUser) -> Response:
    deck = crud.get_deck(session, user, deck_id)
    return templates.TemplateResponse(
        request=request,
        name="deck_detail.html",
        context={
            "deck": deck,
            "cards": crud.list_cards(session, user, deck_id),
            "is_owner": deck.owner_id == user.id,
            "following": crud.is_following(session, user, deck_id),
            "allow_public": crud.get_app_settings(session).allow_public_decks,
        },
    )


@router.post("/decks/{deck_id}/update")
def update_deck_form(
    deck_id: int,
    session: SessionDep,
    user: CurrentUser,
    description: Annotated[str, Form()] = "",
    context: Annotated[str, Form()] = "",
    visibility: Annotated[VisibilityForm | None, Form()] = None,
) -> RedirectResponse:
    data = DeckUpdate(description=description, context=context)
    if visibility is not None:
        data.visibility = visibility
    crud.update_deck(session, user, deck_id, data)
    return RedirectResponse(f"/decks/{deck_id}?notice=deck-saved", status_code=303)


@router.post("/decks/{deck_id}/delete")
def delete_deck_form(deck_id: int, session: SessionDep, user: CurrentUser) -> RedirectResponse:
    crud.delete_deck(session, user, deck_id)
    return RedirectResponse("/?notice=deck-deleted", status_code=303)


@router.post("/decks/{deck_id}/follow")
def follow_deck_form(deck_id: int, session: SessionDep, user: CurrentUser) -> RedirectResponse:
    crud.follow_deck(session, user, deck_id)
    return RedirectResponse(f"/decks/{deck_id}?notice=deck-followed", status_code=303)


@router.post("/decks/{deck_id}/unfollow")
def unfollow_deck_form(deck_id: int, session: SessionDep, user: CurrentUser) -> RedirectResponse:
    crud.unfollow_deck(session, user, deck_id)
    return RedirectResponse("/explore?notice=deck-unfollowed", status_code=303)


@router.post("/decks/{deck_id}/copy")
def copy_deck_form(deck_id: int, session: SessionDep, user: CurrentUser) -> RedirectResponse:
    copy = crud.copy_deck(session, user, deck_id)
    return RedirectResponse(f"/decks/{copy.id}?notice=deck-copied", status_code=303)


@router.post("/decks/{deck_id}/cards")
def create_card_form(
    deck_id: int,
    session: SessionDep,
    user: CurrentUser,
    question: Annotated[str, Form()],
    answer: Annotated[str, Form()],
    details: Annotated[str, Form()] = "",
    context: Annotated[str, Form()] = "",
    expected_time_s: Annotated[str, Form()] = "",
    tags: Annotated[str, Form()] = "",
) -> RedirectResponse:
    crud.create_card(
        session,
        user,
        CardCreate(
            deck_id=deck_id,
            question=question,
            answer=answer,
            details=details,
            context=context,
            expected_time_s=int(expected_time_s) if expected_time_s.strip() else None,
            tags=[tag.strip() for tag in tags.split(",") if tag.strip()],
        ),
    )
    return RedirectResponse(f"/decks/{deck_id}?notice=card-created", status_code=303)


@router.post("/cards/{card_id}/delete")
def delete_card_form(
    card_id: int,
    session: SessionDep,
    user: CurrentUser,
    deck_id: Annotated[int, Form()],
) -> RedirectResponse:
    crud.delete_card(session, user, card_id)
    return RedirectResponse(f"/decks/{deck_id}?notice=card-deleted", status_code=303)


@router.get("/explore", response_class=HTMLResponse)
def explore_page(request: Request, session: SessionDep, user: CurrentUser) -> Response:
    return templates.TemplateResponse(
        request=request,
        name="explore.html",
        context={
            "decks": [
                (
                    deck,
                    owner,
                    count,
                    deck.id is not None and crud.is_following(session, user, deck.id),
                )
                for deck, owner, count in crud.list_public_decks(session)
            ],
        },
    )


@router.get("/study", response_class=HTMLResponse)
def study_page(
    request: Request, session: SessionDep, user: CurrentUser, deck_id: int | None = None
) -> Response:
    return templates.TemplateResponse(
        request=request,
        name="study.html",
        context={
            "decks": crud.list_decks(session, user),
            "deck_id": deck_id,
            "settings": crud.effective_settings(session, user),
            "voice_allowed": crud.get_app_settings(session).voice_allowed,
            "due_count": len(crud.get_due(session, user, deck_id)),
        },
    )


def _settings_page(
    request: Request, session: SessionDep, user: CurrentUser, new_token: str | None = None
) -> Response:
    return templates.TemplateResponse(
        request=request,
        name="settings.html",
        context={
            "settings": crud.get_settings(session, user),
            "app_settings": crud.get_app_settings(session),
            "tokens": auth.list_api_tokens(session, user),
            "new_token": new_token,
        },
    )


@router.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request, session: SessionDep, user: CurrentUser) -> Response:
    return _settings_page(request, session, user)


@router.post("/settings")
def update_settings_form(
    session: SessionDep,
    user: CurrentUser,
    eval_mode: Annotated[EvalModeForm, Form()],
    judge_language: Annotated[str, Form()],
    stt_language: Annotated[str, Form()],
    daily_new_limit: Annotated[int, Form()],
    daily_review_limit: Annotated[int, Form()],
    voice_auto_judge: Annotated[bool, Form()] = False,
    auto_confirm: Annotated[bool, Form()] = False,
    teacher_enabled: Annotated[bool, Form()] = False,
) -> RedirectResponse:
    crud.update_settings(
        session,
        user,
        SettingsUpdate(
            eval_mode=eval_mode,
            judge_language=judge_language,
            stt_language=stt_language,
            voice_auto_judge=voice_auto_judge,
            auto_confirm=auto_confirm,
            teacher_enabled=teacher_enabled,
            daily_new_limit=daily_new_limit,
            daily_review_limit=daily_review_limit,
        ),
    )
    return RedirectResponse("/settings?notice=settings-saved", status_code=303)


@router.post("/settings/tokens", response_class=HTMLResponse)
def create_token_form(
    request: Request, session: SessionDep, user: CurrentUser, name: Annotated[str, Form()]
) -> Response:
    if not name.strip():
        raise ValueError("Token name is required")
    _, raw = auth.create_api_token(session, user, name)
    # Rendered directly (no redirect): the raw token is shown once, never stored.
    return _settings_page(request, session, user, new_token=raw)


@router.post("/settings/tokens/{token_id}/revoke")
def revoke_token_form(token_id: int, session: SessionDep, user: CurrentUser) -> RedirectResponse:
    try:
        auth.revoke_api_token(session, user, token_id)
    except LookupError as exc:
        raise crud.NotFoundError(str(exc)) from exc
    return RedirectResponse("/settings?notice=token-revoked", status_code=303)


@router.get("/admin", response_class=HTMLResponse)
def admin_page(
    request: Request, session: SessionDep, _: AdminUser, config: AuthConfigDep
) -> Response:
    return templates.TemplateResponse(
        request=request,
        name="admin.html",
        context={
            "users": crud.list_users(session),
            "app_settings": crud.get_app_settings(session),
            "public_decks": crud.list_public_decks(session),
            "oidc_enabled": config.oidc_enabled,
        },
    )


@router.post("/admin/users/{user_id}")
def admin_user_form(
    user_id: int,
    session: SessionDep,
    admin: AdminUser,
    config: AuthConfigDep,
    action: Annotated[UserAction, Form()],
) -> RedirectResponse:
    if action == "delete":
        crud.delete_user(session, admin, user_id)
        return RedirectResponse("/admin?notice=user-deleted", status_code=303)
    else:
        status = {"approve": "active", "suspend": "disabled", "reactivate": "active"}.get(action)
        role = {"promote": "admin", "demote": "user"}.get(action)
        crud.admin_update_user(
            session, admin, user_id, status=status, role=role, oidc_enabled=config.oidc_enabled
        )
    return RedirectResponse("/admin?notice=user-updated", status_code=303)


@router.post("/admin/settings")
def admin_settings_form(
    session: SessionDep,
    _: AdminUser,
    registration: Annotated[Registration, Form()],
    default_eval_mode: Annotated[EvalModeForm, Form()],
    default_judge_language: Annotated[str, Form()],
    default_stt_language: Annotated[str, Form()],
    allow_public_decks: Annotated[bool, Form()] = False,
    teacher_allowed: Annotated[bool, Form()] = False,
    voice_allowed: Annotated[bool, Form()] = False,
) -> RedirectResponse:
    crud.update_app_settings(
        session,
        AppSettingsUpdate(
            registration=registration,
            allow_public_decks=allow_public_decks,
            teacher_allowed=teacher_allowed,
            voice_allowed=voice_allowed,
            default_settings=SettingsUpdate(
                eval_mode=default_eval_mode,
                judge_language=default_judge_language,
                stt_language=default_stt_language,
            ),
        ),
    )
    return RedirectResponse("/admin?notice=app-settings-saved", status_code=303)


@router.post("/admin/decks/{deck_id}/unpublish")
def admin_unpublish_form(deck_id: int, session: SessionDep, _: AdminUser) -> RedirectResponse:
    crud.unpublish_deck(session, deck_id)
    return RedirectResponse("/admin?notice=deck-unpublished", status_code=303)
