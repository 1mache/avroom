"""Unit tests for the inference worker pool."""

from __future__ import annotations

import os
import pickle
import sys
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np

_APP_ROOT = Path(__file__).resolve().parents[1]
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))

from core.inference_pool.session_lock import session_lock
from core.inference_pool.types import JobKind, JobRequest, JobResult
from settings import get_inference_job_timeout_sec, get_inference_worker_count


def test_default_worker_count_is_zero() -> None:
    """Pool mode stays opt-in; default preserves inline execution."""
    with patch.dict(os.environ, {"INFERENCE_WORKERS": "0"}, clear=False):
        assert get_inference_worker_count() == 0


def test_job_timeout_flag_off_returns_none() -> None:
    """INFERENCE_JOB_TIMEOUT=false disables the wait cutoff so jobs can finish."""
    with patch.dict(os.environ, {"INFERENCE_JOB_TIMEOUT": "false"}, clear=False):
        assert get_inference_job_timeout_sec() is None


def test_job_timeout_flag_on_uses_seconds() -> None:
    with patch.dict(
        os.environ,
        {"INFERENCE_JOB_TIMEOUT": "true", "INFERENCE_JOB_TIMEOUT_SEC": "90"},
        clear=False,
    ):
        assert get_inference_job_timeout_sec() == 90


def test_job_request_pickle_round_trip() -> None:
    """IPC payloads must survive multiprocessing spawn pickling."""
    job = JobRequest(
        job_id="abc",
        kind=JobKind.SEGMENT,
        storage_dir=str(_APP_ROOT / "tmp" / "images"),
        image_id="session-1",
        x=10,
        y=20,
        exclude_mask_ids=("pinned",),
        verify="auto",
    )
    restored = pickle.loads(pickle.dumps(job))
    assert restored == job
    assert restored.exclude_mask_ids == ("pinned",)
    assert restored.verify == "auto"


def test_job_result_pickle_round_trip() -> None:
    result = JobResult(
        job_id="abc",
        ok=True,
        candidates=[("mask_0", b"png-bytes")],
    )
    restored = pickle.loads(pickle.dumps(result))
    assert restored.job_id == result.job_id
    assert restored.ok is True
    assert restored.candidates == [("mask_0", b"png-bytes")]


def test_inline_client_delegates_to_dispatch() -> None:
    try:
        from core.inference_pool.client import InferenceClient, init_inference_client, shutdown_inference_client
    except ModuleNotFoundError as exc:
        print(f"Skipping inline client test (missing dependency: {exc.name})")
        return

    expected = JobResult(
        job_id="job-1",
        ok=True,
        candidates=[("mask_0", b"cutout")],
    )

    init_inference_client(None)
    client = InferenceClient(None)

    with patch("core.inference_pool.client.execute", return_value=expected) as execute_mock:
        candidates = client.run_segment(
            image_id="session-1",
            base_dir=_APP_ROOT / "tmp" / "images",
            x=1,
            y=2,
        )

    assert candidates == [("mask_0", b"cutout")]
    execute_mock.assert_called_once()
    shutdown_inference_client()


def test_segment_execute_skips_dispatch_level_lock() -> None:
    """image_processing helpers already hold inference_session; avoid double acquire."""
    from core.inference_pool.dispatch import execute

    job = JobRequest(
        job_id="seg-1",
        kind=JobKind.SEGMENT,
        storage_dir=str(_APP_ROOT / "tmp" / "images"),
        image_id="session-1",
        x=1,
        y=2,
    )
    expected = JobResult(job_id="seg-1", ok=True, candidates=[])

    with patch.dict(os.environ, {"AVROOM_INFERENCE_WORKER": ""}, clear=False):
        with patch("core.inference_pool.dispatch.inference_session") as lock_mock:
            with patch("core.inference_pool.dispatch._execute_impl", return_value=expected):
                result = execute(job)

    assert result.ok is True
    lock_mock.assert_not_called()


def test_novel_view_execute_skips_dispatch_level_lock() -> None:
    """OSMesa mesh render must not wait on the CUDA inference_session lock."""
    from core.inference_pool.dispatch import execute

    job = JobRequest(
        job_id="nv-1",
        kind=JobKind.NOVEL_VIEW,
        storage_dir=str(_APP_ROOT / "tmp" / "images"),
        cutout_path=str(_APP_ROOT / "tmp" / "images" / "cutout.png"),
        mesh_path=str(_APP_ROOT / "tmp" / "images" / "mesh.glb"),
        elevation_deg=0.0,
        azimuth_deg=45.0,
        relative_elevation_deg=0.0,
        radius=1.0,
    )
    expected = JobResult(job_id="nv-1", ok=True)

    with patch.dict(os.environ, {"AVROOM_INFERENCE_WORKER": ""}, clear=False):
        with patch("core.inference_pool.dispatch.inference_session") as lock_mock:
            with patch("core.inference_pool.dispatch._execute_impl", return_value=expected):
                result = execute(job)

    assert result.ok is True
    lock_mock.assert_not_called()


def test_cpu_kinds_bypass_worker_pool() -> None:
    """Smart paste / rescale / novel-view must not wait behind pool FIFO jobs."""
    try:
        from core.inference_pool.client import InferenceClient
    except ModuleNotFoundError as exc:
        print(f"Skipping pool-bypass test (missing dependency: {exc.name})")
        return

    pool = MagicMock()
    client = InferenceClient(pool)
    storage = str(_APP_ROOT / "tmp" / "images")

    for kind in (JobKind.SMART_PASTE, JobKind.RESCALE_BY_DEPTH, JobKind.NOVEL_VIEW):
        pool.reset_mock()
        expected = JobResult(job_id="cpu-1", ok=True)
        job = JobRequest(job_id="cpu-1", kind=kind, storage_dir=storage)
        with patch("core.inference_pool.client.execute", return_value=expected) as execute_mock:
            result = client._run(job)
        assert result.ok is True
        execute_mock.assert_called_once_with(job)
        pool.submit_and_wait.assert_not_called()

    pool.reset_mock()
    segment_job = JobRequest(
        job_id="seg-1",
        kind=JobKind.SEGMENT,
        storage_dir=storage,
        image_id="session-1",
        x=1,
        y=2,
    )
    pool.submit_and_wait.return_value = JobResult(
        job_id="seg-1", ok=True, candidates=[("mask_0", b"cutout")]
    )
    with patch("core.inference_pool.client.execute") as execute_mock:
        result = client._run(segment_job)
    assert result.ok is True
    execute_mock.assert_not_called()
    pool.submit_and_wait.assert_called_once_with(segment_job)


def test_smart_paste_skips_gpu_lock_on_cache_hit() -> None:
    """Warm depth/normal caches: paste math must not acquire inference_session."""
    try:
        from core.image_processing import run_smart_paste
        from schemas.common import CutoutBounds
    except ModuleNotFoundError as exc:
        print(f"Skipping smart-paste lock test (missing dependency: {exc.name})")
        return

    metadata = MagicMock()
    metadata.session_id = "sess-1"
    metadata.object_id = 0
    metadata.average_depth = 100.0
    metadata.display_scale = 1.0
    metadata.content_hash = "abc123"
    metadata.is_3d = False

    depth = np.full((10, 10), 100.0, dtype=np.float32)
    normals = np.ones((10, 10, 3), dtype=np.float32)
    bounds = CutoutBounds(
        left=2, top=2, right=8, bottom=8, natural_width=10, natural_height=10
    )

    paste_result = MagicMock()
    paste_result.source_average_depth = 100.0
    paste_result.target_depth = 100.0
    paste_result.scale_factor = 1.0
    paste_result.azimuth_deg = None
    paste_result.relative_elevation_deg = None

    smart_paster = MagicMock()
    smart_paster.smart_paste.return_value = paste_result

    def load_attr(name: str, module: str | None = None) -> object:
        helpers = {
            "drop_is_at_original_footprint": lambda **_kwargs: False,
            "sample_depth_at_point": lambda _depth, _x, _y: 100.0,
            "origin_depth_sample_point": lambda *_args: (5, 5),
            "SmartPaster": lambda: smart_paster,
        }
        return helpers[name]

    cutout_path = MagicMock()
    cutout_path.read_bytes.return_value = b"png-bytes"

    with (
        patch("core.image_processing._load_object_metadata_for_rescale", return_value=metadata),
        patch("core.image_processing.resolve_object_cutout_path", return_value=cutout_path),
        patch("core.image_processing.extract_cutout_bounds_from_png_bytes", return_value=bounds),
        patch("core.image_processing.load_canvas_bytes", return_value=b"canvas"),
        patch("core.image_processing.content_hash_for_bytes", return_value="hash"),
        patch("core.image_processing.load_normal_map", return_value=normals) as load_normals,
        patch("core.image_processing.get_or_compute_normals") as compute_normals,
        patch("core.image_processing._compute_session_depth_map", return_value=depth),
        patch("core.image_processing.load_avroom_attr", side_effect=load_attr),
        patch("core.image_processing._persist_rescale_metadata"),
        patch("core.image_processing.get_normal_map_enabled", return_value=True),
        patch("core.image_processing.inference_session") as lock_mock,
    ):
        result = run_smart_paste(
            base_dir=_APP_ROOT / "tmp" / "images",
            object_uuid="obj-1",
            x=5,
            y=5,
            scale_by_pov=True,
            smart_rotate=True,
        )

    assert result.display_scale == 1.0
    load_normals.assert_called_once()
    compute_normals.assert_not_called()
    lock_mock.assert_not_called()
    smart_paster.smart_paste.assert_called_once()


def test_session_lock_serializes_same_session() -> None:
    """Canvas writer acquired via session_lock must serialize same-session work."""
    active = 0
    max_active = 0
    guard = threading.Lock()

    def worker() -> None:
        nonlocal active, max_active
        with session_lock("session-a"):
            with guard:
                active += 1
                max_active = max(max_active, active)
            time.sleep(0.05)
            with guard:
                active -= 1

    threads = [threading.Thread(target=worker) for _ in range(3)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    assert max_active == 1


if __name__ == "__main__":
    test_default_worker_count_is_zero()
    test_job_timeout_flag_off_returns_none()
    test_job_timeout_flag_on_uses_seconds()
    test_job_request_pickle_round_trip()
    test_job_result_pickle_round_trip()
    test_inline_client_delegates_to_dispatch()
    test_segment_execute_skips_dispatch_level_lock()
    test_novel_view_execute_skips_dispatch_level_lock()
    test_cpu_kinds_bypass_worker_pool()
    test_smart_paste_skips_gpu_lock_on_cache_hit()
    test_session_lock_serializes_same_session()
    print("inference pool tests passed")
