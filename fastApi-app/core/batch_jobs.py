from __future__ import annotations

import logging
import uuid
from pathlib import Path

import cv2
import numpy as np

from core.avroom_package import load_avroom_attr
from core.depth_cache import get_or_compute_depth
from core.image_codec import encode_png
from core.image_processing import (
    build_object_metadata_for_inpaint,
    load_canvas_bytes,
)
from core.inference_pool.client import InferenceJobError, get_inference_client
from core.inference_pool.session_runtime import (
    SessionConflictError,
    acquire_canvas_writer,
    drop_lease,
    mask_id_for_candidate_slot,
    pinned_mask_ids,
    release_canvas_writer,
    try_admit_inpaint,
)
from core.mask_cache import delete_candidate, load_refined_mask, save_candidate
from core.object_metadata import get_object_by_uuid, next_object_id, save_object_metadata
from core.object_storage import object_cutout_path, object_glb_path
from core.session_history import commit_background
from core.repositories.session_repo import get_session_last_changed, touch_session
from schemas.batch import (
    BatchBoxSource,
    BatchClicksSource,
    BatchGlbResult,
    BatchObjectResult,
    BatchObjectsSource,
    BatchRequest,
    BatchResponse,
)
from settings import get_3d_storage_dir

logger = logging.getLogger(__name__)

_MIN_MASK_PIXELS = 200


def run_session_batch(image_id: str, request: BatchRequest, base_dir: Path) -> BatchResponse:
    """Discover, peel with auto-verify, then optional GLB. Failures are per-object."""

    batch_id = str(uuid.uuid4())
    then = request.then or ["inpaint"]
    logger.info(
        "Batch starting: image_id=%s batch_id=%s source=%s then=%s",
        image_id,
        batch_id,
        request.source.kind,
        then,
    )

    created: list[BatchObjectResult] = []
    glb_targets: list[int] = []

    if isinstance(request.source, BatchObjectsSource):
        for object_uuid in request.source.uuids:
            meta = get_object_by_uuid(object_uuid)
            if meta is None or meta.session_id != image_id:
                created.append(
                    BatchObjectResult(status="skipped", error="unknown object uuid")
                )
                continue
            created.append(
                BatchObjectResult(
                    object_id=meta.object_id,
                    object_uuid=meta.uuid,
                    status="glb_only",
                )
            )
            glb_targets.append(meta.object_id)
    elif "inpaint" in then:
        jobs = _discover_mask_jobs(image_id, request.source, base_dir)
        logger.info("Batch discovered %d mask jobs: image_id=%s", len(jobs), image_id)
        remaining = list(jobs)
        while remaining:
            depth = _session_depth(image_id, base_dir)
            masks = [job["mask"] for job in remaining]
            order = load_avroom_attr("peel_order", module="avroom_object_removal.core")(
                masks, depth
            )
            idx = order[0]
            job = remaining.pop(idx)
            result = _inpaint_one_job(image_id, job["mask_id"], base_dir)
            created.append(result)
            if result.status == "created" and result.object_id is not None:
                glb_targets.append(result.object_id)
                remaining = _resegment_occluded(
                    image_id, base_dir, job["mask"], remaining
                )
    else:
        logger.info("Batch skipped inpaint: image_id=%s", image_id)

    glbs: list[BatchGlbResult] = []
    if "generate_3d" in then:
        for object_id in glb_targets:
            glbs.append(_generate_glb(image_id, object_id))

    last_changed = get_session_last_changed(image_id) or ""
    logger.info(
        "Batch complete: image_id=%s batch_id=%s objects=%d glbs=%d",
        image_id,
        batch_id,
        len(created),
        len(glbs),
    )
    return BatchResponse(
        batch_id=batch_id,
        image_id=image_id,
        objects=created,
        glbs=glbs,
        last_changed=last_changed,
    )


def _decode_bgr(image_bytes: bytes) -> np.ndarray:
    array = np.frombuffer(image_bytes, dtype=np.uint8)
    bgr = cv2.imdecode(array, cv2.IMREAD_COLOR)
    if bgr is None:
        raise ValueError("Could not decode session canvas")
    return bgr


def _session_depth(image_id: str, base_dir: Path) -> np.ndarray:
    image_bytes = load_canvas_bytes(image_id, base_dir)
    segmentor = load_avroom_attr("ObjectSegmentor")()
    depth_map, _ = get_or_compute_depth(
        base_dir, image_id, image_bytes, segmentor.depth.map_depth
    )
    return depth_map


def _mask_to_cutout(bgr: np.ndarray, mask: np.ndarray) -> bytes:
    bool_mask = mask > 127 if mask.dtype == np.uint8 or float(mask.max()) > 1 else mask > 0.5
    bgra = cv2.cvtColor(bgr, cv2.COLOR_BGR2BGRA)
    bgra[:, :, 3] = (bool_mask.astype(np.uint8) * 255)
    return encode_png(bgra, "batch candidate cutout")


def _discover_mask_jobs(
    image_id: str,
    source: BatchBoxSource | BatchClicksSource,
    base_dir: Path,
) -> list[dict[str, object]]:
    if isinstance(source, BatchClicksSource):
        first = source.points[0]
        segment_points = tuple((point.x, point.y) for point in source.points)
        try:
            candidates = get_inference_client().run_segment(
                image_id=image_id,
                base_dir=base_dir,
                x=first.x,
                y=first.y,
                points=segment_points,
                exclude_mask_ids=frozenset(pinned_mask_ids(image_id)),
                verify="auto",
            )
        except (InferenceJobError, ValueError, SessionConflictError) as exc:
            logger.error(
                "Batch clicks skipped: points=%d error=%s",
                len(source.points),
                exc,
            )
            return []
        if not candidates:
            return []
        mask_id, _cutout = candidates[0]
        return [
            {
                "mask_id": mask_id,
                "mask": load_refined_mask(base_dir, image_id, mask_id),
            }
        ]

    image_bytes = load_canvas_bytes(image_id, base_dir)
    bgr = _decode_bgr(image_bytes)
    depth = _session_depth(image_id, base_dir)
    SamImageAdapter = load_avroom_attr(
        "SamImageAdapter", module="avroom_object_removal.ai_engines.segmentation"
    )
    ImageSegmentationFacade = load_avroom_attr(
        "ImageSegmentationFacade",
        module="avroom_object_removal.ai_engines.segmentation",
    )
    adapted = SamImageAdapter().get_adapted_image(depth, image_id=image_id, point=(0, 0))
    masks = ImageSegmentationFacade().get_all_masks_for_image(adapted)
    filter_masks_in_box = load_avroom_attr(
        "filter_masks_in_box", module="avroom_object_removal.core"
    )
    keep = filter_masks_in_box(masks, source.x0, source.y0, source.x1, source.y1)
    pinned = frozenset(pinned_mask_ids(image_id))
    jobs = []
    slot = 0
    for index in keep:
        mask = masks[index]
        if mask.ndim == 3:
            mask = mask[:, :, 0]
        mask_u8 = (mask > 127).astype(np.uint8) * 255 if mask.max() > 1 else (mask > 0.5).astype(np.uint8) * 255
        if int(np.count_nonzero(mask_u8)) < _MIN_MASK_PIXELS:
            continue
        mask_id = mask_id_for_candidate_slot(slot, pinned)
        slot += 1
        save_candidate(base_dir, image_id, mask_id, mask_u8, _mask_to_cutout(bgr, mask_u8))
        jobs.append({"mask_id": mask_id, "mask": mask_u8})
    return jobs


def _inpaint_one_job(image_id: str, mask_id: str, base_dir: Path) -> BatchObjectResult:
    lease = None
    try:
        lease = try_admit_inpaint(image_id, mask_id, base_dir)
        acquire_canvas_writer(image_id)
        background_bytes, cutout_bytes, _fmt = get_inference_client().run_inpaint(
            image_id=image_id,
            mask_id=mask_id,
            base_dir=base_dir,
        )
        object_id = next_object_id(image_id)
        object_metadata = build_object_metadata_for_inpaint(
            image_id=image_id,
            mask_id=mask_id,
            object_id=object_id,
            base_dir=base_dir,
        )
        new_cursor = commit_background(image_id, background_bytes, base_dir)
        object_metadata = object_metadata.model_copy(update={"stage_seq": new_cursor})
        save_object_metadata(object_metadata)
        object_cutout_path(base_dir, image_id, object_id).write_bytes(cutout_bytes)
        delete_candidate(base_dir, image_id, mask_id)
        touch_session(image_id)
        logger.info(
            "Batch inpaint created object_id=%d uuid=%s image_id=%s",
            object_id,
            object_metadata.uuid,
            image_id,
        )
        return BatchObjectResult(
            object_id=object_id,
            object_uuid=object_metadata.uuid,
            status="created",
        )
    except Exception as exc:
        logger.error("Batch inpaint skipped mask_id=%s image_id=%s error=%s", mask_id, image_id, exc)
        return BatchObjectResult(status="skipped", error=str(exc))
    finally:
        if lease is not None:
            drop_lease(image_id, lease)
        try:
            release_canvas_writer(image_id)
        except Exception:
            pass


def _resegment_occluded(
    image_id: str,
    base_dir: Path,
    peeled_mask: np.ndarray,
    remaining: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Re-run auto segment for jobs that overlapped the peeled mask."""

    peel_bool = peeled_mask > 127
    refreshed: list[dict[str, object]] = []
    for job in remaining:
        mask = np.asarray(job["mask"])
        overlap = int(np.count_nonzero((mask > 127) & peel_bool))
        if overlap < _MIN_MASK_PIXELS:
            refreshed.append(job)
            continue
        leftover = (mask > 127) & (~peel_bool)
        if not leftover.any():
            logger.info("Batch dropped fully covered mask after peel: image_id=%s", image_id)
            continue
        ys, xs = np.nonzero(leftover)
        x, y = int(xs[len(xs) // 2]), int(ys[len(ys) // 2])
        try:
            candidates = get_inference_client().run_segment(
                image_id=image_id,
                base_dir=base_dir,
                x=x,
                y=y,
                exclude_mask_ids=frozenset(pinned_mask_ids(image_id)),
                verify="auto",
            )
        except (InferenceJobError, ValueError, SessionConflictError) as exc:
            logger.error("Batch re-segment skipped: x=%d y=%d error=%s", x, y, exc)
            continue
        if not candidates:
            continue
        mask_id, _cutout = candidates[0]
        refreshed.append(
            {
                "mask_id": mask_id,
                "mask": load_refined_mask(base_dir, image_id, mask_id),
            }
        )
    return refreshed


def _generate_glb(image_id: str, object_id: int) -> BatchGlbResult:
    from core.object_storage import resolve_object_cutout_path
    from settings import get_image_storage_dir

    cutout_path = resolve_object_cutout_path(get_image_storage_dir(), image_id, object_id)
    try:
        glb_bytes = get_inference_client().run_generate_3d(cutout_path=cutout_path)
        assert isinstance(glb_bytes, bytes)
        glb_dir = get_3d_storage_dir()
        glb_dir.mkdir(parents=True, exist_ok=True)
        object_glb_path(glb_dir, image_id, object_id).write_bytes(glb_bytes)
        touch_session(image_id)
        logger.info("Batch GLB ok: image_id=%s object_id=%d bytes=%d", image_id, object_id, len(glb_bytes))
        return BatchGlbResult(object_id=object_id, ok=True)
    except Exception as exc:
        logger.error("Batch GLB failed: image_id=%s object_id=%d error=%s", image_id, object_id, exc)
        return BatchGlbResult(object_id=object_id, ok=False, error=str(exc))
