from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import cv2
import numpy as np
import pytest

_APP_ROOT = Path(__file__).resolve().parents[1]
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))

from core.debug_vision import NORMAL_HUB_MODELS, render_normal_map_png  # noqa: E402


def _png_bytes(width: int = 24, height: int = 16) -> bytes:
    bgr = np.full((height, width, 3), 80, dtype=np.uint8)
    ok, buffer = cv2.imencode(".png", bgr)
    assert ok and buffer is not None
    return buffer.tobytes()


def test_render_normal_map_png_uses_strategy_and_colorize() -> None:
    h, w = 16, 24
    fake_normals = np.zeros((h, w, 3), dtype=np.float32)
    fake_normals[:, :, 2] = 1.0
    fake_bgr = np.full((h, w, 3), 128, dtype=np.uint8)

    strategy_instance = MagicMock()
    strategy_instance.map_normals.return_value = fake_normals
    strategy_cls = MagicMock(return_value=strategy_instance)
    colorize = MagicMock(return_value=fake_bgr)

    def _load_attr(name: str, module: str = "avroom_object_removal"):
        del module
        if name == "Metric3DNormalMappingStrategy":
            return strategy_cls
        if name == "colorize_normals":
            return colorize
        raise AssertionError(f"unexpected attr {name}")

    with patch("core.debug_vision.load_avroom_attr", side_effect=_load_attr):
        png = render_normal_map_png(_png_bytes(w, h), hub_model="metric3d_vit_small")

    strategy_cls.assert_called_once_with(hub_model="metric3d_vit_small")
    strategy_instance.map_normals.assert_called_once()
    colorize.assert_called_once()
    assert png[:8] == b"\x89PNG\r\n\x1a\n"


def test_render_normal_map_png_rejects_unknown_hub() -> None:
    with pytest.raises(ValueError, match="Unknown hub_model"):
        render_normal_map_png(_png_bytes(), hub_model="metric3d_convnext_large")


def test_normal_hub_models_are_vit_only() -> None:
    assert "metric3d_vit_small" in NORMAL_HUB_MODELS
    assert "metric3d_convnext_large" not in NORMAL_HUB_MODELS
