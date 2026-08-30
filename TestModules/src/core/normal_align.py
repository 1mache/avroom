from __future__ import annotations

import logging
import math
from typing import NamedTuple

import numpy as np

logger = logging.getLogger(__name__)

# Skip auto-rotate when inferred orbit delta is below this (degrees).
_ORBIT_DEADZONE_DEG = 3.0

# When |nx| and |nz| are both tiny the surface is near-vertical; yaw is noise.
_NEAR_VERTICAL_HORIZONTAL = 0.15

# |mesh-up Y| above this → horizontal surface (floor/ceiling). Floor-standing
# cutouts keep their upright pose when smart-pasted onto walls.
_FLOOR_LIKE_MESH_NY = 0.7

# Perpendicular wall normals have |dot| below this; parallel/opposite pairs skip
# the wall-mount pitch correction.
_WALL_PERPENDICULAR_DOT_MAX = 0.5

# Wall-mount auto-tilt applies when inferred yaw exceeds this (degrees).
_WALL_MOUNT_MIN_YAW_DEG = 45.0


class OrbitPose(NamedTuple):
    """Signed mesh-orbit deltas matching ``Model3DFrame.capture()`` / novel-view."""

    azimuth_deg: float
    relative_elevation_deg: float


def sample_normal_at_point(normal_map: np.ndarray, x: int, y: int) -> np.ndarray:
    """Return a unit normal at ``(x, y)``, clamped to map bounds."""
    if normal_map.ndim != 3 or normal_map.shape[2] != 3:
        raise ValueError(f"Normal map must be HxWx3, got shape={normal_map.shape}")

    height, width = normal_map.shape[:2]
    clamped_x = max(0, min(x, width - 1))
    clamped_y = max(0, min(y, height - 1))
    if clamped_x != x or clamped_y != y:
        logger.debug(
            "Normal sample clamped: requested=(%d,%d) clamped=(%d,%d)",
            x,
            y,
            clamped_x,
            clamped_y,
        )

    sample = normal_map[clamped_y, clamped_x].astype(np.float64, copy=False)
    norm = float(np.linalg.norm(sample))
    if norm < 1e-8:
        raise ValueError(f"Zero normal at ({clamped_x},{clamped_y}).")
    return (sample / norm).astype(np.float32)


def _normalize_vector(vector: np.ndarray) -> np.ndarray:
    arr = np.asarray(vector, dtype=np.float64).reshape(3)
    norm = float(np.linalg.norm(arr))
    if norm < 1e-8:
        raise ValueError("Normal vector must be non-zero.")
    return arr / norm


def _metric3d_to_mesh_up(normal: np.ndarray) -> np.ndarray:
    """Map Metric3D camera-frame normal to Y-up for orbit math.

    Metric3D uses OpenCV camera coords (+X right, +Y down, +Z forward). Mesh
    orbit / Three.js use +Y up with ``atan2(x, z)`` azimuth.
    """
    nx, ny, nz = _normalize_vector(normal)
    return np.array([nx, -ny, nz], dtype=np.float64)


def _orbit_components_from_normal(normal: np.ndarray) -> tuple[float, float]:
    """Return ``(azimuth_deg, relative_elevation_deg)`` for one surface normal."""
    nx, ny, nz = _metric3d_to_mesh_up(normal)
    horizontal = math.hypot(nx, nz)
    if horizontal < _NEAR_VERTICAL_HORIZONTAL:
        azimuth_deg = 0.0
    else:
        azimuth_deg = math.degrees(math.atan2(nx, nz))
    rel_elev_deg = math.degrees(math.asin(max(-1.0, min(1.0, ny))))
    return azimuth_deg, rel_elev_deg


def _wrap_azimuth_delta(delta_deg: float) -> float:
    wrapped = delta_deg
    while wrapped > 180.0:
        wrapped -= 360.0
    while wrapped < -180.0:
        wrapped += 360.0
    return wrapped


def _is_floor_like_normal(normal: np.ndarray) -> bool:
    """True when the surface is roughly horizontal (floor or ceiling)."""
    _, ny, _ = _metric3d_to_mesh_up(normal)
    return abs(ny) > _FLOOR_LIKE_MESH_NY


def _is_wall_like_normal(normal: np.ndarray) -> bool:
    """True for vertical walls/ceilings — not floor-like, not near-horizontal."""
    _, ny, _ = _metric3d_to_mesh_up(normal)
    return abs(ny) <= _FLOOR_LIKE_MESH_NY


def _wall_mount_elevation_deg(
    source_normal: np.ndarray,
    dest_normal: np.ndarray,
    delta_az_deg: float,
) -> float | None:
    """Pitch correction for flat wall-mounted objects on vertical walls.

    Wall-surface normals only differ in yaw; camera orbit still needs ~±90°
    relative elevation so a thin mesh hangs flat on the new wall instead of
    appearing edge-on, pole-on (invisible), or tipped toward the floor.
    """
    if not (_is_wall_like_normal(source_normal) and _is_wall_like_normal(dest_normal)):
        return None
    if abs(delta_az_deg) < _WALL_MOUNT_MIN_YAW_DEG:
        return None

    src = _metric3d_to_mesh_up(source_normal)
    dst = _metric3d_to_mesh_up(dest_normal)
    dot = float(np.clip(np.dot(src, dst), -1.0, 1.0))
    if dot > _WALL_PERPENDICULAR_DOT_MAX:
        return None

    cross = np.cross(src, dst)
    if abs(cross[1]) >= 1e-3:
        # +90° puts the camera at the north pole (top-down); use cross.y sign.
        return math.copysign(90.0, float(cross[1]))

    if dot < -0.5:
        # Opposite walls: cross.y ≈ 0; follow yaw handedness for pitch sign.
        return math.copysign(90.0, -delta_az_deg)

    return None


def _wall_mount_azimuth_deg(az_src: float) -> float:
    """In-plane heading for wall-mounted flat objects after pitch correction.

    Wall-normal yaw alone mis-rotates thin meshes in-plane; ``wrap(az_src + 180)``
    keeps the object's upright aligned with world Y when viewed from below.
    """
    return _wrap_azimuth_delta(az_src + 180.0)


def orbit_pose_from_normals(
    source_normal: np.ndarray,
    dest_normal: np.ndarray,
) -> OrbitPose | None:
    """Infer mesh-orbit deltas that align ``source_normal`` toward ``dest_normal``.

    Returns ``None`` when the delta falls inside the deadzone (including identical
    floor-to-floor drops).

    # ponytail: novel-view has no roll; floor normals make azimuth undefined.
    # Floor-standing objects stay upright when repositioned onto walls.
    """
    if _is_floor_like_normal(source_normal):
        logger.debug("Orbit pose skipped: floor-standing source")
        return None

    az_src, el_src = _orbit_components_from_normal(source_normal)
    az_dst, el_dst = _orbit_components_from_normal(dest_normal)
    # Both axes are src - dst so they match novel-view: clockwise+ yaw, up+
    # elevation (polar shrinks → look from above → seat out, legs into the wall).
    delta_az = _wrap_azimuth_delta(az_src - az_dst)
    delta_el = el_src - el_dst
    wall_mount_el = _wall_mount_elevation_deg(source_normal, dest_normal, delta_az)
    if wall_mount_el is not None:
        delta_el = wall_mount_el
        delta_az = _wall_mount_azimuth_deg(az_src)

    if math.hypot(delta_az, delta_el) < _ORBIT_DEADZONE_DEG:
        logger.debug(
            "Orbit pose below deadzone: az=%.2f el=%.2f (threshold=%.2f)",
            delta_az,
            delta_el,
            _ORBIT_DEADZONE_DEG,
        )
        return None

    logger.info(
        "Orbit pose from normals: az=%.2f el=%.2f (src az=%.2f el=%.2f dst az=%.2f el=%.2f)",
        delta_az,
        delta_el,
        az_src,
        el_src,
        az_dst,
        el_dst,
    )
    return OrbitPose(azimuth_deg=delta_az, relative_elevation_deg=delta_el)
