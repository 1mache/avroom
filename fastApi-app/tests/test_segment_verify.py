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

from avroom_object_removal import CutoutSelectionResult  # noqa: E402
from core.image_processing import segment_candidates_on_image  # noqa: E402


def _write_session_png(base_dir: Path, image_id: str, width: int = 40, height: int = 40) -> None:
    bgr = np.full((height, width, 3), 80, dtype=np.uint8)
    ok, buffer = cv2.imencode(".png", bgr)
    assert ok and buffer is not None
    (base_dir / f"{image_id}.png").write_bytes(buffer.tobytes())


def _candidate_pair(index: int, height: int = 40, width: int = 40) -> tuple[np.ndarray, np.ndarray]:
    mask = np.zeros((height, width), dtype=np.uint8)
    mask[5:20, 5:20] = 255
    cutout = np.zeros((height, width, 4), dtype=np.uint8)
    cutout[5:20, 5:20, :3] = index * 20
    cutout[5:20, 5:20, 3] = 255
    return mask, cutout


def _six_pairs() -> tuple[tuple[np.ndarray, np.ndarray], ...]:
    return tuple(_candidate_pair(index) for index in range(6))


def _patch_segmentor(pairs: tuple[tuple[np.ndarray, np.ndarray], ...]):
    instance = MagicMock()
    instance.depth.map_depth = MagicMock()
    instance.get_mask_for_object_at_position.return_value = pairs
    getter = MagicMock(return_value=MagicMock(return_value=instance))
    return patch("core.image_processing._get_object_segmentor_class", getter)


def test_manual_verify_returns_all_candidates(tmp_path: Path) -> None:
    image_id = "session-manual"
    _write_session_png(tmp_path, image_id)
    depth = np.zeros((40, 40), dtype=np.uint8)

    with (
        _patch_segmentor(_six_pairs()),
        patch("core.image_processing.get_or_compute_depth", return_value=(depth, "cache")),
    ):
        results = segment_candidates_on_image(
            image_id=image_id,
            base_dir=tmp_path,
            x=10,
            y=10,
            verify="manual",
        )

    assert len(results) == 6
    assert [mask_id for mask_id, _bytes in results] == ["0", "1", "2", "3", "4", "5"]


def test_auto_verify_returns_only_winner(tmp_path: Path) -> None:
    image_id = "session-auto"
    _write_session_png(tmp_path, image_id)
    depth = np.zeros((40, 40), dtype=np.uint8)
    selection = CutoutSelectionResult(
        winner_index=2,
        scores=(0.1, 0.2, 0.9, 0.3, 0.4, 0.5),
        reasons=("scored", "scored", "winner", "scored", "scored", "scored"),
    )

    with (
        _patch_segmentor(_six_pairs()),
        patch("core.image_processing.get_or_compute_depth", return_value=(depth, "cache")),
        patch("core.image_processing._get_cutout_clip_scorer", return_value=MagicMock()),
        patch("avroom_object_removal.select_best_cutout", return_value=selection) as select_mock,
    ):
        results = segment_candidates_on_image(
            image_id=image_id,
            base_dir=tmp_path,
            x=10,
            y=10,
            verify="auto",
        )

    assert len(results) == 1
    assert results[0][0] == "2"
    select_mock.assert_called_once()


def test_auto_verify_raises_when_no_winner(tmp_path: Path) -> None:
    image_id = "session-auto-none"
    _write_session_png(tmp_path, image_id)
    depth = np.zeros((40, 40), dtype=np.uint8)
    selection = CutoutSelectionResult(
        winner_index=None,
        scores=(0.1, 0.2, 0.3, 0.2, 0.1, 0.0),
        reasons=("scored",) * 6,
    )

    with (
        _patch_segmentor(_six_pairs()),
        patch("core.image_processing.get_or_compute_depth", return_value=(depth, "cache")),
        patch("core.image_processing._get_cutout_clip_scorer", return_value=MagicMock()),
        patch("avroom_object_removal.select_best_cutout", return_value=selection),
    ):
        with pytest.raises(ValueError, match="no viable mask"):
            segment_candidates_on_image(
                image_id=image_id,
                base_dir=tmp_path,
                x=10,
                y=10,
                verify="auto",
            )
