from typing import Literal

from fastapi import APIRouter, Query

from app.dependencies import CurrentUser, SessionDep
from app.schemas import StatsBreakdownResponse, StatsResponse
from app.stats import get_breakdown, get_stats

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("", response_model=StatsResponse)
def read_stats(
    session: SessionDep,
    user: CurrentUser,
    scope: Literal["deck", "card", "tag"],
    target_id: int = Query(alias="id"),
) -> StatsResponse:
    return get_stats(session, user, scope, str(target_id))


@router.get("/breakdown", response_model=StatsBreakdownResponse)
def read_breakdown(
    session: SessionDep,
    user: CurrentUser,
    group: Literal["card", "tag"],
    deck_id: int | None = None,
) -> StatsBreakdownResponse:
    """Mean rating and correct rate per card or per tag, for one deck or all."""
    return get_breakdown(session, user, group, deck_id)
