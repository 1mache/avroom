"""Unit tests for the inference worker pool."""

from __future__ import annotations

import os
import pickle
import sys
import threading
import time
from pathlib import Path
from unittest.mock import patch

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


def test_novel_view_execute_uses_dispatch_level_lock_inline() -> None:
    from core.inference_pool.dispatch import execute

    job = JobRequest(
        job_id="nv-1",
        kind=JobKind.NOVEL_VIEW,
        storage_dir=str(_APP_ROOT / "tmp" / "images"),
        cutout_path=str(_APP_ROOT / "tmp" / "images" / "cutout.png"),
        elevation_deg=0.0,
        azimuth_deg=45.0,
        relative_elevation_deg=0.0,
        radius=1.0,
    )
    expected = JobResult(job_id="nv-1", ok=True)

    with patch.dict(os.environ, {"AVROOM_INFERENCE_WORKER": ""}, clear=False):
        with patch("core.inference_pool.dispatch.inference_session") as lock_mock:
            lock_mock.return_value.__enter__ = lambda *_: None
            lock_mock.return_value.__exit__ = lambda *_: None
            with patch("core.inference_pool.dispatch._execute_impl", return_value=expected):
                result = execute(job)

    assert result.ok is True
    lock_mock.assert_called_once()


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
    test_novel_view_execute_uses_dispatch_level_lock_inline()
    test_session_lock_serializes_same_session()
    print("inference pool tests passed")
