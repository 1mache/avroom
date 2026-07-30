from __future__ import annotations

import logging

import cv2
import numpy as np

from ..ai_engines.content_validation.content_validation_facade import ContentValidationFacade
from ..ai_engines.content_validation.content_validation_result import ContentValidationResult
from ..utils.debug_image_saver import DebugImageSaver

logger = logging.getLogger(__name__)


class ContentImageValidator:
    """Core orchestrator for ML-based upload content validation.

    Decodes image bytes (or reads from disk) into BGR and delegates to
    :class:`ContentValidationFacade`. Standalone pre-pipeline gate — not
    wired into :class:`ObjectRemover`, :class:`ObjectSegmentor`, or
    :class:`BackgroundInpainter`.
    """

    def __init__(
        self,
        validation_facade: ContentValidationFacade | None = None,
        debug_image_saver: DebugImageSaver | None = None,
    ) -> None:
        self.validation: ContentValidationFacade = validation_facade or ContentValidationFacade()
        self.image_saver: DebugImageSaver = debug_image_saver or DebugImageSaver()
        logger.info("ContentImageValidator initialized")

    def validate_upload(
        self,
        image_path: str,
        image_bytes: bytes | None = None,
    ) -> ContentValidationResult:
        """Validate upload content from bytes or a filesystem path.

        Args:
            image_path: Filesystem path or synthetic cache key
                (e.g. ``memory://<sha256>`` when FastAPI supplies bytes).
            image_bytes: Raw image bytes. When provided, disk is not read.

        Returns:
            Structured validation result with pass/fail checks and messages.

        Raises:
            ValueError: When bytes cannot be decoded into a valid image.
            FileNotFoundError: When ``image_bytes`` is None and path is missing.
        """
        image_bgr = self._decode_image(image_path, image_bytes)
        logger.info(
            "Content validation starting: path=%s shape=%s",
            image_path,
            image_bgr.shape,
        )
        self.image_saver.save("content_validation_input", image_bgr)
        result = self.validation.validate(image_bgr)
        logger.info(
            "Content validation finished: is_valid=%s failed_checks=%s",
            result.is_valid,
            [name for name, passed in result.checks.items() if not passed],
        )
        return result

    def _decode_image(self, image_path: str, image_bytes: bytes | None) -> np.ndarray:
        if image_bytes is not None:
            decoded = cv2.imdecode(np.frombuffer(image_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
            if decoded is None:
                logger.error("Could not decode image bytes for content validation")
                raise ValueError("Uploaded file is not a valid image.")
            return decoded

        if image_path.startswith("memory://"):
            raise ValueError("image_bytes must be provided when image_path is a memory key.")

        decoded = cv2.imread(image_path, cv2.IMREAD_COLOR)
        if decoded is None:
            logger.error("Could not read image from path: %s", image_path)
            raise FileNotFoundError(f"Image not found or unreadable: {image_path}")
        return decoded
