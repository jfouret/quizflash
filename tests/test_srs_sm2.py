from datetime import UTC, datetime, timedelta

import pytest

from app.srs.sm2 import SM2Scheduler

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def test_again_resets_progress_and_reschedules_from_review_time() -> None:
    scheduler = SM2Scheduler()
    state = scheduler.init_state(NOW)
    state, first_due = scheduler.review(state, 3, NOW, {})
    state, _ = scheduler.review(state, 3, first_due, {})
    previous_ease = state["ease"]
    review_time = first_due + timedelta(days=10)

    reset_state, reset_due = scheduler.review(state, 1, review_time, {})

    assert reset_state["repetitions"] == 0
    assert reset_state["interval_days"] == pytest.approx(1.0)
    assert reset_state["ease"] < previous_ease
    assert reset_due == review_time + timedelta(days=1)


def test_good_progresses_through_learning_intervals() -> None:
    scheduler = SM2Scheduler()
    state = scheduler.init_state(NOW)

    first_state, first_due = scheduler.review(state, 3, NOW, {})
    second_state, second_due = scheduler.review(first_state, 3, first_due, {})
    third_state, third_due = scheduler.review(second_state, 3, second_due, {})

    assert first_state["repetitions"] == 1
    assert first_state["interval_days"] == pytest.approx(1.0)
    assert first_due == NOW + timedelta(days=1)
    assert second_state["repetitions"] == 2
    assert second_state["interval_days"] == pytest.approx(6.0)
    assert second_due == first_due + timedelta(days=6)
    assert third_state["repetitions"] == 3
    assert third_state["interval_days"] == pytest.approx(15.0)
    assert third_due == second_due + timedelta(days=15)


def test_custom_ease_and_minimum_interval_are_used() -> None:
    scheduler = SM2Scheduler()
    params = {"ease_start": 1.8, "min_interval_days": 2.0}
    state = scheduler.init_state(NOW)

    first_state, first_due = scheduler.review(state, 3, NOW, params)
    second_state, second_due = scheduler.review(first_state, 3, first_due, params)
    third_state, third_due = scheduler.review(second_state, 3, second_due, params)

    assert first_state["ease"] == pytest.approx(1.8)
    assert first_state["interval_days"] == pytest.approx(2.0)
    assert first_due == NOW + timedelta(days=2)
    assert second_state["interval_days"] == pytest.approx(12.0)
    assert second_due == first_due + timedelta(days=12)
    assert third_state["ease"] == pytest.approx(1.8)
    assert third_state["interval_days"] == pytest.approx(21.6)
    assert third_due == second_due + timedelta(days=21.6)


@pytest.mark.parametrize("rating", [0, 5])
def test_invalid_rating_is_rejected(rating: int) -> None:
    scheduler = SM2Scheduler()
    state = scheduler.init_state(NOW)

    with pytest.raises(ValueError, match="rating must be between 1 and 4"):
        scheduler.review(state, rating, NOW, {})
