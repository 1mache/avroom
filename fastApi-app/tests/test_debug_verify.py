from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import cv2
import numpy as np
import pytest
from fastapi import HTTPException

_APP_ROOT = Path(__file__).resolve().parents[1]
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))

from avroom_object_removal import CutoutSelectionResult  # noqa: E402
from core.debug_vision import run_auto_mask_pick, run_inpaint_verify  # noqa: E402
from schemas.debug import DebugAutoMaskPickResponse, DebugInpaintVerifyResponse  # noqa: E402


def _png_bytes(width: int = 20, height: int = 20) -> bytes:
    bgr = np.full((height, width, 3), 80, dtype=np.uint8)
    ok, buffer = cv2.imencode(".png", bgr)
    assert ok and buffer is not None
    return buffer.tobytes()


def _pair() -> tuple[np.ndarray, np.ndarray]:
    mask = np.zeros((20, 20), dtype=np.uint8)
    mask[4:16, 4:16] = 255
    cutout = np.zeros((20, 20, 4), dtype=np.uint8)
    cutout[4:16, 4:16, :3] = (10, 20, 30)
    cutout[4:16, 4:16, 3] = 255
    return mask, cutout


def _selection() -> CutoutSelectionResult:
    return CutoutSelectionResult(winner_index=0, scores=(0.9,), reasons=("winner",))


def _load_attr(name: str, module: str = "avroom_object_removal"):
    del module
    if name == "select_best_cutout":
        return MagicMock(return_value=_selection())
    if name == "DEFAULT_THRESHOLD":
        return 0.6
    if name == "_cutout_preview_bgr":
        return lambda cutout, _click: cutout[:, :, :3]
    if name == "_crop_on_gray":
        return lambda _cutout: None
    if name == "_pil_rgb_to_bgr":
        return lambda _pil: np.zeros((4, 4, 3), dtype=np.uint8)
    if name == "HybridInpaintingStrategy":
        class _FakeHybrid:
            def inpaint(self, image: np.ndarray, mask: np.ndarray, **kwargs: object) -> np.ndarray:
                trace = kwargs.get("verify_trace")
                if isinstance(trace, list):
                    trace.append(
                        {
                            "attempt_index": 0,
                            "ok": True,
                            "sd_skipped": False,
                            "scores": {"photorealistic room": 0.8},
                            "winner_label": "photorealistic room",
                            "params": {
                                "prompt": "p",
                                "negative_prompt": "n",
                                "strength": 0.35,
                                "num_inference_steps": 30,
                                "guidance_scale": 10.0,
                            },
                            "param_fixes_json": "{}",
                            "candidate_bgr": image.copy(),
                            "clip_crop_bgr": image[4:16, 4:16].copy(),
                            "lama_bgr": image.copy(),
                        }
                    )
                return image

        return _FakeHybrid
    raise KeyError(name)


def test_auto_mask_pick_payload_validates() -> None:
    with (
        patch("core.debug_vision._segment_click", return_value=(_pair(),)),
        patch("core.debug_vision.load_avroom_attr", side_effect=_load_attr),
        patch("core.debug_vision._get_cutout_clip_scorer", return_value=MagicMock()),
    ):
        payload = run_auto_mask_pick(_png_bytes(), x=8, y=8)

    model = DebugAutoMaskPickResponse.model_validate(payload)
    assert model.winner_index == 0
    assert model.candidates[0].reason == "winner"
    assert model.candidates[0].clip_crop_b64 is None


def test_inpaint_verify_payload_validates() -> None:
    with (
        patch("core.debug_vision._segment_click", return_value=(_pair(),)),
        patch("core.debug_vision.load_avroom_attr", side_effect=_load_attr),
        patch("core.debug_vision._get_cutout_clip_scorer", return_value=MagicMock()),
    ):
        payload = run_inpaint_verify(_png_bytes(), x=8, y=8, mask_index=None)

    model = DebugInpaintVerifyResponse.model_validate(payload)
    assert model.passed is True
    assert model.mask_index == 0
    assert len(model.attempts) == 1
    assert model.attempts[0].params.strength == 0.35


def test_click_out_of_bounds() -> None:
    with pytest.raises(ValueError, match="outside the image"):
        run_auto_mask_pick(_png_bytes(), x=99, y=0)


def test_debug_endpoints_disabled_are_404() -> None:
    from api.debug_vision import _require_enabled

    with patch("api.debug_vision.get_debug_endpoints_enabled", return_value=False):
        with pytest.raises(HTTPException) as exc:
            _require_enabled()
    assert exc.value.status_code == 404
