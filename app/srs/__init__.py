"""Spaced-repetition schedulers."""

from app.srs.base import Scheduler
from app.srs.fsrs_impl import FSRSScheduler
from app.srs.sm2 import SM2Scheduler

SCHEDULERS: dict[str, Scheduler] = {
    "fsrs": FSRSScheduler(),
    "sm2": SM2Scheduler(),
}


def get_scheduler(name: str) -> Scheduler:
    try:
        return SCHEDULERS[name]
    except KeyError as exc:
        raise ValueError(f"Unknown scheduler: {name}") from exc


__all__ = ["FSRSScheduler", "SM2Scheduler", "Scheduler", "get_scheduler"]
