from typing import Literal

from fastapi import APIRouter, Query

from app.dependencies import SessionDep
from app.schemas import StatsResponse
from app.stats import get_stats

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("", response_model=StatsResponse)
def read_stats(
    session: SessionDep,
    scope: Literal["deck", "card", "tag"],
    target_id: int = Query(alias="id"),
) -> StatsResponse:
    return get_stats(session, scope, str(target_id))
