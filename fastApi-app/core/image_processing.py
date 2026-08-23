from __future__ import annotations

import functools
import io
import logging
from dataclasses import dataclass

import cv2
import numpy as np

from pathlib import Path

from PIL import Image, ImageDraw, UnidentifiedImageError

from schemas.image import ImageProcessingOptions, VerifyMode
from core.avroom_package import load_avroom_attr
from core.image_codec import encode_png
from core.mask_cache import delete_candidates, load_cutout_bytes, load_refined_mask, save_candidate
from core.inference_pool.session_runtime import mask_id_for_candidate_slot
from core.object_storage import current_background_path, object_cutout_path, resolve_object_cutout_path
from core.depth_cache import (
    compute_average_depth_over_mask,
    get_or_compute_depth,
    memory_image_key,
)
from core.camera_calib_cache import load_camera_calib
from core.camera_calibration import cache_dict_to_calibration_result
from core.object_metadata import ObjectMetadata, create_object_metadata, get_object_by_uuid, set_object_rescale_state
from core.inference_lock import inference_session


logger = logging.getLogger(__name__)

# Debug click overlays live in their own subdirectory so they are never picked
# up by the session artifact globs that scan the storage dir itself.
DEBUG_DIR_SUBPATH = "point"
_DEBUG_MARKER_RADIUS_PX = 6
_DEBUG_MARKER_OUTLINE_PX = 2


def debug_click_image_path(base_dir: Path, image_id: str) -> Path:
    """Return the canonical path of a session's debug click overlay."""

    return base_dir / DEBUG_DIR_SUBPATH / f"{image_id}_debug.png"


@functools.lru_cache(maxsize=1)
def _get_cutout_clip_scorer():
    """Lazy singleton CLIP scorer for auto mask pick (same model as upload validation)."""
    try:
        from avroom_object_removal import ClipZeroShotContentValidationStrategy
    except ModuleNotFoundError as exc:
        if exc.name == "avroom_object_removal":
            logger.error("avroom_object_removal package not importable")
            raise RuntimeError(
                "Missing local package `avroom_object_removal`. Install repo dependencies or run `pip install -e ./TestModules`."
            ) from exc
        raise
    return ClipZeroShotContentValidationStrategy()


@functools.lru_cache(maxsize=1)
def _get_cutout_tiebreaker():
    """Lazy Gemini picker when ``GEMINI_API_KEY`` is configured.

    All-candidates mode: heuristic scores cannot rank thin-structure
    completeness (chair legs), so every consensus-cluster candidate goes to
    Gemini instead of only the tie-band top scorers.
    """
    import os

    from avroom_object_removal import GeminiCutoutAllCandidatesTiebreakStrategy
    from avroom_object_removal.ai_engines.gemini.gemini_client import (
        PLACEHOLDER_API_KEY,
        has_real_api_key,
    )

    key = os.environ.get("GEMINI_API_KEY", PLACEHOLDER_API_KEY)
    if not has_real_api_key(key):
        return None
    return GeminiCutoutAllCandidatesTiebreakStrategy()


def _create_debug_click_image(
    source_image: Image.Image,
    x: int,
    y: int,
    base_dir: Path,
    image_id: str,
) -> None:
    """Create RGB debug image with a marker drawn at click coordinates."""

    debug_image: Image.Image = source_image.convert("RGB")
    draw = ImageDraw.Draw(debug_image)
    draw.ellipse(
        (
            x - _DEBUG_MARKER_RADIUS_PX,
            y - _DEBUG_MARKER_RADIUS_PX,
            x + _DEBUG_MARKER_RADIUS_PX,
            y + _DEBUG_MARKER_RADIUS_PX,
        ),
        fill="red",
        outline="white",
        width=_DEBUG_MARKER_OUTLINE_PX,
    )

    debug_image_path = debug_click_image_path(base_dir, image_id)
    debug_image_path.parent.mkdir(parents=True, exist_ok=True)
    debug_image.save(debug_image_path)


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


def load_canvas_bytes(image_id: str, base_dir: Path) -> bytes:
    """Load the cumulative background canvas bytes for progressive removal.

    For progressive removal, each subsequent segmentation/inpainting operation
    should work on the latest state of the room — i.e., the canvas that already
    has previously removed objects replaced by inpainted background. If such a
    canvas exists (``{image_id}_background.png``), it is returned; otherwise the
    original upload is used as the starting point.

    Args:
        image_id: Session image identifier.
        base_dir: Directory that contains session artifacts.

    Returns:
        Raw PNG/image bytes of the canvas (background if available, original otherwise).
    """

    canvas_path = current_background_path(base_dir, image_id)
    if canvas_path.exists():
        canvas_bytes = canvas_path.read_bytes()
        logger.debug(
            "Loaded canvas bytes: image_id=%s source=background bytes=%d",
            image_id,
            len(canvas_bytes),
        )
        return canvas_bytes

    original_bytes = load_image_bytes(image_id=image_id, base_dir=base_dir)
    logger.debug(
        "Loaded canvas bytes: image_id=%s source=original bytes=%d",
        image_id,
        len(original_bytes),
    )
    return original_bytes


def _validate_click_coordinates(image_bytes: bytes, x: int, y: int, base_dir: Path, image_id: str) -> None:
    """Validate natural-image click coordinates and write debug click overlay."""

    try:
        with Image.open(io.BytesIO(image_bytes)) as source_image:
            width, height = source_image.size

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
            logger.debug(
                "Click within bounds: image_id=%s click=(%d,%d) size=%dx%d",
                image_id,
                x,
                y,
                width,
                height,
            )

            _create_debug_click_image(source_image, x, y, base_dir, image_id)
            logger.debug("Saved debug click overlay: image_id=%s", image_id)

    except UnidentifiedImageError as exc:
        logger.exception("Unable to open image bytes for image_id='%s'", image_id)
        raise ValueError(f"Stored file for image_id='{image_id}' is not a valid image.") from exc


def _decode_original_bgr(image_bytes: bytes, image_id: str) -> np.ndarray:
    """Decode stored image bytes into OpenCV BGR array for inpainting."""

    decoded = cv2.imdecode(np.frombuffer(image_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
    if decoded is None:
        logger.error("Could not decode original image bytes: image_id=%s", image_id)
        raise ValueError(f"Stored file for image_id='{image_id}' is not a valid image.")
    return decoded


def _decode_cutout_alpha(cutout_bytes: bytes, image_id: str, mask_id: str) -> np.ndarray:
    """Decode cached cutout PNG alpha channel as a compose mask."""

    decoded = cv2.imdecode(np.frombuffer(cutout_bytes, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
    if decoded is None or decoded.ndim < 3 or decoded.shape[2] < 4:
        logger.error(
            "Could not decode cutout alpha: image_id=%s mask_id=%s shape=%s",
            image_id,
            mask_id,
            None if decoded is None else decoded.shape,
        )
        raise ValueError(
            f"Cached cutout for image_id='{image_id}', mask_id='{mask_id}' is not a valid BGRA PNG."
        )
    return decoded[:, :, 3]


def segment_at_click(
    image_bytes: bytes,
    x: int,
    y: int,
    options: ImageProcessingOptions | None = None,
    session_id: str | None = None,
    base_dir: Path | None = None,
) -> tuple[bytes, bytes, str]:
    """Segmentation stub that returns background and cutout images.

    - `image_bytes` are the bytes of the original image.
    - `x`, `y` are the click coordinates in pixels (origin top-left).
    - `options` can be used to configure the segmentation behavior.
    """

    if not image_bytes:
        logger.warning("segment_at_click called with empty bytes — returning empty result")
        return b"", b"", "png"

    remover = load_avroom_attr("ObjectRemover")()
    image_key = memory_image_key(image_bytes)

    depth_map = None
    if session_id is not None and base_dir is not None:
        depth_map, _ = get_or_compute_depth(
            base_dir,
            session_id,
            image_bytes,
            remover.depth.map_depth,
        )

    logger.info("Running ObjectRemover: image_key=%s click=(%d,%d)", image_key, x, y)
    background_bgr, cutout_bgra = remover.remove_object(
        image_path=image_key,
        x=x,
        y=y,
        image_bytes=image_bytes,
        depth_map=depth_map,
    )
    logger.info(
        "ObjectRemover finished: bg_shape=%s cutout_shape=%s",
        background_bgr.shape,
        cutout_bgra.shape,
    )

    background_bytes = encode_png(background_bgr, "background")
    cutout_bytes = encode_png(cutout_bgra, "cutout")
    logger.debug(
        "Encoded result: bg_bytes=%d cutout_bytes=%d",
        len(background_bytes),
        len(cutout_bytes),
    )
    return background_bytes, cutout_bytes, "png"


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

    image_bytes = load_image_bytes(image_id=image_id, base_dir=base_dir)
    logger.debug("Loaded image bytes: image_id=%s bytes=%d", image_id, len(image_bytes))

    _validate_click_coordinates(image_bytes, x, y, base_dir, image_id)

    with inference_session():
        background_bytes, cutout_bytes, image_format = segment_at_click(
            image_bytes=image_bytes,
            x=x,
            y=y,
            options=options,
            session_id=image_id,
            base_dir=base_dir,
        )

    return background_bytes, cutout_bytes, image_format


def segment_candidates_on_image(
    image_id: str,
    base_dir: Path,
    x: int,
    y: int,
    options: ImageProcessingOptions | None = None,
    exclude_mask_ids: frozenset[str] | None = None,
    verify: str | VerifyMode | None = None,
) -> list[tuple[str, bytes]]:
    """Run segmentation only and cache every candidate mask.

    The returned bytes are BGRA cutout previews for the frontend. The matching
    refined masks stay on disk as `.npy` files because JSON/base64 is wasteful
    and inpainting needs exact pixel arrays, not visualized masks.

    When ``verify`` is ``auto``, all candidates are still cached, but only the
    CLIP-selected winner is returned. Raises ``ValueError`` if none is viable.
    """

    del options  # TODO: parameter not used. legacy click options. remove it or use
    pinned = exclude_mask_ids or frozenset()
    image_bytes = load_canvas_bytes(image_id=image_id, base_dir=base_dir)
    _validate_click_coordinates(image_bytes, x, y, base_dir, image_id)

    with inference_session():
        # New segmentation invalidates older unchosen candidates except pinned masks.
        delete_candidates(base_dir, image_id, exclude_mask_ids=pinned)

        segmentor = load_avroom_attr("ObjectSegmentor")()
        depth_map, _ = get_or_compute_depth(
            base_dir,
            image_id,
            image_bytes,
            segmentor.depth.map_depth,
        )
        image_key = memory_image_key(image_bytes)
        logger.info("Running ObjectSegmentor: image_key=%s click=(%d,%d)", image_key, x, y)
        candidate_pairs = segmentor.get_mask_for_object_at_position(
            image_path=image_key,
            x=x,
            y=y,
            image_bytes=image_bytes,
            depth_map=depth_map,
        )
        logger.info("ObjectSegmentor finished: image_id=%s candidates=%d", image_id, len(candidate_pairs))

        results: list[tuple[str, bytes]] = []
        cutouts_bgra: list[np.ndarray] = []
        for index, (refined_mask, cutout_bgra) in enumerate(candidate_pairs):
            mask_id = mask_id_for_candidate_slot(index, pinned)
            cutout_bytes = encode_png(cutout_bgra, f"candidate cutout {mask_id}")
            save_candidate(base_dir, image_id, mask_id, refined_mask, cutout_bytes)
            results.append((mask_id, cutout_bytes))
            cutouts_bgra.append(cutout_bgra)

        verify_mode = VerifyMode(verify) if verify else VerifyMode.MANUAL
        if verify_mode is VerifyMode.AUTO:
            from avroom_object_removal import select_best_cutout

            refined_masks = [pair[0] for pair in candidate_pairs]
            source_bgr = _decode_original_bgr(image_bytes, image_id)
            selection = select_best_cutout(
                cutouts_bgra,
                click_xy=(x, y),
                refined_masks=refined_masks,
                scene_bgr=source_bgr,
                depth_map=depth_map,
                tiebreaker=_get_cutout_tiebreaker(),
            )
            for index, reason in enumerate(selection.reasons):
                checks = (
                    selection.clip_checks[index]
                    if index < len(selection.clip_checks)
                    else None
                )
                avg = (
                    selection.scores[index] if index < len(selection.scores) else 0.0
                )
                passed = reason in ("scored", "ranked", "winner")
                logger.info(
                    "Auto mask pick candidate %d image_id=%s: %s avg=%.3f checks=%s reason=%s",
                    index,
                    image_id,
                    "PASS" if passed else "FAIL",
                    avg,
                    checks,
                    reason,
                )
            logger.info(
                "Auto mask pick: image_id=%s winner=%s scores=%s finalists=%s tiebreak=%s",
                image_id,
                selection.winner_index,
                selection.scores,
                selection.finalist_indices,
                selection.tiebreak_method,
            )
            if selection.winner_index is None:
                raise ValueError("no viable mask")
            return [results[selection.winner_index]]

    return results


def inpaint_selected_mask_on_image(
    image_id: str,
    mask_id: str,
    base_dir: Path,
) -> tuple[bytes, bytes, str]:
    """Run background inpainting for one previously cached mask candidate."""

    image_bytes = load_canvas_bytes(image_id=image_id, base_dir=base_dir)
    source_bgr = _decode_original_bgr(image_bytes, image_id)
    refined_mask = load_refined_mask(base_dir, image_id, mask_id)
    cutout_bytes = load_cutout_bytes(base_dir, image_id, mask_id)
    compose_mask = _decode_cutout_alpha(cutout_bytes, image_id, mask_id)

    with inference_session():
        inpainter = load_avroom_attr("BackgroundInpainter")()
        logger.info(
            "Running BackgroundInpainter: image_id=%s mask_id=%s image_shape=%s mask_shape=%s compose_shape=%s",
            image_id,
            mask_id,
            source_bgr.shape,
            refined_mask.shape,
            compose_mask.shape,
        )
        background_bgr = inpainter.cut_mask_from_image(
            original_image=source_bgr,
            mask=refined_mask,
            compose_mask=compose_mask,
            inpaint_out={},
        )
        logger.info("BackgroundInpainter finished: image_id=%s mask_id=%s bg_shape=%s", image_id, mask_id, background_bgr.shape)

    background_bytes = encode_png(background_bgr, "background")
    return background_bytes, cutout_bytes, "png"


def build_object_metadata_for_inpaint(
    image_id: str,
    mask_id: str,
    object_id: int,
    base_dir: Path,
) -> ObjectMetadata:
    """Compute average mask depth and build metadata before canvas is overwritten.

    Uses the current canvas bytes and depth cache. Expects a cache hit when
    segmentation ran on the same canvas state immediately before inpaint.
    """
    image_bytes = load_canvas_bytes(image_id=image_id, base_dir=base_dir)
    with inference_session():
        segmentor = load_avroom_attr("ObjectSegmentor")()
        depth_map, content_hash = get_or_compute_depth(
            base_dir,
            image_id,
            image_bytes,
            segmentor.depth.map_depth,
        )
        refined_mask = load_refined_mask(base_dir, image_id, mask_id)
        average_depth = compute_average_depth_over_mask(depth_map, refined_mask)

        calib_payload = load_camera_calib(base_dir, image_id)
        calibration = (
            cache_dict_to_calibration_result(calib_payload) if calib_payload is not None else None
        )

        elevation_facade = load_avroom_attr(
            "ElevationEstimationFacade",
            "avroom_object_removal.ai_engines.elevation_estimation",
        )()
        elevation_result = elevation_facade.estimate(
            depth_map,
            refined_mask,
            calibration=calibration,
            image_width=depth_map.shape[1],
            image_height=depth_map.shape[0],
        )
        source_elevation_deg = elevation_result.elevation_deg
    logger.info(
        "Object metadata prepared: image_id=%s object_id=%d mask_id=%s average_depth=%.2f source_elevation=%.2f",
        image_id,
        object_id,
        mask_id,
        average_depth,
        source_elevation_deg,
    )
    return create_object_metadata(
        session_id=image_id,
        object_id=object_id,
        average_depth=average_depth,
        content_hash=content_hash,
        source_elevation_deg=source_elevation_deg,
    )


@dataclass(frozen=True)
class RescaleByDepthResult:
    """Outcome of rescaling one object cutout based on placement depth."""

    object_uuid: str
    session_id: str
    object_id: int
    source_average_depth: float
    target_depth: float
    scale_factor: float
    display_scale: float


@dataclass(frozen=True)
class SmartPasteBridgeResult:
    """Outcome of smart paste after persistence."""

    object_uuid: str
    session_id: str
    object_id: int
    source_average_depth: float
    target_depth: float
    scale_factor: float
    display_scale: float


def _compute_depth_rescale(
    source_average_depth: float,
    depth_map: np.ndarray,
    x: int,
    y: int,
) -> tuple[float, float, float]:
    """Delegate depth-proportional scale math to TestModules."""
    compute_fn = load_avroom_attr(
        "compute_depth_rescale",
        module="avroom_object_removal.core.cutout_rescaler",
    )
    result = compute_fn(
        source_average_depth=source_average_depth,
        depth_map=depth_map,
        x=x,
        y=y,
    )
    return (
        result.source_average_depth,
        result.target_depth,
        result.scale_factor,
    )

def _load_object_metadata_for_rescale(base_dir: Path, object_uuid: str) -> ObjectMetadata:
    metadata = get_object_by_uuid(object_uuid)
    if metadata is None:
        raise FileNotFoundError(f"Object metadata not found for uuid='{object_uuid}'")

    cutout_path = resolve_object_cutout_path(base_dir, metadata.session_id, metadata.object_id)
    if not cutout_path.exists():
        raise FileNotFoundError(
            f"Cutout not found for uuid='{object_uuid}' at path='{cutout_path}'"
        )
    return metadata


def _compute_session_depth_map(base_dir: Path, session_id: str) -> np.ndarray:
    image_bytes = load_canvas_bytes(image_id=session_id, base_dir=base_dir)
    with inference_session():
        segmentor = load_avroom_attr("ObjectSegmentor")()
        depth_map, _ = get_or_compute_depth(
            base_dir,
            session_id,
            image_bytes,
            segmentor.depth.map_depth,
        )
    return depth_map


def _persist_rescale_metadata(
    object_uuid: str,
    *,
    target_depth: float,
    display_scale: float,
) -> None:
    set_object_rescale_state(
        object_uuid,
        average_depth=target_depth,
        display_scale=display_scale,
    )


def rescale_cutout_by_depth(
    base_dir: Path,
    object_uuid: str,
    x: int,
    y: int,
) -> RescaleByDepthResult:
    """Compute depth-proportional UI scale at ``(x, y)`` and persist metadata only.

    Samples depth from the session's current canvas, compares it to the object's
    stored ``average_depth``, updates cumulative ``display_scale``, and advances
    ``average_depth`` so later rescales do not compound. The cutout PNG is never
    modified.
    """
    logger.info(
        "Rescale by depth requested: object_uuid=%s placement=(%d,%d)",
        object_uuid,
        x,
        y,
    )

    metadata = _load_object_metadata_for_rescale(base_dir, object_uuid)
    depth_map = _compute_session_depth_map(base_dir, metadata.session_id)

    source_average_depth, target_depth, scale_factor = _compute_depth_rescale(
        source_average_depth=metadata.average_depth,
        depth_map=depth_map,
        x=x,
        y=y,
    )
    display_scale = metadata.display_scale * scale_factor
    logger.info(
        "Depth scale computed: object_uuid=%s source_depth=%.2f target_depth=%.2f "
        "scale=%.4f display_scale=%.4f",
        object_uuid,
        source_average_depth,
        target_depth,
        scale_factor,
        display_scale,
    )

    _persist_rescale_metadata(
        object_uuid,
        target_depth=target_depth,
        display_scale=display_scale,
    )

    logger.info(
        "Rescale by depth complete: object_uuid=%s session_id=%s object_id=%d display_scale=%.4f",
        object_uuid,
        metadata.session_id,
        metadata.object_id,
        display_scale,
    )

    return RescaleByDepthResult(
        object_uuid=object_uuid,
        session_id=metadata.session_id,
        object_id=metadata.object_id,
        source_average_depth=source_average_depth,
        target_depth=target_depth,
        scale_factor=scale_factor,
        display_scale=display_scale,
    )


def run_smart_paste(
    base_dir: Path,
    object_uuid: str,
    x: int,
    y: int,
) -> SmartPasteBridgeResult:
    """Run smart paste for one object at ``(x, y)`` and persist metadata only."""
    logger.info(
        "Smart paste requested: object_uuid=%s placement=(%d,%d)",
        object_uuid,
        x,
        y,
    )

    metadata = _load_object_metadata_for_rescale(base_dir, object_uuid)
    depth_map = _compute_session_depth_map(base_dir, metadata.session_id)

    with inference_session():
        smart_paster = load_avroom_attr("SmartPaster")()
        paste_result = smart_paster.smart_paste(
            source_average_depth=metadata.average_depth,
            depth_map=depth_map,
            x=x,
            y=y,
        )

    display_scale = metadata.display_scale * paste_result.scale_factor
    logger.info(
        "Smart paste scale computed: object_uuid=%s source_depth=%.2f target_depth=%.2f "
        "scale=%.4f display_scale=%.4f",
        object_uuid,
        paste_result.source_average_depth,
        paste_result.target_depth,
        paste_result.scale_factor,
        display_scale,
    )

    _persist_rescale_metadata(
        base_dir,
        object_uuid,
        target_depth=paste_result.target_depth,
        display_scale=display_scale,
    )

    logger.info(
        "Smart paste complete: object_uuid=%s session_id=%s object_id=%d display_scale=%.4f",
        object_uuid,
        metadata.session_id,
        metadata.object_id,
        display_scale,
    )

    return SmartPasteBridgeResult(
        object_uuid=object_uuid,
        session_id=metadata.session_id,
        object_id=metadata.object_id,
        source_average_depth=paste_result.source_average_depth,
        target_depth=paste_result.target_depth,
        scale_factor=paste_result.scale_factor,
        display_scale=display_scale,
    )

