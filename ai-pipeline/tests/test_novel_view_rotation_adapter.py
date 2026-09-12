"""Unit tests for novel-view pose direction adapter."""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from avroom_object_removal.ai_engines.novel_view.novel_view_rotation_adapter import (
    BACK,
    FRONT,
    HIGH_TILT,
    LOW_TILT,
    QUARTER,
    SIDE,
    THREE_QUARTER,
    ZOOM_STEP,
    AzimuthDirection,
    ElevationDirection,
    NovelViewRotationAdapter,
    ZoomDirection,
)


class TestAzimuthDirection:
    def test_passthrough_signed_value(self) -> None:
        assert NovelViewRotationAdapter.to_signed_azimuth(-30.0) == -30.0
        assert NovelViewRotationAdapter.to_signed_azimuth(45.0) == 45.0

    def test_clockwise_positive(self) -> None:
        assert (
            NovelViewRotationAdapter.to_signed_azimuth(
                QUARTER,
                AzimuthDirection.CLOCKWISE,
            )
            == 45.0
        )

    def test_counter_clockwise_negative(self) -> None:
        assert (
            NovelViewRotationAdapter.to_signed_azimuth(
                SIDE,
                AzimuthDirection.C_CLOCKWISE,
            )
            == -90.0
        )

    def test_zero_with_direction(self) -> None:
        assert (
            NovelViewRotationAdapter.to_signed_azimuth(
                FRONT,
                AzimuthDirection.CLOCKWISE,
            )
            == 0.0
        )

    def test_named_constants(self) -> None:
        assert BACK == 180.0
        assert THREE_QUARTER == 135.0

    def test_rejects_negative_magnitude_with_direction(self) -> None:
        with pytest.raises(ValueError, match="non-negative"):
            NovelViewRotationAdapter.to_signed_azimuth(
                -15.0,
                AzimuthDirection.CLOCKWISE,
            )

    def test_rejects_non_finite_without_direction(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            NovelViewRotationAdapter.to_signed_azimuth(float("nan"))

    def test_rejects_non_finite_with_direction(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            NovelViewRotationAdapter.to_signed_azimuth(
                float("inf"),
                AzimuthDirection.CLOCKWISE,
            )


class TestElevationDirection:
    def test_passthrough_signed_value(self) -> None:
        assert NovelViewRotationAdapter.to_signed_elevation(-10.0) == -10.0

    def test_up_positive(self) -> None:
        assert (
            NovelViewRotationAdapter.to_signed_elevation(
                LOW_TILT,
                ElevationDirection.UP,
            )
            == 15.0
        )

    def test_down_negative(self) -> None:
        assert (
            NovelViewRotationAdapter.to_signed_elevation(
                HIGH_TILT,
                ElevationDirection.DOWN,
            )
            == -45.0
        )

    def test_rejects_negative_magnitude_with_direction(self) -> None:
        with pytest.raises(ValueError, match="non-negative"):
            NovelViewRotationAdapter.to_signed_elevation(
                -5.0,
                ElevationDirection.UP,
            )


class TestZoomDirection:
    def test_passthrough_signed_value(self) -> None:
        assert NovelViewRotationAdapter.to_signed_radius(-0.25) == -0.25

    def test_zoom_in_negative(self) -> None:
        assert (
            NovelViewRotationAdapter.to_signed_radius(
                ZOOM_STEP,
                ZoomDirection.ZOOM_IN,
            )
            == -0.5
        )

    def test_zoom_out_positive(self) -> None:
        assert (
            NovelViewRotationAdapter.to_signed_radius(
                ZOOM_STEP,
                ZoomDirection.ZOOM_OUT,
            )
            == 0.5
        )

    def test_rejects_negative_magnitude_with_direction(self) -> None:
        with pytest.raises(ValueError, match="non-negative"):
            NovelViewRotationAdapter.to_signed_radius(
                -1.0,
                ZoomDirection.ZOOM_IN,
            )


class TestResolvePose:
    def test_resolves_all_axes(self) -> None:
        resolved = NovelViewRotationAdapter.resolve_pose(
            azimuth_deg=QUARTER,
            relative_elevation_deg=LOW_TILT,
            radius=ZOOM_STEP,
            azimuth_direction=AzimuthDirection.C_CLOCKWISE,
            elevation_direction=ElevationDirection.UP,
            zoom_direction=ZoomDirection.ZOOM_IN,
        )
        assert resolved.azimuth_deg == -45.0
        assert resolved.relative_elevation_deg == 15.0
        assert resolved.radius == -0.5

    def test_no_directions_passthrough(self) -> None:
        resolved = NovelViewRotationAdapter.resolve_pose(
            azimuth_deg=-20.0,
            relative_elevation_deg=5.0,
            radius=-0.1,
        )
        assert resolved.azimuth_deg == -20.0
        assert resolved.relative_elevation_deg == 5.0
        assert math.isclose(resolved.radius, -0.1)
