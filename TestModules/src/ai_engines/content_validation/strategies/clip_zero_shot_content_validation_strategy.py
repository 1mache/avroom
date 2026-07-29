from __future__ import annotations

import logging
from typing import Callable

import cv2
import numpy as np
from PIL import Image

from ..content_validation_result import ContentValidationResult
from ..content_validation_strategy import ContentValidationStrategy

logger = logging.getLogger(__name__)

# Label groups for zero-shot CLIP scoring. Each group contributes one check.
_SCENE_POSITIVE_LABELS: tuple[str, ...] = (
    "a photo of an indoor room",
    "a photo of a living room",
    "a photo of a bedroom interior",
    "a photo of a kitchen interior",
    "a photo of an outdoor landscape",
    "a photo of a garden or patio space",
)
_SCENE_NEGATIVE_LABELS: tuple[str, ...] = (
    "a photo of a single person",
    "a photo of a product on white background",
    "a photo of a selfie",
    "a photo of one isolated object",
)
_PERSON_LABELS: tuple[str, ...] = (
    "a photo of a person",
    "a portrait photo of a person",
    "a selfie photo",
    "a close-up of a human face",
)
_PRODUCT_LABELS: tuple[str, ...] = (
    "a product photo on white background",
    "a studio product shot",
    "a single object on plain background",
    "an e-commerce product image",
)
_SCREENSHOT_LABELS: tuple[str, ...] = (
    "a screenshot of a computer screen",
    "a photo of a phone screen",
    "a photo of a monitor or TV",
    "a UI screenshot",
)
_OBSTRUCTION_LABELS: tuple[str, ...] = (
    "a photo with a hand covering the lens",
    "a photo with a finger in front of the camera",
    "a photo with a body blocking most of the view",
)
_NSFW_LABELS: tuple[str, ...] = (
    "a nude photo",
    "an explicit NSFW image",
    "a sexual image",
)
_STYLIZED_LABELS: tuple[str, ...] = (
    "an anime illustration",
    "a painting or artwork",
    "a heavily filtered Instagram photo",
    "a cartoon image",
)


class ClipZeroShotContentValidationStrategy(ContentValidationStrategy):
    """Zero-shot CLIP classifier for upload content suitability.

    Uses ``openai/clip-vit-base-patch32`` (lazy-loaded on first ``validate``).
    Thresholds are configurable at construction for testing.
    """

    DEFAULT_MODEL_ID = "openai/clip-vit-base-patch32"
    DEFAULT_POSITIVE_THRESHOLD = 0.20
    DEFAULT_NEGATIVE_THRESHOLD = 0.25

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

    def _score_labels(self, pil_image: Image.Image, labels: tuple[str, ...]) -> dict[str, float]:
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

    @staticmethod
    def _group_max(scores: dict[str, float]) -> float:
        if not scores:
            return 0.0
        return max(scores.values())

    def validate(self, image: np.ndarray) -> ContentValidationResult:
        if image.ndim != 3 or image.shape[2] != 3:
            raise ValueError("Content validation expects a BGR uint8 image with shape (H, W, 3).")

        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        pil_image = Image.fromarray(rgb)

        positive_scores = self._score_labels(pil_image, _SCENE_POSITIVE_LABELS)
        negative_scores = self._score_labels(pil_image, _SCENE_NEGATIVE_LABELS)
        person_scores = self._score_labels(pil_image, _PERSON_LABELS)
        product_scores = self._score_labels(pil_image, _PRODUCT_LABELS)
        screenshot_scores = self._score_labels(pil_image, _SCREENSHOT_LABELS)
        obstruction_scores = self._score_labels(pil_image, _OBSTRUCTION_LABELS)
        nsfw_scores = self._score_labels(pil_image, _NSFW_LABELS)
        stylized_scores = self._score_labels(pil_image, _STYLIZED_LABELS)

        positive_max = self._group_max(positive_scores)
        negative_max = self._group_max(negative_scores)
        person_max = self._group_max(person_scores)
        product_max = self._group_max(product_scores)
        screenshot_max = self._group_max(screenshot_scores)
        obstruction_max = self._group_max(obstruction_scores)
        nsfw_max = self._group_max(nsfw_scores)
        stylized_max = self._group_max(stylized_scores)

        scene_pass = positive_max >= self._positive_threshold and positive_max > negative_max
        person_pass = person_max < self._negative_threshold
        product_pass = product_max < self._negative_threshold
        screenshot_pass = screenshot_max < self._negative_threshold
        obstruction_pass = obstruction_max < self._negative_threshold
        nsfw_pass = nsfw_max < self._negative_threshold
        stylized_pass = stylized_max < self._negative_threshold

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
            "scene_positive_max": positive_max,
            "scene_negative_max": negative_max,
            "person_max": person_max,
            "product_max": product_max,
            "screenshot_max": screenshot_max,
            "obstruction_max": obstruction_max,
            "nsfw_max": nsfw_max,
            "stylized_max": stylized_max,
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
