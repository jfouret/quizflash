from fastapi import APIRouter

from app import crud
from app.dependencies import CurrentUser, SessionDep
from app.history import history_page
from app.schemas import HistoryCleared, HistoryPage

router = APIRouter(prefix="/api/history", tags=["history"])


@router.get("", response_model=HistoryPage)
def list_history(
    session: SessionDep,
    user: CurrentUser,
    deck_id: int | None = None,
    limit: int = 50,
    offset: int = 0,
) -> HistoryPage:
    """The caller's past answers, newest first, optionally for one deck."""
    return history_page(session, user, deck_id, limit, offset)


@router.delete("", response_model=HistoryCleared)
def clear_history(
    session: SessionDep, user: CurrentUser, deck_id: int | None = None
) -> HistoryCleared:
    """Delete the caller's history, for one deck or everywhere."""
    return HistoryCleared(deleted=crud.clear_history(session, user, deck_id))
