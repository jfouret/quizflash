from datetime import datetime
from typing import Any, Protocol


class Scheduler(Protocol):
    name: str

    def init_state(self, now: datetime) -> dict[str, Any]: ...

    def review(
        self,
        state: dict[str, Any],
        rating: int,
        now: datetime,
        params: dict[str, Any],
    ) -> tuple[dict[str, Any], datetime]: ...
