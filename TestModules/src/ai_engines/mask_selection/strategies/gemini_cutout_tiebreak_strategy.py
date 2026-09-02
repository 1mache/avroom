from __future__ import annotations

import json
import logging
import os
from typing import Any, Callable

import cv2
import numpy as np

from ...gemini.gemini_client import (
    PLACEHOLDER_API_KEY,
    encode_png_b64,
    has_real_api_key,
    post_gemini,
    resolve_model_id,
)
from ...inpainting_verification.crop import (
    GEMINI_CROP_PAD_RATIO,
    draw_mask_outline,
    mask_crop_window,
)
from ..mask_selection_tiebreak_strategy import (
    MaskSelectionTiebreakStrategy,
    TiebreakRequest,
    TiebreakResult,
)

logger = logging.getLogger(__name__)

CompleteFn = Callable[[list[dict[str, Any]]], str]

_SYSTEM_PROMPT: str = (
    "You compare SAM segmentation candidates and pick exactly ONE mask for "
    "removing the single object the user clicked. The first image is a scene "
    "crop where a RED CIRCLE marks the click: first decide what single object "
    "sits under that red circle — everything else in the scene is background, "
    "even objects touching or overlapping it. Each numbered image is one "
    "candidate cutout on gray. Optional cyan outlines show that candidate's "
    "inpaint region on the original photo. "
    "Judge in this strict order:\n"
    "1. SINGLE OBJECT ONLY. The mask must segment exactly the ONE object "
    "under the red circle — not that object merged with a neighboring desk, "
    "table, chair, or shelf it touches, not an object group, and not a "
    "room/scene blob of wall+floor+furniture. If a candidate includes any "
    "second object or large background region (wall area, floor patch, "
    "ceiling), it is WRONG and must lose to any candidate that isolates only "
    "the clicked object, even if the isolated one looks less impressive. "
    "Prefer the tightest mask that still fully contains that one object.\n"
    "2. COMPLETENESS of that one object. Name what was clicked (chair, "
    "whiteboard, lamp, table...) and require ALL of its parts: for furniture "
    "include seat, back, arms, and every leg/support/base to the floor; for "
    "wall-mounted items include the full panel/surface and frame; for thin "
    "parts (legs, stands, bezels) treat them as object, never background. "
    "Compare candidates: if one is missing legs or is cut off mid-part, it "
    "loses to any complete version of the same object.\n"
    "3. PURITY (tie-break only). Among equally single and complete candidates, "
    "prefer clean edges with no leaked background and no stray pixels.\n"
    "Never reward a mask for covering more of the scene: rule 1 beats rule 2, "
    "so a complete-looking chair+desk merge still loses to a complete chair "
    "alone.\n"
    "Reply with JSON only: "
    '{"candidate_index": int, "reason": string}. '
    "candidate_index MUST be one of the listed indices."
)


class GeminiCutoutTiebreakStrategy(MaskSelectionTiebreakStrategy):
    """Gemini judge when CLIP averages tie among cutout finalists."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model_id: str | None = None,
        complete_fn: CompleteFn | None = None,
    ) -> None:
        self._api_key = (
            api_key
            if api_key is not None
            else os.environ.get("GEMINI_API_KEY", PLACEHOLDER_API_KEY)
        )
        self._model_id_override = model_id
        self._complete_fn = complete_fn
        logger.info(
            "GeminiCutoutTiebreakStrategy configured (model=%s key_set=%s)",
            self._resolve_model_id(),
            has_real_api_key(self._api_key),
        )

    def _resolve_model_id(self) -> str:
        return resolve_model_id(self._model_id_override)

    def pick_among(self, request: TiebreakRequest) -> TiebreakResult:
        if len(request.finalist_indices) == 1:
            only = request.finalist_indices[0]
            return TiebreakResult(
                candidate_index=only,
                reason="single finalist",
                method="clip_fallback",
            )

        if self._complete_fn is None and not has_real_api_key(self._api_key):
            return self._clip_fallback(request, reason="placeholder key")

        try:
            parts = self._build_parts(request)
            if self._complete_fn is not None:
                raw = self._complete_fn(parts)
            else:
                raw = post_gemini(
                    parts,
                    api_key=self._api_key,
                    model_id=self._resolve_model_id(),
                )
            candidate_index, reason = _parse_pick_payload(raw, request.finalist_indices)
        except (ValueError, KeyError, TypeError, json.JSONDecodeError, OSError) as exc:
            logger.warning("Gemini cutout tiebreak failed (%s); CLIP fallback.", exc)
            return self._clip_fallback(request, reason=str(exc))

        logger.info(
            "Gemini cutout tiebreak winner=%d finalists=%s reason=%r",
            candidate_index,
            request.finalist_indices,
            reason[:80],
        )
        return TiebreakResult(
            candidate_index=candidate_index,
            reason=reason,
            method="gemini",
        )

    def _clip_fallback(self, request: TiebreakRequest, *, reason: str) -> TiebreakResult:
        winner = max(
            request.finalist_indices,
            key=lambda index: request.clip_averages.get(index, 0.0),
        )
        logger.info(
            "Gemini cutout tiebreak CLIP fallback reason=%s winner=%d",
            reason,
            winner,
        )
        return TiebreakResult(
            candidate_index=winner,
            reason=f"clip_fallback: {reason}",
            method="clip_fallback",
        )

    def _build_parts(self, request: TiebreakRequest) -> list[dict[str, Any]]:
        click_points = request.click_xys or (request.click_xy,)
        scene = request.scene_bgr
        scene_marked = scene.copy()
        for click_x, click_y in click_points:
            cv2.circle(scene_marked, (click_x, click_y), 8, (0, 0, 255), 2)

        click_mask = np.zeros(scene.shape[:2], dtype=np.uint8)
        for click_x, click_y in click_points:
            if 0 <= click_y < scene.shape[0] and 0 <= click_x < scene.shape[1]:
                click_mask[click_y, click_x] = 255
        window = mask_crop_window(click_mask, pad_ratio=GEMINI_CROP_PAD_RATIO)
        scene_crop = scene_marked[window.y0 : window.y1, window.x0 : window.x1]

        indices_text = ", ".join(str(index) for index in request.finalist_indices)
        click_text = ", ".join(f"({x}, {y})" for x, y in click_points)
        parts: list[dict[str, Any]] = [
            {"text": _SYSTEM_PROMPT},
            {
                "text": (
                    f"Valid candidate_index values: [{indices_text}]. "
                    f"Clicks at {click_text}."
                ),
            },
            {"text": "Scene crop with click markers (red circles)."},
            {"inline_data": {"mime_type": "image/png", "data": encode_png_b64(scene_crop)}},
        ]

        for index in request.finalist_indices:
            crop_bgr = request.cutout_crops_bgr[index]
            parts.append({"text": f"Candidate {index}: cutout on gray."})
            parts.append(
                {
                    "inline_data": {
                        "mime_type": "image/png",
                        "data": encode_png_b64(crop_bgr),
                    },
                }
            )
            refined = (request.refined_masks or {}).get(index)
            if refined is not None:
                outlined = draw_mask_outline(scene_crop.copy(), refined, window)
                parts.append(
                    {
                        "text": (
                            f"Candidate {index}: scene crop with cyan inpaint outline."
                        ),
                    }
                )
                parts.append(
                    {
                        "inline_data": {
                            "mime_type": "image/png",
                            "data": encode_png_b64(outlined),
                        },
                    }
                )

        # Heuristic scores are deliberately NOT sent: they misrank
        # thin-structure completeness and would bias the visual judgment.
        return parts


def _parse_pick_payload(raw: str, allowed: tuple[int, ...]) -> tuple[int, str]:
    data: Any = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("Gemini JSON must be an object")
    candidate_index = int(data["candidate_index"])
    if candidate_index not in allowed:
        raise ValueError(
            f"candidate_index {candidate_index} not in allowed {allowed}"
        )
    reason = str(data.get("reason", ""))
    return candidate_index, reason
