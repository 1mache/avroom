from __future__ import annotations

import logging
import threading
from collections.abc import Iterator
from contextlib import contextmanager

logger = logging.getLogger(__name__)

_inference_lock = threading.Lock()


@contextmanager
def inference_session() -> Iterator[None]:
    """Serialize access to process-wide shared AI model instances.

    Shared SAM / depth / LaMa / SD weights are not safe for concurrent CUDA
    forwards. FastAPI runs blocking handlers on a thread pool; this lock keeps
    inference correct while the event loop stays free for light requests.
    """
    logger.debug("Inference lock acquire requested")
    _inference_lock.acquire()
    logger.debug("Inference lock acquired")
    try:
        yield
    finally:
        _inference_lock.release()
        logger.debug("Inference lock released")
