from __future__ import annotations

import logging

import numpy as np

from ..content_validation_result import ContentValidationResult
from ..content_validation_strategy import ContentValidationStrategy

logger = logging.getLogger(__name__)


class CompositeContentValidationStrategy(ContentValidationStrategy):
    """Merge results from multiple :class:`ContentValidationStrategy` instances.

    ``is_valid`` is ``True`` only when every child check passes. Scores and
    messages from all children are unioned so callers see a single report.
    """

    def __init__(self, strategies: tuple[ContentValidationStrategy, ...]) -> None:
        if not strategies:
            raise ValueError("CompositeContentValidationStrategy requires at least one strategy.")
        self._strategies = strategies
        logger.info(
            "CompositeContentValidationStrategy ready (children=%s)",
            [type(s).__name__ for s in strategies],
        )

    def validate(self, image: np.ndarray) -> ContentValidationResult:
        merged_checks: dict[str, bool] = {}
        merged_scores: dict[str, float] = {}
        merged_messages: list[str] = []

        for strategy in self._strategies:
            result = strategy.validate(image)
            merged_checks.update(result.checks)
            merged_scores.update(result.scores)
            merged_messages.extend(result.messages)

        is_valid = all(merged_checks.values()) if merged_checks else True
        return ContentValidationResult(
            is_valid=is_valid,
            checks=merged_checks,
            scores=merged_scores,
            messages=tuple(merged_messages),
        )
