from __future__ import annotations

"""API-process session concurrency: canvas writer and region leases.

Coordination for same-session segment/inpaint overlap lives only in the API
process. Worker subprocesses remain GPU-only and must not own these locks.
"""

import logging
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import AbstractSet

import numpy as np

from core.mask_cache import load_refined_mask, mask_id_from_index
from settings import get_inference_job_timeout_sec

logger = logging.getLogger(__name__)


class SessionConflictError(Exception):
    """Raised when concurrent session work conflicts (overlap or writer timeout)."""


@dataclass
class InpaintLease:
    """Reservation for one in-flight inpaint on a session canvas."""

    mask_id: str
    mask: np.ndarray
    session_id: str


@dataclass
class _SessionState:
    registry_lock: threading.Lock
    canvas_writer: threading.Lock
    leases: list[InpaintLease]


_registry_guard = threading.Lock()
_sessions: dict[str, _SessionState] = {}


def _get_session(session_id: str) -> _SessionState:
    with _registry_guard:
        state = _sessions.get(session_id)
        if state is None:
            state = _SessionState(
                registry_lock=threading.Lock(),
                canvas_writer=threading.Lock(),
                leases=[],
            )
            _sessions[session_id] = state
        return state


def _as_bool_mask(mask: np.ndarray) -> np.ndarray:
    """Normalize a refined mask array to boolean for overlap tests."""

    if mask.dtype == np.bool_:
        return mask
    return mask.astype(bool)


def _masks_overlap(mask_a: np.ndarray, mask_b: np.ndarray) -> bool:
    """Return True when two boolean masks share at least one foreground pixel."""

    if mask_a.shape != mask_b.shape:
        return False
    return bool(np.any(mask_a & mask_b))


def _click_in_mask(mask: np.ndarray, x: int, y: int) -> bool:
    """Return True when the click lies inside the mask foreground."""

    if y < 0 or x < 0 or y >= mask.shape[0] or x >= mask.shape[1]:
        return False
    return bool(mask[y, x])


def try_admit_inpaint(image_id: str, mask_id: str, base_dir: Path) -> InpaintLease:
    """Register an inpaint lease after overlap checks and pin the mask on disk.

    Raises:
        FileNotFoundError: When the selected mask candidate is missing.
        SessionConflictError: When the mask overlaps an active lease.
    """

    refined_mask = load_refined_mask(base_dir, image_id, mask_id)
    mask_bool = _as_bool_mask(refined_mask)
    state = _get_session(image_id)

    with state.registry_lock:
        for lease in state.leases:
            if _masks_overlap(mask_bool, lease.mask):
                raise SessionConflictError(
                    f"Inpaint mask overlaps an in-flight removal for image_id='{image_id}'"
                )
        lease = InpaintLease(mask_id=mask_id, mask=mask_bool, session_id=image_id)
        state.leases.append(lease)
        logger.debug(
            "Inpaint lease admitted: image_id=%s mask_id=%s active_leases=%d",
            image_id,
            mask_id,
            len(state.leases),
        )
        return lease


def acquire_canvas_writer(image_id: str, timeout_sec: int | None = None) -> None:
    """Block until this session's canvas writer lock is available.

    Raises:
        SessionConflictError: When the writer cannot be acquired before timeout.
    """

    timeout = get_inference_job_timeout_sec() if timeout_sec is None else timeout_sec
    state = _get_session(image_id)
    acquired = state.canvas_writer.acquire(timeout=timeout)
    if not acquired:
        raise SessionConflictError(
            f"Canvas writer busy for image_id='{image_id}' (timeout after {timeout}s)"
        )
    logger.debug("Canvas writer acquired: image_id=%s", image_id)


def release_canvas_writer(image_id: str) -> None:
    """Release the canvas writer lock if held by the current thread."""

    state = _get_session(image_id)
    try:
        state.canvas_writer.release()
        logger.debug("Canvas writer released: image_id=%s", image_id)
    except RuntimeError:
        pass


def drop_lease(image_id: str, lease: InpaintLease) -> None:
    """Remove one inpaint lease without touching the canvas writer."""

    state = _get_session(image_id)
    with state.registry_lock:
        try:
            state.leases.remove(lease)
            logger.debug(
                "Inpaint lease dropped: image_id=%s mask_id=%s active_leases=%d",
                image_id,
                lease.mask_id,
                len(state.leases),
            )
        except ValueError:
            pass


def assert_segment_click_allowed(image_id: str, x: int, y: int) -> None:
    """Reject segment clicks that fall inside an active inpaint lease region.

    Raises:
        SessionConflictError: When the click overlaps an active lease.
    """

    state = _get_session(image_id)
    with state.registry_lock:
        for lease in state.leases:
            if _click_in_mask(lease.mask, x, y):
                raise SessionConflictError(
                    f"Segment click overlaps an in-flight removal for image_id='{image_id}'"
                )


def pinned_mask_ids(image_id: str) -> set[str]:
    """Return mask ids pinned by active inpaint leases for one session."""

    state = _get_session(image_id)
    with state.registry_lock:
        return {lease.mask_id for lease in state.leases}


def mask_id_for_candidate_slot(slot: int, exclude_mask_ids: AbstractSet[str]) -> str:
    """Return the public mask id for the slot-th new candidate, skipping pinned ids."""

    candidate_index = 0
    assigned = 0
    while True:
        mask_id = mask_id_from_index(candidate_index)
        candidate_index += 1
        if mask_id in exclude_mask_ids:
            continue
        if assigned == slot:
            return mask_id
        assigned += 1
