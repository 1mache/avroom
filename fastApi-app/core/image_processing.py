from __future__ import annotations

import io
import logging

import sys
import tempfile
import types
import uuid

import cv2

from pathlib import Path

from PIL import Image, ImageDraw, UnidentifiedImageError

from schemas.image import ImageProcessingOptions


logger = logging.getLogger(__name__)


def get_image_path(image_id: str, base_dir: Path) -> Path:
    """Resolve filesystem path for a stored image regardless of extension."""

    candidates = sorted(base_dir.glob(f"{image_id}.*"))
    if not candidates:
        raise FileNotFoundError(f"No stored image found for image_id='{image_id}' in {base_dir}")
    return candidates[0]


def load_image_bytes(image_id: str, base_dir: Path) -> bytes:
    """Load raw image bytes for a given `image_id` from disk.

    The caller is responsible for handling any filesystem-related exceptions
    that may occur if the image does not exist.
    """

    image_path = get_image_path(image_id=image_id, base_dir=base_dir)
    return image_path.read_bytes()


def segment_at_click(
    image_bytes: bytes,
    x: int,
    y: int,
    options: ImageProcessingOptions | None = None,
) -> tuple[bytes, bytes, str]:
    """Segmentation stub that returns background and cutout images.

    - `image_bytes` are the bytes of the original image.
    - `x`, `y` are the click coordinates in pixels (origin top-left).
    - `options` can be used to configure the segmentation behavior.
    """

    if not image_bytes:
        return b"", b"", "png"

    # Delegate segmentation/removal to TestModules' ObjectRemover pipeline.
    # ObjectRemover expects an `image_path`, so we persist the incoming bytes as a
    # temporary PNG file first. Then we encode the two numpy-array returns back
    # into PNG bytes so the API can base64 them.

    test_src_dir = Path(__file__).resolve().parents[2] / "TestModules" / "src"
    test_core_dir = test_src_dir / "core"
    test_utils_dir = test_src_dir / "utils"
    test_ai_engines_dir = test_src_dir / "ai_engines"
    test_routing_dir = test_src_dir / "routing"

    saved_modules: dict[str, object | None] = {
        "core": sys.modules.get("core"),
        "utils": sys.modules.get("utils"),
        "ai_engines": sys.modules.get("ai_engines"),
        "routing": sys.modules.get("routing"),
    }

    def _ensure_stub_pkg(name: str, package_path: Path) -> None:
        pkg = types.ModuleType(name)
        pkg.__path__ = [str(package_path)]  # type: ignore[attr-defined]
        sys.modules[name] = pkg

    try:
        if str(test_src_dir) not in sys.path:
            sys.path.insert(0, str(test_src_dir))

        # Avoid name collisions with fastApi-app's own `core` package.
        _ensure_stub_pkg("core", test_core_dir)
        _ensure_stub_pkg("utils", test_utils_dir)
        _ensure_stub_pkg("ai_engines", test_ai_engines_dir)
        _ensure_stub_pkg("routing", test_routing_dir)

        # Lazy import: resolves against the stubbed package roots.
        from core.objectRemover import ObjectRemover  # type: ignore

        remover = ObjectRemover()

        # Persist bytes as PNG for cv2.imread compatibility.
        with Image.open(io.BytesIO(image_bytes)) as pil_img:
            pil_img = pil_img.convert("RGB")

            tmp_root = Path(tempfile.gettempdir()) / "avroom_object_remover"
            tmp_root.mkdir(parents=True, exist_ok=True)
            tmp_image_path = tmp_root / f"{uuid.uuid4()}.png"
            pil_img.save(tmp_image_path, format="PNG")

        background_bgr, cutout_bgra = remover.remove_object(str(tmp_image_path), x, y)

        ok_bg, bg_buf = cv2.imencode(".png", background_bgr)
        ok_co, co_buf = cv2.imencode(".png", cutout_bgra)
        if not ok_bg or bg_buf is None:
            raise RuntimeError("Failed to encode background image to PNG.")
        if not ok_co or co_buf is None:
            raise RuntimeError("Failed to encode cutout image to PNG.")

        background_bytes = bg_buf.tobytes()
        cutout_bytes = co_buf.tobytes()

        # Best-effort cleanup: temp file is only needed for OpenCV loading.
        try:
            tmp_image_path.unlink(missing_ok=True)  # type: ignore[attr-defined]
        except Exception:
            pass

        return background_bytes, cutout_bytes, "png"
    finally:
        # Restore module bindings to avoid impacting other fastApi-app imports.
        for name, mod in saved_modules.items():
            if mod is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = mod


def process_click_on_image(
    image_id: str,
    base_dir: Path,
    x: int,
    y: int,
    options: ImageProcessingOptions | None = None,
) -> tuple[bytes, bytes, str]:
    """High-level click-based processing function wired to disk storage.

    This helper ties together the idea of an `image_id` (used by the API) and
    the pure segmentation logic defined in `segment_at_click`.
    """

    image_path = get_image_path(image_id=image_id, base_dir=base_dir)
    image_bytes = load_image_bytes(image_id=image_id, base_dir=base_dir)

    try:
        with Image.open(io.BytesIO(image_bytes)) as source_image:
            width, height = source_image.size

            # bounds check
            if not (0 <= x < width and 0 <= y < height):
                logger.error(
                    "Click out of bounds for image_id='%s': x=%d y=%d image_width=%d image_height=%d",
                    image_id,
                    x,
                    y,
                    width,
                    height,
                )
                raise ValueError(f"Click coordinates (x={x}, y={y}) are out of bounds for image size {width}x{height}.")

            debug_image = source_image.convert("RGB")

            draw = ImageDraw.Draw(debug_image)
            radius = 6
            draw.ellipse(
                (x - radius, y - radius, x + radius, y + radius),
                fill="red",
                outline="white",
                width=2,
            )

            tmp_dir = base_dir / "tmp"
            tmp_dir.mkdir(parents=True, exist_ok=True)
            debug_image_path = tmp_dir / f"{image_id}_debug{image_path.suffix}"
            debug_image.save(debug_image_path)
    except UnidentifiedImageError:
        logger.exception("Unable to open image bytes for image_id='%s'", image_id)

    background_bytes, cutout_bytes, image_format = segment_at_click(
        image_bytes=image_bytes,
        x=x,
        y=y,
        options=options,
    )
    return background_bytes, cutout_bytes, image_format

