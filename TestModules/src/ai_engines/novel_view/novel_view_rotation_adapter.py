from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

# Azimuth magnitude constants (degrees).
FRONT = 0.0
QUARTER = 45.0
SIDE = 90.0
THREE_QUARTER = 135.0
BACK = 180.0

# Relative elevation magnitude constants (degrees).
LEVEL = 0.0
LOW_TILT = 15.0
HIGH_TILT = 45.0

# Radius / zoom magnitude constants (model-specific distance delta).
NO_ZOOM = 0.0
ZOOM_STEP = 0.5


class AzimuthDirection(str, Enum):
    """Horizontal orbit direction viewed from above the object."""

    CLOCKWISE = "CLOCKWISE"
    C_CLOCKWISE = "C_CLOCKWISE"


class ElevationDirection(str, Enum):
    """Relative elevation tilt from the source view."""

    UP = "UP"
    DOWN = "DOWN"


class ZoomDirection(str, Enum):
    """Camera distance delta relative to the model default."""

    ZOOM_IN = "ZOOM_IN"
    ZOOM_OUT = "ZOOM_OUT"


@dataclass(frozen=True)
class ResolvedNovelViewPose:
    """Signed pose values ready for :class:`NovelViewFacade.synthesize`."""

    azimuth_deg: float
    relative_elevation_deg: float
    radius: float


class NovelViewRotationAdapter:
    """Convert optional readable pose directions into signed Zero123 pose values.

    When a direction is omitted for an axis, the supplied signed value is passed
    through unchanged. When a direction is present, the magnitude must be a
    finite non-negative number and is signed according to the direction enum.
    """

    @staticmethod
    def to_signed_azimuth(
        azimuth_deg: float,
        direction: AzimuthDirection | None = None,
    ) -> float:
        """Return signed azimuth for the model (CLOCKWISE positive, C_CLOCKWISE negative)."""

        return NovelViewRotationAdapter._apply_direction(
            azimuth_deg,
            direction,
            positive_when={
                AzimuthDirection.CLOCKWISE,
            },
            axis_name="azimuth_deg",
        )

    @staticmethod
    def to_signed_elevation(
        elevation_deg: float,
        direction: ElevationDirection | None = None,
    ) -> float:
        """Return signed relative elevation (UP positive, DOWN negative)."""

        return NovelViewRotationAdapter._apply_direction(
            elevation_deg,
            direction,
            positive_when={
                ElevationDirection.UP,
            },
            axis_name="relative_elevation_deg",
        )

    @staticmethod
    def to_signed_radius(
        radius: float,
        direction: ZoomDirection | None = None,
    ) -> float:
        """Return signed radius (ZOOM_OUT positive/farther, ZOOM_IN negative/closer)."""

        return NovelViewRotationAdapter._apply_direction(
            radius,
            direction,
            positive_when={
                ZoomDirection.ZOOM_OUT,
            },
            axis_name="radius",
        )

    @staticmethod
    def resolve_pose(
        *,
        azimuth_deg: float,
        relative_elevation_deg: float = 0.0,
        radius: float = 0.0,
        azimuth_direction: AzimuthDirection | None = None,
        elevation_direction: ElevationDirection | None = None,
        zoom_direction: ZoomDirection | None = None,
    ) -> ResolvedNovelViewPose:
        """Normalize all pose axes that supply an optional direction."""

        return ResolvedNovelViewPose(
            azimuth_deg=NovelViewRotationAdapter.to_signed_azimuth(
                azimuth_deg,
                azimuth_direction,
            ),
            relative_elevation_deg=NovelViewRotationAdapter.to_signed_elevation(
                relative_elevation_deg,
                elevation_direction,
            ),
            radius=NovelViewRotationAdapter.to_signed_radius(
                radius,
                zoom_direction,
            ),
        )

    @staticmethod
    def _apply_direction(
        magnitude: float,
        direction: Enum | None,
        *,
        positive_when: set[Enum],
        axis_name: str,
    ) -> float:
        if direction is None:
            if not math.isfinite(magnitude):
                raise ValueError(f"{axis_name} must be a finite number.")
            return magnitude

        if not math.isfinite(magnitude):
            raise ValueError(
                f"When {axis_name} direction is set, magnitude must be a finite number."
            )
        if magnitude < 0:
            raise ValueError(
                f"When {axis_name} direction is set, magnitude must be non-negative "
                f"(got {magnitude})."
            )

        signed = magnitude if direction in positive_when else -magnitude
        return signed
