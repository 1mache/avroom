"""AWS-mode transport: SES via boto3 (already a dependency for the S3
storage backend). Credentials resolve from the instance's IAM role — no
keys anywhere in env/config."""

from __future__ import annotations

import boto3  # type: ignore[import-untyped]  # no stubs published; first boto3 import in the codebase

from settings import get_notify_ses_region


def send(from_addr: str, to: str, subject: str, body: str) -> None:
    """Send one plain-text email via SES's SendEmail API."""
    kwargs = {}
    region = get_notify_ses_region()
    if region:
        kwargs["region_name"] = region

    client = boto3.client("ses", **kwargs)
    client.send_email(
        Source=from_addr,
        Destination={"ToAddresses": [to]},
        Message={
            "Subject": {"Data": subject},
            "Body": {"Text": {"Data": body}},
        },
    )
