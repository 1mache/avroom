from __future__ import annotations

"""Import a user-supplied PNG cutout into an existing session.

Processing and content validation are deliberately minimal today — only decode,
size, and alpha checks run. ``validate_import_cutout`` is the seam where a
future CLIP / inference-pool pipeline will plug in (mirroring upload validation).
"""

import io
import logging
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, UnidentifiedImageError

from core.cutout_bounds import extract_cutout_bounds_from_png_bytes
from core.depth_cache import content_hash_for_bytes
from core.image_codec import encode_png
from core.image_processing import load_canvas_bytes
from core.object_metadata import ObjectMetadata, create_object_metadata, next_object_id, save_object_metadata
from core.object_storage import object_cutout_path
from core.repositories.session_repo import touch_session
from schemas.common import DEFAULT_SOURCE_ELEVATION_DEG
from settings import get_upload_max_bytes

logger = logging.getLogger(__name__)

# ponytail: replace with depth/elevation pipeline when import validation lands.
_PLACEHOLDER_AVERAGE_DEPTH = 128.0

_ALLOWED_MIME_TYPES = frozenset({"image/png"})
_ALLOWED_EXTENSIONS = frozenset({".png"})


class ImportValidationError(ValueError):
    """Raised when an import file fails pre-persistence validation."""


def validate_import_cutout(
    file_bytes: bytes,
    *,
    filename: str | None = None,
    content_type: str | None = None,
) -> Image.Image:
    """Run import-time validation and return a decoded RGBA image.

    Future CLIP/content checks belong here (or behind an inference-pool job
    called from this function) — not in the route handler.
    """
    if len(file_bytes) > get_upload_max_bytes():
        raise ImportValidationError(
            f"Import file exceeds the maximum size of {get_upload_max_bytes()} bytes.",
        )

    if content_type and content_type not in _ALLOWED_MIME_TYPES:
        raise ImportValidationError("Only PNG cutouts are supported for import.")

    if filename:
        suffix = Path(filename).suffix.lower()
        if suffix and suffix not in _ALLOWED_EXTENSIONS:
            raise ImportValidationError("Only PNG cutouts are supported for import.")

    try:
        image = Image.open(io.BytesIO(file_bytes))
        image.load()
    except UnidentifiedImageError as exc:
        raise ImportValidationError("File is not a valid PNG image.") from exc

    if image.format and image.format.upper() != "PNG":
        raise ImportValidationError("Only PNG cutouts are supported for import.")

    rgba = image.convert("RGBA")
    alpha = np.array(rgba)[:, :, 3]
    if not np.any(alpha > 0):
        raise ImportValidationError("Cutout PNG has no visible pixels (empty alpha).")

    # Future: ContentImageValidator / inference-pool VALIDATE_IMPORT_CONTENT here.

    logger.debug(
        "Import cutout validated: bytes=%d size=%dx%d filename=%r",
        len(file_bytes),
        rgba.width,
        rgba.height,
        filename,
    )
    return rgba


def _crop_to_alpha_bounds(cutout_rgba: Image.Image) -> Image.Image:
    """Tight-crop *cutout_rgba* to its visible pixels.

    Full-frame cutouts exported from a room photo are often canvas-sized with
    mostly transparent padding; cropping first accepts those without rejecting
    on PNG dimensions alone.
    """
    alpha = np.array(cutout_rgba)[:, :, 3]
    visible = alpha > 0
    if not np.any(visible):
        raise ImportValidationError("Cutout PNG has no visible pixels (empty alpha).")

    ys, xs = np.where(visible)
    left = int(xs.min())
    right = int(xs.max()) + 1
    top = int(ys.min())
    bottom = int(ys.max()) + 1
    return cutout_rgba.crop((left, top, right, bottom))


def _scale_to_fit_canvas(
    cutout_rgba: Image.Image,
    *,
    canvas_width: int,
    canvas_height: int,
) -> Image.Image:
    """Shrink *cutout_rgba* uniformly when its crop still exceeds the session canvas."""
    import_width, import_height = cutout_rgba.size
    if import_width <= canvas_width and import_height <= canvas_height:
        return cutout_rgba

    scale = min(canvas_width / import_width, canvas_height / import_height)
    new_width = max(1, int(round(import_width * scale)))
    new_height = max(1, int(round(import_height * scale)))
    return cutout_rgba.resize((new_width, new_height), Image.Resampling.LANCZOS)


def normalize_to_session_canvas(
    cutout_rgba: Image.Image,
    *,
    canvas_width: int,
    canvas_height: int,
) -> bytes:
    """Crop to visible pixels, fit within the session canvas, then center-paste."""
    cutout_rgba = _crop_to_alpha_bounds(cutout_rgba)
    cutout_rgba = _scale_to_fit_canvas(
        cutout_rgba,
        canvas_width=canvas_width,
        canvas_height=canvas_height,
    )
    import_width, import_height = cutout_rgba.size

    canvas = Image.new("RGBA", (canvas_width, canvas_height), (0, 0, 0, 0))
    offset_x = (canvas_width - import_width) // 2
    offset_y = (canvas_height - import_height) // 2
    canvas.paste(cutout_rgba, (offset_x, offset_y), cutout_rgba)

    bgra = cv2.cvtColor(np.array(canvas), cv2.COLOR_RGBA2BGRA)
    png_bytes = encode_png(bgra, "import cutout")
    bounds = extract_cutout_bounds_from_png_bytes(png_bytes)
    if bounds is None or bounds.left >= bounds.right or bounds.top >= bounds.bottom:
        raise ImportValidationError("Cutout PNG has no visible pixels (empty alpha).")
    return png_bytes


def _session_canvas_size(base_dir: Path, session_id: str) -> tuple[int, int]:
    canvas_bytes = load_canvas_bytes(session_id, base_dir)
    with Image.open(io.BytesIO(canvas_bytes)) as canvas:
        return canvas.size


def import_object_cutout(
    *,
    session_id: str,
    base_dir: Path,
    file_bytes: bytes,
    filename: str | None = None,
    content_type: str | None = None,
) -> ObjectMetadata:
    """Validate, normalize, and persist one imported cutout as a new session object."""
    cutout_rgba = validate_import_cutout(file_bytes, filename=filename, content_type=content_type)
    canvas_width, canvas_height = _session_canvas_size(base_dir, session_id)
    cutout_bytes = normalize_to_session_canvas(
        cutout_rgba,
        canvas_width=canvas_width,
        canvas_height=canvas_height,
    )

    canvas_bytes = load_canvas_bytes(session_id, base_dir)
    content_hash = content_hash_for_bytes(canvas_bytes)
    object_id = next_object_id(session_id)

    metadata = create_object_metadata(
        session_id=session_id,
        object_id=object_id,
        average_depth=_PLACEHOLDER_AVERAGE_DEPTH,
        content_hash=content_hash,
        source_elevation_deg=DEFAULT_SOURCE_ELEVATION_DEG,
    )
    object_cutout_path(base_dir, session_id, object_id).write_bytes(cutout_bytes)
    save_object_metadata(metadata)
    touch_session(session_id)

    logger.info(
        "Object import complete: session_id=%s object_id=%d object_uuid=%s canvas=%dx%d",
        session_id,
        object_id,
        metadata.uuid,
        canvas_width,
        canvas_height,
    )
    return metadata
