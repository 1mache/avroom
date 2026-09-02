"""Tests for the durable job queue (core/repositories/job_repo.py, core/jobs/)."""

from __future__ import annotations

import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

import numpy as np
import pytest

_APP_ROOT = Path(__file__).resolve().parents[1]
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))

import settings  # noqa: E402
from core.inference_pool.session_runtime import SessionConflictError  # noqa: E402
from core.jobs.dispatcher import _dispatch_one  # noqa: E402
from core.mask_cache import cutout_path as candidate_cutout_path  # noqa: E402
from core.mask_cache import delete_candidates, refined_mask_path, save_candidate  # noqa: E402
from core.object_metadata import create_object_metadata, get_object_by_uuid  # noqa: E402
from core.repositories import session_repo  # noqa: E402
from core.repositories.job_repo import (  # noqa: E402
    claim_next_job,
    create_job,
    fail_job,
    finish_job,
    get_job,
    list_active_jobs,
    list_session_jobs,
    mark_running_orphans_failed,
    reserved_mask_ids,
)


@pytest.fixture
def storage_sandbox(monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect image storage to an isolated directory."""
    root = Path(tempfile.mkdtemp(prefix="avroom_jobs_test_"))
    images_dir = root / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(settings, "IMAGE_STORAGE_DIR", str(images_dir))
    assert settings.get_image_storage_dir() == images_dir
    return images_dir


def _make_user_and_session(uid: str = "sess-1") -> str:
    """Register a session (auto-provisioning the local user) and return its user_id."""
    session_repo.register_uid(uid)
    from core.auth.single_user import LOCAL_USER_ID

    return LOCAL_USER_ID


def test_create_job_is_queued_and_listed() -> None:
    user_id = _make_user_and_session()
    job = create_job(user_id, "sess-1", "segment", {"x": 1, "y": 2})

    assert job.status == "queued"
    listed = list_session_jobs(user_id, "sess-1")
    assert [j.job_id for j in listed] == [job.id]
    assert listed[0].kind == "segment"
    assert listed[0].object_id is None


def test_generate_3d_job_reports_its_target_object_id() -> None:
    """The frontend's Rotate-button spinner (WorkspaceScreen.handleRotate)
    has to survive exit/return by finding its own queued/running generate_3d
    job for the selected object -- that only works if JobInfo carries the
    object_id from the job's payload."""
    user_id = _make_user_and_session()
    job = create_job(user_id, "sess-1", "generate_3d", {"object_id": 3})

    listed = list_session_jobs(user_id, "sess-1")
    assert listed[0].object_id == 3

    active = list_active_jobs(user_id)
    assert active[0].object_id == 3

    claimed = claim_next_job()
    assert claimed is not None and claimed.id == job.id


def test_segment_job_reports_its_verify_mode() -> None:
    """The picker-chain effect (useSessionJobs.ts) must never open the mask
    picker for an auto-verify segment job -- it needs JobInfo.verify to tell
    an auto job (backend already narrowed candidates to its one CLIP-picked
    winner) apart from a manual one (the user actually wants to choose)."""
    user_id = _make_user_and_session()
    job = create_job(user_id, "sess-1", "segment", {"x": 1, "y": 2, "verify": "auto"})

    listed = list_session_jobs(user_id, "sess-1")
    assert listed[0].verify == "auto"

    active = list_active_jobs(user_id)
    assert active[0].verify == "auto"


def test_claim_next_job_skip_locked_gives_job_to_exactly_one_thread() -> None:
    user_id = _make_user_and_session()
    job = create_job(user_id, "sess-1", "segment", {"x": 0, "y": 0})

    results: list[Any] = []
    barrier = threading.Barrier(2)

    def worker() -> None:
        barrier.wait(timeout=5)
        results.append(claim_next_job())

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    non_none = [r for r in results if r is not None]
    assert len(non_none) == 1
    assert non_none[0].id == job.id
    assert non_none[0].status == "running"


def test_mark_running_orphans_failed_only_touches_running() -> None:
    user_id = _make_user_and_session()
    running_job = create_job(user_id, "sess-1", "segment", {"x": 0, "y": 0})
    time.sleep(0.01)  # Windows wall-clock resolution can tie two fast inserts (see test_session_sync.py)
    queued_job = create_job(user_id, "sess-1", "inpaint", {"mask_id": "0"})

    claimed = claim_next_job()
    assert claimed is not None and claimed.id == running_job.id

    count = mark_running_orphans_failed()
    assert count == 1

    failed = get_job(user_id, running_job.id)
    assert failed is not None
    assert failed.status == "failed"
    assert failed.error is not None

    still_queued = get_job(user_id, queued_job.id)
    assert still_queued is not None
    assert still_queued.status == "queued"


def test_dispatch_classifies_session_conflict_as_conflict_status(monkeypatch: pytest.MonkeyPatch) -> None:
    user_id = _make_user_and_session()
    job = create_job(user_id, "sess-1", "segment", {"x": 5, "y": 5})
    claimed = claim_next_job()
    assert claimed is not None

    def _boom(_job: Any) -> dict[str, Any]:
        raise SessionConflictError("region leased")

    monkeypatch.setattr("core.jobs.dispatcher.run_segment_job", _boom)
    _dispatch_one(claimed)

    result = get_job(user_id, job.id)
    assert result is not None
    assert result.status == "conflict"
    assert "leased" in (result.error or "")


def test_dispatch_classifies_other_exceptions_as_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    user_id = _make_user_and_session()
    job = create_job(user_id, "sess-1", "segment", {"x": 5, "y": 5})
    claimed = claim_next_job()
    assert claimed is not None

    def _boom(_job: Any) -> dict[str, Any]:
        raise ValueError("bad input")

    monkeypatch.setattr("core.jobs.dispatcher.run_segment_job", _boom)
    _dispatch_one(claimed)

    result = get_job(user_id, job.id)
    assert result is not None
    assert result.status == "failed"
    assert "bad input" in (result.error or "")


def test_list_active_jobs_excludes_done_and_other_users(other_users_session: str) -> None:
    from conftest import OTHER_USER_ID

    user_id = _make_user_and_session()

    my_failed = create_job(user_id, "sess-1", "inpaint", {"mask_id": "0"})
    fail_job(my_failed.id, "failed", "boom")

    my_done_segment = create_job(user_id, "sess-1", "segment", {"x": 0, "y": 0})
    finish_job(my_done_segment.id, {"mask_ids": ["0"]})

    someone_elses = create_job(OTHER_USER_ID, other_users_session, "segment", {"x": 0, "y": 0})

    active_ids = {j.job_id for j in list_active_jobs(user_id)}
    assert active_ids == {my_failed.id}
    assert my_done_segment.id not in active_ids
    assert someone_elses.id not in active_ids


def _write_fake_candidate(base_dir: Path, uid: str, mask_id: str) -> None:
    mask = np.zeros((4, 4), dtype=bool)
    mask[1, 1] = True
    save_candidate(base_dir, uid, mask_id, mask, b"fake-png-bytes")


def test_reserved_mask_ids_protects_unconsumed_segment_and_queued_inpaint(storage_sandbox: Path) -> None:
    user_id = _make_user_and_session()

    # An earlier segment result the user hasn't opened the picker for yet.
    first = create_job(user_id, "sess-1", "segment", {"x": 1, "y": 1})
    finish_job(first.id, {"mask_ids": ["0", "1"]})

    # A submitted-but-not-yet-run inpaint targeting a third mask.
    create_job(user_id, "sess-1", "inpaint", {"mask_id": "2"})

    assert reserved_mask_ids("sess-1") == {"0", "1", "2"}


def test_pinning_survives_a_second_segments_candidate_wipe(storage_sandbox: Path) -> None:
    """The regression this subsystem exists to avoid: a second segment must
    never delete a still-unconsumed first segment result's candidate files."""
    user_id = _make_user_and_session()
    _write_fake_candidate(storage_sandbox, "sess-1", "0")
    _write_fake_candidate(storage_sandbox, "sess-1", "1")

    first = create_job(user_id, "sess-1", "segment", {"x": 1, "y": 1})
    finish_job(first.id, {"mask_ids": ["0", "1"]})

    delete_candidates(storage_sandbox, "sess-1", exclude_mask_ids=reserved_mask_ids("sess-1"))

    assert refined_mask_path(storage_sandbox, "sess-1", "0").exists()
    assert candidate_cutout_path(storage_sandbox, "sess-1", "0").exists()
    assert refined_mask_path(storage_sandbox, "sess-1", "1").exists()


def test_inpaint_job_success_deletes_row_and_creates_object(
    storage_sandbox: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from core.jobs.handlers import run_inpaint_job

    user_id = _make_user_and_session()
    _write_fake_candidate(storage_sandbox, "sess-1", "0")

    class _FakeClient:
        def run_inpaint(self, *, image_id: str, mask_id: str, base_dir: Path) -> tuple[bytes, bytes, str]:
            return b"fake-bg", b"fake-cutout", "png"

    fake_metadata = create_object_metadata(
        session_id="sess-1", object_id=0, average_depth=100.0, content_hash="abc123"
    )

    monkeypatch.setattr("core.jobs.handlers.get_inference_client", lambda: _FakeClient())
    monkeypatch.setattr("core.jobs.handlers.build_object_metadata_for_inpaint", lambda **kwargs: fake_metadata)

    job = create_job(user_id, "sess-1", "inpaint", {"mask_id": "0"})
    claimed = claim_next_job()
    assert claimed is not None

    run_inpaint_job(claimed)

    saved = get_object_by_uuid(fake_metadata.uuid)
    assert saved is not None
    assert saved.session_id == "sess-1"
    assert saved.object_id == 0

    background_path = storage_sandbox / "sess-1_background.png"
    cutout_out_path = storage_sandbox / "sess-1_0_cutout.png"
    assert background_path.read_bytes() == b"fake-bg"
    assert cutout_out_path.read_bytes() == b"fake-cutout"


def test_run_segment_job_leases_every_seed(storage_sandbox: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from unittest.mock import MagicMock, patch

    from core.jobs.handlers import run_segment_job

    user_id = _make_user_and_session("sess-multi-seed")
    job = create_job(
        user_id,
        "sess-multi-seed",
        "segment",
        {
            "x": 10,
            "y": 10,
            "points": [{"x": 10, "y": 10}, {"x": 30, "y": 30}],
            "verify": "manual",
        },
    )

    lease_calls: list[tuple[int, int]] = []

    def _record_lease(_image_id: str, x: int, y: int) -> None:
        lease_calls.append((x, y))

    fake_client = MagicMock(run_segment=MagicMock(return_value=[("0", b"png")]))
    monkeypatch.setattr("core.jobs.handlers.get_inference_client", lambda: fake_client)
    with patch("core.jobs.handlers.assert_segment_click_allowed", side_effect=_record_lease):
        result = run_segment_job(job)

    assert result == {"mask_ids": ["0"]}
    assert lease_calls == [(10, 10), (30, 30)]


def _seed_upload_canvas(base_dir: Path, uid: str, width: int = 64, height: int = 48) -> None:
    import cv2

    bgr = np.full((height, width, 3), 120, dtype=np.uint8)
    ok, encoded = cv2.imencode(".png", bgr)
    assert ok and encoded is not None
    (base_dir / f"{uid}.png").write_bytes(encoded.tobytes())


def _mask_png_b64(width: int, height: int, blobs: list[tuple[int, int, int, int]]) -> str:
    import base64
    import io

    from PIL import Image

    image = Image.new("L", (width, height), 0)
    pixels = image.load()
    assert pixels is not None
    for x0, y0, x1, y1 in blobs:
        for y in range(y0, y1):
            for x in range(x0, x1):
                pixels[x, y] = 255
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def test_split_mask_components_splits_disconnected_blobs() -> None:
    from core.image_processing import split_mask_components

    mask = np.zeros((20, 30), dtype=np.uint8)
    mask[2:10, 2:10] = 255
    mask[2:10, 20:28] = 255

    components = split_mask_components(mask)
    assert len(components) == 2
    assert int(np.count_nonzero(components[0])) == 64
    assert int(np.count_nonzero(components[1])) == 64


def test_decode_erase_mask_rejects_wrong_shape() -> None:
    from core.image_processing import decode_erase_mask_png

    mask_b64 = _mask_png_b64(10, 10, [(2, 2, 8, 8)])
    with pytest.raises(ValueError, match="does not match canvas"):
        decode_erase_mask_png(mask_b64, (20, 20))


def test_erase_submit_creates_one_job_per_blob(storage_sandbox: Path) -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from api.sessions import router

    user_id = _make_user_and_session()
    _seed_upload_canvas(storage_sandbox, "sess-1", 64, 48)
    mask_b64 = _mask_png_b64(64, 48, [(4, 4, 12, 12), (40, 30, 50, 40)])

    app = FastAPI()
    app.include_router(router)
    response = TestClient(app).post(
        "/images/erase",
        json={"image_id": "sess-1", "mask_b64": mask_b64},
    )
    assert response.status_code == 202

    erase_jobs = [job for job in list_session_jobs(user_id, "sess-1") if job.kind == "erase"]
    assert len(erase_jobs) == 2
    assert all(refined_mask_path(storage_sandbox, "sess-1", job.job_id).exists() for job in erase_jobs)


def test_erase_job_success_writes_background_without_object(
    storage_sandbox: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from core.jobs.handlers import run_erase_job
    from core.mask_cache import save_refined_mask_only
    from core.object_metadata import list_object_ids
    from core.repositories.job_repo import delete_job

    user_id = _make_user_and_session()
    _seed_upload_canvas(storage_sandbox, "sess-1", 64, 48)

    class _FakeClient:
        def run_erase(self, *, image_id: str, mask_id: str, base_dir: Path) -> bytes:
            return b"fake-bg"

    monkeypatch.setattr("core.jobs.handlers.get_inference_client", lambda: _FakeClient())
    monkeypatch.setattr("core.jobs.handlers.notify_pipeline_event", lambda *args, **kwargs: None)

    job = create_job(user_id, "sess-1", "erase", {})
    mask = np.zeros((48, 64), dtype=np.uint8)
    mask[10:20, 10:20] = 255
    save_refined_mask_only(storage_sandbox, "sess-1", job.id, mask)

    claimed = claim_next_job()
    assert claimed is not None and claimed.id == job.id

    run_erase_job(claimed)
    delete_job(job.id)

    assert list_object_ids("sess-1") == []
    assert (storage_sandbox / "sess-1_background.png").read_bytes() == b"fake-bg"
    assert not refined_mask_path(storage_sandbox, "sess-1", job.id).exists()


def test_dispatch_erase_conflict(storage_sandbox: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from core.jobs.handlers import run_erase_job
    from core.mask_cache import save_refined_mask_only

    user_id = _make_user_and_session()
    _seed_upload_canvas(storage_sandbox, "sess-1", 64, 48)

    def _boom(_job: Any) -> None:
        raise SessionConflictError("overlap")

    monkeypatch.setattr("core.jobs.dispatcher.run_erase_job", _boom)

    job = create_job(user_id, "sess-1", "erase", {})
    mask = np.zeros((48, 64), dtype=np.uint8)
    mask[10:20, 10:20] = 255
    save_refined_mask_only(storage_sandbox, "sess-1", job.id, mask)

    claimed = claim_next_job()
    assert claimed is not None
    _dispatch_one(claimed)

    result = get_job(user_id, job.id)
    assert result is not None
    assert result.status == "conflict"
