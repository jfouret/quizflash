"""Per-deck grading scale.

A deck grades answers on the integer levels `0..max` `max` is configurable per
deck; labels are optional and may cover only some levels. The schedulers
(FSRS/SM-2) only understand a fixed 1..4 quality, so every stored rating is
mapped to that range before it reaches a scheduler.
"""

from typing import Any

DEFAULT_MAX = 5
MAX_MAX = 100

# The notation decks are created with: 0 means the answer was absent or false,
# 5 means perfect. Labels are advisory, the judge receives them with the scale.
DEFAULT_LABELS: dict[int, str] = {
    0: "False or absent",
    1: "Bad",
    2: "Average",
    3: "Better than average",
    4: "Good",
    5: "Perfect",
}


def default_scale() -> dict[str, Any]:
    """A fresh copy of the default scale, so callers cannot mutate module state."""
    return {"max": DEFAULT_MAX, "labels": dict(DEFAULT_LABELS)}


DEFAULT_GRADING: dict[str, Any] = default_scale()


def normalize(raw: dict[str, Any] | None) -> dict[str, Any]:
    """Return a valid scale, tolerant of empty or malformed stored values."""
    if not raw:
        return default_scale()
    maximum = raw.get("max", DEFAULT_MAX)
    if isinstance(maximum, bool) or not isinstance(maximum, int) or not 1 <= maximum <= MAX_MAX:
        maximum = DEFAULT_MAX
    labels: dict[int, str] = {}
    for key, value in (raw.get("labels") or {}).items():
        try:
            level = int(key)
        except (TypeError, ValueError):
            continue
        if 0 <= level <= maximum and isinstance(value, str) and value.strip():
            labels[level] = value.strip()
    return {"max": maximum, "labels": labels}


def levels(scale: dict[str, Any]) -> list[int]:
    """Every level of a normalized scale, lowest first."""
    return list(range(normalize(scale)["max"] + 1))


def label(scale: dict[str, Any], level: int) -> str:
    value = normalize(scale)["labels"].get(level, "")
    return value if isinstance(value, str) else ""


def scheduler_rating(scale: dict[str, Any], level: int) -> int:
    """Map a deck level onto the schedulers' fixed 1..4 quality.

    shortcut: a linear map, not a per-scheduler calibration; revisit if a
    scheduler ever exposes its own scale.
    """
    maximum = int(normalize(scale)["max"])
    level = max(0, min(level, maximum))
    return 1 + (level * 3 + maximum // 2) // maximum


__all__ = [
    "DEFAULT_GRADING",
    "DEFAULT_LABELS",
    "DEFAULT_MAX",
    "MAX_MAX",
    "default_scale",
    "label",
    "levels",
    "normalize",
    "scheduler_rating",
]
