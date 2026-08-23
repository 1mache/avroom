"""Pure rendering of notification subject/body — no IO, easy to unit test."""

from __future__ import annotations


def build_subject(display_name: str, event: str, ok: bool) -> str:
    """Return the email subject line for one pipeline event."""
    status = event if ok else f"{event} failed"
    return f"Avroom: {status} — {display_name}"


def build_body(display_name: str, uid: str, event: str, ok: bool, detail: str | None) -> str:
    """Return the plain-text email body. Always names the session (both its
    display name and uid), so a later rename doesn't break traceability."""
    lines = [
        f"Session: {display_name} ({uid})",
        f"Event: {event}",
        f"Status: {'ok' if ok else 'failed'}",
    ]
    if detail:
        lines.append(f"Detail: {detail}")
    return "\n".join(lines)
