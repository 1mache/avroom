from __future__ import annotations

import numpy as np

from avroom_object_removal.core.cutout_rescaler import (
    compute_depth_rescale,
    compute_depth_scale_factor,
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


def test_compute_depth_rescale_scales_proportionally() -> None:
    depth_map = np.full((64, 64), 100, dtype=np.uint8)
    depth_map[32, 32] = 50

    result = compute_depth_rescale(
        source_average_depth=100.0,
        depth_map=depth_map,
        x=32,
        y=32,
    )

    assert result.scale_factor == compute_depth_scale_factor(100.0, 50.0)
    assert result.target_depth == 50.0


def test_compute_depth_scale_factor_dampens_extremes() -> None:
    assert compute_depth_scale_factor(100.0, 50.0) == 0.88
    assert compute_depth_scale_factor(80.0, 160.0) == 1.12
    assert compute_depth_scale_factor(100.0, 100.0) == 1.0


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

    assert result.scale_factor == compute_depth_scale_factor(100.0, 50.0)
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

    assert result.scale_factor == compute_depth_scale_factor(80.0, 160.0)
    assert result.target_depth == 160.0
