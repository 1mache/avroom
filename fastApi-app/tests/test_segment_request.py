from __future__ import annotations

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

_APP_ROOT = Path(__file__).resolve().parents[1]
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))

from schemas.image import SegmentPoint, SegmentRequest  # noqa: E402


def test_segment_request_accepts_points_matching_primary() -> None:
    request = SegmentRequest(
        image_id="sess-1",
        x=10,
        y=20,
        points=[SegmentPoint(x=10, y=20), SegmentPoint(x=30, y=40)],
    )
    assert request.points is not None
    assert len(request.points) == 2


def test_segment_request_rejects_mismatched_primary() -> None:
    with pytest.raises(ValidationError, match="points\\[0\\]"):
        SegmentRequest(
            image_id="sess-1",
            x=10,
            y=20,
            points=[SegmentPoint(x=99, y=20)],
        )
