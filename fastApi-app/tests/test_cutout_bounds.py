"""Unit tests for cutout bounds helpers."""

from __future__ import annotations

import sys
from pathlib import Path

_APP_ROOT = Path(__file__).resolve().parents[1]
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))

from core.cutout_bounds import scale_cutout_bounds  # noqa: E402
from schemas.common import CutoutBounds  # noqa: E402


def test_scale_cutout_bounds_allows_negative_overflow() -> None:
    """Large display_scale may push edges past the canvas; must not ValidationError."""
    base = CutoutBounds(
        left=100,
        top=50,
        right=300,
        bottom=250,
        natural_width=2000,
        natural_height=1500,
    )
    # width=200, height=200; scale 2.5 → grow 150 each side → top = 50-150 = -100
    scaled = scale_cutout_bounds(base, 2.5)
    assert scaled.left == -50
    assert scaled.top == -100
    assert scaled.right == 450
    assert scaled.bottom == 400
    assert scaled.natural_width == 2000
    assert scaled.natural_height == 1500
