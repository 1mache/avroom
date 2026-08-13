from __future__ import annotations

import logging
from dataclasses import dataclass

from core.avroom_package import load_avroom_attr
from core.depth_cache import memory_image_key

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ContentValidationOutcome:
    """Picklable content validation result for inference jobs."""

    is_valid: bool
    checks: dict[str, bool]
    scores: dict[str, float]
    messages: tuple[str, ...]


def validate_upload_content(image_bytes: bytes) -> ContentValidationOutcome:
    """Run ML content validation on raw upload bytes."""
    validator = load_avroom_attr("ContentImageValidator")()
    result = validator.validate_upload(
        image_path=memory_image_key(image_bytes),
        image_bytes=image_bytes,
    )
    return ContentValidationOutcome(
        is_valid=result.is_valid,
        checks=dict(result.checks),
        scores=dict(result.scores),
        messages=result.messages,
    )
