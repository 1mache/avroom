"""Email notifications on AI pipeline completion.

Public surface is exactly one function, `notify_pipeline_event`, meant to be
called from wherever an AI operation finishes — including the pipeline code
being developed in parallel on another branch, once merged. It takes no
dependency on `core.inference_pool` so that refactor can't break it.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable

from core.notifications.message import build_body, build_subject
from core.repositories.session_repo import get_session_notify_target
from settings import get_notify_backend, get_notify_enabled, get_notify_from

logger = logging.getLogger(__name__)


def _spawn(fn: Callable[[], None]) -> None:
    threading.Thread(target=fn, daemon=True).start()


def _backend_send(from_addr: str, to: str, subject: str, body: str) -> None:
    if get_notify_backend() == "ses":
        from core.notifications.ses_backend import send
    else:
        from core.notifications.smtp_backend import send
    send(from_addr, to, subject, body)


def notify_pipeline_event(
    uid: str,
    event: str,
    *,
    ok: bool = True,
    detail: str | None = None,
) -> None:
    """Notify a session's owner that one AI pipeline event finished.

    Never raises and never blocks the caller: the send happens on a daemon
    thread, and any failure (missing recipient, dead mail server, ...) is
    logged at WARNING and swallowed. An AI request that already succeeded
    must not be turned into a 500 by a notification failing to go out.

    Args:
        uid: The session id the event belongs to.
        event: Free-form description, e.g. "Object removed", "3D model ready".
        ok: Whether the pipeline event succeeded.
        detail: Optional extra line for the email body (e.g. an object id).
    """
    if not get_notify_enabled():
        return

    target = get_session_notify_target(uid)
    if target is None:
        logger.warning("Notify skipped: no recipient for session uid=%s", uid)
        return
    display_name, recipient = target

    subject = build_subject(display_name, event, ok)
    body = build_body(display_name, uid, event, ok, detail)
    from_addr = get_notify_from()

    def _send() -> None:
        try:
            _backend_send(from_addr, recipient, subject, body)
        except Exception:
            logger.warning("Notify failed: uid=%s event=%s", uid, event, exc_info=True)

    _spawn(_send)


def notify_account_created(email: str) -> None:
    """Send a welcome email to a freshly registered account.

    Same contract as `notify_pipeline_event`: fires on a daemon thread and
    never raises -- signup must succeed even if the mail server is down.

    # ponytail: signup is open registration with an attacker-controlled
    # email; anyone can make the configured SMTP account send mail to any
    # address. Fine locally / on SES (sandbox verification gates recipients
    # there); add signup rate-limiting before pointing a real SMTP relay
    # (e.g. Gmail) at a public deployment.
    """
    if not get_notify_enabled():
        return
    from_addr = get_notify_from()

    def _send() -> None:
        try:
            _backend_send(
                from_addr,
                email,
                "Welcome to Avroom",
                "Your Avroom account is ready.\n\n"
                "You'll get an email here whenever a room finishes processing.",
            )
        except Exception:
            logger.warning("Welcome email failed: email=%s", email, exc_info=True)

    _spawn(_send)


def request_recipient_verification(email: str) -> None:
    """Kick off SES address verification for a newly registered account.

    No-op unless notifications are on AND the SES backend is active -- local
    dev sends through Mailpit, which needs no verification at all. Never
    raises and never blocks: signup must succeed even if SES is unreachable.
    """
    if not get_notify_enabled() or get_notify_backend() != "ses":
        return

    def _verify() -> None:
        try:
            from core.notifications.ses_backend import verify_recipient

            verify_recipient(email)
        except Exception:
            logger.warning("SES recipient verification failed: email=%s", email, exc_info=True)

    _spawn(_verify)
