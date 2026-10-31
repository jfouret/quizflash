from collections.abc import Callable
from typing import Any

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.auth import AuthProvider
from fastmcp.server.dependencies import get_access_token
from sqlmodel import Session

from app import crud
from app.models import User
from app.schemas import (
    CardCreate,
    CardRead,
    CardUpdate,
    DeckCreate,
    DeckRead,
    DeckUpdate,
    DueCard,
    EvalMode,
    SchedulerName,
    StatsScope,
    TagRead,
)
from app.stats import get_stats as calculate_stats
from app.teacher.base import Teacher
from app.teacher.service import explain_card as teacher_explanation


def create_mcp(
    session_factory: Callable[[], Session], teacher: Teacher, auth: AuthProvider | None
) -> FastMCP:
    mcp = FastMCP("QuizDeck", auth=auth)

    def current_user(session: Session) -> User:
        """Resolve the user bound to the verified bearer token of this request."""
        access = get_access_token()
        user = session.get(User, int(access.client_id)) if access else None
        if user is None or user.status != "active":
            raise ToolError("Authentication required")
        return user

    @mcp.tool
    def list_decks() -> list[dict[str, Any]]:
        """List all decks."""
        with session_factory() as session:
            return [
                DeckRead.model_validate(deck).model_dump(mode="json")
                for deck in crud.list_decks(session, current_user(session))
            ]

    @mcp.tool
    def get_deck(deck_id: int) -> dict[str, Any]:
        """Get one deck by numeric ID."""
        with session_factory() as session:
            return DeckRead.model_validate(
                crud.get_deck(session, current_user(session), deck_id)
            ).model_dump(mode="json")

    @mcp.tool
    def create_deck(
        name: str,
        description: str = "",
        context: str = "",
        scheduler: SchedulerName = "fsrs",
        scheduler_params: dict[str, Any] | None = None,
        eval_mode: EvalMode | None = None,
    ) -> dict[str, Any]:
        """Create a deck with optional context, scheduler, and evaluation settings."""
        data = DeckCreate(
            name=name,
            description=description,
            context=context,
            scheduler=scheduler,
            scheduler_params=scheduler_params or {},
            eval_mode=eval_mode,
        )
        with session_factory() as session:
            return DeckRead.model_validate(
                crud.create_deck(session, current_user(session), data)
            ).model_dump(mode="json")

    @mcp.tool
    def update_deck(deck_id: int, data: DeckUpdate) -> dict[str, Any]:
        """Patch a deck; omit fields to leave them unchanged."""
        with session_factory() as session:
            return DeckRead.model_validate(
                crud.update_deck(session, current_user(session), deck_id, data)
            ).model_dump(mode="json")

    @mcp.tool
    def delete_deck(deck_id: int) -> None:
        """Delete a deck, its cards, states, and answer logs."""
        with session_factory() as session:
            crud.delete_deck(session, current_user(session), deck_id)

    @mcp.tool
    def list_cards(deck_id: int | None = None, tag: str | None = None) -> list[dict[str, Any]]:
        """List cards, optionally filtered by deck ID or exact tag name."""
        with session_factory() as session:
            return [
                CardRead.model_validate(card).model_dump(mode="json")
                for card in crud.list_cards(session, current_user(session), deck_id, tag)
            ]

    @mcp.tool
    def get_card(card_id: int) -> dict[str, Any]:
        """Get one card by numeric ID."""
        with session_factory() as session:
            return CardRead.model_validate(
                crud.get_card(session, current_user(session), card_id)
            ).model_dump(mode="json")

    @mcp.tool
    def create_card(
        deck_id: int,
        question: str,
        answer: str,
        details: str = "",
        context: str = "",
        expected_time_s: int | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create a card and initialize its scheduling state."""
        data = CardCreate(
            deck_id=deck_id,
            question=question,
            answer=answer,
            details=details,
            context=context,
            expected_time_s=expected_time_s,
            tags=tags or [],
        )
        with session_factory() as session:
            return CardRead.model_validate(
                crud.create_card(session, current_user(session), data)
            ).model_dump(mode="json")

    @mcp.tool
    def update_card(card_id: int, data: CardUpdate) -> dict[str, Any]:
        """Patch a card; omit fields to leave them unchanged."""
        with session_factory() as session:
            return CardRead.model_validate(
                crud.update_card(session, current_user(session), card_id, data)
            ).model_dump(mode="json")

    @mcp.tool
    def delete_card(card_id: int) -> None:
        """Delete a card, its scheduling state, and answer logs."""
        with session_factory() as session:
            crud.delete_card(session, current_user(session), card_id)

    @mcp.tool
    def list_tags() -> list[dict[str, Any]]:
        """List all first-class tags."""
        with session_factory() as session:
            return [
                TagRead.model_validate(tag).model_dump(mode="json")
                for tag in crud.list_tags(session, current_user(session))
            ]

    @mcp.tool
    def list_due(deck_id: int | None = None) -> list[dict[str, Any]]:
        """List the current continuous review queue, ordered by due date."""
        with session_factory() as session:
            return [
                DueCard(
                    card=CardRead.model_validate(card),
                    due=state.due,
                    is_new=state.last_review is None,
                ).model_dump(mode="json")
                for card, state in crud.get_due(session, current_user(session), deck_id)
            ]

    @mcp.tool
    def get_stats(scope: StatsScope, target: str) -> dict[str, Any]:
        """Aggregate answer logs for a deck/card ID or tag name."""
        with session_factory() as session:
            return calculate_stats(session, current_user(session), scope, target).model_dump(
                mode="json"
            )

    @mcp.tool
    def explain_card(card_id: int) -> dict[str, Any]:
        """Ask the LLM teacher to explain a card using its deck and card context."""
        with session_factory() as session:
            user = current_user(session)
            if not crud.get_app_settings(session).teacher_allowed:
                raise ToolError("Teacher explanations are disabled")
            explanation = teacher_explanation(session, user, card_id, teacher)
            return {"explanation": explanation, "model": teacher.model}

    @mcp.tool
    def list_public_decks() -> list[dict[str, Any]]:
        """List decks published in the public space by any user."""
        with session_factory() as session:
            current_user(session)
            return [
                {
                    **DeckRead.model_validate(deck).model_dump(mode="json"),
                    "owner_name": owner,
                    "card_count": count,
                }
                for deck, owner, count in crud.list_public_decks(session)
            ]

    @mcp.tool
    def follow_deck(deck_id: int) -> dict[str, Any]:
        """Follow a public deck to train on it without owning it."""
        with session_factory() as session:
            deck = crud.follow_deck(session, current_user(session), deck_id)
            return DeckRead.model_validate(deck).model_dump(mode="json")

    @mcp.tool
    def copy_deck(deck_id: int) -> dict[str, Any]:
        """Copy a public (or owned) deck into a new private deck you own."""
        with session_factory() as session:
            deck = crud.copy_deck(session, current_user(session), deck_id)
            return DeckRead.model_validate(deck).model_dump(mode="json")

    return mcp
