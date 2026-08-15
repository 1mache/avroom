from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class InpaintingVerificationResult:
    """Outcome of one inpaint-quality check.

    ``param_fixes_json`` is always a JSON object string. On failure the CLIP
    v1 strategy echoes the input params (no invented knobs). A later strategy
    can put real deltas in the same field.
    """

    ok: bool
    param_fixes_json: str
