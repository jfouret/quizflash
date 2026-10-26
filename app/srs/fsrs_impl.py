import json
from datetime import UTC, datetime
from typing import Any

from fsrs import Card, Rating, Scheduler


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class FSRSScheduler:
    name = "fsrs"

    def init_state(self, now: datetime) -> dict[str, Any]:
        return dict(Card(due=_aware_utc(now)).to_dict())

    def review(
        self,
        state: dict[str, Any],
        rating: int,
        now: datetime,
        params: dict[str, Any],
    ) -> tuple[dict[str, Any], datetime]:
        scheduler = Scheduler(
            desired_retention=float(params.get("desired_retention", 0.9)),
            maximum_interval=int(params.get("max_interval_days", 36500)),
        )
        card = Card.from_json(json.dumps(state))
        updated, _ = scheduler.review_card(
            card=card,
            rating=Rating(rating),
            review_datetime=_aware_utc(now),
        )
        due = updated.due.astimezone(UTC)
        return dict(updated.to_dict()), due
