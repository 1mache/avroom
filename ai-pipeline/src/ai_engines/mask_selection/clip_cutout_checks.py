from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Protocol

from PIL import Image

CHECK_PASS_THRESHOLD: Final[float] = 0.55


@dataclass(frozen=True)
class ClipCutoutCheck:
    """One binary CLIP gate for cutout auto-pick."""

    key: str
    positive: str
    negative: str


CLIP_CUTOUT_CHECKS: Final[tuple[ClipCutoutCheck, ...]] = (
    ClipCutoutCheck("complete", "a complete object", "a partial or cut-off object"),
    ClipCutoutCheck("single", "one isolated object", "multiple objects"),
    ClipCutoutCheck(
        "not_scene",
        "a furniture or household object",
        "floor, wall, or empty background",
    ),
    ClipCutoutCheck("not_fragment", "a whole object", "a fragment or edge piece"),
)


class LabelScorer(Protocol):
    """Minimal CLIP surface for batched label scoring."""

    def score_labels(self, pil_image: Image.Image, labels: tuple[str, ...]) -> dict[str, float]:
        """Return a softmax distribution over ``labels``."""


def score_cutout_checks(scorer: LabelScorer, pil_crop: Image.Image) -> dict[str, float]:
    """Score every cutout check in one batched ``score_labels`` call."""
    labels: list[str] = []
    for check in CLIP_CUTOUT_CHECKS:
        labels.append(check.positive)
        labels.append(check.negative)
    distribution = scorer.score_labels(pil_crop, tuple(labels))
    out: dict[str, float] = {}
    for check in CLIP_CUTOUT_CHECKS:
        out[check.key] = distribution[check.positive]
    return out


def first_failing_check(scores: dict[str, float]) -> str | None:
    """Return the first check key below threshold, or None if all pass."""
    for check in CLIP_CUTOUT_CHECKS:
        if scores[check.key] < CHECK_PASS_THRESHOLD:
            return check.key
    return None


def passes_all_checks(scores: dict[str, float]) -> bool:
    """True when every check meets ``CHECK_PASS_THRESHOLD``."""
    return first_failing_check(scores) is None


def average_positive_score(scores: dict[str, float]) -> float:
    """Mean P(positive) across all configured checks."""
    if not scores:
        return 0.0
    return sum(scores.values()) / float(len(scores))
