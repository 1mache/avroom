"""Visualize all-mask SAM output across a few different depth-mapping models.

Manual harness. Uses the new Facade + Strategy public API:

* ``DepthAnythingMappingStrategy`` for depth maps
* ``SamSegmentationStrategy`` for direct ``predict_mask`` calls (we want all
  candidates from SAM, not just the tight one the facade returns)
"""

from __future__ import annotations

import os

import cv2
import numpy as np

from avroom_object_removal.ai_engines.depth.strategies.depth_anything_mapping_strategy import (
    DepthAnythingMappingStrategy,
)
from avroom_object_removal.ai_engines.segmentation.strategies.sam_segmentation_strategy import (
    SamSegmentationStrategy,
    _load_sam_predictor,
    _resolve_checkpoint_path,
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _depth_to_rgb_array(depth: np.ndarray) -> np.ndarray:
    """Adapt a (possibly grayscale) depth map to a 3-channel RGB array."""
    arr = np.array(depth)
    if arr.ndim == 2:
        arr = cv2.cvtColor(arr.astype(np.uint8), cv2.COLOR_GRAY2RGB)
    elif arr.ndim == 3 and arr.shape[2] == 4:
        arr = cv2.cvtColor(arr, cv2.COLOR_RGBA2RGB)
    return arr


def test_sam_models() -> None:
    """Generate combined SAM mask visualizations using different depth models."""
    image_path = os.path.join(BASE_DIR, "..", "inputs", "test.jpg")
    orig_image = cv2.imread(image_path)
    if orig_image is None:
        print(f"Error: could not load image at {image_path}")
        return

    # Pin one SAM strategy + predictor for the whole run.
    sam_strategy = SamSegmentationStrategy()
    predictor = _load_sam_predictor(
        str(_resolve_checkpoint_path()),
        sam_strategy.DEFAULT_MODEL_TYPE,
        sam_strategy._device,
    )

    models_to_test = [
        "LiheYoung/depth-anything-small-hf",
        "depth-anything/Depth-Anything-V2-Small-hf",
        "Intel/dpt-swinv2-tiny-256",
    ]

    out_base = os.path.join(BASE_DIR, "..", "outputs", "depthMapsSAMall")
    os.makedirs(out_base, exist_ok=True)

    for model_name in models_to_test:
        print("\n" + "=" * 50)
        print(f"Generating combined mask image for: {model_name}")

        try:
            depth_strategy = DepthAnythingMappingStrategy(model_name=model_name)
            depth_map = depth_strategy.map_depth(orig_image)
            adapted_image = _depth_to_rgb_array(depth_map)

            # Use SAM's automatic mask generator if available, else fall back
            # to a single multimask predict at image center.
            try:
                from segment_anything import SamAutomaticMaskGenerator

                generator = SamAutomaticMaskGenerator(predictor.model)
                ann = generator.generate(adapted_image)
                masks = [a["segmentation"] for a in ann]
            except Exception:
                # Fallback: just one prediction at the center.
                h, w = adapted_image.shape[:2]
                masks = [
                    sam_strategy.predict_mask(
                        adapted_image, x=w // 2, y=h // 2, expand_pixels=0
                    )
                ]

            combined_mask_img = np.zeros_like(orig_image)
            for mask in masks:
                color = np.random.randint(50, 255, (3,), dtype=np.uint8)
                bool_mask = mask > 0
                combined_mask_img[bool_mask] = color

            safe_model_name = model_name.replace("/", "_").replace("\\", "_")
            out_path = os.path.join(out_base, f"{safe_model_name}_combined.png")
            cv2.imwrite(out_path, combined_mask_img)

            print(
                f"[SUCCESS] Saved combined image with {len(masks)} separated objects to {out_path}"
            )

        except Exception as e:
            print(f"[ERROR] Failed to process with model {model_name}. Error: {e}")


if __name__ == "__main__":
    test_sam_models()
