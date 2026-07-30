from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ContentValidationResult:
    """Outcome of one content-validation pass over a decoded room image.

    ``checks`` maps logical gate names to pass/fail booleans. ``scores`` holds
    optional continuous metrics (e.g. CLIP label probabilities). ``messages``
    collects human-readable rejection reasons for API responses.
    """

    is_valid: bool
    checks: dict[str, bool]
    scores: dict[str, float]
    messages: tuple[str, ...]
