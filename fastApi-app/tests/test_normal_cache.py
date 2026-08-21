from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

_APP_ROOT = Path(__file__).resolve().parents[1]
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))

from core.depth_cache import content_hash_for_bytes  # noqa: E402
from core.normal_cache import (  # noqa: E402
    delete_session_normal_maps,
    get_or_compute_normals,
    load_normal_map,
    save_normal_map,
    warm_normals_for_session,
)


def _png_bytes(width: int = 16, height: int = 12) -> bytes:
    bgr = np.full((height, width, 3), 90, dtype=np.uint8)
    ok, buffer = cv2.imencode(".png", bgr)
    assert ok and buffer is not None
    return buffer.tobytes()


def _fake_normals(bgr: np.ndarray) -> np.ndarray:
    h, w = bgr.shape[:2]
    normals = np.zeros((h, w, 3), dtype=np.float32)
    normals[:, :, 2] = 1.0
    return normals


def test_save_load_roundtrip(tmp_path: Path) -> None:
    session_id = "uid-test"
    image_bytes = _png_bytes()
    content_hash = content_hash_for_bytes(image_bytes)
    normals = _fake_normals(np.zeros((12, 16, 3), dtype=np.uint8))

    save_normal_map(tmp_path, session_id, content_hash, normals)
    loaded = load_normal_map(tmp_path, session_id, content_hash)
    assert loaded is not None
    assert loaded.shape == (12, 16, 3)
    assert loaded.dtype == np.float32
    assert np.allclose(loaded, normals)


def test_get_or_compute_hits_cache(tmp_path: Path) -> None:
    session_id = "uid-hit"
    image_bytes = _png_bytes()
    calls = {"n": 0}

    def map_fn(bgr: np.ndarray) -> np.ndarray:
        calls["n"] += 1
        return _fake_normals(bgr)

    first, hash1 = get_or_compute_normals(tmp_path, session_id, image_bytes, map_fn)
    second, hash2 = get_or_compute_normals(tmp_path, session_id, image_bytes, map_fn)
    assert calls["n"] == 1
    assert hash1 == hash2
    assert np.allclose(first, second)


def test_get_or_compute_misses_on_new_bytes(tmp_path: Path) -> None:
    session_id = "uid-miss"
    bytes_a = _png_bytes(16, 12)
    bytes_b = _png_bytes(20, 14)
    calls = {"n": 0}

    def map_fn(bgr: np.ndarray) -> np.ndarray:
        calls["n"] += 1
        return _fake_normals(bgr)

    get_or_compute_normals(tmp_path, session_id, bytes_a, map_fn)
    get_or_compute_normals(tmp_path, session_id, bytes_b, map_fn)
    assert calls["n"] == 2
    assert len(list(tmp_path.glob(f"{session_id}_normal_*.npy"))) == 2


def test_warm_skips_pool_on_hit(tmp_path: Path) -> None:
    session_id = "uid-warm"
    image_bytes = _png_bytes()
    calls = {"n": 0}

    def from_bytes(data: bytes) -> np.ndarray:
        calls["n"] += 1
        decoded = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
        assert decoded is not None
        return _fake_normals(decoded)

    warm_normals_for_session(tmp_path, session_id, image_bytes, from_bytes)
    warm_normals_for_session(tmp_path, session_id, image_bytes, from_bytes)
    assert calls["n"] == 1


def test_delete_session_normal_maps(tmp_path: Path) -> None:
    session_id = "uid-del"
    image_bytes = _png_bytes()
    content_hash = content_hash_for_bytes(image_bytes)
    save_normal_map(tmp_path, session_id, content_hash, _fake_normals(np.zeros((12, 16, 3), dtype=np.uint8)))
    assert delete_session_normal_maps(tmp_path, session_id) == 1
    assert load_normal_map(tmp_path, session_id, content_hash) is None


def test_save_rejects_bad_shape(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="HxWx3"):
        save_normal_map(tmp_path, "uid", "abc", np.zeros((4, 5), dtype=np.float32))
