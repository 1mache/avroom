from __future__ import annotations

import logging
import os
from pathlib import Path

from core.inference_lock import inference_session
from core.inference_pool.types import JobKind, JobRequest, JobResult

logger = logging.getLogger(__name__)

# Facade-only jobs do not pass through image_processing helpers that already
# acquire inference_session(); they need the lock here in inline mode.
_FACADE_JOB_KINDS = frozenset({
    JobKind.GENERATE_3D,
    JobKind.NOVEL_VIEW,
    JobKind.VALIDATE_CONTENT,
    JobKind.CALIBRATE_CAMERA,
    JobKind.DEBUG_DEPTH_MAP,
    JobKind.DEBUG_SAM_EVERYTHING,
})


def _execute_impl(job: JobRequest) -> JobResult:
    """Run one job using existing pipeline entry points."""
    base_dir = Path(job.storage_dir)

    if job.kind == JobKind.SEGMENT:
        from core.image_processing import segment_candidates_on_image
        from schemas.image import ImageProcessingOptions

        assert job.image_id is not None and job.x is not None and job.y is not None
        options = ImageProcessingOptions.model_validate(job.options) if job.options else None
        candidates = segment_candidates_on_image(
            image_id=job.image_id,
            base_dir=base_dir,
            x=job.x,
            y=job.y,
            options=options,
            exclude_mask_ids=frozenset(job.exclude_mask_ids or ()),
        )
        return JobResult(job_id=job.job_id, ok=True, candidates=candidates)

    if job.kind == JobKind.INPAINT:
        from core.image_processing import inpaint_selected_mask_on_image

        assert job.image_id is not None and job.mask_id is not None
        background_bytes, cutout_bytes, image_format = inpaint_selected_mask_on_image(
            image_id=job.image_id,
            mask_id=job.mask_id,
            base_dir=base_dir,
        )
        return JobResult(
            job_id=job.job_id,
            ok=True,
            background_bytes=background_bytes,
            cutout_bytes=cutout_bytes,
            image_format=image_format,
        )

    if job.kind == JobKind.CLICK:
        from core.image_processing import process_click_on_image
        from schemas.image import ImageProcessingOptions

        assert job.image_id is not None and job.x is not None and job.y is not None
        options = ImageProcessingOptions.model_validate(job.options) if job.options else None
        background_bytes, cutout_bytes, image_format = process_click_on_image(
            image_id=job.image_id,
            base_dir=base_dir,
            x=job.x,
            y=job.y,
            options=options,
        )
        return JobResult(
            job_id=job.job_id,
            ok=True,
            background_bytes=background_bytes,
            cutout_bytes=cutout_bytes,
            image_format=image_format,
        )

    if job.kind == JobKind.RESCALE_BY_DEPTH:
        from core.image_processing import rescale_cutout_by_depth

        assert job.object_uuid is not None and job.x is not None and job.y is not None
        result = rescale_cutout_by_depth(
            base_dir=base_dir,
            object_uuid=job.object_uuid,
            x=job.x,
            y=job.y,
        )
        return JobResult(
            job_id=job.job_id,
            ok=True,
            object_uuid=result.object_uuid,
            session_id=result.session_id,
            object_id=result.object_id,
            source_average_depth=result.source_average_depth,
            target_depth=result.target_depth,
            scale_factor=result.scale_factor,
            cutout_bytes=result.cutout_bytes,
        )

    if job.kind == JobKind.GENERATE_3D:
        from avroom_object_removal.ai_engines.reconstruction_3d import (
            Reconstruction3DFacade,
            ReconstructionQuality,
        )

        assert job.cutout_path is not None
        glb_bytes = Reconstruction3DFacade().generate(
            Path(job.cutout_path),
            quality=ReconstructionQuality.HIGH,
            output="bytes",
        )
        if not isinstance(glb_bytes, bytes):
            raise TypeError("3D facade returned non-bytes output")
        return JobResult(job_id=job.job_id, ok=True, glb_bytes=glb_bytes)

    if job.kind == JobKind.NOVEL_VIEW:
        from avroom_object_removal.ai_engines.novel_view import (
            MeshRenderNovelViewStrategy,
            NovelViewFacade,
        )

        assert job.cutout_path is not None
        assert job.mesh_path is not None
        assert job.elevation_deg is not None
        assert job.azimuth_deg is not None
        assert job.relative_elevation_deg is not None
        assert job.radius is not None
        result_bgra = NovelViewFacade(MeshRenderNovelViewStrategy()).synthesize(
            Path(job.cutout_path),
            elevation_deg=job.elevation_deg,
            azimuth_deg=job.azimuth_deg,
            relative_elevation_deg=job.relative_elevation_deg,
            radius=job.radius,
            seed=0,
            mesh=Path(job.mesh_path),
        )
        return JobResult(job_id=job.job_id, ok=True, novel_view_bgra=result_bgra)

    if job.kind == JobKind.VALIDATE_CONTENT:
        from core.content_validation import validate_upload_content

        assert job.image_bytes is not None
        content = validate_upload_content(job.image_bytes)
        return JobResult(
            job_id=job.job_id,
            ok=True,
            validation_ok=content.is_valid,
            validation_checks=content.checks,
            validation_scores=content.scores,
            validation_messages=content.messages,
        )

    if job.kind == JobKind.CALIBRATE_CAMERA:
        from core.camera_calibration import calibrate_upload_image

        assert job.image_bytes is not None
        calibration = calibrate_upload_image(job.image_bytes)
        return JobResult(
            job_id=job.job_id,
            ok=True,
            camera_calib_gravity=calibration.gravity,
            camera_calib_roll_deg=calibration.roll_deg,
            camera_calib_pitch_deg=calibration.pitch_deg,
            camera_calib_fx=calibration.fx,
            camera_calib_fy=calibration.fy,
            camera_calib_cx=calibration.cx,
            camera_calib_cy=calibration.cy,
            camera_calib_confidence=calibration.confidence,
            camera_calib_camera_model=calibration.camera_model,
        )

    if job.kind == JobKind.DEBUG_DEPTH_MAP:
        from core.debug_vision import render_depth_map_png

        assert job.image_bytes is not None
        debug_options = job.options or {}
        png_bytes = render_depth_map_png(
            job.image_bytes,
            model_name=debug_options["model_name"],
            colormap=debug_options["colormap"],
        )
        return JobResult(job_id=job.job_id, ok=True, debug_png_bytes=png_bytes)

    if job.kind == JobKind.DEBUG_SAM_EVERYTHING:
        from core.debug_vision import render_sam_everything_png

        assert job.image_bytes is not None
        debug_options = job.options or {}
        png_bytes, mask_count = render_sam_everything_png(
            job.image_bytes,
            source=debug_options["source"],
            depth_model_name=debug_options["depth_model_name"],
            points_per_side=debug_options["points_per_side"],
            alpha=debug_options["alpha"],
        )
        return JobResult(
            job_id=job.job_id, ok=True, debug_png_bytes=png_bytes, debug_mask_count=mask_count
        )

    raise ValueError(f"Unsupported job kind: {job.kind}")


def execute(job: JobRequest) -> JobResult:
    """Execute a job, serializing facade-only GPU work in inline mode."""
    if job.kind == JobKind.SHUTDOWN:
        return JobResult(job_id=job.job_id, ok=True)

    try:
        in_worker = os.environ.get("AVROOM_INFERENCE_WORKER") == "1"
        needs_dispatch_lock = not in_worker and job.kind in _FACADE_JOB_KINDS
        if needs_dispatch_lock:
            with inference_session():
                return _execute_impl(job)
        return _execute_impl(job)
    except Exception as exc:
        logger.exception("Inference job failed: job_id=%s kind=%s", job.job_id, job.kind)
        return JobResult(job_id=job.job_id, ok=False, error=str(exc))
