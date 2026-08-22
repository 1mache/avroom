from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np

from core.inference_pool.dispatch import execute
from core.inference_pool.pool import InferencePool
from core.inference_pool.types import JobKind, JobRequest, JobResult
from schemas.image import ImageProcessingOptions
from settings import get_inference_worker_count

if TYPE_CHECKING:
    from core.camera_calibration import CameraCalibrationOutcome
    from core.content_validation import ContentValidationOutcome
    from core.image_processing import RescaleByDepthResult

logger = logging.getLogger(__name__)

_pool: InferencePool | None = None
_client: InferenceClient | None = None


class InferenceJobError(RuntimeError):
    """Raised when an inference job fails in a worker or inline."""


def _new_job_id() -> str:
    """Return a fresh id correlating one submitted job with its result."""
    return str(uuid.uuid4())


class InferenceClient:
    """Submit inference jobs inline or via the worker pool."""

    def __init__(self, pool: InferencePool | None) -> None:
        self._pool = pool

    def _run(self, job: JobRequest) -> JobResult:
        if self._pool is None:
            logger.debug("Running inference inline: job_id=%s kind=%s", job.job_id, job.kind)
            return execute(job)

        logger.debug("Submitting inference to pool: job_id=%s kind=%s", job.job_id, job.kind)
        return self._pool.submit_and_wait(job)

    @staticmethod
    def _raise_if_failed(result: JobResult) -> None:
        if not result.ok:
            raise InferenceJobError(result.error or "Inference job failed")

    def run_segment(
        self,
        *,
        image_id: str,
        base_dir: Path,
        x: int,
        y: int,
        options: ImageProcessingOptions | None = None,
        exclude_mask_ids: frozenset[str] | None = None,
        verify: str | None = None,
    ) -> list[tuple[str, bytes]]:
        job = JobRequest(
            job_id=_new_job_id(),
            kind=JobKind.SEGMENT,
            storage_dir=str(base_dir.resolve()),
            image_id=image_id,
            x=x,
            y=y,
            options=options.model_dump() if options is not None else None,
            exclude_mask_ids=tuple(sorted(exclude_mask_ids or frozenset())),
            verify=verify,
        )
        result = self._run(job)
        self._raise_if_failed(result)
        assert result.candidates is not None
        return result.candidates

    def run_inpaint(
        self,
        *,
        image_id: str,
        mask_id: str,
        base_dir: Path,
    ) -> tuple[bytes, bytes, str]:
        job = JobRequest(
            job_id=_new_job_id(),
            kind=JobKind.INPAINT,
            storage_dir=str(base_dir.resolve()),
            image_id=image_id,
            mask_id=mask_id,
        )
        result = self._run(job)
        self._raise_if_failed(result)
        assert result.background_bytes is not None
        assert result.cutout_bytes is not None
        assert result.image_format is not None
        return result.background_bytes, result.cutout_bytes, result.image_format

    def run_click(
        self,
        *,
        image_id: str,
        base_dir: Path,
        x: int,
        y: int,
        options: ImageProcessingOptions | None = None,
    ) -> tuple[bytes, bytes, str]:
        job = JobRequest(
            job_id=_new_job_id(),
            kind=JobKind.CLICK,
            storage_dir=str(base_dir.resolve()),
            image_id=image_id,
            x=x,
            y=y,
            options=options.model_dump() if options is not None else None,
        )
        result = self._run(job)
        self._raise_if_failed(result)
        assert result.background_bytes is not None
        assert result.cutout_bytes is not None
        assert result.image_format is not None
        return result.background_bytes, result.cutout_bytes, result.image_format

    def run_rescale_by_depth(
        self,
        *,
        base_dir: Path,
        object_uuid: str,
        x: int,
        y: int,
    ) -> RescaleByDepthResult:
        from core.image_processing import RescaleByDepthResult

        job = JobRequest(
            job_id=_new_job_id(),
            kind=JobKind.RESCALE_BY_DEPTH,
            storage_dir=str(base_dir.resolve()),
            object_uuid=object_uuid,
            x=x,
            y=y,
        )
        result = self._run(job)
        self._raise_if_failed(result)
        assert result.object_uuid is not None
        assert result.session_id is not None
        assert result.object_id is not None
        assert result.source_average_depth is not None
        assert result.target_depth is not None
        assert result.scale_factor is not None
        assert result.display_scale is not None
        return RescaleByDepthResult(
            object_uuid=result.object_uuid,
            session_id=result.session_id,
            object_id=result.object_id,
            source_average_depth=result.source_average_depth,
            target_depth=result.target_depth,
            scale_factor=result.scale_factor,
            display_scale=result.display_scale,
        )

    def run_smart_paste(
        self,
        *,
        base_dir: Path,
        object_uuid: str,
        x: int,
        y: int,
    ) -> SmartPasteBridgeResult:
        from core.image_processing import SmartPasteBridgeResult

        job = JobRequest(
            job_id=_new_job_id(),
            kind=JobKind.SMART_PASTE,
            storage_dir=str(base_dir.resolve()),
            object_uuid=object_uuid,
            x=x,
            y=y,
        )
        result = self._run(job)
        self._raise_if_failed(result)
        assert result.object_uuid is not None
        assert result.session_id is not None
        assert result.object_id is not None
        assert result.source_average_depth is not None
        assert result.target_depth is not None
        assert result.scale_factor is not None
        assert result.display_scale is not None
        return SmartPasteBridgeResult(
            object_uuid=result.object_uuid,
            session_id=result.session_id,
            object_id=result.object_id,
            source_average_depth=result.source_average_depth,
            target_depth=result.target_depth,
            scale_factor=result.scale_factor,
            display_scale=result.display_scale,
        )

    def run_generate_3d(self, *, cutout_path: Path) -> bytes:
        job = JobRequest(
            job_id=_new_job_id(),
            kind=JobKind.GENERATE_3D,
            storage_dir=str(cutout_path.parent.resolve()),
            cutout_path=str(cutout_path.resolve()),
        )
        result = self._run(job)
        self._raise_if_failed(result)
        assert result.glb_bytes is not None
        return result.glb_bytes

    def run_novel_view(
        self,
        *,
        cutout_path: Path,
        elevation_deg: float,
        azimuth_deg: float,
        relative_elevation_deg: float,
        radius: float,
        mesh_path: Path,
    ) -> np.ndarray:
        job = JobRequest(
            job_id=_new_job_id(),
            kind=JobKind.NOVEL_VIEW,
            storage_dir=str(cutout_path.parent.resolve()),
            cutout_path=str(cutout_path.resolve()),
            mesh_path=str(mesh_path.resolve()),
            elevation_deg=elevation_deg,
            azimuth_deg=azimuth_deg,
            relative_elevation_deg=relative_elevation_deg,
            radius=radius,
        )
        result = self._run(job)
        self._raise_if_failed(result)
        assert result.novel_view_bgra is not None
        return result.novel_view_bgra

    def run_validate_content(self, *, image_bytes: bytes) -> ContentValidationOutcome:
        from core.content_validation import ContentValidationOutcome

        job = JobRequest(
            job_id=_new_job_id(),
            kind=JobKind.VALIDATE_CONTENT,
            storage_dir=str(Path.cwd()),
            image_bytes=image_bytes,
        )
        result = self._run(job)
        self._raise_if_failed(result)
        assert result.validation_ok is not None
        assert result.validation_checks is not None
        assert result.validation_scores is not None
        assert result.validation_messages is not None
        return ContentValidationOutcome(
            is_valid=result.validation_ok,
            checks=result.validation_checks,
            scores=result.validation_scores,
            messages=result.validation_messages,
        )

    def run_calibrate_camera(self, *, image_bytes: bytes) -> CameraCalibrationOutcome:
        from core.camera_calibration import CameraCalibrationOutcome

        job = JobRequest(
            job_id=_new_job_id(),
            kind=JobKind.CALIBRATE_CAMERA,
            storage_dir=str(Path.cwd()),
            image_bytes=image_bytes,
        )
        result = self._run(job)
        self._raise_if_failed(result)
        assert result.camera_calib_gravity is not None
        assert result.camera_calib_roll_deg is not None
        assert result.camera_calib_pitch_deg is not None
        assert result.camera_calib_fx is not None
        assert result.camera_calib_fy is not None
        assert result.camera_calib_cx is not None
        assert result.camera_calib_cy is not None
        return CameraCalibrationOutcome(
            gravity=result.camera_calib_gravity,
            roll_deg=result.camera_calib_roll_deg,
            pitch_deg=result.camera_calib_pitch_deg,
            fx=result.camera_calib_fx,
            fy=result.camera_calib_fy,
            cx=result.camera_calib_cx,
            cy=result.camera_calib_cy,
            confidence=result.camera_calib_confidence,
            camera_model=result.camera_calib_camera_model or "pinhole",
        )

    def run_map_normals(self, *, image_bytes: bytes) -> np.ndarray:
        """Run Metric3D normal mapping; returns float32 HxWx3 ndarray."""
        job = JobRequest(
            job_id=_new_job_id(),
            kind=JobKind.MAP_NORMALS,
            storage_dir=str(Path.cwd()),
            image_bytes=image_bytes,
        )
        result = self._run(job)
        self._raise_if_failed(result)
        assert result.normal_map is not None
        return result.normal_map  # type: ignore[no-any-return]

    def run_warm_session_maps(self, *, image_id: str, base_dir: Path) -> WarmSessionMapsResult:
        from core.session_maps import WarmSessionMapsResult

        job = JobRequest(
            job_id=_new_job_id(),
            kind=JobKind.WARM_SESSION_MAPS,
            storage_dir=str(base_dir.resolve()),
            image_id=image_id,
        )
        result = self._run(job)
        self._raise_if_failed(result)
        assert result.warm_content_hash is not None
        assert result.depth_cache_hit is not None
        return WarmSessionMapsResult(
            session_id=image_id,
            content_hash=result.warm_content_hash,
            depth_cache_hit=result.depth_cache_hit,
            normal_cache_hit=result.normal_cache_hit,
        )

    def run_debug_depth_map(
        self, *, image_bytes: bytes, model_name: str, colormap: str, strategy: str = "anything"
    ) -> bytes:
        job = JobRequest(
            job_id=_new_job_id(),
            kind=JobKind.DEBUG_DEPTH_MAP,
            storage_dir=str(Path.cwd()),
            image_bytes=image_bytes,
            options={"model_name": model_name, "colormap": colormap, "strategy": strategy},
        )
        result = self._run(job)
        self._raise_if_failed(result)
        assert result.debug_png_bytes is not None
        return result.debug_png_bytes

    def run_debug_normal_map(
        self, *, image_bytes: bytes, hub_model: str = "metric3d_vit_small"
    ) -> bytes:
        job = JobRequest(
            job_id=_new_job_id(),
            kind=JobKind.DEBUG_NORMAL_MAP,
            storage_dir=str(Path.cwd()),
            image_bytes=image_bytes,
            options={"hub_model": hub_model},
        )
        result = self._run(job)
        self._raise_if_failed(result)
        assert result.debug_png_bytes is not None
        return result.debug_png_bytes

    def run_debug_sam_everything(
        self,
        *,
        image_bytes: bytes,
        source: str,
        depth_model_name: str,
        points_per_side: int,
        alpha: float,
        depth_strategy: str = "anything",
        pred_iou_thresh: float = 0.88,
        stability_score_thresh: float = 0.95,
        min_mask_region_area: int = 0,
    ) -> tuple[bytes, int]:
        job = JobRequest(
            job_id=_new_job_id(),
            kind=JobKind.DEBUG_SAM_EVERYTHING,
            storage_dir=str(Path.cwd()),
            image_bytes=image_bytes,
            options={
                "source": source,
                "depth_model_name": depth_model_name,
                "points_per_side": points_per_side,
                "alpha": alpha,
                "depth_strategy": depth_strategy,
                "pred_iou_thresh": pred_iou_thresh,
                "stability_score_thresh": stability_score_thresh,
                "min_mask_region_area": min_mask_region_area,
            },
        )
        result = self._run(job)
        self._raise_if_failed(result)
        assert result.debug_png_bytes is not None
        assert result.debug_mask_count is not None
        return result.debug_png_bytes, result.debug_mask_count

    def run_debug_auto_mask_pick(
        self, *, image_bytes: bytes, x: int, y: int
    ) -> dict[str, Any]:
        job = JobRequest(
            job_id=_new_job_id(),
            kind=JobKind.DEBUG_AUTO_MASK_PICK,
            storage_dir=str(Path.cwd()),
            image_bytes=image_bytes,
            x=x,
            y=y,
        )
        result = self._run(job)
        self._raise_if_failed(result)
        assert result.debug_payload is not None
        return result.debug_payload

    def run_debug_inpaint_verify(
        self, *, image_bytes: bytes, x: int, y: int, mask_index: int | None
    ) -> dict[str, Any]:
        job = JobRequest(
            job_id=_new_job_id(),
            kind=JobKind.DEBUG_INPAINT_VERIFY,
            storage_dir=str(Path.cwd()),
            image_bytes=image_bytes,
            x=x,
            y=y,
            options={"mask_index": mask_index},
        )
        result = self._run(job)
        self._raise_if_failed(result)
        assert result.debug_payload is not None
        return result.debug_payload


def init_inference_client(pool: InferencePool | None = None) -> None:
    """Initialize the process-wide inference client."""
    global _pool, _client
    _pool = pool
    _client = InferenceClient(pool)
    mode = "pool" if pool is not None else "inline"
    logger.info(
        "Inference client initialized: mode=%s workers=%d",
        mode,
        get_inference_worker_count(),
    )


def get_inference_client() -> InferenceClient:
    """Return the initialized inference client."""
    if _client is None:
        init_inference_client(None)
    assert _client is not None
    return _client


def shutdown_inference_client() -> None:
    """Shut down the worker pool if one was started."""
    global _pool, _client
    if _pool is not None:
        _pool.shutdown()
        _pool = None
    _client = None
