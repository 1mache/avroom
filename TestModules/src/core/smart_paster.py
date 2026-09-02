from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

from .cutout_rescaler import DepthRescaleResult, compute_depth_rescale
from .normal_align import OrbitPose, orbit_pose_from_normals, sample_normal_at_point

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SmartPasteResult:
    """Outcome of smart paste before persistence."""

    source_average_depth: float
    target_depth: float
    scale_factor: float
    azimuth_deg: float | None = None
    relative_elevation_deg: float | None = None


class SmartPaster:
    """Orchestrates post-drop object adjustments for smart paste.

    Depth-proportional rescale plus optional auto-rotate inferred from surface
    normals at the original cutout center and the drop point.
    """

    def smart_paste(
        self,
        *,
        source_average_depth: float,
        depth_map: np.ndarray,
        x: int,
        y: int,
        normal_map: np.ndarray | None = None,
        source_x: int | None = None,
        source_y: int | None = None,
    ) -> SmartPasteResult:
        """Run smart paste at natural-image placement ``(x, y)``."""
        logger.info("Smart paste requested: placement=(%d,%d)", x, y)
        depth_result = self._compute_depth_rescale(
            source_average_depth=source_average_depth,
            depth_map=depth_map,
            x=x,
            y=y,
        )
        azimuth_deg: float | None = None
        relative_elevation_deg: float | None = None
        if normal_map is not None and source_x is not None and source_y is not None:
            pose = self._infer_orbit_pose(
                normal_map=normal_map,
                source_x=source_x,
                source_y=source_y,
                dest_x=x,
                dest_y=y,
            )
            if pose is not None:
                azimuth_deg = pose.azimuth_deg
                relative_elevation_deg = pose.relative_elevation_deg

        return SmartPasteResult(
            source_average_depth=depth_result.source_average_depth,
            target_depth=depth_result.target_depth,
            scale_factor=depth_result.scale_factor,
            azimuth_deg=azimuth_deg,
            relative_elevation_deg=relative_elevation_deg,
        )

    def _compute_depth_rescale(
        self,
        source_average_depth: float,
        depth_map: np.ndarray,
        x: int,
        y: int,
    ) -> DepthRescaleResult:
        return compute_depth_rescale(
            source_average_depth=source_average_depth,
            depth_map=depth_map,
            x=x,
            y=y,
        )

    def _infer_orbit_pose(
        self,
        *,
        normal_map: np.ndarray,
        source_x: int,
        source_y: int,
        dest_x: int,
        dest_y: int,
    ) -> OrbitPose | None:
        try:
            source_normal = sample_normal_at_point(normal_map, source_x, source_y)
            dest_normal = sample_normal_at_point(normal_map, dest_x, dest_y)
        except ValueError as exc:
            logger.warning(
                "Smart paste auto-rotate skipped: normal sample failed at "
                "source=(%d,%d) dest=(%d,%d) reason=%s",
                source_x,
                source_y,
                dest_x,
                dest_y,
                exc,
            )
            return None
        return orbit_pose_from_normals(source_normal, dest_normal)
