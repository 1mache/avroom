from __future__ import annotations

"""Drains the durable job queue with `max(1, INFERENCE_WORKERS)` daemon threads.

Default `INFERENCE_WORKERS=0` still means exactly one dispatcher thread,
draining the queue one job at a time behind the existing process-wide GPU
lock (`core/inference_lock.py`) — the queue is real and durable, but on this
machine it still serializes model runs. Raising `INFERENCE_WORKERS` on a
bigger box parallelizes with no code change, since each handler already goes
through `get_inference_client()`, which does the same pool-vs-inline
dispatch every other call site uses.

# ponytail: dispatcher polls claim_next_job() every 0.5s instead of using
# Postgres LISTEN/NOTIFY; switch if queue latency ever matters.
"""

import logging
import threading

from core.inference_pool.session_runtime import SessionConflictError
from core.jobs.handlers import run_generate_3d_job, run_inpaint_job, run_segment_job
from core.repositories.job_repo import JobRecord, claim_next_job, delete_job, fail_job, finish_job
from settings import get_inference_worker_count

logger = logging.getLogger(__name__)

_POLL_INTERVAL_SEC = 0.5

_threads: list[threading.Thread] = []
_stop_event = threading.Event()


def _dispatch_one(job: JobRecord) -> None:
    """Run one claimed job and record its outcome."""
    logger.info("Job started: job_id=%s kind=%s session_id=%s", job.id, job.kind, job.session_id)
    try:
        if job.kind == "segment":
            result = run_segment_job(job)
            finish_job(job.id, result)
        elif job.kind == "inpaint":
            run_inpaint_job(job)
            delete_job(job.id)
        elif job.kind == "generate_3d":
            run_generate_3d_job(job)
            delete_job(job.id)
        else:
            raise ValueError(f"Unsupported job kind: {job.kind}")
    except SessionConflictError as exc:
        fail_job(job.id, "conflict", str(exc))
    except Exception as exc:  # noqa: BLE001 — any handler failure becomes a stored job error
        logger.exception("Job failed: job_id=%s kind=%s", job.id, job.kind)
        fail_job(job.id, "failed", str(exc))


def _worker_loop(worker_index: int) -> None:
    logger.info("Job dispatcher thread started: index=%d", worker_index)
    while not _stop_event.is_set():
        job = claim_next_job()
        if job is None:
            _stop_event.wait(_POLL_INTERVAL_SEC)
            continue
        _dispatch_one(job)
    logger.info("Job dispatcher thread stopped: index=%d", worker_index)


def start_dispatcher() -> None:
    """Start the dispatcher thread pool. Call once from the app lifespan."""
    _stop_event.clear()
    thread_count = max(1, get_inference_worker_count())
    for index in range(thread_count):
        thread = threading.Thread(target=_worker_loop, args=(index,), daemon=True, name=f"job-dispatcher-{index}")
        thread.start()
        _threads.append(thread)
    logger.info("Job dispatcher started: threads=%d", thread_count)


def stop_dispatcher() -> None:
    """Signal every dispatcher thread to stop and join briefly."""
    _stop_event.set()
    for thread in _threads:
        thread.join(timeout=2.0)
    _threads.clear()
    logger.info("Job dispatcher stopped")
