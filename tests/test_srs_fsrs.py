import json
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.srs.fsrs_impl import FSRSScheduler

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def test_initialization_schedules_card_for_immediate_review() -> None:
    state = FSRSScheduler().init_state(NOW)

    assert datetime.fromisoformat(state["due"]) == NOW
    assert state["last_review"] is None


@pytest.mark.parametrize("rating", [1, 2, 3, 4])
def test_every_rating_records_review_and_schedules_next_review(rating: int) -> None:
    scheduler = FSRSScheduler()

    updated_state, due = scheduler.review(scheduler.init_state(NOW), rating, NOW, {})

    assert due > NOW
    assert due == datetime.fromisoformat(updated_state["due"])
    assert datetime.fromisoformat(updated_state["last_review"]) == NOW
    assert updated_state["stability"] is not None


def test_json_state_round_trip_supports_repeat_review() -> None:
    scheduler = FSRSScheduler()
    first_state, first_due = scheduler.review(scheduler.init_state(NOW), 3, NOW, {})
    restored_state: dict[str, Any] = json.loads(json.dumps(first_state))

    assert restored_state == first_state

    second_state, second_due = scheduler.review(restored_state, 3, first_due, {})
    second_round_trip: dict[str, Any] = json.loads(json.dumps(second_state))

    assert second_round_trip == second_state
    assert second_due > first_due
    assert datetime.fromisoformat(second_state["last_review"]) == first_due
    assert second_due == datetime.fromisoformat(second_state["due"])


def test_custom_retention_and_maximum_interval_control_scheduling() -> None:
    scheduler = FSRSScheduler()
    mature_state, review_time = scheduler.review(scheduler.init_state(NOW), 4, NOW, {})

    _, low_retention_due = scheduler.review(
        dict(mature_state), 3, review_time, {"desired_retention": 0.8}
    )
    _, high_retention_due = scheduler.review(
        dict(mature_state), 3, review_time, {"desired_retention": 0.95}
    )
    _, capped_due = scheduler.review(
        dict(mature_state),
        3,
        review_time,
        {"desired_retention": 0.8, "max_interval_days": 1},
    )

    assert high_retention_due < low_retention_due
    assert capped_due == review_time + timedelta(days=1)
