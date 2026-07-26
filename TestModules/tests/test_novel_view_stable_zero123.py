"""Smoke test: cutout PNG -> NovelViewFacade -> novel-view PNG grid.

Manual integration test. First run downloads ``kxic/stable-zero123`` from
Hugging Face (~5 GB Diffusers conversion of Stable Zero123 weights) and needs
CUDA for practical runtime (~SD1.5 VRAM). CPU works but is very slow.

Usage (from repo root):
    python TestModules/tests/test_novel_view_stable_zero123.py [cutout.png]

If no cutout path is given, uses ``fastApi-app/res/test/toilet.png`` with a
synthetic alpha matte when that file has no alpha channel.

Debug outputs land under ``TestModules/outputs/novel_view_rotation_debug/``:

- ``preprocessing/`` — input transforms before Zero123 sees the image
- ``final_results/`` — model-generated novel views (one PNG per azimuth)
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("test_novel_view_stable_zero123")

DEFAULT_CUTOUT = (
    Path(__file__).resolve().parents[2]
    / "fastApi-app"
    / "tmp"
    / "images"
    / "10643e68-0e33-4d5a-be49-41aeff9ac34f_0_cutout.png"
)
OUTPUT_DIR = (
    Path(__file__).resolve().parents[1]
    / "outputs"
    / "novel_view_rotation_debug"
)
PREPROCESS_DIR = OUTPUT_DIR / "preprocessing"
FINAL_RESULTS_DIR = OUTPUT_DIR / "final_results"
AZIMUTHS = (-40, -30, -20, -10, 0, 10, 20, 30, 40)


def _load_or_synthesize_cutout(path: Path) -> np.ndarray:
    """Load a cutout PNG or build a synthetic RGBA from an opaque test image."""

    if not path.exists():
        raise FileNotFoundError(f"Cutout not found: {path}")

    decoded = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
    if decoded is None:
        raise ValueError(f"Cannot decode image: {path}")

    if decoded.ndim == 3 and decoded.shape[2] == 4:
        return decoded

    if decoded.ndim == 3 and decoded.shape[2] == 3:
        logger.warning("Input has no alpha; synthesizing a centered object matte")
        height, width = decoded.shape[:2]
        bgra = cv2.cvtColor(decoded, cv2.COLOR_BGR2BGRA)
        alpha = np.zeros((height, width), dtype=np.uint8)
        margin_x = width // 6
        margin_y = height // 6
        alpha[margin_y : height - margin_y, margin_x : width - margin_x] = 255
        bgra[:, :, 3] = alpha
        return bgra

    raise ValueError(f"Unsupported image shape: {decoded.shape}")


def _save_preprocessing_stages(cutout_bgra: np.ndarray, azimuth: int) -> None:
    """Save every input transformation performed before Zero123 inference."""

    from PIL import Image

    from avroom_object_removal.ai_engines.novel_view.novel_view_preprocess import (
        DEFAULT_MODEL_SIZE,
        crop_alpha_bbox,
        pad_to_square,
        rgba_to_rgb_on_white,
    )
    from avroom_object_removal.ai_engines.reconstruction_3d.reconstruction_image_input import (
        to_pil_rgba,
    )

    filename_prefix = f"azimuth_{azimuth:+04d}deg"

    original_path = (
        PREPROCESS_DIR
        / f"{filename_prefix}_stage_00_original_full_canvas_bgra.png"
    )
    cv2.imwrite(str(original_path), cutout_bgra)

    normalized_rgba = to_pil_rgba(cutout_bgra)
    normalized_rgba.save(
        PREPROCESS_DIR
        / f"{filename_prefix}_stage_01_normalized_full_canvas_rgba.png"
    )

    cropped_rgba, _ = crop_alpha_bbox(normalized_rgba)
    cropped_rgba.save(
        PREPROCESS_DIR
        / f"{filename_prefix}_stage_02_tight_alpha_bounding_box_crop_rgba.png"
    )

    square_padded_rgba = pad_to_square(cropped_rgba)
    square_padded_rgba.save(
        PREPROCESS_DIR
        / f"{filename_prefix}_stage_03_centered_square_transparent_padding_rgba.png"
    )

    resized_rgba = square_padded_rgba.resize(
        (DEFAULT_MODEL_SIZE, DEFAULT_MODEL_SIZE),
        Image.Resampling.LANCZOS,
    )
    resized_rgba.save(
        PREPROCESS_DIR
        / (
            f"{filename_prefix}_stage_04_resized_"
            f"{DEFAULT_MODEL_SIZE}x{DEFAULT_MODEL_SIZE}_rgba.png"
        )
    )

    model_input_rgb = rgba_to_rgb_on_white(resized_rgba)
    model_input_rgb.save(
        PREPROCESS_DIR
        / (
            f"{filename_prefix}_stage_05_exact_model_input_"
            f"{DEFAULT_MODEL_SIZE}x{DEFAULT_MODEL_SIZE}_rgb.png"
        )
    )

    logger.info(
        "Saved preprocessing debug stages: azimuth=%d directory=%s",
        azimuth,
        PREPROCESS_DIR,
    )


def run_smoke(cutout_path: Path) -> None:
    from avroom_object_removal.ai_engines.novel_view import NovelViewFacade

    cutout_bgra = _load_or_synthesize_cutout(cutout_path)
    logger.info("Loaded cutout: shape=%s path=%s", cutout_bgra.shape, cutout_path)

    facade = NovelViewFacade()
    PREPROCESS_DIR.mkdir(parents=True, exist_ok=True)
    FINAL_RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    for azimuth in AZIMUTHS:
        logger.info("Generating novel view at azimuth=%d", azimuth)
        _save_preprocessing_stages(cutout_bgra, azimuth)
        result_bgra = facade.synthesize(
            cutout_bgra,
            elevation_deg=0.0,
            azimuth_deg=float(azimuth),
            relative_elevation_deg=0.0,
            radius=0.0,
            seed=0,
        )
        assert result_bgra.dtype == np.uint8
        assert result_bgra.ndim == 3 and result_bgra.shape[2] == 4

        out_path = FINAL_RESULTS_DIR / (
            f"azimuth_{azimuth:+04d}deg_"
            "generated_novel_view_full_canvas_bgra.png"
        )
        cv2.imwrite(str(out_path), result_bgra)
        logger.info("Wrote %s shape=%s", out_path, result_bgra.shape)

    logger.info(
        "SUCCESS - inspect PNGs under %s (preprocessing/) and %s (final_results/)",
        PREPROCESS_DIR,
        FINAL_RESULTS_DIR,
    )


if __name__ == "__main__":
    cutout = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_CUTOUT
    run_smoke(cutout)
