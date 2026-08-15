"""Tests for session last-changed timestamps and sync-check API."""

from __future__ import annotations

import json
import sys
import tempfile
import time
from pathlib import Path

import pytest

_APP_ROOT = Path(__file__).resolve().parents[1]
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))

import settings
from settings import SessionNotFoundError, evaluate_session_sync


@pytest.fixture
def storage_sandbox(monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect all tmp sidecars and images to an isolated directory."""
    root = Path(tempfile.mkdtemp(prefix="avroom_session_sync_"))
    images_dir = root / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(settings, "IMAGE_STORAGE_DIR", str(images_dir))
    assert settings.get_image_storage_dir() == images_dir
    return root


def _register_session(uid: str) -> None:
    settings.register_uid(uid)


def test_touch_session_writes_and_updates_timestamp(storage_sandbox: Path) -> None:
    uid = "session-a"
    first = settings.touch_session(uid)
    second = settings.touch_session(uid)

    assert first
    assert second
    assert second >= first

    timestamps_file = settings.get_session_timestamps_file()
    assert timestamps_file.exists()
    data = json.loads(timestamps_file.read_text(encoding="utf-8"))
    assert data[uid] == second
    assert settings.get_session_last_changed(uid) == second


def test_clear_session_last_changed_removes_entry(storage_sandbox: Path) -> None:
    uid = "session-b"
    settings.touch_session(uid)
    settings.clear_session_last_changed(uid)

    assert settings.get_session_last_changed(uid) is None
    timestamps_file = settings.get_session_timestamps_file()
    if timestamps_file.exists():
        data = json.loads(timestamps_file.read_text(encoding="utf-8"))
        assert uid not in data


def test_sync_check_matching_timestamp(storage_sandbox: Path) -> None:
    uid = "session-c"
    _register_session(uid)
    last_changed = settings.touch_session(uid)

    server_last_changed, needs_refresh = evaluate_session_sync(uid, last_changed)

    assert server_last_changed == last_changed
    assert needs_refresh is False


def test_sync_check_stale_or_unknown_client_timestamp(storage_sandbox: Path) -> None:
    uid = "session-d"
    _register_session(uid)
    last_changed = settings.touch_session(uid)

    stale = evaluate_session_sync(uid, "2000-01-01T00:00:00+00:00")
    unknown = evaluate_session_sync(uid, None)

    assert stale == (last_changed, True)
    assert unknown == (last_changed, True)


def test_sync_check_unknown_session_returns_404(storage_sandbox: Path) -> None:
    with pytest.raises(SessionNotFoundError):
        evaluate_session_sync("missing-session", None)


def test_set_name_advances_last_changed(storage_sandbox: Path) -> None:
    uid = "session-e"
    _register_session(uid)
    initial = settings.touch_session(uid)

    # touch_session stamps the wall clock, whose resolution on Windows is
    # coarse enough that two back-to-back calls can land on the same value.
    # Real mutations are always further apart than this.
    time.sleep(0.01)

    settings.set_session_name(uid, "Living room")
    updated = settings.touch_session(uid)

    assert updated != initial
    assert settings.get_session_last_changed(uid) == updated

    _, needs_refresh = evaluate_session_sync(uid, initial)
    assert needs_refresh is True


def test_legacy_session_without_timestamp_reports_empty_string(storage_sandbox: Path) -> None:
    uid = "session-f"
    _register_session(uid)

    server_last_changed, needs_refresh = evaluate_session_sync(uid, "")

    assert server_last_changed == ""
    assert needs_refresh is False
