from __future__ import annotations

import logging
from typing import Callable

import cv2
import numpy as np
from PIL import Image

from ..content_validation_result import ContentValidationResult
from ..content_validation_strategy import ContentValidationStrategy

logger = logging.getLogger(__name__)

# Binary CLIP contests: one concept label vs one concrete room/space alternative.
_SCENE_LABEL = "a photo of an indoor room or outdoor space"
_SCENE_ALTERNATIVE_LABEL = "a photo of something else"
_PERSON_LABEL = "a photo of a person, selfie, or portrait"
_PERSON_ALTERNATIVE_LABEL = "a photo of an empty room or outdoor space"
_PRODUCT_LABEL = "a product photo on plain background"
_PRODUCT_ALTERNATIVE_LABEL = "a photo of a room or outdoor space"
_SCREENSHOT_LABEL = "a screenshot or photo of a screen"
_SCREENSHOT_ALTERNATIVE_LABEL = "a photo of a real room or outdoor space"
_OBSTRUCTION_LABEL = "a photo with a hand or body blocking the camera"
_OBSTRUCTION_ALTERNATIVE_LABEL = "a clear photo of a room or outdoor space"
_NSFW_LABEL = "an explicit NSFW or nude photo"
_NSFW_ALTERNATIVE_LABEL = "a normal photo of a room or outdoor space"
_STYLIZED_LABEL = "an anime, painting, cartoon, or heavily filtered image"
_STYLIZED_ALTERNATIVE_LABEL = "a real photograph of a room or outdoor space"


class ClipZeroShotContentValidationStrategy(ContentValidationStrategy):
    """Zero-shot CLIP classifier for upload content suitability.

    Each gate runs a 2-label softmax (concept vs concrete room/space).
    Uses ``openai/clip-vit-base-patch32`` (lazy-loaded on first ``score_labels``
    / ``validate``). ``score_labels`` and ``binary_prob`` are the public scoring
    API reused by core cutout selection. Thresholds are configurable at
    construction for testing.
    """

    DEFAULT_MODEL_ID = "openai/clip-vit-base-patch32"
    DEFAULT_POSITIVE_THRESHOLD = 0.5
    DEFAULT_NEGATIVE_THRESHOLD = 0.5

    def __init__(
        self,
        *,
        model_id: str = DEFAULT_MODEL_ID,
        positive_threshold: float = DEFAULT_POSITIVE_THRESHOLD,
        negative_threshold: float = DEFAULT_NEGATIVE_THRESHOLD,
        score_fn: Callable[[Image.Image, tuple[str, ...]], dict[str, float]] | None = None,
    ) -> None:
        self._model_id = model_id
        self._positive_threshold = positive_threshold
        self._negative_threshold = negative_threshold
        self._score_fn = score_fn
        self._model: object | None = None
        self._processor: object | None = None
        logger.info(
            "ClipZeroShotContentValidationStrategy configured (model=%s)",
            model_id,
        )

    def _ensure_model(self) -> tuple[object, object]:
        if self._model is not None and self._processor is not None:
            return self._model, self._processor

        from transformers import CLIPModel, CLIPProcessor

        logger.info("Loading CLIP model for content validation: %s", self._model_id)
        self._processor = CLIPProcessor.from_pretrained(self._model_id)
        self._model = CLIPModel.from_pretrained(self._model_id)
        getattr(self._model, "eval")()
        return self._model, self._processor

    def score_labels(self, pil_image: Image.Image, labels: tuple[str, ...]) -> dict[str, float]:
        """Return a softmax distribution over ``labels`` for ``pil_image``."""
        if self._score_fn is not None:
            return self._score_fn(pil_image, labels)

        import torch
        from transformers import CLIPProcessor

        model, processor = self._ensure_model()
        assert isinstance(processor, CLIPProcessor)

        inputs = processor(
            text=list(labels),
            images=pil_image,
            return_tensors="pt",
            padding=True,
        )
        with torch.no_grad():
            outputs = model(**inputs)
            logits_per_image = outputs.logits_per_image
            probs = logits_per_image.softmax(dim=1).squeeze(0)

        return {label: float(probs[index].item()) for index, label in enumerate(labels)}

    def binary_prob(self, pil_image: Image.Image, positive: str, negative: str) -> float:
        """Return P(positive) from a 2-label softmax over positive vs negative."""
        scores = self.score_labels(pil_image, (positive, negative))
        return scores[positive]

    def validate(self, image: np.ndarray) -> ContentValidationResult:
        if image.ndim != 3 or image.shape[2] != 3:
            raise ValueError("Content validation expects a BGR uint8 image with shape (H, W, 3).")

        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        pil_image = Image.fromarray(rgb)

        scene_p = self.binary_prob(pil_image, _SCENE_LABEL, _SCENE_ALTERNATIVE_LABEL)
        person_p = self.binary_prob(pil_image, _PERSON_LABEL, _PERSON_ALTERNATIVE_LABEL)
        product_p = self.binary_prob(pil_image, _PRODUCT_LABEL, _PRODUCT_ALTERNATIVE_LABEL)
        screenshot_p = self.binary_prob(pil_image, _SCREENSHOT_LABEL, _SCREENSHOT_ALTERNATIVE_LABEL)
        obstruction_p = self.binary_prob(pil_image, _OBSTRUCTION_LABEL, _OBSTRUCTION_ALTERNATIVE_LABEL)
        nsfw_p = self.binary_prob(pil_image, _NSFW_LABEL, _NSFW_ALTERNATIVE_LABEL)
        stylized_p = self.binary_prob(pil_image, _STYLIZED_LABEL, _STYLIZED_ALTERNATIVE_LABEL)

        scene_pass = scene_p >= self._positive_threshold
        person_pass = person_p < self._negative_threshold
        product_pass = product_p < self._negative_threshold
        screenshot_pass = screenshot_p < self._negative_threshold
        obstruction_pass = obstruction_p < self._negative_threshold
        nsfw_pass = nsfw_p < self._negative_threshold
        stylized_pass = stylized_p < self._negative_threshold

        checks = {
            "scene_space_or_landscape": scene_pass,
            "not_person_centric": person_pass,
            "not_product_shot": product_pass,
            "not_screenshot": screenshot_pass,
            "not_obstructed": obstruction_pass,
            "not_nsfw": nsfw_pass,
            "not_heavily_stylized": stylized_pass,
        }

        scores: dict[str, float] = {
            "scene_p": scene_p,
            "person_p": person_p,
            "product_p": product_p,
            "screenshot_p": screenshot_p,
            "obstruction_p": obstruction_p,
            "nsfw_p": nsfw_p,
            "stylized_p": stylized_p,
        }

        messages: list[str] = []
        if not scene_pass:
            messages.append("Image does not appear to be a room or landscape space.")
        if not person_pass:
            messages.append("Image appears to be person-centric (portrait or selfie).")
        if not product_pass:
            messages.append("Image appears to be a product or single-object studio shot.")
        if not screenshot_pass:
            messages.append("Image appears to be a screenshot or photo of a screen.")
        if not obstruction_pass:
            messages.append("Image appears to have a large foreground obstruction.")
        if not nsfw_pass:
            messages.append("Image appears to contain NSFW content.")
        if not stylized_pass:
            messages.append("Image appears heavily stylized or non-photographic.")

        is_valid = all(checks.values())
        logger.info(
            "CLIP content validation finished: is_valid=%s checks=%s",
            is_valid,
            checks,
        )
        return ContentValidationResult(
            is_valid=is_valid,
            checks=checks,
            scores=scores,
            messages=tuple(messages),
        )
