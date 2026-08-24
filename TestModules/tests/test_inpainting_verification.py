from __future__ import annotations

import sys
from typing import Any
from unittest.mock import MagicMock, patch

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
    InpaintParams,
    InpaintResult,
    InpaintSdParams,
    InpaintingVerificationFacade,
    InpaintingVerificationResult,
    crop_around_mask,
)
from avroom_object_removal.ai_engines.inpainting_verification.crop import (  # noqa: E402
    MIN_VERIFY_CROP_PX,
    build_verify_crops,
    draw_mask_outline,
    mask_crop_window,
)
from avroom_object_removal.ai_engines.inpainting_verification.inpainting_verification_strategy import (
    InpaintingVerificationStrategy,
)
from avroom_object_removal.ai_engines.inpainting_verification.strategies.clip_label_inpainting_verification_strategy import (
    GOOD_LABEL,
)


class _SolidColorInpaintStrategy(ImageInpaintingStrategy):
    def __init__(self, color: tuple[int, int, int], calls: list[InpaintParams | None] | None = None) -> None:
        self._color = np.array(color, dtype=np.uint8)
        self.calls = calls if calls is not None else []

    def inpaint(
        self,
        image: np.ndarray,
        mask: np.ndarray,
        params: InpaintParams | None = None,
        *,
        verify_trace: list[dict[str, Any]] | None = None,
    ) -> InpaintResult:
        self.calls.append(params)
        return InpaintResult(image=np.full_like(image, self._color))


class _SequenceInpaintStrategy(ImageInpaintingStrategy):
    def __init__(self, colors: list[tuple[int, int, int]]) -> None:
        self._colors = [np.array(c, dtype=np.uint8) for c in colors]
        self.calls: list[InpaintParams | None] = []

    def inpaint(
        self,
        image: np.ndarray,
        mask: np.ndarray,
        params: InpaintParams | None = None,
        *,
        verify_trace: list[dict[str, Any]] | None = None,
    ) -> InpaintResult:
        self.calls.append(params)
        color = self._colors[min(len(self.calls) - 1, len(self._colors) - 1)]
        return InpaintResult(image=np.full_like(image, color))


class _ScriptedVerifier(InpaintingVerificationStrategy):
    def __init__(self, oks: list[bool], fixes_json: list[str] | None = None) -> None:
        self._oks = oks
        self._fixes_json = fixes_json
        self.calls = 0
        self.last_original_image: np.ndarray | None = None

    def verify(
        self,
        image: np.ndarray,
        mask: np.ndarray,
        params: InpaintSdParams,
        *,
        original_image: np.ndarray | None = None,
    ) -> InpaintingVerificationResult:
        self.last_original_image = original_image
        ok = self._oks[min(self.calls, len(self._oks) - 1)]
        idx = min(self.calls, len(self._oks) - 1)
        fixes = (
            self._fixes_json[idx]
            if self._fixes_json is not None and idx < len(self._fixes_json)
            else params.to_json()
        )
        self.calls += 1
        return InpaintingVerificationResult(
            ok=ok,
            param_fixes_json=fixes,
            scores={},
            winner_label="",
        )


class _CountingPrimary(ImageInpaintingStrategy):
    def __init__(self, color: tuple[int, int, int]) -> None:
        self._color = np.array(color, dtype=np.uint8)
        self.calls = 0

    def inpaint(
        self,
        image: np.ndarray,
        mask: np.ndarray,
        params: InpaintParams | None = None,
        *,
        verify_trace: list[dict[str, Any]] | None = None,
    ) -> InpaintResult:
        self.calls += 1
        return InpaintResult(image=np.full_like(image, self._color))


def _params() -> InpaintSdParams:
    return InpaintSdParams(
        prompt="p",
        negative_prompt="n",
        strength=0.35,
        num_inference_steps=30,
        guidance_scale=10.0,
        mask_dilate_pixels=0,
        compose_dilate_pixels=0,
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
    assert fixed.mask_dilate_pixels == 10
    assert fixed.compose_dilate_pixels == 8


def test_inpaint_sd_params_round_trips_dilate_fields() -> None:
    params = InpaintSdParams(
        prompt="p",
        negative_prompt="n",
        strength=0.4,
        num_inference_steps=25,
        guidance_scale=9.0,
        mask_dilate_pixels=12,
        compose_dilate_pixels=8,
    )
    restored = InpaintSdParams.from_json(params.to_json())
    assert restored == params


def test_gemini_fail_parses_dilate_fields() -> None:
    params = _params()

    def complete_fn(
        _original: np.ndarray,
        _outlined: np.ndarray,
        received: InpaintSdParams,
    ) -> str:
        assert received.prompt == params.prompt
        return (
            '{"ok":false,"winner_label":"shadow ring","prompt":"fixed wall",'
            '"negative_prompt":"blob","strength":0.5,"num_inference_steps":40,'
            '"guidance_scale":8.0,"mask_dilate_pixels":12,"compose_dilate_pixels":6}'
        )

    strategy = GeminiInpaintingVerificationStrategy(
        api_key="placeholder",
        complete_fn=complete_fn,
    )
    image, mask = _scene()
    result = strategy.verify(image, mask, params, original_image=image)
    fixed = InpaintSdParams.from_json(result.param_fixes_json)
    assert fixed.mask_dilate_pixels == 12
    assert fixed.compose_dilate_pixels == 6


def test_hybrid_fail_with_mask_dilate_reruns_lama() -> None:
    retry = InpaintSdParams(
        prompt="retry",
        negative_prompt="n",
        strength=0.5,
        num_inference_steps=30,
        guidance_scale=10.0,
        mask_dilate_pixels=4,
        compose_dilate_pixels=6,
    )
    primary = _CountingPrimary((1, 1, 1))
    sd = _SequenceInpaintStrategy([(10, 10, 10), (20, 20, 20)])
    hybrid = HybridInpaintingStrategy(
        primary=primary,
        refiner=sd,
        verifier=InpaintingVerificationFacade(
            strategy=_ScriptedVerifier([False, True], [retry.to_json(), retry.to_json()])
        ),
    )
    hybrid.SHARPEN_AMOUNT = 0.0
    image, mask = _scene()
    mask_before = int(np.count_nonzero(mask > 127))
    trace: list[dict[str, Any]] = []
    result = hybrid.inpaint(image, mask, InpaintParams(strength=0.35), verify_trace=trace)
    assert primary.calls == 2
    assert len(sd.calls) == 2
    assert trace[0]["mask_dilate_pixels"] == 4
    assert trace[0]["compose_dilate_pixels"] == 6
    assert trace[0]["mask_pixel_count"] == mask_before
    assert trace[1]["mask_pixel_count"] > mask_before
    assert result.compose_dilate_pixels == 6
    assert result.verification_ok is True


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
    result = hybrid.inpaint(image, mask, InpaintParams(strength=0.35), verify_trace=trace)
    assert len(sd.calls) == 2
    assert np.all(result.image == np.array((20, 20, 20), dtype=np.uint8))
    assert len(trace) == 2
    assert trace[0]["ok"] is False
    assert trace[1]["ok"] is True
    assert "strength" in trace[0]["params"]
    assert trace[0]["candidate_bgr"].shape[:2] == image.shape[:2]


def test_hybrid_always_fail_keeps_last_after_retries_exhausted() -> None:
    sd = _SequenceInpaintStrategy([(11, 0, 0), (22, 0, 0), (33, 0, 0), (44, 0, 0)])
    hybrid = HybridInpaintingStrategy(
        primary=_SolidColorInpaintStrategy((1, 1, 1)),
        refiner=sd,
        verifier=InpaintingVerificationFacade(strategy=_ScriptedVerifier([False])),
    )
    hybrid.SHARPEN_AMOUNT = 0.0
    image, mask = _scene()
    result = hybrid.inpaint(image, mask, InpaintParams(strength=0.35))
    # attempt 0 + INPAINT_VERIFY_MAX_RETRIES (3) = 4 SD calls
    assert len(sd.calls) == 4
    assert np.all(result.image == np.array((44, 0, 0), dtype=np.uint8))


def test_hybrid_skip_sd_when_verify_passes() -> None:
    sd = _SolidColorInpaintStrategy((9, 9, 9))
    hybrid = HybridInpaintingStrategy(
        primary=_SolidColorInpaintStrategy((5, 5, 5)),
        refiner=sd,
        verifier=InpaintingVerificationFacade(strategy=_ScriptedVerifier([True])),
    )
    hybrid.SHARPEN_AMOUNT = 0.0
    image, mask = _scene()
    result = hybrid.inpaint(image, mask, InpaintParams(strength=0.1))
    assert sd.calls == []
    assert np.all(result.image == np.array((5, 5, 5), dtype=np.uint8))


def test_gemini_fail_returns_rewritten_prompt() -> None:
    params = _params()

    def complete_fn(
        _original: np.ndarray,
        _outlined: np.ndarray,
        received: InpaintSdParams,
    ) -> str:
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
    result = strategy.verify(image, mask, params, original_image=image)
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


def test_gemini_clip_fallback_load_failure_accepts_candidate() -> None:
    """HF/network failure on CLIP must not fail an already-finished inpaint."""

    class _BoomClip:
        def verify(
            self,
            _image: np.ndarray,
            _mask: np.ndarray,
            _params: InpaintSdParams,
        ) -> InpaintingVerificationResult:
            raise OSError("Can't load processor for 'openai/clip-vit-base-patch32'")

    strategy = GeminiInpaintingVerificationStrategy(
        api_key="placeholder",
        clip_fallback=_BoomClip(),  # type: ignore[arg-type]
    )
    image, mask = _scene()
    params = _params()
    result = strategy.verify(image, mask, params)
    assert result.ok is True
    assert result.winner_label == "verify_unavailable"
    assert result.param_fixes_json == params.to_json()


def test_gemini_bad_json_falls_back_to_clip() -> None:
    def complete_fn(
        _original: np.ndarray,
        _outlined: np.ndarray,
        _params: InpaintSdParams,
    ) -> str:
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
    result = strategy.verify(image, mask, params, original_image=image)
    assert result.ok is False
    fixed = InpaintSdParams.from_json(result.param_fixes_json)
    assert "leftover shadow" in fixed.prompt


def test_gemini_model_id_reads_env(monkeypatch: Any) -> None:
    monkeypatch.setenv("GEMINI_MODEL", "gemini-2.5-flash")
    strategy = GeminiInpaintingVerificationStrategy(
        api_key="placeholder",
        complete_fn=lambda _orig, _out, _params: '{"ok":true}',
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
    result = hybrid.inpaint(image, mask, InpaintParams(strength=0.1))
    assert len(sd.calls) == 1
    assert np.all(result.image == np.array((8, 8, 8), dtype=np.uint8))


def test_mask_crop_window_enforces_min_size() -> None:
    image = np.zeros((1200, 1600, 3), dtype=np.uint8)
    mask = np.zeros((1200, 1600), dtype=np.uint8)
    mask[600:602, 800:802] = 255
    window = mask_crop_window(mask)
    assert window.width >= MIN_VERIFY_CROP_PX
    assert window.height >= MIN_VERIFY_CROP_PX
    crop = image[window.y0 : window.y1, window.x0 : window.x1]
    assert crop.shape[0] >= MIN_VERIFY_CROP_PX
    assert crop.shape[1] >= MIN_VERIFY_CROP_PX


def test_build_verify_crops_same_window_shapes() -> None:
    original = np.zeros((64, 64, 3), dtype=np.uint8)
    candidate = np.full((64, 64, 3), 40, dtype=np.uint8)
    mask = np.zeros((64, 64), dtype=np.uint8)
    mask[20:30, 20:30] = 255
    orig_crop, outlined_crop, window = build_verify_crops(original, candidate, mask)
    assert orig_crop.shape == outlined_crop.shape
    assert orig_crop.shape[0] == window.height
    assert orig_crop.shape[1] == window.width


def test_draw_mask_outline_changes_boundary_pixels() -> None:
    candidate = np.full((32, 32, 3), 50, dtype=np.uint8)
    mask = np.zeros((32, 32), dtype=np.uint8)
    mask[10:20, 10:20] = 255
    window = mask_crop_window(mask, min_side_px=0, min_side_frac=0.0)
    plain = candidate[window.y0 : window.y1, window.x0 : window.x1].copy()
    outlined = draw_mask_outline(plain, mask, window)
    assert not np.array_equal(plain, outlined)


def test_gemini_dual_crop_complete_fn_receives_two_arrays() -> None:
    params = _params()
    seen: list[np.ndarray] = []

    def complete_fn(
        original_crop: np.ndarray,
        outlined_crop: np.ndarray,
        _received: InpaintSdParams,
    ) -> str:
        seen.append(original_crop)
        seen.append(outlined_crop)
        assert original_crop.shape == outlined_crop.shape
        assert not np.array_equal(original_crop, outlined_crop)
        return '{"ok":true,"winner_label":"clean texture"}'

    strategy = GeminiInpaintingVerificationStrategy(
        api_key="placeholder",
        complete_fn=complete_fn,
    )
    image, mask = _scene()
    image[:, :, 0] = 10
    candidate = image.copy()
    candidate[4:8, 4:8] = 200
    result = strategy.verify(candidate, mask, params, original_image=image)
    assert result.ok is True
    assert len(seen) == 2


def test_gemini_call_gemini_sends_two_png_parts() -> None:
    params = _params()
    posted: list[dict[str, Any]] = []

    def fake_post(parts: list[dict[str, Any]], *, api_key: str, model_id: str) -> str:
        del api_key, model_id
        posted.append({"parts": parts})
        return '{"ok":true,"winner_label":"clean texture"}'

    strategy = GeminiInpaintingVerificationStrategy(api_key="test-key")
    original = np.zeros((16, 16, 3), dtype=np.uint8)
    outlined = np.full((16, 16, 3), 30, dtype=np.uint8)
    from avroom_object_removal.ai_engines.inpainting_verification.strategies import (
        gemini_inpainting_verification_strategy as gemini_mod,
    )

    with patch.object(gemini_mod, "post_gemini", side_effect=fake_post):
        strategy._call_gemini(original, outlined, params)
    parts = posted[0]["parts"]
    inline_parts = [part for part in parts if "inline_data" in part]
    assert len(inline_parts) == 2


def test_gemini_fail_logs_retry_fields(caplog: Any) -> None:
    import logging

    params = _params()

    def complete_fn(
        _original: np.ndarray,
        _outlined: np.ndarray,
        _received: InpaintSdParams,
    ) -> str:
        return (
            '{"ok":false,"winner_label":"shadow ring","prompt":"fixed wall texture",'
            '"negative_prompt":"blob","strength":0.55,"num_inference_steps":40,'
            '"guidance_scale":8.0,"mask_dilate_pixels":8,"compose_dilate_pixels":4}'
        )

    strategy = GeminiInpaintingVerificationStrategy(
        api_key="placeholder",
        complete_fn=complete_fn,
    )
    image, mask = _scene()
    with caplog.at_level(logging.INFO):
        strategy.verify(image, mask, params, original_image=image)
    joined = "\n".join(record.message for record in caplog.records)
    assert "next_strength=0.55" in joined
    assert "next_mask_dilate=8" in joined
    assert "next_compose_dilate=4" in joined
    assert "crop=" in joined


def test_gemini_smearyness_score_parsed_and_logged(caplog: Any) -> None:
    """Gemini JSON with smearyness_score is parsed and appears in the INFO log."""
    import logging

    params = _params()

    def complete_fn(
        _original: np.ndarray,
        _outlined: np.ndarray,
        _received: InpaintSdParams,
    ) -> str:
        return (
            '{"ok":false,"winner_label":"smear blob","smearyness_score":0.82,'
            '"prompt":"crisp floor","negative_prompt":"blur","strength":0.22,'
            '"num_inference_steps":50,"guidance_scale":7.0,'
            '"mask_dilate_pixels":0,"compose_dilate_pixels":0}'
        )

    strategy = GeminiInpaintingVerificationStrategy(
        api_key="placeholder",
        complete_fn=complete_fn,
    )
    image, mask = _scene()
    with caplog.at_level(logging.INFO):
        strategy.verify(image, mask, params, original_image=image)
    joined = "\n".join(record.message for record in caplog.records)
    assert "smearyness_score=0.82" in joined


def test_gemini_smearyness_knob_rewrite_on_high_smear() -> None:
    """When smearyness_score > 0.5 Gemini returns RAISED strength & more steps."""
    params = _params()

    def complete_fn(
        _original: np.ndarray,
        _outlined: np.ndarray,
        _received: InpaintSdParams,
    ) -> str:
        # Gemini raises strength toward 0.5 and raises steps for high smear.
        return (
            '{"ok":false,"winner_label":"smear","smearyness_score":0.75,'
            '"prompt":"sharp tile","negative_prompt":"smear","strength":0.50,'
            '"num_inference_steps":50,"guidance_scale":9.0,'
            '"mask_dilate_pixels":0,"compose_dilate_pixels":0}'
        )

    strategy = GeminiInpaintingVerificationStrategy(
        api_key="placeholder",
        complete_fn=complete_fn,
    )
    image, mask = _scene()
    result = strategy.verify(image, mask, params, original_image=image)
    assert result.ok is False
    fixed = InpaintSdParams.from_json(result.param_fixes_json)
    # high smear → RAISED strength (more denoising to overdraw the blurry base)
    assert fixed.strength > params.strength
    assert fixed.num_inference_steps > params.num_inference_steps


def test_gemini_high_smearyness_gates_mask_dilation() -> None:
    """High smearyness_score forces mask_dilate_pixels to 0 even when Gemini asks for 8."""
    params = _params()

    def complete_fn(
        _original: np.ndarray,
        _outlined: np.ndarray,
        _received: InpaintSdParams,
    ) -> str:
        return (
            '{"ok":false,"winner_label":"smear","smearyness_score":0.85,'
            '"prompt":"floor","negative_prompt":"blur","strength":0.50,'
            '"num_inference_steps":50,"guidance_scale":9.0,'
            '"mask_dilate_pixels":8,"compose_dilate_pixels":4}'
        )

    strategy = GeminiInpaintingVerificationStrategy(
        api_key="placeholder",
        complete_fn=complete_fn,
    )
    image, mask = _scene()
    result = strategy.verify(image, mask, params, original_image=image)
    fixed = InpaintSdParams.from_json(result.param_fixes_json)
    # Code gate must zero this out despite Gemini asking for 8.
    assert fixed.mask_dilate_pixels == 0
    # compose_dilate_pixels is not gated by smearyness, so it passes through.
    assert fixed.compose_dilate_pixels == 4


def test_gemini_smearyness_missing_is_backward_compatible() -> None:
    """JSON without smearyness_score still parses correctly (backward compat)."""
    params = _params()

    def complete_fn(
        _original: np.ndarray,
        _outlined: np.ndarray,
        _received: InpaintSdParams,
    ) -> str:
        # No smearyness_score key at all
        return (
            '{"ok":true,"winner_label":"clean","prompt":"floor","negative_prompt":"",'
            '"strength":0.35,"num_inference_steps":40,"guidance_scale":8.5,'
            '"mask_dilate_pixels":0,"compose_dilate_pixels":0}'
        )

    strategy = GeminiInpaintingVerificationStrategy(
        api_key="placeholder",
        complete_fn=complete_fn,
    )
    image, mask = _scene()
    result = strategy.verify(image, mask, params, original_image=image)
    assert result.ok is True  # no exception raised


def test_hybrid_passes_original_image_to_verifier() -> None:
    verifier = _ScriptedVerifier([True])
    hybrid = HybridInpaintingStrategy(
        primary=_SolidColorInpaintStrategy((1, 1, 1)),
        refiner=_SolidColorInpaintStrategy((2, 2, 2)),
        verifier=InpaintingVerificationFacade(strategy=verifier),
    )
    hybrid.SHARPEN_AMOUNT = 0.0
    image, mask = _scene()
    hybrid.inpaint(image, mask, InpaintParams(strength=0.35))
    assert verifier.last_original_image is not None
    assert np.array_equal(verifier.last_original_image, image)


def test_hybrid_verify_trace_includes_original_crop() -> None:
    hybrid = HybridInpaintingStrategy(
        primary=_SolidColorInpaintStrategy((1, 1, 1)),
        refiner=_SolidColorInpaintStrategy((2, 2, 2)),
        verifier=InpaintingVerificationFacade(strategy=_ScriptedVerifier([True])),
    )
    hybrid.SHARPEN_AMOUNT = 0.0
    image, mask = _scene()
    trace: list[dict[str, Any]] = []
    hybrid.inpaint(image, mask, InpaintParams(strength=0.35), verify_trace=trace)
    assert trace[0]["verify_original_crop_bgr"] is not None
    assert trace[0]["clip_crop_bgr"] is not None
    assert trace[0]["verify_original_crop_bgr"].shape == trace[0]["clip_crop_bgr"].shape
