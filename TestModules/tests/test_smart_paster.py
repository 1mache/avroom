from __future__ import annotations

import numpy as np

from avroom_object_removal.core.cutout_rescaler import (
    _RESCALE_STRENGTH,
    _dampen_scale,
    compute_depth_rescale,
    compute_depth_scale_factor,
    depth_map_extrema,
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
    assert compute_depth_scale_factor(80.0, 160.0) == _dampen_scale(2.0)
    assert compute_depth_scale_factor(100.0, 100.0) == 1.0
    assert _RESCALE_STRENGTH == 0.75


def test_compute_depth_scale_factor_clamps_to_softened_scene_extrema() -> None:
    # Original 100; scene deepest 40 → raw floor 0.4; closest 180 → raw ceiling 1.8.
    lo = _dampen_scale(0.4)
    hi = _dampen_scale(1.8)
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
    assert result.scale_factor == _dampen_scale(2.0)
    assert result.target_depth == 160.0
