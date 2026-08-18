from __future__ import annotations

import base64
import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any, Callable

import cv2
import numpy as np

from ..crop import crop_around_mask
from ..inpaint_sd_params import InpaintSdParams
from ..inpainting_verification_result import InpaintingVerificationResult
from ..inpainting_verification_strategy import InpaintingVerificationStrategy
from .clip_label_inpainting_verification_strategy import (
    ClipLabelInpaintingVerificationStrategy,
)

logger = logging.getLogger(__name__)

PLACEHOLDER_API_KEY: str = "placeholder"
DEFAULT_MODEL_ID: str = "gemini-2.5-flash-lite"
_GENERATE_URL: str = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
)

CompleteFn = Callable[[np.ndarray, InpaintSdParams], str]

_SYSTEM_PROMPT: str = (
    "You judge ONLY the inpainted hole in this crop, not the rest of the room. "
    "Fail (ok=false) if you see a leftover object shadow, dark oval, ghost stain, "
    "blur, grain mismatch, or texture that does not match the surrounding floor/wall. "
    "Pass only if the hole is a seamless continuation of the surrounding surface. "
    "Current Stable Diffusion knobs are in the JSON below. Reply with JSON only: "
    "ok (bool), winner_label (string), prompt, negative_prompt, strength (float), "
    "num_inference_steps (int), guidance_scale (float), mask_dilate_pixels (int), "
    "compose_dilate_pixels (int). If ok is true, copy the input knobs and set both "
    "dilate fields to 0. If ok is false, rewrite prompt/negative_prompt to demand "
    "matching floor/wall texture and forbid leftover shadows; raise strength toward "
    "0.6. Decide mask_dilate_pixels: 0 if the hole size is fine; 4-16 if shadow or "
    "leftover edges sit outside the current mask. Decide compose_dilate_pixels: 0 if "
    "paste boundary is fine; 4-12 if fixes must be committed wider than the cutout."
)

GEMINI_CROP_PAD_RATIO: float = 0.35


class GeminiInpaintingVerificationStrategy(InpaintingVerificationStrategy):
    """Gemini generateContent judge for one inpaint candidate.

    Sends a padded mask crop plus the current :class:`InpaintSdParams`. On
    fail, ``param_fixes_json`` carries Gemini's rewritten knobs for Hybrid
    replay. Missing/placeholder key, HTTP errors, and unparseable JSON fall
    back to :class:`ClipLabelInpaintingVerificationStrategy`.
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
        if self._model_id_override is not None:
            override = self._model_id_override.strip()
            return override or DEFAULT_MODEL_ID
        raw = (os.environ.get("GEMINI_MODEL") or DEFAULT_MODEL_ID).strip()
        return raw or DEFAULT_MODEL_ID

    def _has_real_key(self) -> bool:
        key = (self._api_key or "").strip()
        return bool(key) and key.lower() != PLACEHOLDER_API_KEY

    def verify(
        self,
        image: np.ndarray,
        mask: np.ndarray,
        params: InpaintSdParams,
    ) -> InpaintingVerificationResult:
        crop = crop_around_mask(image, mask, pad_ratio=GEMINI_CROP_PAD_RATIO)
        if self._complete_fn is None and not self._has_real_key():
            logger.warning("GEMINI_API_KEY is placeholder; falling back to CLIP verify.")
            return self._clip.verify(image, mask, params)
        try:
            raw = (
                self._complete_fn(crop, params)
                if self._complete_fn is not None
                else self._call_gemini(crop, params)
            )
            parsed = _parse_gemini_payload(raw, params)
        except (ValueError, KeyError, TypeError, json.JSONDecodeError, OSError) as exc:
            logger.warning("Gemini inpaint verify failed (%s); falling back to CLIP.", exc)
            return self._clip.verify(image, mask, params)

        ok, winner, fixed = parsed
        logger.info("Inpaint Gemini verify ok=%s winner=%s", ok, winner)
        return InpaintingVerificationResult(
            ok=ok,
            param_fixes_json=params.to_json() if ok else fixed.to_json(),
            scores={},
            winner_label=winner,
        )

    def _call_gemini(self, crop_bgr: np.ndarray, params: InpaintSdParams) -> str:
        ok_flag, buf = cv2.imencode(".png", crop_bgr)
        if not ok_flag:
            raise ValueError("Failed to encode inpaint crop as PNG")
        b64 = base64.b64encode(bytes(buf)).decode("ascii")
        body: dict[str, Any] = {
            "contents": [
                {
                    "parts": [
                        {"text": _SYSTEM_PROMPT + "\n" + params.to_json()},
                        {"inline_data": {"mime_type": "image/png", "data": b64}},
                    ]
                }
            ],
            "generationConfig": {"responseMimeType": "application/json"},
        }
        url = _GENERATE_URL.format(model=self._resolve_model_id())
        request = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": self._api_key,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:400]
            raise OSError(f"Gemini HTTP {exc.code}: {detail}") from exc
        return _extract_text(payload)


def _extract_text(payload: dict[str, Any]) -> str:
    candidates = payload.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise ValueError("Gemini response missing candidates")
    content = candidates[0].get("content") if isinstance(candidates[0], dict) else None
    if not isinstance(content, dict):
        raise ValueError("Gemini response missing content")
    parts = content.get("parts")
    if not isinstance(parts, list) or not parts:
        raise ValueError("Gemini response missing parts")
    text = parts[0].get("text") if isinstance(parts[0], dict) else None
    if not isinstance(text, str) or not text.strip():
        raise ValueError("Gemini response missing text")
    return text


def _parse_gemini_payload(
    raw: str, fallback: InpaintSdParams
) -> tuple[bool, str, InpaintSdParams]:
    data: Any = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("Gemini JSON must be an object")
    ok = bool(data["ok"])
    winner = str(
        data.get("winner_label")
        or ("clean texture" if ok else "leftover shadow")
    )
    merged = {
        "prompt": data.get("prompt", fallback.prompt),
        "negative_prompt": data.get("negative_prompt", fallback.negative_prompt),
        "strength": data.get("strength", fallback.strength),
        "num_inference_steps": data.get("num_inference_steps", fallback.num_inference_steps),
        "guidance_scale": data.get("guidance_scale", fallback.guidance_scale),
        "mask_dilate_pixels": data.get("mask_dilate_pixels", 0),
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
    return ok, winner, fixed
