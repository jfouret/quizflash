import os
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response

from app import __version__, auth, crud, grading
from app.agents import (
    AGENT_STEPS,
    DEFAULT_AGENT_CONFIGS,
    ENV_HINTS,
    PROMPT_VARIABLES,
    STEP_LABELS,
    AgentStep,
)
from app.dependencies import AdminUser, AuthConfigDep, CurrentUser, SessionDep
from app.history import history_page
from app.schemas import (
    AgentConfigUpdate,
    AppSettingsUpdate,
    CardCreate,
    CardUpdate,
    DeckCreate,
    DeckUpdate,
    GradingScale,
    Registration,
    SettingsUpdate,
)
from app.stats import get_breakdown
from app.templating import templates

router = APIRouter(include_in_schema=False)
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
EvalModeForm = Literal["ai_preselect", "ai_assess"]
SchedulerForm = Literal["fsrs", "sm2"]
VisibilityForm = Literal["private", "public"]
UserAction = Literal["approve", "suspend", "reactivate", "promote", "demote", "delete"]


def _deck_page(deck_id: int, notice: str) -> str:
    """URL of a deck page on this site.

    Concatenation, not an f-string: the literal prefix is what proves the target
    cannot leave the site, and CodeQL's URL-redirection query only accepts the
    right-hand side of a concatenation as safe.
    """
    return "/decks/" + str(deck_id) + "?notice=" + notice


@router.get("/healthz", include_in_schema=False)
def healthz() -> dict[str, str]:
    """Liveness probe for the container healthcheck; no session required."""
    return {"status": "ok", "version": __version__}


@router.get("/favicon.ico", include_in_schema=False)
def favicon() -> FileResponse:
    """Serve the icon at the root path browsers request by convention."""
    return FileResponse(STATIC_DIR / "favicon.ico", media_type="image/x-icon")


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
    scale = grading.normalize(deck.grading_scale)
    return templates.TemplateResponse(
        request=request,
        name="deck_detail.html",
        context={
            "deck": deck,
            "cards": crud.list_cards(session, user, deck_id),
            "is_owner": deck.owner_id == user.id,
            "following": crud.is_following(session, user, deck_id),
            "allow_public": crud.get_app_settings(session).allow_public_decks,
            "grading_max": scale["max"],
            "grading_labels": ", ".join(
                f"{level}={text}" for level, text in sorted(scale["labels"].items())
            ),
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
    grading_max: Annotated[int, Form()] = grading.DEFAULT_MAX,
    grading_labels: Annotated[str, Form()] = "",
) -> RedirectResponse:
    data = DeckUpdate(
        description=description,
        context=context,
        grading_scale=GradingScale(
            max=grading_max, labels=_parse_labels(grading_labels, grading_max)
        ),
    )
    if visibility is not None:
        data.visibility = visibility
    crud.update_deck(session, user, deck_id, data)
    return RedirectResponse(_deck_page(deck_id, "deck-saved"), status_code=303)


def _parse_labels(raw: str, maximum: int) -> dict[int, str]:
    """Parse `3=Bad, 5=Average` into level labels; blank entries are skipped."""
    labels: dict[int, str] = {}
    for chunk in raw.replace("\n", ",").split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        level, sep, text = chunk.partition("=")
        if not sep or not level.strip().isdigit():
            raise ValueError(f"Label {chunk!r} must look like '3=Bad'")
        labels[int(level.strip())] = text.strip()
    return labels


@router.post("/decks/{deck_id}/delete")
def delete_deck_form(deck_id: int, session: SessionDep, user: CurrentUser) -> RedirectResponse:
    crud.delete_deck(session, user, deck_id)
    return RedirectResponse("/?notice=deck-deleted", status_code=303)


@router.post("/decks/{deck_id}/follow")
def follow_deck_form(deck_id: int, session: SessionDep, user: CurrentUser) -> RedirectResponse:
    crud.follow_deck(session, user, deck_id)
    return RedirectResponse(_deck_page(deck_id, "deck-followed"), status_code=303)


@router.post("/decks/{deck_id}/unfollow")
def unfollow_deck_form(deck_id: int, session: SessionDep, user: CurrentUser) -> RedirectResponse:
    crud.unfollow_deck(session, user, deck_id)
    return RedirectResponse("/explore?notice=deck-unfollowed", status_code=303)


@router.post("/decks/{deck_id}/copy")
def copy_deck_form(deck_id: int, session: SessionDep, user: CurrentUser) -> RedirectResponse:
    copy = crud.copy_deck(session, user, deck_id)
    assert copy.id is not None  # a committed row always has an id
    return RedirectResponse(_deck_page(copy.id, "deck-copied"), status_code=303)


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
    return RedirectResponse(_deck_page(deck_id, "card-created"), status_code=303)


@router.post("/cards/{card_id}/delete")
def delete_card_form(
    card_id: int,
    session: SessionDep,
    user: CurrentUser,
    deck_id: Annotated[int, Form()],
) -> RedirectResponse:
    crud.delete_card(session, user, card_id)
    return RedirectResponse(_deck_page(deck_id, "card-deleted"), status_code=303)


@router.post("/cards/{card_id}/update")
def update_card_form(
    card_id: int,
    session: SessionDep,
    user: CurrentUser,
    deck_id: Annotated[int, Form()],
    question: Annotated[str, Form()],
    answer: Annotated[str, Form()],
    details: Annotated[str, Form()] = "",
    context: Annotated[str, Form()] = "",
    expected_time_s: Annotated[str, Form()] = "",
    tags: Annotated[str, Form()] = "",
) -> RedirectResponse:
    crud.update_card(
        session,
        user,
        card_id,
        CardUpdate(
            question=question,
            answer=answer,
            details=details,
            context=context,
            expected_time_s=int(expected_time_s) if expected_time_s.strip() else None,
            tags=[tag.strip() for tag in tags.split(",") if tag.strip()],
        ),
    )
    return RedirectResponse(_deck_page(deck_id, "card-saved"), status_code=303)


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
    request: Request,
    session: SessionDep,
    user: CurrentUser,
    deck_id: Annotated[list[int] | None, Query()] = None,
) -> Response:
    return templates.TemplateResponse(
        request=request,
        name="study.html",
        context={
            "decks": crud.list_decks(session, user),
            "deck_ids": deck_id or [],
            "settings": crud.effective_settings(session, user),
            "voice_allowed": crud.get_app_settings(session).voice_allowed,
            "study_tags": crud.list_study_tags(session, user, deck_id),
            "due_count": len(crud.get_due(session, user, deck_id)),
        },
    )


@router.get("/history", response_class=HTMLResponse)
def history_view(
    request: Request,
    session: SessionDep,
    user: CurrentUser,
    deck_id: int | None = None,
    page: int = 1,
) -> Response:
    limit = 50
    offset = (max(1, page) - 1) * limit
    return templates.TemplateResponse(
        request=request,
        name="history.html",
        context={
            "decks": crud.list_decks(session, user),
            "deck_id": deck_id,
            "page": max(1, page),
            "limit": limit,
            "history": history_page(session, user, deck_id, limit, offset),
        },
    )


@router.post("/history/clear")
def clear_history_form(
    session: SessionDep,
    user: CurrentUser,
    deck_id: Annotated[str, Form()] = "",
) -> RedirectResponse:
    crud.clear_history(session, user, int(deck_id) if deck_id.strip() else None)
    return RedirectResponse("/history?notice=history-cleared", status_code=303)


@router.get("/stats", response_class=HTMLResponse)
def stats_view(
    request: Request,
    session: SessionDep,
    user: CurrentUser,
    deck_id: int | None = None,
) -> Response:
    return templates.TemplateResponse(
        request=request,
        name="stats.html",
        context={
            "decks": crud.list_decks(session, user),
            "deck_id": deck_id,
            "by_card": get_breakdown(session, user, "card", deck_id).model_dump(),
            "by_tag": get_breakdown(session, user, "tag", deck_id).model_dump(),
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
    tts_enabled: Annotated[bool, Form()] = False,
    question_vocal: Annotated[bool, Form()] = False,
    teacher_vocal: Annotated[bool, Form()] = False,
    batch_enabled: Annotated[bool, Form()] = False,
    batch_size: Annotated[int, Form()] = 5,
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
            tts_enabled=tts_enabled,
            question_vocal=question_vocal,
            teacher_vocal=teacher_vocal,
            batch_enabled=batch_enabled,
            batch_size=batch_size,
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
    tts_allowed: Annotated[bool, Form()] = False,
) -> RedirectResponse:
    crud.update_app_settings(
        session,
        AppSettingsUpdate(
            registration=registration,
            allow_public_decks=allow_public_decks,
            teacher_allowed=teacher_allowed,
            voice_allowed=voice_allowed,
            tts_allowed=tts_allowed,
            default_settings=SettingsUpdate(
                eval_mode=default_eval_mode,
                judge_language=default_judge_language,
                stt_language=default_stt_language,
            ),
        ),
    )
    return RedirectResponse("/admin?notice=app-settings-saved", status_code=303)


@router.get("/admin/agents", response_class=HTMLResponse)
def agents_page(
    request: Request, session: SessionDep, _: AdminUser, step: AgentStep = "judge"
) -> Response:
    configs = {config.step: config for config in crud.list_agent_configs(session)}
    return templates.TemplateResponse(
        request=request,
        name="agents.html",
        context={
            "configs": configs,
            "steps": AGENT_STEPS,
            "labels": STEP_LABELS,
            "prompt_variables": PROMPT_VARIABLES,
            "env_hints": ENV_HINTS,
            "key_configured": {
                key: bool(os.getenv(config.api_key_env) or os.getenv("OPENROUTER_API_KEY"))
                for key, config in configs.items()
            },
            "defaults": DEFAULT_AGENT_CONFIGS[step],
            "step": step,
        },
    )


@router.post("/admin/agents/{step}")
def update_agent_form(
    step: AgentStep,
    session: SessionDep,
    _: AdminUser,
    model: Annotated[str, Form()] = "",
    base_url: Annotated[str, Form()] = "",
    api_key_env: Annotated[str, Form()] = "OPENROUTER_API_KEY",
    voice: Annotated[str, Form()] = "",
    system_prompt: Annotated[str, Form()] = "",
    prompt_template: Annotated[str, Form()] = "",
) -> RedirectResponse:
    if step in {"judge", "teacher"} and not prompt_template.strip():
        raise ValueError("Prompt template is required")
    if not (os.getenv(api_key_env) or os.getenv("OPENROUTER_API_KEY")):
        raise ValueError(
            f"{api_key_env} must be defined in the environment; API keys are never stored in the UI"
        )
    crud.update_agent_config(
        session,
        step,
        AgentConfigUpdate(
            model=model,
            base_url=base_url,
            api_key_env=api_key_env,
            voice=voice,
            system_prompt=system_prompt,
            prompt_template=prompt_template,
        ),
    )
    return RedirectResponse("/admin/agents?step=" + step + "&notice=agent-saved", status_code=303)


@router.post("/admin/decks/{deck_id}/unpublish")
def admin_unpublish_form(deck_id: int, session: SessionDep, _: AdminUser) -> RedirectResponse:
    crud.unpublish_deck(session, deck_id)
    return RedirectResponse("/admin?notice=deck-unpublished", status_code=303)
