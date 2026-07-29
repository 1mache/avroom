from __future__ import annotations

from typing import Any

import numpy as np

from avroom_object_removal import (
    BackgroundInpainter,
    ImageInpaintingFacade,
    ImageInpaintingStrategy,
)


class _SolidColorInpaintStrategy(ImageInpaintingStrategy):
    """Stub strategy that returns a uniform BGR frame regardless of input."""

    def __init__(self, color: tuple[int, int, int]) -> None:
        self._color = np.array(color, dtype=np.uint8)

    def inpaint(self, image: np.ndarray, mask: np.ndarray, **kwargs: Any) -> np.ndarray:
        return np.full_like(image, self._color)


def test_cut_mask_from_image_preserves_pixels_outside_mask() -> None:
    """Only mask-region pixels should come from the inpainting model output."""
    original = np.zeros((4, 4, 3), dtype=np.uint8)
    original[:, :] = (10, 20, 30)

    mask = np.zeros((4, 4), dtype=np.uint8)
    mask[1:3, 1:3] = 255

    model_color = (200, 100, 50)
    stub_facade = ImageInpaintingFacade(strategy=_SolidColorInpaintStrategy(model_color))
    inpainter = BackgroundInpainter(inpainting_facade=stub_facade)

    result = inpainter.cut_mask_from_image(original_image=original, mask=mask)

    mask_bool = mask > 127
    assert np.all(result[mask_bool] == np.array(model_color, dtype=np.uint8))
    assert np.array_equal(result[~mask_bool], original[~mask_bool])


def test_cut_mask_from_image_empty_mask_returns_original() -> None:
    """An empty mask should leave the original image unchanged."""
    original = np.full((3, 3, 3), (5, 15, 25), dtype=np.uint8)
    mask = np.zeros((3, 3), dtype=np.uint8)

    model_color = (99, 88, 77)
    stub_facade = ImageInpaintingFacade(strategy=_SolidColorInpaintStrategy(model_color))
    inpainter = BackgroundInpainter(inpainting_facade=stub_facade)

    result = inpainter.cut_mask_from_image(original_image=original, mask=mask)

    assert np.array_equal(result, original)
