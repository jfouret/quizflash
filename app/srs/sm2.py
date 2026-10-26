from datetime import datetime, timedelta
from typing import Any


class SM2Scheduler:
    name = "sm2"

    def init_state(self, now: datetime) -> dict[str, Any]:
        return {
            "repetitions": 0,
            "interval_days": 0.0,
            "ease": 2.5,
            "initialized_at": now.isoformat(),
        }

    def review(
        self,
        state: dict[str, Any],
        rating: int,
        now: datetime,
        params: dict[str, Any],
    ) -> tuple[dict[str, Any], datetime]:
        if rating not in range(1, 5):
            raise ValueError("rating must be between 1 and 4")
        repetitions = int(state.get("repetitions", 0))
        interval = float(state.get("interval_days", 0))
        default_ease = float(params.get("ease_start", 2.5))
        ease = default_ease if repetitions == 0 else float(state.get("ease", default_ease))
        minimum = float(params.get("min_interval_days", 1))

        quality = rating + 1
        ease = max(1.3, ease + 0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
        if rating <= 2:
            repetitions = 0
            interval = minimum
        else:
            repetitions += 1
            if repetitions == 1:
                interval = minimum
            elif repetitions == 2:
                interval = 6 * minimum
            else:
                interval = max(minimum, interval * ease)

        new_state = {
            "repetitions": repetitions,
            "interval_days": interval,
            "ease": ease,
            "initialized_at": state.get("initialized_at", now.isoformat()),
        }
        return new_state, now + timedelta(days=interval)
