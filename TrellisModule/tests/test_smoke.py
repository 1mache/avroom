"""Smoke test: ObjectRemover cutout -> Trellis3DGenerator -> GLB bytes.

This is a MANUAL integration test. It hits the live Hugging Face Space
(microsoft/TRELLIS.2) and runs the full ObjectRemover pipeline, so it is
slow (model load + queue wait). Run it explicitly, never in CI.

Usage (from repo root):
    python TrellisModule/tests/test_smoke.py

Requirements:
    pip install -r requirements.txt
    pip install -e ./TrellisModule

Update IMAGE_PATH and CLICK_POINT to match a test image you have locally.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

# Allow running from repo root without installing
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "TestModules" / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("test_smoke")


# -- CONFIGURE THESE --
IMAGE_PATH = str(Path(__file__).resolve().parents[2] / "TestModules" / "inputs" / "test.jpg")
CLICK_POINT = (825, 825)  # (x, y) pixel in the image to segment
# ---------------------


def test_full_pipeline() -> None:
    from avroom_object_removal import ObjectRemover
    from avroom_trellis import Quality, Trellis3DGenerator

    # Verify test image exists
    if not Path(IMAGE_PATH).exists():
        logger.warning("IMAGE_PATH not found: %s — skipping ObjectRemover step", IMAGE_PATH)
        test_direct_input()
        return

    logger.info("Step 1: Running ObjectRemover on %s point=%s", IMAGE_PATH, CLICK_POINT)
    remover = ObjectRemover()
    with open(IMAGE_PATH, "rb") as f:
        image_bytes = f.read()

    _bg_bgr, cutout_bgra = remover.remove_object(
        image_path=IMAGE_PATH,
        x=CLICK_POINT[0],
        y=CLICK_POINT[1],
        image_bytes=image_bytes,
    )
    logger.info(
        "ObjectRemover done: cutout shape=%s dtype=%s",
        cutout_bgra.shape,
        cutout_bgra.dtype,
    )

    logger.info("Step 2: Generating GLB via Trellis 2 (quality=FAST)...")
    generator = Trellis3DGenerator()
    glb_bytes = generator.generate(cutout_bgra, quality=Quality.FAST)

    _assert_glb(glb_bytes)

    out_path = Path(__file__).parent / "output_smoke.glb"
    out_path.write_bytes(glb_bytes)
    logger.info("GLB written to: %s (%d bytes)", out_path, len(glb_bytes))
    logger.info("SUCCESS — open the GLB at https://gltf-viewer.donmccurdy.com/")


def test_direct_input() -> None:
    """Minimal test: pass a solid-color RGBA image without ObjectRemover."""

    import numpy as np
    from avroom_trellis import Quality, Trellis3DGenerator

    logger.info("test_direct_input: creating synthetic BGRA input...")
    # 256x256 solid red square with full alpha
    arr = np.zeros((256, 256, 4), dtype=np.uint8)
    arr[:, :, 2] = 200  # red channel (BGR order)
    arr[:, :, 3] = 255  # alpha

    generator = Trellis3DGenerator()
    glb_bytes = generator.generate(arr, quality=Quality.FAST)

    _assert_glb(glb_bytes)
    logger.info("test_direct_input PASSED: GLB magic OK, size=%d bytes", len(glb_bytes))


def test_type_error() -> None:
    """Non-image bytes must raise TypeError / ValueError."""

    from avroom_trellis import Trellis3DGenerator

    generator = Trellis3DGenerator()
    try:
        generator.generate(b"this is not an image")
        raise AssertionError("Expected ValueError not raised.")
    except ValueError:
        logger.info("test_type_error PASSED: ValueError raised for non-image bytes.")


def _assert_glb(data: bytes) -> None:
    assert isinstance(data, bytes), f"Expected bytes, got {type(data)}"
    assert len(data) > 0, "GLB bytes are empty."
    assert data[:4] == b"glTF", (
        f"Missing GLB magic bytes. Got: {data[:4]!r}. "
        "The Space may have returned an error response."
    )


if __name__ == "__main__":
    test_type_error()
    test_full_pipeline()
