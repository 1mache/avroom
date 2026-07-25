"""Smoke test: cutout PNG -> NovelViewFacade -> novel-view PNG grid.

Manual integration test. First run downloads ``kxic/stable-zero123`` from
Hugging Face (~5 GB Diffusers conversion of Stable Zero123 weights) and needs
CUDA for practical runtime (~SD1.5 VRAM). CPU works but is very slow.

Usage (from repo root):
    python TestModules/tests/test_novel_view_stable_zero123.py [cutout.png]

If no cutout path is given, uses ``fastApi-app/res/test/toilet.png`` with a
synthetic alpha matte when that file has no alpha channel.

Outputs are written to ``TestModules/outputs/novel_view_az*.png``.
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
    Path(__file__).resolve().parents[2] / "fastApi-app" / "res" / "test" / "toilet.png"
)
OUTPUT_DIR = Path(__file__).resolve().parents[1] / "outputs"
AZIMUTHS = (0, 45, 90, 180)


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


def run_smoke(cutout_path: Path) -> None:
    from avroom_object_removal.ai_engines.novel_view import NovelViewFacade

    cutout_bgra = _load_or_synthesize_cutout(cutout_path)
    logger.info("Loaded cutout: shape=%s path=%s", cutout_bgra.shape, cutout_path)

    facade = NovelViewFacade()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for azimuth in AZIMUTHS:
        logger.info("Generating novel view at azimuth=%d", azimuth)
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

        out_path = OUTPUT_DIR / f"novel_view_az{azimuth}.png"
        cv2.imwrite(str(out_path), result_bgra)
        logger.info("Wrote %s shape=%s", out_path, result_bgra.shape)

    logger.info("SUCCESS - inspect PNGs under %s", OUTPUT_DIR)


if __name__ == "__main__":
    cutout = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_CUTOUT
    run_smoke(cutout)
