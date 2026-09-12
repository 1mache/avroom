from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any

MAX_MASK_DILATE_PER_RETRY: int = 16
MAX_COMPOSE_DILATE_PER_RETRY: int = 12
MAX_CUMULATIVE_MASK_DILATE: int = 32


@dataclass(frozen=True)
class InpaintSdParams:
    """Snapshot of Stable Diffusion knobs and verifier retry directives.

    SD fields are inputs to one inpaint pass. ``mask_dilate_pixels`` and
    ``compose_dilate_pixels`` are **verifier output** on fail: the verification
    AI decides whether and how much to expand the inpaint hole and paste mask
    on the next retry (``0`` means no expansion).
    """

    prompt: str
    negative_prompt: str
    strength: float
    num_inference_steps: int
    guidance_scale: float
    mask_dilate_pixels: int = 0
    compose_dilate_pixels: int = 0

    def to_json(self) -> str:
        """Serialize known knobs to a JSON object string."""
        return json.dumps(asdict(self), separators=(",", ":"))

    @classmethod
    def from_json(cls, raw: str) -> InpaintSdParams:
        """Parse a JSON object, keeping only known fields."""
        data: Any = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError("InpaintSdParams JSON must be an object")
        return cls(
            prompt=str(data["prompt"]),
            negative_prompt=str(data["negative_prompt"]),
            strength=float(data["strength"]),
            num_inference_steps=int(data["num_inference_steps"]),
            guidance_scale=float(data["guidance_scale"]),
            mask_dilate_pixels=int(data.get("mask_dilate_pixels", 0)),
            compose_dilate_pixels=int(data.get("compose_dilate_pixels", 0)),
        )

    def clamp_dilate_fields(
        self,
        *,
        cumulative_mask_dilate: int = 0,
    ) -> InpaintSdParams:
        """Clamp AI-returned dilate values to safety caps without inventing expansion."""
        mask_cap = max(0, MAX_CUMULATIVE_MASK_DILATE - cumulative_mask_dilate)
        mask_dilate = min(max(0, self.mask_dilate_pixels), MAX_MASK_DILATE_PER_RETRY, mask_cap)
        compose_dilate = min(max(0, self.compose_dilate_pixels), MAX_COMPOSE_DILATE_PER_RETRY)
        if mask_dilate == self.mask_dilate_pixels and compose_dilate == self.compose_dilate_pixels:
            return self
        return InpaintSdParams(
            prompt=self.prompt,
            negative_prompt=self.negative_prompt,
            strength=self.strength,
            num_inference_steps=self.num_inference_steps,
            guidance_scale=self.guidance_scale,
            mask_dilate_pixels=mask_dilate,
            compose_dilate_pixels=compose_dilate,
        )
