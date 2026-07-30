from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ContentValidationOutcome:
    """Picklable content validation result for inference jobs."""

    is_valid: bool
    checks: dict[str, bool]
    scores: dict[str, float]
    messages: tuple[str, ...]


def _get_content_image_validator_class():
    try:
        from avroom_object_removal import ContentImageValidator
    except ModuleNotFoundError as exc:
        if exc.name == "avroom_object_removal":
            logger.error("avroom_object_removal package not importable")
            raise RuntimeError(
                "Missing local package `avroom_object_removal`. Install repo dependencies or run `pip install -e ./TestModules`."
            ) from exc
        raise
    return ContentImageValidator


def validate_upload_content(image_bytes: bytes) -> ContentValidationOutcome:
    """Run ML content validation on raw upload bytes."""
    validator = _get_content_image_validator_class()()
    image_key = f"memory://{hashlib.sha256(image_bytes).hexdigest()}"
    result = validator.validate_upload(image_path=image_key, image_bytes=image_bytes)
    return ContentValidationOutcome(
        is_valid=result.is_valid,
        checks=dict(result.checks),
        scores=dict(result.scores),
        messages=result.messages,
    )
