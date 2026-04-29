from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


@dataclass(frozen=True)
class GenerationParams:
    """All parameters forwarded to the Trellis 2 Space.

    The Space exposes a two-step pipeline:
    - Step 1 (image_to_3d): 15 inputs — image, seed, resolution, then 4 groups
      of 3 guidance params (ss, shape_slat, tex_slat stages).
    - Step 2 (extract_glb): decimation_target + texture_size control mesh density
      and texture resolution of the exported GLB.

    Guidance strengths / rescales / rescale_t are held constant across presets
    because they affect generation fidelity, not speed. Only step counts and
    export resolution vary between FAST / BALANCED / HIGH.
    """

    # -- Step 1 --
    resolution: str  # "512" | "1024" | "1536"

    # Sparse-structure (shape coarse pass)
    ss_guidance_strength: float
    ss_guidance_rescale: float
    ss_sampling_steps: int
    ss_rescale_t: float

    # Shape SLAT (fine shape pass)
    shape_slat_guidance_strength: float
    shape_slat_guidance_rescale: float
    shape_slat_sampling_steps: int
    shape_slat_rescale_t: float

    # Texture SLAT (material / color pass)
    tex_slat_guidance_strength: float
    tex_slat_guidance_rescale: float
    tex_slat_sampling_steps: int
    tex_slat_rescale_t: float

    # -- Step 2 --
    decimation_target: int   # triangle count after decimation
    texture_size: int        # texture atlas resolution in px


class Quality(str, Enum):
    """Generation quality preset. Higher quality = slower wall-clock time.

    On the public Space (Zero GPU), FAST targets ≤60 s end-to-end including
    queue wait at off-peak hours (512³ shape takes ~3 s on H100).
    """

    FAST = "fast"
    BALANCED = "balanced"
    HIGH = "high"


# Guidance constants shared across all presets (tuned for plausibility, not speed).
_SS_STRENGTH = 7.5
_SS_RESCALE = 0.7
_SS_RESCALE_T = 0.7
_SLAT_STRENGTH = 7.5
_SLAT_RESCALE = 0.7
_SLAT_RESCALE_T = 0.7

PRESETS: dict[Quality, GenerationParams] = {
    Quality.FAST: GenerationParams(
        resolution="512",
        ss_guidance_strength=_SS_STRENGTH,
        ss_guidance_rescale=_SS_RESCALE,
        ss_sampling_steps=10,
        ss_rescale_t=_SS_RESCALE_T,
        shape_slat_guidance_strength=_SLAT_STRENGTH,
        shape_slat_guidance_rescale=_SLAT_RESCALE,
        shape_slat_sampling_steps=10,
        shape_slat_rescale_t=_SLAT_RESCALE_T,
        tex_slat_guidance_strength=_SLAT_STRENGTH,
        tex_slat_guidance_rescale=_SLAT_RESCALE,
        tex_slat_sampling_steps=10,
        tex_slat_rescale_t=_SLAT_RESCALE_T,
        decimation_target=100_000,
        texture_size=1024,
    ),
    Quality.BALANCED: GenerationParams(
        resolution="1024",
        ss_guidance_strength=_SS_STRENGTH,
        ss_guidance_rescale=_SS_RESCALE,
        ss_sampling_steps=25,
        ss_rescale_t=_SS_RESCALE_T,
        shape_slat_guidance_strength=_SLAT_STRENGTH,
        shape_slat_guidance_rescale=_SLAT_RESCALE,
        shape_slat_sampling_steps=25,
        shape_slat_rescale_t=_SLAT_RESCALE_T,
        tex_slat_guidance_strength=_SLAT_STRENGTH,
        tex_slat_guidance_rescale=_SLAT_RESCALE,
        tex_slat_sampling_steps=25,
        tex_slat_rescale_t=_SLAT_RESCALE_T,
        decimation_target=300_000,
        texture_size=2048,
    ),
    Quality.HIGH: GenerationParams(
        resolution="1536",
        ss_guidance_strength=_SS_STRENGTH,
        ss_guidance_rescale=_SS_RESCALE,
        ss_sampling_steps=50,
        ss_rescale_t=_SS_RESCALE_T,
        shape_slat_guidance_strength=_SLAT_STRENGTH,
        shape_slat_guidance_rescale=_SLAT_RESCALE,
        shape_slat_sampling_steps=50,
        shape_slat_rescale_t=_SLAT_RESCALE_T,
        tex_slat_guidance_strength=_SLAT_STRENGTH,
        tex_slat_guidance_rescale=_SLAT_RESCALE,
        tex_slat_sampling_steps=50,
        tex_slat_rescale_t=_SLAT_RESCALE_T,
        decimation_target=500_000,
        texture_size=4096,
    ),
}
