from __future__ import annotations

import numpy as np

from avroom_object_removal.core.cutout_rescaler import (
    _GROW_STRENGTH,
    _MAX_SCALE,
    _MIN_SCALE,
    _SHRINK_STRENGTH,
    _dampen_scale,
    compute_depth_rescale,
    compute_depth_scale_factor,
    depth_map_extrema,
    drop_is_at_original_footprint,
    origin_depth_sample_point,
    rescale_cutout_by_depth,
)
from avroom_object_removal.core.smart_paster import SmartPaster


def _make_cutout(size: int = 64, blob_size: int = 20) -> np.ndarray:
    cutout = np.zeros((size, size, 4), dtype=np.uint8)
    center = size // 2
    half = blob_size // 2
    cutout[
        center - half : center + half,
        center - half : center + half,
        3,
    ] = 255
    cutout[
        center - half : center + half,
        center - half : center + half,
        :3,
    ] = 128
    return cutout


def test_depth_map_extrema_returns_scene_range() -> None:
    depth_map = np.full((8, 8), 100, dtype=np.uint8)
    depth_map[0, 0] = 40
    depth_map[7, 7] = 200
    assert depth_map_extrema(depth_map) == (40.0, 200.0)


def test_compute_depth_scale_factor_dampens_target_over_source() -> None:
    assert compute_depth_scale_factor(100.0, 50.0) == _dampen_scale(0.5)
    assert compute_depth_scale_factor(80.0, 160.0) == _MAX_SCALE
    assert compute_depth_scale_factor(100.0, 100.0) == 1.0
    assert _SHRINK_STRENGTH == 0.40
    assert _GROW_STRENGTH == 1.15


def test_compute_depth_scale_factor_far_shrink_is_milder_than_raw_ratio() -> None:
    """Far-wall uint8 ratios are tiny; do not collapse to ~0.26 of original size."""
    far = compute_depth_scale_factor(203.0, 39.0)
    assert far == _MIN_SCALE
    closer = compute_depth_scale_factor(160.0, 220.0)
    assert closer > 1.2
    shrink_delta = 1.0 - compute_depth_scale_factor(100.0, 50.0)
    grow_delta = compute_depth_scale_factor(100.0, 150.0) - 1.0
    assert grow_delta > shrink_delta


def test_compute_depth_scale_factor_clamps_to_softened_scene_extrema() -> None:
    # Original 100; scene deepest 40 → raw floor 0.4; closest 180 → raw ceiling 1.8.
    lo = max(_MIN_SCALE, _dampen_scale(0.4))
    hi = min(_MAX_SCALE, _dampen_scale(1.8))
    assert compute_depth_scale_factor(100.0, 20.0, deepest=40.0, closest=180.0) == lo
    assert compute_depth_scale_factor(100.0, 250.0, deepest=40.0, closest=180.0) == hi
    assert compute_depth_scale_factor(100.0, 120.0, deepest=40.0, closest=180.0) == _dampen_scale(
        1.2
    )


def test_compute_depth_scale_factor_pov_direction() -> None:
    """Deeper → smaller; closer to camera → larger."""
    assert compute_depth_scale_factor(100.0, 70.0) < 1.0
    assert compute_depth_scale_factor(100.0, 140.0) > 1.0


def test_compute_depth_rescale_uses_scene_extrema() -> None:
    depth_map = np.full((64, 64), 100, dtype=np.uint8)
    depth_map[32, 32] = 50

    result = compute_depth_rescale(
        source_average_depth=100.0,
        depth_map=depth_map,
        x=32,
        y=32,
    )

    deepest, closest = depth_map_extrema(depth_map)
    assert deepest == 50.0
    assert closest == 100.0
    expected = compute_depth_scale_factor(
        100.0, 50.0, deepest=deepest, closest=closest
    )
    assert result.scale_factor == expected
    assert result.scale_factor == _dampen_scale(0.5)
    assert result.target_depth == 50.0


def test_rescale_cutout_by_depth_scales_pixels_for_debug() -> None:
    cutout = _make_cutout()
    depth_map = np.full((64, 64), 100, dtype=np.uint8)
    depth_map[32, 32] = 50

    result = rescale_cutout_by_depth(
        cutout_bgra=cutout,
        source_average_depth=100.0,
        depth_map=depth_map,
        x=32,
        y=32,
    )

    assert result.scale_factor == _dampen_scale(0.5)
    assert result.target_depth == 50.0
    assert result.cutout_bgra.shape == cutout.shape


def test_smart_paster_delegates_to_depth_rescale() -> None:
    depth_map = np.full((64, 64), 80, dtype=np.uint8)
    depth_map[10, 10] = 160

    result = SmartPaster().smart_paste(
        source_average_depth=80.0,
        depth_map=depth_map,
        x=10,
        y=10,
    )

    deepest, closest = depth_map_extrema(depth_map)
    assert result.scale_factor == compute_depth_scale_factor(
        80.0, 160.0, deepest=deepest, closest=closest
    )
    assert result.scale_factor == _MAX_SCALE
    assert result.target_depth == 160.0
    assert result.azimuth_deg is None
    assert result.relative_elevation_deg is None


def test_smart_paster_infers_pose_from_normals() -> None:
    depth_map = np.full((64, 64), 100, dtype=np.uint8)
    normal_map = np.zeros((64, 64, 3), dtype=np.float32)
    normal_map[:, :] = np.array([-1.0, 0.0, 0.0], dtype=np.float32)  # back wall
    normal_map[20:40, 20:40] = np.array([0.0, 0.0, -1.0], dtype=np.float32)  # toward camera

    result = SmartPaster().smart_paste(
        source_average_depth=100.0,
        depth_map=depth_map,
        x=30,
        y=30,
        normal_map=normal_map,
        source_x=10,
        source_y=10,
    )

    assert result.azimuth_deg is not None
    assert abs(result.azimuth_deg) > 45.0
    assert result.relative_elevation_deg is not None


def test_smart_paster_skips_scale_when_disabled() -> None:
    depth_map = np.full((64, 64), 80, dtype=np.uint8)
    depth_map[10, 10] = 160

    result = SmartPaster().smart_paste(
        source_average_depth=80.0,
        depth_map=depth_map,
        x=10,
        y=10,
        scale_by_pov=False,
    )

    assert result.scale_factor == 1.0
    assert result.target_depth == 80.0
    assert result.azimuth_deg is None
    assert result.relative_elevation_deg is None


def test_pov_scale_no_change_when_dropped_at_original_position() -> None:
    """Dropping at the same pixel as the origin must not resize the object.

    The real-world fix: average_depth is now stored as the depth *at the click
    pixel*, not the mask average.  So dropping back on the same pixel gives
    target_depth == source_average_depth → scale == 1.0 even on a non-uniform
    depth map where the mask average would differ from the click-point depth.
    """
    depth_map = np.full((64, 64), 100, dtype=np.uint8)
    # Non-uniform region: object centroid pixel has a different depth than the
    # surrounding mask pixels, mimicking a real depth map.  If we used the mask
    # average (~93) as source_average_depth the scale would not be 1.0 on drop.
    depth_map[30:34, 30:34] = 60   # part of hypothetical mask, different depth

    # source_average_depth == depth AT the click pixel (32,32) == 60
    # (this is what build_object_metadata_for_inpaint now stores)
    click_depth = float(depth_map[32, 32])  # 60

    result = SmartPaster().smart_paste(
        source_average_depth=click_depth,
        depth_map=depth_map,
        x=32,
        y=32,  # drop at the same click pixel
        scale_by_pov=True,
        smart_rotate=False,
    )

    assert result.scale_factor == 1.0, (
        f"Expected scale_factor=1.0 (drop at origin pixel), got {result.scale_factor}"
    )


def test_pov_scale_restores_original_size_when_returned_to_origin() -> None:
    """Object moved to a different pixel then dropped back to origin pixel → scale == 1.0.

    The object was at (32,32) with click_depth=60.  It was moved to (10,10)
    where depth=180, giving scale > 1.0.  Dropping back to (32,32) must give
    scale == 1.0 again — the reference depth is always the origin click pixel.
    """
    depth_map = np.full((64, 64), 100, dtype=np.uint8)
    depth_map[30:34, 30:34] = 60   # origin click region
    depth_map[10, 10] = 180        # distant placement (closer to camera → bigger)

    click_depth = float(depth_map[32, 32])  # 60 — stored at object creation

    # First move: drop at (10,10) — should scale up
    moved = SmartPaster().smart_paste(
        source_average_depth=click_depth,
        depth_map=depth_map,
        x=10,
        y=10,
        scale_by_pov=True,
        smart_rotate=False,
    )
    assert moved.scale_factor != 1.0, "Moving to a different depth must change scale"

    # Return: drop at origin pixel — must restore scale to 1.0
    returned = SmartPaster().smart_paste(
        source_average_depth=click_depth,
        depth_map=depth_map,
        x=32,
        y=32,
        scale_by_pov=True,
        smart_rotate=False,
    )

    assert returned.scale_factor == 1.0, (
        f"Returning to origin pixel must restore original size, got {returned.scale_factor}"
    )
    assert returned.target_depth == click_depth


def test_drop_near_origin_counts_as_original_footprint() -> None:
    """A drag-back ~90px off center still counts; a real move ~140px does not."""
    kwargs = dict(left=1100, top=700, right=1214, bottom=796, natural_width=1600, natural_height=1200)
    assert drop_is_at_original_footprint(**kwargs, x=1157, y=748)
    # Failing run "put back": +47,+74 from center (1157, 748)
    assert drop_is_at_original_footprint(**kwargs, x=1204, y=822)
    # Failing run "moved away": -115,-76 from center
    assert not drop_is_at_original_footprint(**kwargs, x=1042, y=672)


def test_origin_depth_sample_point_is_bbox_feet() -> None:
    assert origin_depth_sample_point(100, 200, 180, 360) == (140, 359)


def test_smart_paster_skips_rotate_when_disabled() -> None:
    depth_map = np.full((64, 64), 80, dtype=np.uint8)
    depth_map[30, 30] = 160
    normal_map = np.zeros((64, 64, 3), dtype=np.float32)
    normal_map[:, :] = np.array([-1.0, 0.0, 0.0], dtype=np.float32)
    normal_map[20:40, 20:40] = np.array([0.0, 0.0, -1.0], dtype=np.float32)

    result = SmartPaster().smart_paste(
        source_average_depth=80.0,
        depth_map=depth_map,
        x=30,
        y=30,
        normal_map=normal_map,
        source_x=10,
        source_y=10,
        smart_rotate=False,
    )

    assert result.scale_factor > 1.0
    assert result.azimuth_deg is None
    assert result.relative_elevation_deg is None
