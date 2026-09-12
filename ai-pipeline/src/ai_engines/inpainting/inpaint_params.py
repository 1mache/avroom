from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class InpaintParams:
    """Caller-facing knobs for :meth:`ImageInpaintingStrategy.inpaint`.

    ``prompt``/``negative_prompt`` left ``None`` fall back to whatever the SD
    strategy instance was constructed with (see
    :class:`StableDiffusionInpaintingStrategy`'s ``prompt``/``negative_prompt``
    constructor args) rather than a fixed default -- a strategy created with
    a custom prompt should not need a caller to repeat it on every call.
    A strategy that reads no knobs at all (e.g. :class:`LamaInpaintingStrategy`)
    ignores this type entirely, which is why it is optional on the interface.
    """

    prompt: str | None = None
    negative_prompt: str | None = None
    strength: float = 0.40
    num_inference_steps: int = 42
    guidance_scale: float = 10.0
