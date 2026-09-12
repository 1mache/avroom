from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request
from typing import Any

import cv2
import numpy as np

PLACEHOLDER_API_KEY: str = "placeholder"
DEFAULT_MODEL_ID: str = "gemini-2.5-flash-lite"
_GENERATE_URL: str = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
)
DEFAULT_TIMEOUT_S: int = 30


def resolve_model_id(model_id_override: str | None = None) -> str:
    """Return Gemini model id from override or ``GEMINI_MODEL`` env."""
    if model_id_override is not None:
        override = model_id_override.strip()
        return override or DEFAULT_MODEL_ID
    raw = (os.environ.get("GEMINI_MODEL") or DEFAULT_MODEL_ID).strip()
    return raw or DEFAULT_MODEL_ID


def has_real_api_key(api_key: str | None) -> bool:
    """True when ``api_key`` is set and not the placeholder sentinel."""
    key = (api_key or "").strip()
    return bool(key) and key.lower() != PLACEHOLDER_API_KEY


def encode_png_b64(crop_bgr: np.ndarray) -> str:
    """Encode a BGR array as base64 PNG for Gemini inline_data."""
    ok_flag, buf = cv2.imencode(".png", crop_bgr)
    if not ok_flag:
        raise ValueError("Failed to encode crop as PNG")
    return base64.b64encode(bytes(buf)).decode("ascii")


def post_gemini(
    parts: list[dict[str, Any]],
    *,
    api_key: str,
    model_id: str,
    timeout: int = DEFAULT_TIMEOUT_S,
) -> str:
    """POST a generateContent request and return the first text part."""
    body: dict[str, Any] = {
        "contents": [{"parts": parts}],
        "generationConfig": {"responseMimeType": "application/json"},
    }
    url = _GENERATE_URL.format(model=model_id)
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": api_key,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:400]
        raise OSError(f"Gemini HTTP {exc.code}: {detail}") from exc
    return extract_text(payload)


def extract_text(payload: dict[str, Any]) -> str:
    """Pull the first text part from a generateContent JSON payload."""
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
