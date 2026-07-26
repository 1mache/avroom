from __future__ import annotations

import logging
import os
from typing import Any

from core.inference_pool.dispatch import execute
from core.inference_pool.types import JobKind, JobRequest, JobResult

logger = logging.getLogger(__name__)


def worker_main(
    job_queue: Any,
    results: Any,
    events: Any,
    worker_id: int,
) -> None:
    """Worker subprocess entry point: consume jobs until SHUTDOWN."""
    os.environ["AVROOM_INFERENCE_WORKER"] = "1"

    from logging_config import setup_logging

    setup_logging()
    worker_logger = logging.getLogger(__name__)
    worker_logger.info("Inference worker started: worker_id=%d pid=%d", worker_id, os.getpid())

    while True:
        job: JobRequest = job_queue.get()
        if job.kind == JobKind.SHUTDOWN:
            worker_logger.info("Inference worker shutting down: worker_id=%d", worker_id)
            break

        worker_logger.info(
            "Inference worker processing job: worker_id=%d job_id=%s kind=%s",
            worker_id,
            job.job_id,
            job.kind,
        )
        result: JobResult = execute(job)
        results[job.job_id] = result
        event = events.get(job.job_id)
        if event is not None:
            event.set()
