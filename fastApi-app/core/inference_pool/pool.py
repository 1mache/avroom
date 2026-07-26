from __future__ import annotations

import logging
import multiprocessing
import uuid
from multiprocessing.context import BaseContext
from typing import Any

from core.inference_pool.types import JobKind, JobRequest, JobResult
from core.inference_pool.worker import worker_main
from settings import get_inference_job_timeout_sec, get_inference_worker_count

logger = logging.getLogger(__name__)


class InferencePool:
    """Manage N inference worker subprocesses and synchronous job submission."""

    def __init__(
        self,
        *,
        worker_count: int,
        mp_context: BaseContext,
        manager: Any,
        job_queue: Any,
        results: Any,
        events: Any,
        processes: list[Any],
    ) -> None:
        self._worker_count = worker_count
        self._mp_context = mp_context
        self._manager = manager
        self._job_queue = job_queue
        self._results = results
        self._events = events
        self._processes = processes

    @classmethod
    def start(cls) -> InferencePool:
        """Spawn worker subprocesses and return a running pool."""
        worker_count = get_inference_worker_count()
        if worker_count <= 0:
            raise RuntimeError("InferencePool.start() requires INFERENCE_WORKERS > 0")

        mp_context = multiprocessing.get_context("spawn")
        manager = mp_context.Manager()
        job_queue = mp_context.Queue()
        results = manager.dict()
        events = manager.dict()
        processes: list[Any] = []

        for worker_id in range(worker_count):
            process = mp_context.Process(
                target=worker_main,
                args=(job_queue, results, events, worker_id),
                name=f"inference-worker-{worker_id}",
                daemon=True,
            )
            process.start()
            processes.append(process)

        logger.info("Inference pool started: workers=%d", worker_count)
        return cls(
            worker_count=worker_count,
            mp_context=mp_context,
            manager=manager,
            job_queue=job_queue,
            results=results,
            events=events,
            processes=processes,
        )

    def submit_and_wait(self, job: JobRequest) -> JobResult:
        """Enqueue a job and block until the matching result is available."""
        if job.job_id in self._results:
            del self._results[job.job_id]

        event = self._manager.Event()
        self._events[job.job_id] = event
        self._job_queue.put(job)

        timeout_sec = get_inference_job_timeout_sec()
        if not event.wait(timeout=timeout_sec):
            self._events.pop(job.job_id, None)
            raise TimeoutError(
                f"Inference job timed out after {timeout_sec}s: job_id={job.job_id} kind={job.kind}"
            )

        self._events.pop(job.job_id, None)
        result: JobResult | None = self._results.pop(job.job_id, None)
        if result is None:
            raise RuntimeError(f"Inference job completed without result: job_id={job.job_id}")
        return result

    def shutdown(self) -> None:
        """Signal workers to exit and join subprocesses."""
        logger.info("Inference pool shutting down: workers=%d", self._worker_count)
        for _ in range(self._worker_count):
            shutdown_job = JobRequest(job_id=str(uuid.uuid4()), kind=JobKind.SHUTDOWN, storage_dir="")
            self._job_queue.put(shutdown_job)

        for process in self._processes:
            process.join(timeout=30)
            if process.is_alive():
                logger.warning("Force terminating inference worker pid=%s", process.pid)
                process.terminate()
                process.join(timeout=5)

        self._manager.shutdown()
        logger.info("Inference pool shut down")
