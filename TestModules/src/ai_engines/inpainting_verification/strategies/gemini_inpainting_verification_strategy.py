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
DEFAULT_MODEL_ID: str = "gemini-2.0-flash"
_GENERATE_URL: str = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
)

CompleteFn = Callable[[np.ndarray, InpaintSdParams], str]

_SYSTEM_PROMPT: str = (
    "You judge a room-photo inpaint crop. Current Stable Diffusion knobs are "
    "in the JSON below. Reply with JSON only: ok (bool), winner_label (string), "
    "prompt, negative_prompt, strength (float), num_inference_steps (int), "
    "guidance_scale (float). If ok is true, copy the input knobs. If ok is "
    "false, rewrite prompt/negative_prompt and optionally the numeric knobs "
    "so a retry is more likely to fill the hole with photorealistic background."
)


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
        model_id: str = DEFAULT_MODEL_ID,
        complete_fn: CompleteFn | None = None,
        clip_fallback: ClipLabelInpaintingVerificationStrategy | None = None,
    ) -> None:
        self._api_key = (
            api_key
            if api_key is not None
            else os.environ.get("GEMINI_API_KEY", PLACEHOLDER_API_KEY)
        )
        self._model_id = model_id
        self._complete_fn = complete_fn
        self._clip = clip_fallback or ClipLabelInpaintingVerificationStrategy()
        logger.info(
            "GeminiInpaintingVerificationStrategy configured (model=%s key_set=%s)",
            model_id,
            self._has_real_key(),
        )

    def _has_real_key(self) -> bool:
        key = (self._api_key or "").strip()
        return bool(key) and key.lower() != PLACEHOLDER_API_KEY

    def verify(
        self,
        image: np.ndarray,
        mask: np.ndarray,
        params: InpaintSdParams,
    ) -> InpaintingVerificationResult:
        crop = crop_around_mask(image, mask)
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
        url = _GENERATE_URL.format(model=self._model_id) + f"?key={self._api_key}"
        request = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise OSError(f"Gemini HTTP {exc.code}") from exc
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
    winner = str(data.get("winner_label") or ("photorealistic room" if ok else "unrealistic shaped object"))
    merged = {
        "prompt": data.get("prompt", fallback.prompt),
        "negative_prompt": data.get("negative_prompt", fallback.negative_prompt),
        "strength": data.get("strength", fallback.strength),
        "num_inference_steps": data.get("num_inference_steps", fallback.num_inference_steps),
        "guidance_scale": data.get("guidance_scale", fallback.guidance_scale),
    }
    fixed = InpaintSdParams.from_json(json.dumps(merged))
    return ok, winner, fixed
