from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

from core.auth.identity import current_user_id
from core.cutout_bounds import extract_cutout_bounds_from_png_bytes
from core.image_codec import to_base64_ascii
from core.mask_cache import delete_candidate, load_cutout_bytes
from core.repositories.job_repo import JobRecord, delete_job, get_job, list_active_jobs
from schemas.jobs import JobDetailResponse, JobInfo, SegmentMaskResult
from settings import get_image_storage_dir

router = APIRouter(prefix="/jobs", tags=["jobs"])
logger = logging.getLogger(__name__)


def _to_job_info(record: JobRecord) -> JobInfo:
    return JobInfo(
        job_id=record.id,
        session_id=record.session_id,
        kind=record.kind,
        status=record.status,
        error=record.error,
        created_at=record.created_at.isoformat(),
        # Only generate_3d payloads carry "object_id" (mirrors job_repo._row_to_info).
        object_id=record.payload.get("object_id"),
        # Only segment payloads carry "verify".
        verify=record.payload.get("verify"),
    )


def _inflate_segment_masks(record: JobRecord) -> list[SegmentMaskResult] | None:
    """Load cached candidate PNGs for a done segment job's mask ids."""
    if record.kind != "segment" or record.status != "done" or record.result is None:
        return None
    storage_dir = get_image_storage_dir()
    masks: list[SegmentMaskResult] = []
    for mask_id in record.result.get("mask_ids", []):
        try:
            cutout_bytes = load_cutout_bytes(storage_dir, record.session_id, mask_id)
        except FileNotFoundError:
            logger.warning(
                "Segment job result references missing candidate: job_id=%s mask_id=%s",
                record.id,
                mask_id,
            )
            continue
        masks.append(
            SegmentMaskResult(
                mask_id=mask_id,
                cutout_b64=to_base64_ascii(cutout_bytes),
                format="png",
                cutout_bounds=extract_cutout_bounds_from_png_bytes(cutout_bytes),
            )
        )
    return masks


@router.get("/active", response_model=list[JobInfo])
async def get_active_jobs(user_id: str = Depends(current_user_id)) -> list[JobInfo]:
    """Every non-done job for the caller, across all sessions (dashboard badges)."""
    jobs = list_active_jobs(user_id)
    logger.debug("Active jobs requested: user_id=%s count=%d", user_id, len(jobs))
    return jobs


@router.get("/{job_id}", response_model=JobDetailResponse)
async def get_job_detail(job_id: str, user_id: str = Depends(current_user_id)) -> JobDetailResponse:
    """One job owned by the caller, with inflated mask candidates if applicable."""
    record = get_job(user_id, job_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Job not found for id='{job_id}'")
    info = _to_job_info(record)
    return JobDetailResponse(**info.model_dump(), masks=_inflate_segment_masks(record))


@router.delete("/{job_id}", status_code=204)
async def dismiss_job(job_id: str, user_id: str = Depends(current_user_id)) -> None:
    """Dismiss a failed/conflict job, or discard an unconsumed segment result.

    For a done segment job this also deletes its candidate files on disk so
    the mask ids can be reused by a future segment in the same session.
    """
    record = get_job(user_id, job_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Job not found for id='{job_id}'")

    if record.kind == "segment" and record.status == "done" and record.result is not None:
        storage_dir = get_image_storage_dir()
        for mask_id in record.result.get("mask_ids", []):
            delete_candidate(storage_dir, record.session_id, mask_id)

    delete_job(job_id)
    logger.info("Job dismissed: job_id=%s user_id=%s", job_id, user_id)
