from __future__ import annotations

import sys
from typing import Any
from unittest.mock import MagicMock

sys.modules.setdefault("torch", MagicMock())
sys.modules.setdefault("transformers", MagicMock())
sys.modules.setdefault("diffusers", MagicMock())

import numpy as np
from PIL import Image

from avroom_object_removal import (  # noqa: E402
    ClipLabelInpaintingVerificationStrategy,
    GeminiInpaintingVerificationStrategy,
    HybridInpaintingStrategy,
    ImageInpaintingStrategy,
    InpaintSdParams,
    InpaintingVerificationFacade,
    InpaintingVerificationResult,
    crop_around_mask,
)
from avroom_object_removal.ai_engines.inpainting_verification.inpainting_verification_strategy import (
    InpaintingVerificationStrategy,
)
from avroom_object_removal.ai_engines.inpainting_verification.strategies.clip_label_inpainting_verification_strategy import (
    GOOD_LABEL,
)


class _SolidColorInpaintStrategy(ImageInpaintingStrategy):
    def __init__(self, color: tuple[int, int, int], calls: list[dict[str, Any]] | None = None) -> None:
        self._color = np.array(color, dtype=np.uint8)
        self.calls = calls if calls is not None else []

    def inpaint(self, image: np.ndarray, mask: np.ndarray, **kwargs: Any) -> np.ndarray:
        self.calls.append(dict(kwargs))
        return np.full_like(image, self._color)


class _SequenceInpaintStrategy(ImageInpaintingStrategy):
    def __init__(self, colors: list[tuple[int, int, int]]) -> None:
        self._colors = [np.array(c, dtype=np.uint8) for c in colors]
        self.calls: list[dict[str, Any]] = []

    def inpaint(self, image: np.ndarray, mask: np.ndarray, **kwargs: Any) -> np.ndarray:
        self.calls.append(dict(kwargs))
        color = self._colors[min(len(self.calls) - 1, len(self._colors) - 1)]
        return np.full_like(image, color)


class _ScriptedVerifier(InpaintingVerificationStrategy):
    def __init__(self, oks: list[bool]) -> None:
        self._oks = oks
        self.calls = 0

    def verify(
        self,
        image: np.ndarray,
        mask: np.ndarray,
        params: InpaintSdParams,
    ) -> InpaintingVerificationResult:
        ok = self._oks[min(self.calls, len(self._oks) - 1)]
        self.calls += 1
        return InpaintingVerificationResult(
            ok=ok,
            param_fixes_json=params.to_json(),
            scores={},
            winner_label="",
        )


def _params() -> InpaintSdParams:
    return InpaintSdParams(
        prompt="p",
        negative_prompt="n",
        strength=0.35,
        num_inference_steps=30,
        guidance_scale=10.0,
    )


def _scene() -> tuple[np.ndarray, np.ndarray]:
    image = np.zeros((16, 16, 3), dtype=np.uint8)
    mask = np.zeros((16, 16), dtype=np.uint8)
    mask[4:8, 4:8] = 255
    return image, mask


def test_crop_around_mask_pads_and_clamps() -> None:
    image = np.zeros((10, 10, 3), dtype=np.uint8)
    mask = np.zeros((10, 10), dtype=np.uint8)
    mask[2:4, 2:4] = 255
    crop = crop_around_mask(image, mask, pad_ratio=0.25)
    # bbox 2x2, pad 1px each side -> 4x4
    assert crop.shape[0] == 4
    assert crop.shape[1] == 4


def test_clip_verify_pass_when_good_label_wins() -> None:
    def score_fn(_img: Image.Image, labels: tuple[str, ...]) -> dict[str, float]:
        return {label: (1.0 if label == GOOD_LABEL else 0.0) for label in labels}

    strategy = ClipLabelInpaintingVerificationStrategy(score_fn=score_fn)
    image, mask = _scene()
    result = strategy.verify(image, mask, _params())
    assert result.ok is True
    assert result.winner_label == GOOD_LABEL
    assert result.scores[GOOD_LABEL] == 1.0


def test_clip_verify_fail_rewrites_retry_params() -> None:
    def score_fn(_img: Image.Image, labels: tuple[str, ...]) -> dict[str, float]:
        return {label: (1.0 if "shadow" in label else 0.0) for label in labels}

    strategy = ClipLabelInpaintingVerificationStrategy(score_fn=score_fn)
    image, mask = _scene()
    params = _params()
    result = strategy.verify(image, mask, params)
    assert result.ok is False
    fixed = InpaintSdParams.from_json(result.param_fixes_json)
    assert "leftover shadow" in fixed.prompt
    assert fixed.strength > params.strength


def test_hybrid_fail_then_pass_uses_second_sd() -> None:
    sd = _SequenceInpaintStrategy([(10, 10, 10), (20, 20, 20)])
    hybrid = HybridInpaintingStrategy(
        primary=_SolidColorInpaintStrategy((1, 1, 1)),
        refiner=sd,
        verifier=InpaintingVerificationFacade(strategy=_ScriptedVerifier([False, True])),
    )
    hybrid.SHARPEN_AMOUNT = 0.0
    image, mask = _scene()
    trace: list[dict[str, Any]] = []
    result = hybrid.inpaint(image, mask, strength=0.35, verify_trace=trace)
    assert len(sd.calls) == 2
    assert np.all(result == np.array((20, 20, 20), dtype=np.uint8))
    assert len(trace) == 2
    assert trace[0]["ok"] is False
    assert trace[1]["ok"] is True
    assert "strength" in trace[0]["params"]
    assert trace[0]["candidate_bgr"].shape[:2] == image.shape[:2]


def test_hybrid_always_fail_keeps_last_after_two_retries() -> None:
    sd = _SequenceInpaintStrategy([(11, 0, 0), (22, 0, 0), (33, 0, 0), (44, 0, 0)])
    hybrid = HybridInpaintingStrategy(
        primary=_SolidColorInpaintStrategy((1, 1, 1)),
        refiner=sd,
        verifier=InpaintingVerificationFacade(strategy=_ScriptedVerifier([False])),
    )
    hybrid.SHARPEN_AMOUNT = 0.0
    image, mask = _scene()
    result = hybrid.inpaint(image, mask, strength=0.35)
    assert len(sd.calls) == 3
    assert np.all(result == np.array((33, 0, 0), dtype=np.uint8))


def test_hybrid_skip_sd_when_verify_passes() -> None:
    sd = _SolidColorInpaintStrategy((9, 9, 9))
    hybrid = HybridInpaintingStrategy(
        primary=_SolidColorInpaintStrategy((5, 5, 5)),
        refiner=sd,
        verifier=InpaintingVerificationFacade(strategy=_ScriptedVerifier([True])),
    )
    hybrid.SHARPEN_AMOUNT = 0.0
    image, mask = _scene()
    result = hybrid.inpaint(image, mask, strength=0.1)
    assert sd.calls == []
    assert np.all(result == np.array((5, 5, 5), dtype=np.uint8))


def test_gemini_fail_returns_rewritten_prompt() -> None:
    params = _params()

    def complete_fn(_crop: np.ndarray, received: InpaintSdParams) -> str:
        assert received.prompt == params.prompt
        return (
            '{"ok":false,"winner_label":"smeared blob","prompt":"fixed wall",'
            '"negative_prompt":"blob","strength":0.5,"num_inference_steps":40,'
            '"guidance_scale":8.0}'
        )

    strategy = GeminiInpaintingVerificationStrategy(
        api_key="placeholder",
        complete_fn=complete_fn,
    )
    image, mask = _scene()
    result = strategy.verify(image, mask, params)
    assert result.ok is False
    assert result.winner_label == "smeared blob"
    fixed = InpaintSdParams.from_json(result.param_fixes_json)
    assert fixed.prompt == "fixed wall"
    assert fixed.strength == 0.5


def test_gemini_placeholder_key_uses_clip_fallback() -> None:
    def score_fn(_img: Image.Image, labels: tuple[str, ...]) -> dict[str, float]:
        return {label: (1.0 if label == GOOD_LABEL else 0.0) for label in labels}

    strategy = GeminiInpaintingVerificationStrategy(
        api_key="placeholder",
        clip_fallback=ClipLabelInpaintingVerificationStrategy(score_fn=score_fn),
    )
    image, mask = _scene()
    params = _params()
    result = strategy.verify(image, mask, params)
    assert result.ok is True
    assert result.param_fixes_json == params.to_json()


def test_gemini_bad_json_falls_back_to_clip() -> None:
    def complete_fn(_crop: np.ndarray, _params: InpaintSdParams) -> str:
        return "not-json"

    def score_fn(_img: Image.Image, labels: tuple[str, ...]) -> dict[str, float]:
        return {label: (1.0 if "shadow" in label else 0.0) for label in labels}

    strategy = GeminiInpaintingVerificationStrategy(
        api_key="test-key",
        complete_fn=complete_fn,
        clip_fallback=ClipLabelInpaintingVerificationStrategy(score_fn=score_fn),
    )
    image, mask = _scene()
    params = _params()
    result = strategy.verify(image, mask, params)
    assert result.ok is False
    fixed = InpaintSdParams.from_json(result.param_fixes_json)
    assert "leftover shadow" in fixed.prompt


def test_gemini_model_id_reads_env(monkeypatch: Any) -> None:
    monkeypatch.setenv("GEMINI_MODEL", "gemini-2.5-flash")
    strategy = GeminiInpaintingVerificationStrategy(
        api_key="placeholder",
        complete_fn=lambda _crop, _params: '{"ok":true}',
    )
    assert strategy._resolve_model_id() == "gemini-2.5-flash"
    monkeypatch.setenv("GEMINI_MODEL", "gemini-2.5-flash-lite")
    assert strategy._resolve_model_id() == "gemini-2.5-flash-lite"


def test_hybrid_skip_sd_then_verify_fail_starts_sd() -> None:
    sd = _SolidColorInpaintStrategy((8, 8, 8))
    hybrid = HybridInpaintingStrategy(
        primary=_SolidColorInpaintStrategy((5, 5, 5)),
        refiner=sd,
        verifier=InpaintingVerificationFacade(strategy=_ScriptedVerifier([False, True])),
    )
    hybrid.SHARPEN_AMOUNT = 0.0
    image, mask = _scene()
    result = hybrid.inpaint(image, mask, strength=0.1)
    assert len(sd.calls) == 1
    assert np.all(result == np.array((8, 8, 8), dtype=np.uint8))
