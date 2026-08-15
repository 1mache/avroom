from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class InpaintingVerificationResult:
    """Outcome of one inpaint-quality check.

    ``param_fixes_json`` is always a JSON object string. Gemini puts rewritten
    knobs here on fail. CLIP fallback echoes the input params.
    """

    ok: bool
    param_fixes_json: str
    scores: dict[str, float]
    winner_label: str
