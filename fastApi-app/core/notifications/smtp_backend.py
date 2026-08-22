"""Local-mode transport: plain SMTP, stdlib only. Talks to Mailpit by
default (localhost:1025, no auth, no TLS) — nothing to configure."""

from __future__ import annotations

import smtplib
from email.message import EmailMessage

from settings import get_smtp_host, get_smtp_password, get_smtp_port, get_smtp_user


def send(from_addr: str, to: str, subject: str, body: str) -> None:
    """Send one plain-text email over SMTP.

    Auth/TLS are only attempted when `SMTP_USER` is set, since Mailpit
    (the local default) accepts unauthenticated plaintext connections.
    """
    msg = EmailMessage()
    msg["From"] = from_addr
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)

    user = get_smtp_user()
    with smtplib.SMTP(get_smtp_host(), get_smtp_port(), timeout=10) as client:
        if user:
            client.starttls()
            client.login(user, get_smtp_password())
        client.send_message(msg)
