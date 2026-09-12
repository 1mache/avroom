from __future__ import annotations

import json
import logging
import os
from typing import Any, Callable

import numpy as np

from ....utils.mask_bool import mask_pixel_count
from ...gemini.gemini_client import (
    DEFAULT_MODEL_ID,
    PLACEHOLDER_API_KEY,
    encode_png_b64,
    has_real_api_key,
    post_gemini,
    resolve_model_id,
)
from ..crop import (
    GEMINI_CROP_PAD_RATIO,
    CropWindow,
    build_verify_crops,
    crop_around_mask,
    mask_pixels_in_window,
)
from ..inpaint_sd_params import InpaintSdParams
from ..inpainting_verification_result import InpaintingVerificationResult
from ..inpainting_verification_strategy import InpaintingVerificationStrategy
from .clip_label_inpainting_verification_strategy import (
    ClipLabelInpaintingVerificationStrategy,
)

logger = logging.getLogger(__name__)

CompleteFn = Callable[[np.ndarray, np.ndarray, InpaintSdParams], str]

_SYSTEM_PROMPT: str = (
    "You compare two crops of the same window. Image 1 is the original scene before "
    "inpainting. Image 2 is the inpainted result; the cyan outline marks the inpaint "
    "region. Judge ONLY pixels INSIDE the cyan outline on image 2 against the "
    "surrounding surface visible in image 1 just OUTSIDE the outline. "
    "Fail (ok=false) if you see a leftover object shadow, dark oval, ghost stain, blur, "
    "grain mismatch, smeared blob, or invented furniture/table inside the outline. "
    "Pass only if the filled region is a seamless continuation of the surrounding "
    "floor/wall. "
    "Estimate smearyness_score (float 0.0-1.0): 0.0 = perfectly sharp, crisp texture "
    "matching the surroundings; 1.0 = completely blurred, blotchy, or smeared fill. "
    "Current Stable Diffusion knobs are in the JSON below. Reply with JSON only, "
    "always include ALL of these fields: ok (bool), winner_label (string), "
    "smearyness_score (float 0.0-1.0), prompt, negative_prompt, strength (float), "
    "num_inference_steps (int), guidance_scale (float), mask_dilate_pixels (int), "
    "compose_dilate_pixels (int). "
    "If ok is true, copy the input knobs and set both dilate fields to 0. "
    "If ok is false, rewrite prompt/negative_prompt to demand matching floor/wall "
    "texture and forbid leftover shadows. Then tune SD knobs based on the PRIMARY CAUSE: "
    "IMPORTANT — strength multiplies the effective step count (actual steps = "
    "int(num_inference_steps * strength)), so very low strength means very few "
    "denoising steps regardless of num_inference_steps. "
    "If smearyness_score > 0.5 (blurred/blotchy fill is the main issue): "
    "RAISE strength toward 0.45-0.6 (more denoising redrawing over the blurry base), "
    "RAISE num_inference_steps by 10-20 (more refinement budget), and optionally "
    "RAISE guidance_scale by 1-2 (sharper adherence to prompt). "
    "Set mask_dilate_pixels = 0 — expanding the hole cannot fix blurriness and only "
    "adds more area to smear. "
    "If smearyness_score <= 0.5 and hallucinated furniture/objects appear: "
    "LOWER strength toward 0.2-0.3 (preserve more of the structural base) and "
    "strengthen negative_prompt to forbid the hallucinated content. "
    "If smearyness_score <= 0.5 and shadow/edge/grain mismatch is the failure: "
    "keep strength near current value; "
    "decide mask_dilate_pixels: 0 if hole size is fine, 4-16 if shadow or leftover "
    "edges sit outside the current mask; "
    "decide compose_dilate_pixels: 0 if paste boundary is fine, 4-12 if fixes must "
    "be committed wider than the cutout."
)


class GeminiInpaintingVerificationStrategy(InpaintingVerificationStrategy):
    """Gemini generateContent judge for one inpaint candidate.

    Sends original + outlined candidate crops of the same window plus the current
    :class:`InpaintSdParams`. On fail, ``param_fixes_json`` carries Gemini's rewritten
    knobs for Hybrid replay. Missing/placeholder key, HTTP errors, and unparseable JSON
    fall back to :class:`ClipLabelInpaintingVerificationStrategy`.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model_id: str | None = None,
        complete_fn: CompleteFn | None = None,
        clip_fallback: ClipLabelInpaintingVerificationStrategy | None = None,
    ) -> None:
        self._api_key = (
            api_key
            if api_key is not None
            else os.environ.get("GEMINI_API_KEY", PLACEHOLDER_API_KEY)
        )
        self._model_id_override = model_id
        self._complete_fn = complete_fn
        self._clip = clip_fallback or ClipLabelInpaintingVerificationStrategy()
        logger.info(
            "GeminiInpaintingVerificationStrategy configured (model=%s key_set=%s)",
            self._resolve_model_id(),
            self._has_real_key(),
        )

    def _resolve_model_id(self) -> str:
        """Return the model id from constructor override or ``GEMINI_MODEL`` env."""
        return resolve_model_id(self._model_id_override)

    def _has_real_key(self) -> bool:
        return has_real_api_key(self._api_key)

    def verify(
        self,
        image: np.ndarray,
        mask: np.ndarray,
        params: InpaintSdParams,
        *,
        original_image: np.ndarray | None = None,
    ) -> InpaintingVerificationResult:
        dual_crop = original_image is not None
        window: CropWindow | None = None
        outlined_crop: np.ndarray
        original_crop: np.ndarray | None = None

        if dual_crop:
            assert original_image is not None
            original_crop, outlined_crop, window = build_verify_crops(
                original_image,
                image,
                mask,
                pad_ratio=GEMINI_CROP_PAD_RATIO,
            )
        else:
            logger.warning(
                "Gemini verify missing original_image; falling back to single-crop."
            )
            outlined_crop = crop_around_mask(image, mask, pad_ratio=GEMINI_CROP_PAD_RATIO)
            original_crop = None

        if self._complete_fn is None and not self._has_real_key():
            logger.warning("GEMINI_API_KEY is placeholder; falling back to CLIP verify.")
            return self._clip_fallback(image, mask, params, reason="placeholder key")

        try:
            if self._complete_fn is not None:
                if dual_crop:
                    assert original_crop is not None
                    raw = self._complete_fn(original_crop, outlined_crop, params)
                else:
                    raw = self._complete_fn(outlined_crop, outlined_crop, params)
            elif dual_crop:
                assert original_crop is not None
                raw = self._call_gemini(original_crop, outlined_crop, params)
            else:
                raw = self._call_gemini_legacy(outlined_crop, params)
            parsed = _parse_gemini_payload(raw, params)
        except (ValueError, KeyError, TypeError, json.JSONDecodeError, OSError) as exc:
            logger.warning("Gemini inpaint verify failed (%s); falling back to CLIP.", exc)
            return self._clip_fallback(image, mask, params, reason=str(exc))

        ok, winner, fixed, smearyness_score = parsed
        crop_h, crop_w = outlined_crop.shape[:2]
        mask_px = (
            mask_pixels_in_window(mask, window)
            if window is not None
            else mask_pixel_count(mask)
        )
        _log_gemini_verify(
            ok=ok,
            winner=winner,
            params=params,
            fixed=fixed,
            model=self._resolve_model_id(),
            crop_w=crop_w,
            crop_h=crop_h,
            window=window,
            mask_px=mask_px,
            dual_crop=dual_crop,
            smearyness_score=smearyness_score,
        )
        return InpaintingVerificationResult(
            ok=ok,
            param_fixes_json=params.to_json() if ok else fixed.to_json(),
            scores={},
            winner_label=winner,
        )

    def _clip_fallback(
        self,
        image: np.ndarray,
        mask: np.ndarray,
        params: InpaintSdParams,
        *,
        reason: str,
    ) -> InpaintingVerificationResult:
        try:
            result = self._clip.verify(image, mask, params)
        except Exception as exc:
            # Network / HF hub blips must not discard an already-finished inpaint.
            logger.warning(
                "Gemini verify CLIP fallback also failed (%s); "
                "accepting candidate without verify. gemini_reason=%s",
                exc,
                reason,
            )
            return InpaintingVerificationResult(
                ok=True,
                param_fixes_json=params.to_json(),
                scores={},
                winner_label="verify_unavailable",
            )
        top_label = result.winner_label
        top_score = result.scores.get(top_label, 0.0) if result.scores else 0.0
        logger.warning(
            "Gemini verify CLIP fallback reason=%s clip_ok=%s clip_winner=%s top_score=%.3f",
            reason,
            result.ok,
            top_label,
            top_score,
        )
        return result

    def _call_gemini(
        self,
        original_crop_bgr: np.ndarray,
        outlined_crop_bgr: np.ndarray,
        params: InpaintSdParams,
    ) -> str:
        parts: list[dict[str, Any]] = [
            {"text": _SYSTEM_PROMPT},
            {"text": "Image 1: original before inpainting."},
            {"inline_data": {"mime_type": "image/png", "data": encode_png_b64(original_crop_bgr)}},
            {"text": "Image 2: inpainted result; cyan outline = inpaint region."},
            {"inline_data": {"mime_type": "image/png", "data": encode_png_b64(outlined_crop_bgr)}},
            {"text": params.to_json()},
        ]
        return post_gemini(parts, api_key=self._api_key, model_id=self._resolve_model_id())

    def _call_gemini_legacy(self, crop_bgr: np.ndarray, params: InpaintSdParams) -> str:
        parts: list[dict[str, Any]] = [
            {"text": _SYSTEM_PROMPT + "\n" + params.to_json()},
            {"inline_data": {"mime_type": "image/png", "data": encode_png_b64(crop_bgr)}},
        ]
        return post_gemini(parts, api_key=self._api_key, model_id=self._resolve_model_id())


def _parse_gemini_payload(
    raw: str, fallback: InpaintSdParams
) -> tuple[bool, str, InpaintSdParams, float | None]:
    data: Any = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("Gemini JSON must be an object")
    ok = bool(data["ok"])
    winner = str(
        data.get("winner_label")
        or ("clean texture" if ok else "leftover shadow")
    )
    raw_smear = data.get("smearyness_score")
    smearyness_score: float | None = (
        float(raw_smear) if raw_smear is not None else None
    )
    # High smearyness means the fill is blurry — expanding the hole adds more area
    # to smear and cannot fix the root cause, so force the dilation to zero.
    smear_dominant = smearyness_score is not None and smearyness_score > 0.5
    merged = {
        "prompt": data.get("prompt", fallback.prompt),
        "negative_prompt": data.get("negative_prompt", fallback.negative_prompt),
        "strength": data.get("strength", fallback.strength),
        "num_inference_steps": data.get("num_inference_steps", fallback.num_inference_steps),
        "guidance_scale": data.get("guidance_scale", fallback.guidance_scale),
        "mask_dilate_pixels": 0 if smear_dominant else data.get("mask_dilate_pixels", 0),
        "compose_dilate_pixels": data.get("compose_dilate_pixels", 0),
    }
    fixed = InpaintSdParams.from_json(json.dumps(merged))
    if ok:
        fixed = InpaintSdParams(
            prompt=fixed.prompt,
            negative_prompt=fixed.negative_prompt,
            strength=fixed.strength,
            num_inference_steps=fixed.num_inference_steps,
            guidance_scale=fixed.guidance_scale,
            mask_dilate_pixels=0,
            compose_dilate_pixels=0,
        )
    return ok, winner, fixed, smearyness_score


def _log_gemini_verify(
    *,
    ok: bool,
    winner: str,
    params: InpaintSdParams,
    fixed: InpaintSdParams,
    model: str,
    crop_w: int,
    crop_h: int,
    window: CropWindow | None,
    mask_px: int,
    dual_crop: bool,
    smearyness_score: float | None = None,
) -> None:
    window_text = (
        f"({window.y0},{window.y1})-({window.x0},{window.x1})"
        if window is not None
        else "n/a"
    )
    strength = params.strength if ok else fixed.strength
    mask_dilate = 0 if ok else fixed.mask_dilate_pixels
    compose_dilate = 0 if ok else fixed.compose_dilate_pixels
    smear_text = f"{smearyness_score:.2f}" if smearyness_score is not None else "n/a"
    base = (
        "Inpaint Gemini verify ok=%s winner=%s smearyness_score=%s model=%s crop=%dx%d "
        "window=%s mask_px=%d dual_crop=%s strength=%s mask_dilate=%s compose_dilate=%s"
    )
    if ok:
        logger.info(
            base,
            ok,
            winner,
            smear_text,
            model,
            crop_w,
            crop_h,
            window_text,
            mask_px,
            dual_crop,
            strength,
            mask_dilate,
            compose_dilate,
        )
        return
    prompt_snip = fixed.prompt[:80]
    logger.info(
        base
        + " next_strength=%s next_steps=%s next_guidance=%s "
          "next_mask_dilate=%s next_compose_dilate=%s next_prompt=%r",
        ok,
        winner,
        smear_text,
        model,
        crop_w,
        crop_h,
        window_text,
        mask_px,
        dual_crop,
        strength,
        mask_dilate,
        compose_dilate,
        fixed.strength,
        fixed.num_inference_steps,
        fixed.guidance_scale,
        fixed.mask_dilate_pixels,
        fixed.compose_dilate_pixels,
        prompt_snip,
    )
