from __future__ import annotations

import logging
import os
from typing import Final

import cv2
import numpy as np

logger = logging.getLogger(__name__)

_DEFAULT_OUTPUT_FOLDER: Final[str] = "outputs"


class DebugImageSaver:
    """Write intermediate / debug images to a fixed `outputs/` directory.

    The output directory is resolved relative to the repository's
    ``TestModules/`` folder (i.e. two parents above this file), so that all
    pipeline stages share one canonical location regardless of which entry
    point triggered them.
    """

    def __init__(self, output_folder_name: str = _DEFAULT_OUTPUT_FOLDER) -> None:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        # Go two levels up: utils -> src -> TestModules.
        self.project_root = os.path.abspath(os.path.join(current_dir, "..", ".."))
        self.output_dir = os.path.join(self.project_root, output_folder_name)
        os.makedirs(self.output_dir, exist_ok=True)
        logger.info(f"DebugImageSaver initialized. Saving to: {self.output_dir}")

    def save(self, filename: str, image: np.ndarray) -> str:
        """Save a numpy image to the outputs directory.

        Boolean masks are upcast to ``uint8`` 0/255 before writing so OpenCV
        produces a visible PNG instead of an effectively empty file.
        """
        if image is None or not isinstance(image, np.ndarray):
            logger.warning(f"Cannot save {filename}: invalid image data.")
            return ""

        save_image = image
        if save_image.dtype == bool:
            save_image = (save_image * 255).astype(np.uint8)

        if not filename.lower().endswith((".png", ".jpg", ".jpeg")):
            filename += ".png"

        filepath = os.path.join(self.output_dir, filename)

        try:
            cv2.imwrite(filepath, save_image)
            logger.debug(f"[DEBUG SAVER] Image saved successfully: {filename}")
            return filepath
        except Exception as e:
            logger.error(f"[DEBUG SAVER] Failed to save {filename}: {e}")
            return ""
