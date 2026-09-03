from __future__ import annotations

"""Postgres-backed durable job queue.

Each queued/running/failed/unconsumed-segment-result row lives here as a
`JobRow`. Successful inpaint/generate_3d rows are deleted once their real
result (an `ObjectRow`, a GLB file) exists — this table is not a history log,
only the set of work still relevant to a client.

Mirrors the self-contained-session convention of `session_repo.py` /
`object_metadata.py`: every function opens its own `session_scope`.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from sqlalchemy import select

from db.models import JobRow, SessionRow
from db.session import session_scope
from schemas.jobs import JobInfo, JobKind, JobStatus

logger = logging.getLogger(__name__)


@dataclass
class JobRecord:
    """Full internal view of one job row, including its JSON payload/result.

    Distinct from `schemas.jobs.JobInfo` (the wire-safe subset returned to
    clients) so the dispatcher and the single-job detail route can read
    `payload`/`result` without exposing them on every list endpoint.
    """

    id: str
    user_id: str
    session_id: str
    kind: JobKind
    status: JobStatus
    payload: dict[str, Any]
    result: dict[str, Any] | None
    error: str | None
    created_at: datetime


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _row_to_record(row: JobRow) -> JobRecord:
    return JobRecord(
        id=row.id,
        user_id=row.user_id,
        session_id=row.session_id,
        kind=row.kind,  # type: ignore[arg-type]
        status=row.status,  # type: ignore[arg-type]
        payload=row.payload,
        result=row.result,
        error=row.error,
        created_at=row.created_at,
    )


def _row_to_info(row: JobRow, project_id: str | None = None) -> JobInfo:
    return JobInfo(
        job_id=row.id,
        session_id=row.session_id,
        project_id=project_id,
        kind=row.kind,  # type: ignore[arg-type]
        status=row.status,  # type: ignore[arg-type]
        error=row.error,
        created_at=row.created_at.isoformat(),
        # Only generate_3d payloads carry "object_id"; .get() is a plain None
        # for segment ("x"/"y"/"options") and inpaint ("mask_id") payloads.
        object_id=row.payload.get("object_id"),
        # Only segment payloads carry "verify".
        verify=row.payload.get("verify"),
    )


def create_job(user_id: str, session_id: str, kind: JobKind, payload: dict[str, Any]) -> JobRecord:
    """Insert a new job in `queued` status and return it."""
    with session_scope() as db:
        row = JobRow(
            user_id=user_id,
            session_id=session_id,
            kind=kind,
            status="queued",
            payload=payload,
            result=None,
            error=None,
        )
        db.add(row)
        db.flush()
        record = _row_to_record(row)
    logger.info("Job queued: job_id=%s kind=%s session_id=%s user_id=%s", record.id, kind, session_id, user_id)
    return record


def claim_next_job() -> JobRecord | None:
    """Atomically claim the oldest queued job across all sessions/users (FIFO).

    Uses `SELECT ... FOR UPDATE SKIP LOCKED` so multiple dispatcher threads
    (or, in the future, multiple API instances) never claim the same row —
    the database serializes this, no application-level lock needed.
    """
    with session_scope() as db:
        job_id = db.execute(
            select(JobRow.id)
            .where(JobRow.status == "queued")
            .order_by(JobRow.created_at)
            .with_for_update(skip_locked=True)
            .limit(1)
        ).scalar_one_or_none()
        if job_id is None:
            return None

        row = db.get(JobRow, job_id)
        assert row is not None
        row.status = "running"
        row.started_at = _now_utc()
        db.flush()
        record = _row_to_record(row)
    logger.debug("Job claimed: job_id=%s kind=%s", record.id, record.kind)
    return record


def finish_job(job_id: str, result: dict[str, Any]) -> None:
    """Mark a job `done` with its result. Used only for kinds that keep a
    row after success (segment — see module docstring)."""
    with session_scope() as db:
        row = db.get(JobRow, job_id)
        if row is None:
            return
        row.status = "done"
        row.result = result
        row.finished_at = _now_utc()
    logger.info("Job finished: job_id=%s", job_id)


def fail_job(job_id: str, status: Literal["failed", "conflict"], error: str) -> None:
    """Mark a job `failed` or `conflict` with an error message."""
    with session_scope() as db:
        row = db.get(JobRow, job_id)
        if row is None:
            return
        row.status = status
        row.error = error
        row.finished_at = _now_utc()
    logger.warning("Job %s: job_id=%s error=%s", status, job_id, error)


def delete_job(job_id: str) -> None:
    """Delete a job row outright (successful inpaint/3D, or a user dismissal)."""
    with session_scope() as db:
        row = db.get(JobRow, job_id)
        if row is None:
            return
        db.delete(row)
    logger.debug("Job row deleted: job_id=%s", job_id)


def get_job(user_id: str, job_id: str) -> JobRecord | None:
    """Return one job owned by *user_id*, or None if absent/not owned.

    Ownership is checked here (rather than surfaced as a distinct error) so
    callers can 404 a job belonging to someone else exactly like an unknown
    id — never confirming the row exists.
    """
    with session_scope() as db:
        row = db.get(JobRow, job_id)
        if row is None or row.user_id != user_id:
            return None
        return _row_to_record(row)


def list_session_jobs(user_id: str, session_id: str) -> list[JobInfo]:
    """Return every job for one session owned by *user_id*, oldest first."""
    with session_scope() as db:
        rows = db.execute(
            select(JobRow)
            .where(JobRow.user_id == user_id, JobRow.session_id == session_id)
            .order_by(JobRow.created_at)
        ).scalars().all()
        return [_row_to_info(row) for row in rows]


def list_active_jobs(user_id: str) -> list[JobInfo]:
    """Return every non-done job for *user_id* across all sessions (dashboard).

    "Active" = queued, running, failed, or conflict — everything the
    dashboard should show a badge for. Finished segment results (`done`) are
    session-scoped work the user consumes inside the workspace, not
    dashboard-level noise.

    Joins `sessions` for `project_id` -- the Projects dashboard filters this
    same list by project to light up one project card's busy/failed dot, so
    a job started in a room stays visible after backing out to that screen.
    """
    with session_scope() as db:
        rows = db.execute(
            select(JobRow, SessionRow.project_id)
            .join(SessionRow, SessionRow.id == JobRow.session_id)
            .where(JobRow.user_id == user_id, JobRow.status != "done")
            .order_by(JobRow.created_at)
        ).all()
        return [_row_to_info(row, project_id) for row, project_id in rows]


def reserved_mask_ids(session_id: str) -> set[str]:
    """Return mask ids that must survive a new segment's candidate wipe.

    Two sources, both required:
      - unconsumed (`done`) segment job results — so a second segment never
        deletes a still-unconsumed first result's candidate files;
      - the `mask_id` of any `queued`/`running` inpaint job — a submitted
        inpaint doesn't take its in-memory lease (`pinned_mask_ids`) until
        the dispatcher actually claims and starts it, and that queue wait can
        now be arbitrarily long, so without this a concurrent segment could
        wipe the very mask an already-submitted inpaint is waiting to use.
    """
    with session_scope() as db:
        segment_results = db.execute(
            select(JobRow.result).where(
                JobRow.session_id == session_id, JobRow.kind == "segment", JobRow.status == "done"
            )
        ).scalars().all()
        reserved: set[str] = set()
        for result in segment_results:
            if result:
                reserved.update(result.get("mask_ids", []))

        inpaint_payloads = db.execute(
            select(JobRow.payload).where(
                JobRow.session_id == session_id,
                JobRow.kind == "inpaint",
                JobRow.status.in_(("queued", "running")),
            )
        ).scalars().all()
        for payload in inpaint_payloads:
            mask_id = payload.get("mask_id")
            if mask_id:
                reserved.add(mask_id)

        return reserved


def mark_running_orphans_failed() -> int:
    """Flip every `running` job to `failed` on startup and return the count.

    A `running` row with no live dispatcher thread behind it (the process
    that was running it died) can never finish — `queued` rows need no such
    sweep since a fresh dispatcher simply claims them.
    """
    with session_scope() as db:
        rows = db.execute(select(JobRow).where(JobRow.status == "running")).scalars().all()
        for row in rows:
            row.status = "failed"
            row.error = "Server restarted while this job was running."
            row.finished_at = _now_utc()
        count = len(rows)
    if count:
        logger.warning("Marked %d orphaned running job(s) as failed on startup", count)
    return count
