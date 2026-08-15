from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class InpaintSdParams:
    """Snapshot of Stable Diffusion knobs used for one inpaint pass.

    Unknown JSON keys are dropped on parse so a later verifier can add
    fields without breaking v1 replay (Hybrid only forwards known keys).
    """

    prompt: str
    negative_prompt: str
    strength: float
    num_inference_steps: int
    guidance_scale: float

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
        )
