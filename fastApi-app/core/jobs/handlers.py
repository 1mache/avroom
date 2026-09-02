from __future__ import annotations

"""Job handlers: the former blocking route bodies, minus the HTTP layer.

Each function takes a `JobRecord` (one claimed queue row) and does the
actual work. They raise on failure so the dispatcher can classify it
(`SessionConflictError` -> job status `"conflict"`, anything else ->
`"failed"`). Segment returns a result dict (`{"mask_ids": [...]}`) the
dispatcher stores on the row; inpaint and generate_3d return nothing because
their real result is an `ObjectRow` / GLB file on disk, not the job row
itself — the dispatcher deletes the row on their success (see
`core/repositories/job_repo.py` module docstring).
"""

import logging
from typing import Any

from core.image_processing import build_object_metadata_for_inpaint
from core.inference_pool.client import get_inference_client
from core.inference_pool.session_runtime import (
    acquire_canvas_writer,
    assert_segment_click_allowed,
    drop_lease,
    pinned_mask_ids,
    release_canvas_writer,
    try_admit_inpaint,
)
from core.mask_cache import delete_candidate
from core.notifications import notify_pipeline_event
from core.object_3d import ensure_object_glb
from core.object_metadata import next_object_id, save_object_metadata
from core.object_storage import object_cutout_path, resolve_object_cutout_path
from core.session_history import commit_background
from core.repositories.job_repo import JobRecord, reserved_mask_ids
from core.repositories.session_repo import touch_session
from schemas.image import ImageProcessingOptions
from settings import get_image_storage_dir

logger = logging.getLogger(__name__)


def run_segment_job(job: JobRecord) -> dict[str, Any]:
    """Run segmentation for a queued job and return ``{"mask_ids": [...]}``.

    Raises:
        SessionConflictError: When the click falls inside an active inpaint
            lease region (classified by the dispatcher as job status
            "conflict", matching the 409 this used to be at request time).
    """
    storage_dir = get_image_storage_dir()
    x = job.payload["x"]
    y = job.payload["y"]
    options_payload = job.payload.get("options")
    options = ImageProcessingOptions.model_validate(options_payload) if options_payload else None
    verify = job.payload.get("verify")
    raw_points = job.payload.get("points")
    if raw_points:
        segment_points = tuple((int(point["x"]), int(point["y"])) for point in raw_points)
    else:
        segment_points = ((x, y),)

    for point_x, point_y in segment_points:
        assert_segment_click_allowed(job.session_id, point_x, point_y)

    # Pinned = masks reserved by in-flight inpaint leases; reserved = masks
    # belonging to an earlier segment job's still-unconsumed result. Both must
    # be excluded or a second segment would delete the first result's files
    # out from under a picker the user hasn't opened yet (multiple unconsumed
    # segment results per session are allowed — see docs/backend/concurrency.md).
    excluded = pinned_mask_ids(job.session_id) | reserved_mask_ids(job.session_id)
    candidates = get_inference_client().run_segment(
        image_id=job.session_id,
        base_dir=storage_dir,
        x=x,
        y=y,
        points=segment_points,
        options=options,
        exclude_mask_ids=frozenset(excluded),
        verify=verify,
    )
    mask_ids = [mask_id for mask_id, _cutout_bytes in candidates]
    logger.info(
        "Segment job produced %d candidate(s): job_id=%s session_id=%s",
        len(mask_ids),
        job.id,
        job.session_id,
    )
    return {"mask_ids": mask_ids}


def run_inpaint_job(job: JobRecord) -> None:
    """Run inpaint for a queued job: writes the object, background, cutout.

    Same lock sandwich the blocking route used to run inline: admit the
    lease, acquire the canvas writer, run the model, allocate the object id
    and persist everything, drop the lease, release the writer.
    """
    storage_dir = get_image_storage_dir()
    mask_id = job.payload["mask_id"]
    lease = None

    try:
        lease = try_admit_inpaint(job.session_id, mask_id, storage_dir)
        acquire_canvas_writer(job.session_id)
        try:
            background_bytes, cutout_bytes, _image_format = get_inference_client().run_inpaint(
                image_id=job.session_id,
                mask_id=mask_id,
                base_dir=storage_dir,
            )
        except Exception as exc:
            logger.exception("Inpaint job failed: job_id=%s session_id=%s", job.id, job.session_id)
            notify_pipeline_event(job.session_id, "Object removed", ok=False, detail=str(exc))
            raise

        object_id = next_object_id(job.session_id)
        object_metadata = build_object_metadata_for_inpaint(
            image_id=job.session_id,
            mask_id=mask_id,
            object_id=object_id,
            base_dir=storage_dir,
        )
        new_cursor = commit_background(job.session_id, background_bytes, storage_dir)
        object_metadata = object_metadata.model_copy(update={"stage_seq": new_cursor})
        save_object_metadata(object_metadata)
        object_cutout_path(storage_dir, job.session_id, object_id).write_bytes(cutout_bytes)

        delete_candidate(storage_dir, job.session_id, mask_id)
        touch_session(job.session_id)
    finally:
        if lease is not None:
            drop_lease(job.session_id, lease)
        release_canvas_writer(job.session_id)

    logger.info(
        "Inpaint job complete: job_id=%s session_id=%s object_id=%d object_uuid=%s",
        job.id,
        job.session_id,
        object_id,
        object_metadata.uuid,
    )
    notify_pipeline_event(job.session_id, "Object removed", detail=f"Object {object_id}")


def run_erase_job(job: JobRecord) -> None:
    """Run erase for a queued job: inpaint the mask region, no object created."""
    storage_dir = get_image_storage_dir()
    mask_id = job.id
    lease = None

    try:
        lease = try_admit_inpaint(job.session_id, mask_id, storage_dir)
        acquire_canvas_writer(job.session_id)
        try:
            background_bytes = get_inference_client().run_erase(
                image_id=job.session_id,
                mask_id=mask_id,
                base_dir=storage_dir,
            )
        except Exception as exc:
            logger.exception("Erase job failed: job_id=%s session_id=%s", job.id, job.session_id)
            notify_pipeline_event(job.session_id, "Region erased", ok=False, detail=str(exc))
            raise

        commit_background(job.session_id, background_bytes, storage_dir)
        delete_candidate(storage_dir, job.session_id, mask_id)
        touch_session(job.session_id)
    finally:
        if lease is not None:
            drop_lease(job.session_id, lease)
        release_canvas_writer(job.session_id)

    logger.info("Erase job complete: job_id=%s session_id=%s", job.id, job.session_id)
    notify_pipeline_event(job.session_id, "Region erased")


def run_generate_3d_job(job: JobRecord) -> None:
    """Run 3D generation for a queued job, reusing the shared GLB cache-or-generate helper."""
    object_id = job.payload["object_id"]
    storage_dir = get_image_storage_dir()
    cutout_path = resolve_object_cutout_path(storage_dir, job.session_id, object_id)
    if not cutout_path.exists():
        raise FileNotFoundError(
            f"Cutout image not found for uid='{job.session_id}' object_id={object_id}"
        )

    try:
        ensure_object_glb(uid=job.session_id, object_id=object_id, cutout_path=cutout_path)
    except Exception as exc:
        logger.exception("3D generation job failed: job_id=%s session_id=%s", job.id, job.session_id)
        notify_pipeline_event(
            job.session_id, "3D model ready", ok=False, detail=f"Object {object_id}: {exc}"
        )
        raise

    logger.info(
        "3D generation job complete: job_id=%s session_id=%s object_id=%d",
        job.id,
        job.session_id,
        object_id,
    )
    notify_pipeline_event(job.session_id, "3D model ready", detail=f"Object {object_id}")
