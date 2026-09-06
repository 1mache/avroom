"""Tests for AI pipeline completion notifications (core/notifications/)."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import pytest

_APP_ROOT = Path(__file__).resolve().parents[1]
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))

import settings
from core import notifications
from core.notifications.message import build_body, build_subject
from core.repositories import session_repo


# --- message.py: pure functions, no IO ------------------------------------


def test_build_subject_success_names_session_and_event() -> None:
    assert build_subject("Living room", "3D model ready", ok=True) == (
        "Avroom: 3D model ready — Living room"
    )


def test_build_subject_failure_says_failed() -> None:
    assert build_subject("Living room", "Object removed", ok=False) == (
        "Avroom: Object removed failed — Living room"
    )


def test_build_body_includes_uid_and_detail() -> None:
    body = build_body("Living room", "abc-123", "Object removed", ok=True, detail="Object 2")
    assert "Living room" in body
    assert "abc-123" in body
    assert "Object removed" in body
    assert "Object 2" in body


def test_build_body_omits_detail_line_when_none() -> None:
    body = build_body("Living room", "abc-123", "Object removed", ok=True, detail=None)
    assert "Detail" not in body


# --- settings.py: zero-config backend derivation ---------------------------


def test_notify_backend_defaults_to_smtp(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NOTIFY_BACKEND", raising=False)
    monkeypatch.delenv("STORAGE_BACKEND", raising=False)
    assert settings.get_notify_backend() == "smtp"


def test_notify_backend_is_ses_when_storage_backend_is_s3(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NOTIFY_BACKEND", raising=False)
    monkeypatch.setenv("STORAGE_BACKEND", "s3")
    assert settings.get_notify_backend() == "ses"


def test_notify_backend_explicit_env_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STORAGE_BACKEND", "s3")
    monkeypatch.setenv("NOTIFY_BACKEND", "smtp")
    assert settings.get_notify_backend() == "smtp"


# --- session_repo.get_session_notify_target --------------------------------


def test_notify_target_named_session_returns_name_and_email() -> None:
    session_repo.register_uid("sess-1")
    session_repo.set_session_name("sess-1", "Living room")

    target = session_repo.get_session_notify_target("sess-1")

    assert target == ("Living room", "avroom-team@proton.me")


def test_notify_target_unnamed_session_falls_back_to_uid() -> None:
    session_repo.register_uid("sess-2")

    name, _email = session_repo.get_session_notify_target("sess-2")  # type: ignore[misc]

    assert name == "sess-2"


def test_notify_target_unknown_session_returns_none() -> None:
    assert session_repo.get_session_notify_target("no-such-session") is None


# --- notify_pipeline_event: never raises, never blocks ---------------------


@pytest.fixture(autouse=True)
def _run_spawned_work_synchronously(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests need the "background" send to have happened by the time the
    call returns, so run it inline instead of on a real thread."""
    monkeypatch.setattr(notifications, "_spawn", lambda fn: fn())


def test_notify_pipeline_event_calls_backend_with_rendered_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_repo.register_uid("sess-3")
    session_repo.set_session_name("sess-3", "Kitchen")

    calls: list[tuple[str, str, str, str]] = []
    monkeypatch.setattr(
        notifications,
        "_backend_send",
        lambda from_addr, to, subject, body: calls.append((from_addr, to, subject, body)),
    )

    notifications.notify_pipeline_event("sess-3", "Object removed", detail="Object 1")

    assert len(calls) == 1
    _from_addr, to, subject, body = calls[0]
    assert to == "avroom-team@proton.me"
    assert "Kitchen" in subject
    assert "Object 1" in body


def test_notify_pipeline_event_swallows_backend_exception(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    session_repo.register_uid("sess-4")

    def _boom(from_addr: str, to: str, subject: str, body: str) -> None:
        raise ConnectionRefusedError("no smtp server")

    monkeypatch.setattr(notifications, "_backend_send", _boom)

    with caplog.at_level(logging.WARNING):
        notifications.notify_pipeline_event("sess-4", "Object removed")  # must not raise

    assert any("sess-4" in record.message for record in caplog.records)


def test_notify_pipeline_event_noop_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    session_repo.register_uid("sess-5")
    monkeypatch.setenv("NOTIFY_ENABLED", "false")

    called = False

    def _spy(*_args: object) -> None:
        nonlocal called
        called = True

    monkeypatch.setattr(notifications, "_backend_send", _spy)
    notifications.notify_pipeline_event("sess-5", "Object removed")

    assert called is False


def test_request_recipient_verification_noop_on_smtp(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NOTIFY_BACKEND", raising=False)
    monkeypatch.delenv("STORAGE_BACKEND", raising=False)

    called = False

    def _spy(_email: str) -> None:
        nonlocal called
        called = True

    monkeypatch.setattr("core.notifications.ses_backend.verify_recipient", _spy)
    notifications.request_recipient_verification("new-user@example.com")

    assert called is False


def test_request_recipient_verification_calls_ses_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NOTIFY_BACKEND", "ses")

    calls: list[str] = []
    monkeypatch.setattr("core.notifications.ses_backend.verify_recipient", calls.append)

    notifications.request_recipient_verification("new-user@example.com")

    assert calls == ["new-user@example.com"]


def test_notify_account_created_calls_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, str, str, str]] = []
    monkeypatch.setattr(
        notifications,
        "_backend_send",
        lambda from_addr, to, subject, body: calls.append((from_addr, to, subject, body)),
    )

    notifications.notify_account_created("new-user@example.com")

    assert len(calls) == 1
    _from_addr, to, subject, _body = calls[0]
    assert to == "new-user@example.com"
    assert "Welcome" in subject


def test_notify_account_created_swallows_backend_exception(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def _boom(from_addr: str, to: str, subject: str, body: str) -> None:
        raise ConnectionRefusedError("no smtp server")

    monkeypatch.setattr(notifications, "_backend_send", _boom)

    with caplog.at_level(logging.WARNING):
        notifications.notify_account_created("new-user@example.com")  # must not raise

    assert any("new-user@example.com" in record.message for record in caplog.records)


def test_notify_account_created_noop_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NOTIFY_ENABLED", "false")

    called = False

    def _spy(*_args: object) -> None:
        nonlocal called
        called = True

    monkeypatch.setattr(notifications, "_backend_send", _spy)
    notifications.notify_account_created("new-user@example.com")

    assert called is False


def test_notify_pipeline_event_noop_when_session_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    called = False

    def _spy(*_args: object) -> None:
        nonlocal called
        called = True

    monkeypatch.setattr(notifications, "_backend_send", _spy)
    notifications.notify_pipeline_event("no-such-session", "Object removed")

    assert called is False
