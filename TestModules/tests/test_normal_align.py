from __future__ import annotations

import math

import numpy as np
import pytest

from avroom_object_removal.core.normal_align import (
    orbit_pose_from_normals,
    sample_normal_at_point,
)


def _unit(*components: float) -> np.ndarray:
    arr = np.array(components, dtype=np.float32)
    return arr / np.linalg.norm(arr)


def test_sample_normal_at_point_clamps_and_renormalizes() -> None:
    normal_map = np.zeros((4, 4, 3), dtype=np.float32)
    normal_map[3, 3] = np.array([3.0, 0.0, 4.0], dtype=np.float32)

    sampled = sample_normal_at_point(normal_map, 10, 10)

    assert sampled.shape == (3,)
    assert sampled.dtype == np.float32
    np.testing.assert_allclose(sampled, [0.6, 0.0, 0.8], atol=1e-5)


def test_floor_to_same_floor_returns_none() -> None:
    floor = _unit(0.0, -1.0, 0.0)  # Metric3D Y-down: up in world

    assert orbit_pose_from_normals(floor, floor) is None


def test_near_vertical_pair_forces_zero_azimuth() -> None:
    floor = _unit(0.0, -1.0, 0.0)
    tilted = _unit(0.05, -0.99, 0.05)

    pose = orbit_pose_from_normals(floor, tilted)

    assert pose is None or abs(pose.azimuth_deg) < 1.0


def test_facing_wall_to_side_wall_adds_wall_mount_pitch() -> None:
    front = _unit(0.0, 0.0, -1.0)
    side = _unit(1.0, 0.0, 0.0)

    pose = orbit_pose_from_normals(front, side)

    assert pose is not None
    assert abs(pose.azimuth_deg) < 5.0
    assert abs(pose.relative_elevation_deg) > 70.0


def test_perpendicular_wall_repro_normals_add_pitch() -> None:
    """Regression for smart-paste side wall → back wall (debug session 32f685)."""
    source = _unit(-0.9997962713241577, 0.011782204732298851, 0.016390038654208183)
    dest = _unit(-0.05202031880617142, -0.006351917050778866, -0.9986258149147034)

    pose = orbit_pose_from_normals(source, dest)

    assert pose is not None
    assert 85.0 < pose.azimuth_deg < 95.0
    assert pose.relative_elevation_deg < -70.0


def test_opposite_walls_add_wall_mount_pitch() -> None:
    """Regression for smart-paste right wall → left wall (opposite normals)."""
    right = _unit(-0.9997962713241577, 0.011782204732298851, 0.016390038654208183)
    left = _unit(0.9988390207290649, 0.0011867205612361431, -0.0481584295630455)

    pose = orbit_pose_from_normals(right, left)

    assert pose is not None
    assert 85.0 < pose.azimuth_deg < 95.0
    assert pose.relative_elevation_deg < -70.0


def test_floor_to_camera_facing_wall_skips_rotation() -> None:
    floor = _unit(0.0, -1.0, 0.0)
    wall = _unit(0.0, 0.0, 1.0)

    assert orbit_pose_from_normals(floor, wall) is None


def test_floor_to_toward_camera_wall_skips_rotation() -> None:
    """Floor-standing furniture stays upright when smart-pasted near a wall."""
    floor = _unit(0.106, -0.906, -0.420)
    wall = _unit(-0.467, 0.404, -0.796)

    assert orbit_pose_from_normals(floor, wall) is None


def test_small_delta_inside_deadzone_returns_none() -> None:
    base = _unit(0.0, 0.0, -1.0)
    tiny = _unit(0.02, 0.0, -0.9998)

    assert orbit_pose_from_normals(base, tiny) is None


def test_invalid_zero_normal_raises() -> None:
    with pytest.raises(ValueError, match="non-zero"):
        orbit_pose_from_normals(np.zeros(3), _unit(1.0, 0.0, 0.0))


def test_wrap_azimuth_across_180() -> None:
    back = _unit(0.0, 0.0, 1.0)
    side = _unit(1.0, 0.0, 0.0)

    pose = orbit_pose_from_normals(back, side)

    assert pose is not None
    assert abs(pose.azimuth_deg - 180.0) < 5.0
    assert abs(pose.relative_elevation_deg) > 70.0
