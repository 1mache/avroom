from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, Field


class DebugCheckResult(BaseModel):
    """One technical or content validation check's outcome, for the debug report."""

    name: Annotated[str, Field(description="Check identifier, e.g. 'blur' or 'exposure'.")]
    passed: Annotated[bool, Field(description="Whether this check passed.")]
    score: Annotated[
        float | None, Field(default=None, description="Check-specific numeric score, if any.")
    ]
    message: Annotated[
        str, Field(default="", description="Human-readable detail, populated mainly on failure.")
    ]


class DebugValidationResponse(BaseModel):
    """Full validation scoreboard for one uploaded image — technical + content checks.

    Unlike `POST /images/upload`, this never stops at the first failed check
    and never persists anything; it always returns 200 so a failed check reads
    as data, not an error.
    """

    ok: Annotated[bool, Field(description="True iff every technical and content check passed.")]
    technical_ok: Annotated[bool, Field(description="True iff every technical check passed.")]
    content_ok: Annotated[
        bool | None,
        Field(description="True/False if content validation ran; None if it was skipped."),
    ]
    technical: Annotated[
        list[DebugCheckResult], Field(description="Every technical check, in run order.")
    ]
    content: Annotated[
        list[DebugCheckResult],
        Field(default_factory=list, description="Every content (CLIP) check, if it ran."),
    ]
    content_skipped_reason: Annotated[
        str | None,
        Field(default=None, description="Why the content stage did not run, if it didn't."),
    ]
    elapsed_ms: Annotated[float, Field(description="Total wall time for both stages.")]


class DebugMaskCandidate(BaseModel):
    """One SAM cutout scored by auto mask pick."""

    index: Annotated[int, Field(description="Candidate index in SAM order.")]
    score: Annotated[float, Field(description="CLIP P(good); 0.0 when pre-filtered.")]
    reason: Annotated[str, Field(description="Prefilter or score tag, e.g. winner / click_miss.")]
    preview_b64: Annotated[str, Field(description="PNG preview with click marker, base64.")]
    clip_crop_b64: Annotated[
        str | None, Field(default=None, description="Gray-composited CLIP crop PNG, or null if not scored.")
    ]
    cutout_b64: Annotated[str, Field(description="BGRA cutout PNG, base64.")]


class DebugAutoMaskPickResponse(BaseModel):
    """All SAM candidates plus CLIP ranking for one click. No session writes."""

    click_xy: Annotated[list[int], Field(description="Natural-image click [x, y].")]
    threshold: Annotated[float, Field(description="Minimum P(good) to become winner.")]
    winner_index: Annotated[int | None, Field(description="Chosen candidate, or null.")]
    candidates: Annotated[list[DebugMaskCandidate], Field(description="Every SAM candidate.")]
    elapsed_ms: Annotated[float, Field(description="Wall time for segment + rank.")]


class DebugSdParams(BaseModel):
    """SD knobs used for one inpaint pass."""

    prompt: Annotated[str, Field(description="Positive prompt.")]
    negative_prompt: Annotated[str, Field(description="Negative prompt.")]
    strength: Annotated[float, Field(description="Denoising strength.")]
    num_inference_steps: Annotated[int, Field(description="Diffusion steps.")]
    guidance_scale: Annotated[float, Field(description="CFG scale.")]
    mask_dilate_pixels: Annotated[int, Field(default=0, description="Verifier mask expansion for next retry.")]
    compose_dilate_pixels: Annotated[int, Field(default=0, description="Verifier compose expansion for next retry.")]


class DebugInpaintAttempt(BaseModel):
    """One verify loop iteration after an SD (or skipped-SD) candidate."""

    attempt_index: Annotated[int, Field(description="0-based verify attempt.")]
    ok: Annotated[bool, Field(description="Whether the verifier passed this candidate.")]
    sd_skipped: Annotated[bool, Field(description="True if this attempt used LaMa only.")]
    scores: Annotated[dict[str, float], Field(description="CLIP label scores when fallback ran.")]
    winner_label: Annotated[str, Field(description="Verifier winner label.")]
    params: Annotated[DebugSdParams, Field(description="Params sent into this SD/verify pass.")]
    param_fixes_json: Annotated[str, Field(description="JSON returned by the verifier.")]
    mask_dilate_pixels: Annotated[int, Field(default=0, description="AI mask dilate for next retry.")]
    compose_dilate_pixels: Annotated[int, Field(default=0, description="AI compose dilate for next retry.")]
    mask_pixel_count: Annotated[int, Field(default=0, description="Inpaint mask pixel count at verify time.")]
    next_params: Annotated[DebugSdParams | None, Field(default=None, description="Parsed retry recipe on fail.")]
    candidate_b64: Annotated[str, Field(description="Full-image candidate PNG, base64.")]
    clip_crop_b64: Annotated[str, Field(description="Padded mask crop sent to verifier, base64.")]


class DebugInpaintVerifyResponse(BaseModel):
    """Hybrid inpaint + CLIP retry trace for one mask. No session writes."""

    click_xy: Annotated[list[int], Field(description="Natural-image click [x, y].")]
    mask_index: Annotated[int, Field(description="Candidate index that was inpainted.")]
    passed: Annotated[bool, Field(description="True if the last attempt passed CLIP.")]
    retries_exhausted: Annotated[bool, Field(description="True if CLIP never passed.")]
    lama_b64: Annotated[str | None, Field(description="LaMa-only PNG, if captured.")]
    final_b64: Annotated[str, Field(description="Final hybrid output after sharpen.")]
    attempts: Annotated[list[DebugInpaintAttempt], Field(description="Verify loop, in order.")]
    elapsed_ms: Annotated[float, Field(description="Wall time for segment + inpaint + verify.")]
