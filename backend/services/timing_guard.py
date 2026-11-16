"""Guard rails for dub timing (personal v1, change 4).

A line is *rushed* when its translated text would be spoken faster than the
language's normal rate to fit its slot: ``speech_rate.rate_ratio`` above
``RUSHED_RATIO``. The export gate lists rushed lines plus lines the duration
planner already marked ``impossible``.
"""
from __future__ import annotations

from typing import Iterable, Optional

from services.speech_rate import rate_ratio

RUSHED_RATIO = 1.25


def line_ratio(text: str, start: float, end: float, lang: str) -> Optional[float]:
    """Predicted rate ratio for one line, or None when it has no usable slot/text."""
    slot = float(end) - float(start)
    if not (text or "").strip() or slot <= 0:
        return None
    return rate_ratio(text, slot, lang)


def flag_lines(lines: Iterable[dict], lang: str) -> list[dict]:
    """Return ``[{id, kind, rate_ratio}]`` for every rushed or impossible line.

    ``lines``: dicts with ``id``, ``text``, ``start``, ``end`` and an optional
    ``plan_status`` (the duration planner's verdict). ``impossible`` wins over
    ``rushed`` for the same line.
    """
    flagged: list[dict] = []
    for line in lines:
        ratio = line_ratio(line.get("text", ""), line.get("start", 0.0), line.get("end", 0.0), lang)
        if line.get("plan_status") == "impossible":
            kind = "impossible"
        elif ratio is not None and ratio > RUSHED_RATIO:
            kind = "rushed"
        else:
            continue
        flagged.append({
            "id": str(line["id"]),
            "kind": kind,
            "rate_ratio": None if ratio is None else round(ratio, 3),
        })
    return flagged
