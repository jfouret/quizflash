from typing import Literal

from fastapi import APIRouter, Query

from app.dependencies import CurrentUser, SessionDep
from app.schemas import StatsResponse
from app.stats import get_stats

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("", response_model=StatsResponse)
def read_stats(
    session: SessionDep,
    user: CurrentUser,
    scope: Literal["deck", "card", "tag"],
    target_id: int = Query(alias="id"),
) -> StatsResponse:
    return get_stats(session, user, scope, str(target_id))
