from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


@dataclass(frozen=True)
class GenerationParams:
    """Subset of Trellis 2 parameters that meaningfully trade quality for speed.

    All other inputs to the Space (`ss_*`, `shape_slat_*`, `tex_slat_*`
    guidance strengths / rescales / rescale_t values) are held at the Space's
    own published defaults inside
    :class:`TrellisReconstructionStrategy`, because they affect generation
    fidelity rather than wall time and have no clear "better for our case"
    setting.

    Only the four fields below differ between presets:

    * ``resolution`` -- exported voxel grid; one of ``"512" / "1024" / "1536"``.
    * ``sampling_steps`` -- shared step count applied to all three diffusion
      stages (``ss``, ``shape_slat``, ``tex_slat``). Higher = slower + sharper.
    * ``decimation_target`` -- target triangle count for the GLB mesh
      (Space range ``100_000 - 500_000``).
    * ``texture_size`` -- exported texture edge in pixels (``1024 - 4096``).
    """

    resolution: str
    sampling_steps: int
    decimation_target: int
    texture_size: int


class ReconstructionQuality(str, Enum):
    """Quality preset for 3D reconstruction. Higher quality = slower wall time.

    On the public Trellis 2 Space (Zero GPU), FAST targets <=60 s end-to-end
    including queue wait at off-peak hours.
    """

    FAST = "fast"
    BALANCED = "balanced"
    HIGH = "high"


PRESETS: dict[ReconstructionQuality, GenerationParams] = {
    ReconstructionQuality.FAST: GenerationParams(
        resolution="512",
        sampling_steps=10,
        decimation_target=100_000,
        texture_size=1024,
    ),
    ReconstructionQuality.BALANCED: GenerationParams(
        resolution="1024",
        sampling_steps=25,
        decimation_target=300_000,
        texture_size=2048,
    ),
    ReconstructionQuality.HIGH: GenerationParams(
        resolution="1536",
        sampling_steps=50,
        decimation_target=500_000,
        texture_size=4096,
    ),
}
