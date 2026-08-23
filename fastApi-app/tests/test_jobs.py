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


def test_list_active_jobs_excludes_done_and_other_users() -> None:
    user_id = _make_user_and_session()
    other_user_id = "00000000-0000-0000-0000-000000000099"
    from db.models import SessionRow, User
    from db.session import session_scope

    with session_scope() as db:
        db.add(User(id=other_user_id, email="other@example.com", is_active=True))
    session_repo.register_uid("sess-other")  # owned by local user by default; reassign below
    with session_scope() as db:
        row = db.get(SessionRow, "sess-other")
        assert row is not None
        row.user_id = other_user_id

    my_failed = create_job(user_id, "sess-1", "inpaint", {"mask_id": "0"})
    fail_job(my_failed.id, "failed", "boom")

    my_done_segment = create_job(user_id, "sess-1", "segment", {"x": 0, "y": 0})
    finish_job(my_done_segment.id, {"mask_ids": ["0"]})

    someone_elses = create_job(other_user_id, "sess-other", "segment", {"x": 0, "y": 0})

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
