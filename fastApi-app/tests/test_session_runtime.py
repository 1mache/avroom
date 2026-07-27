"""Unit tests for session canvas writer and region lease concurrency."""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

import numpy as np
import pytest

_APP_ROOT = Path(__file__).resolve().parents[1]
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))

from core.inference_pool.session_runtime import (  # noqa: E402
    SessionConflictError,
    acquire_canvas_writer,
    assert_segment_click_allowed,
    drop_lease,
    pinned_mask_ids,
    release_canvas_writer,
    try_admit_inpaint,
)
from core.mask_cache import (  # noqa: E402
    delete_candidate,
    delete_candidates,
    save_candidate,
)


def _write_mask(base_dir: Path, image_id: str, mask_id: str, active_pixels: list[tuple[int, int]]) -> np.ndarray:
    """Create a bool mask with foreground at the given pixel coordinates."""

    mask = np.zeros((100, 100), dtype=bool)
    for y, x in active_pixels:
        mask[y, x] = True
    cutout = b"fake-cutout"
    save_candidate(base_dir, image_id, mask_id, mask.astype(np.uint8), cutout)
    return mask


def test_overlapping_inpaint_admits_raise_conflict(tmp_path: Path) -> None:
    image_id = "session-overlap"
    _write_mask(tmp_path, image_id, "0", [(10, 10), (10, 11)])
    _write_mask(tmp_path, image_id, "1", [(10, 11), (10, 12)])

    lease_a = try_admit_inpaint(image_id, "0", tmp_path)
    try:
        with pytest.raises(SessionConflictError):
            try_admit_inpaint(image_id, "1", tmp_path)
    finally:
        drop_lease(image_id, lease_a)


def test_non_overlapping_inpaint_admits_both_register(tmp_path: Path) -> None:
    image_id = "session-disjoint"
    _write_mask(tmp_path, image_id, "0", [(5, 5)])
    _write_mask(tmp_path, image_id, "1", [(50, 50)])

    lease_a = try_admit_inpaint(image_id, "0", tmp_path)
    lease_b = try_admit_inpaint(image_id, "1", tmp_path)
    try:
        assert pinned_mask_ids(image_id) == {"0", "1"}
    finally:
        drop_lease(image_id, lease_a)
        drop_lease(image_id, lease_b)


def test_canvas_writer_blocks_second_thread_until_release() -> None:
    image_id = "session-writer"
    order: list[str] = []
    gate = threading.Event()

    def first() -> None:
        acquire_canvas_writer(image_id, timeout_sec=5)
        try:
            order.append("first-acquired")
            gate.set()
            time.sleep(0.1)
            order.append("first-done")
        finally:
            release_canvas_writer(image_id)

    def second() -> None:
        assert gate.wait(timeout=5)
        acquire_canvas_writer(image_id, timeout_sec=5)
        try:
            order.append("second-acquired")
        finally:
            release_canvas_writer(image_id)

    t1 = threading.Thread(target=first)
    t2 = threading.Thread(target=second)
    t1.start()
    t2.start()
    t1.join(timeout=5)
    t2.join(timeout=5)

    assert order == ["first-acquired", "first-done", "second-acquired"]


def test_segment_click_inside_lease_raises_conflict(tmp_path: Path) -> None:
    image_id = "session-segment-block"
    _write_mask(tmp_path, image_id, "0", [(20, 20)])

    lease = try_admit_inpaint(image_id, "0", tmp_path)
    try:
        with pytest.raises(SessionConflictError):
            assert_segment_click_allowed(image_id, x=20, y=20)
    finally:
        drop_lease(image_id, lease)


def test_segment_click_outside_lease_is_allowed(tmp_path: Path) -> None:
    image_id = "session-segment-allow"
    _write_mask(tmp_path, image_id, "0", [(20, 20)])

    lease = try_admit_inpaint(image_id, "0", tmp_path)
    try:
        assert_segment_click_allowed(image_id, x=80, y=80)
    finally:
        drop_lease(image_id, lease)


def test_delete_candidates_skips_pinned_mask_ids(tmp_path: Path) -> None:
    image_id = "session-delete-skip"
    _write_mask(tmp_path, image_id, "0", [(1, 1)])
    _write_mask(tmp_path, image_id, "1", [(2, 2)])
    _write_mask(tmp_path, image_id, "2", [(3, 3)])

    delete_candidates(tmp_path, image_id, exclude_mask_ids={"1"})

    assert (tmp_path / f"{image_id}_mask_0_refined.npy").exists() is False
    assert (tmp_path / f"{image_id}_mask_1_refined.npy").exists() is True
    assert (tmp_path / f"{image_id}_mask_2_refined.npy").exists() is False


def test_delete_candidate_removes_only_one_mask(tmp_path: Path) -> None:
    image_id = "session-delete-one"
    _write_mask(tmp_path, image_id, "0", [(1, 1)])
    _write_mask(tmp_path, image_id, "1", [(2, 2)])

    delete_candidate(tmp_path, image_id, "0")

    assert (tmp_path / f"{image_id}_mask_0_refined.npy").exists() is False
    assert (tmp_path / f"{image_id}_mask_1_refined.npy").exists() is True


def test_mask_id_for_candidate_slot_skips_pinned_ids() -> None:
    from core.inference_pool.session_runtime import mask_id_for_candidate_slot

    assert mask_id_for_candidate_slot(0, {"1"}) == "0"
    assert mask_id_for_candidate_slot(1, {"1"}) == "2"
    assert mask_id_for_candidate_slot(2, {"1"}) == "3"


def test_segment_wipe_preserves_pinned_files_via_exclude(tmp_path: Path) -> None:
    """Simulate segment pre-wipe: pinned mask files survive delete_candidates."""

    image_id = "session-segment-pin"
    _write_mask(tmp_path, image_id, "pinned", [(10, 10)])
    _write_mask(tmp_path, image_id, "0", [(1, 1)])
    _write_mask(tmp_path, image_id, "1", [(2, 2)])

    delete_candidates(tmp_path, image_id, exclude_mask_ids={"pinned"})

    assert (tmp_path / f"{image_id}_mask_pinned_refined.npy").exists() is True
    assert (tmp_path / f"{image_id}_mask_0_refined.npy").exists() is False
    assert (tmp_path / f"{image_id}_mask_1_refined.npy").exists() is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
