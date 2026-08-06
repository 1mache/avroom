from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ElevationEstimationResult:
    """Object-centric source elevation for Zero123-style novel-view synthesis."""

    elevation_deg: float
    used_calibration: bool
