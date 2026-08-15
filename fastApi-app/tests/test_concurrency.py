"""Smoke tests for FastAPI concurrency refactor."""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

_APP_ROOT = Path(__file__).resolve().parents[1]
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))

from core.inference_lock import inference_session


def test_inference_lock_serializes_concurrent_threads() -> None:
    """Two threads cannot hold the inference lock at the same time."""
    active = 0
    max_active = 0
    lock = threading.Lock()

    def worker() -> None:
        nonlocal active, max_active
        with inference_session():
            with lock:
                active += 1
                max_active = max(max_active, active)
            time.sleep(0.05)
            with lock:
                active -= 1

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    assert max_active == 1


def test_heavy_endpoints_are_sync_handlers() -> None:
    """Heavy routes must be plain def so Starlette runs them in a thread pool."""
    import ast

    handler_names = {
        "handle_click",
        "segment_image",
        "inpaint_mask",
        "rescale_object_by_depth",
        "duplicate_object",
        "delete_object",
        "generate_test_3d",
        "synthesize_novel_view",
        "run_batch",
    }
    source_files = (
        _APP_ROOT / "api" / "routes.py",
        _APP_ROOT / "api" / "model_3d.py",
        _APP_ROOT / "api" / "novel_view.py",
    )
    found_async: list[str] = []
    for path in source_files:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            if not isinstance(node, ast.AsyncFunctionDef):
                continue
            if node.name in handler_names:
                found_async.append(f"{path.name}:{node.name}")

    assert not found_async, f"heavy handlers must not be async: {found_async}"


if __name__ == "__main__":
    test_inference_lock_serializes_concurrent_threads()
    test_heavy_endpoints_are_sync_handlers()
    print("concurrency smoke tests passed")
