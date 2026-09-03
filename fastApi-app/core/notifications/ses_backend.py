"""AWS-mode transport: SES via boto3 (already a dependency for the S3
storage backend). Credentials resolve from the instance's IAM role — no
keys anywhere in env/config."""

from __future__ import annotations

import boto3  # type: ignore[import-untyped]  # no stubs published; first boto3 import in the codebase

from settings import get_notify_ses_region


def _client():  # type: ignore[no-untyped-def]
    kwargs = {}
    region = get_notify_ses_region()
    if region:
        kwargs["region_name"] = region
    return boto3.client("ses", **kwargs)


def send(from_addr: str, to: str, subject: str, body: str) -> None:
    """Send one plain-text email via SES's SendEmail API."""
    client = _client()
    client.send_email(
        Source=from_addr,
        Destination={"ToAddresses": [to]},
        Message={
            "Subject": {"Data": subject},
            "Body": {"Text": {"Data": body}},
        },
    )


def verify_recipient(email: str) -> None:
    """Ask SES to send its own address-verification mail to `email`.

    Only meaningful while the account is in the SES sandbox, where mail can
    only be delivered to verified addresses. Idempotent and harmless once
    the account leaves the sandbox.
    """
    _client().verify_email_identity(EmailAddress=email)
