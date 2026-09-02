from __future__ import annotations

import sys
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import MagicMock, patch

import cv2
import numpy as np
import pytest

_APP_ROOT = Path(__file__).resolve().parents[1]
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))

from schemas.batch import BatchBoxSource, BatchGlbResult, BatchObjectsSource, BatchRequest  # noqa: E402


def _write_session_png(base_dir: Path, image_id: str, width: int = 40, height: int = 40) -> None:
    bgr = np.full((height, width, 3), 80, dtype=np.uint8)
    ok, buffer = cv2.imencode(".png", bgr)
    assert ok and buffer is not None
    (base_dir / f"{image_id}.png").write_bytes(buffer.tobytes())


def test_batch_forces_auto_and_glbs_after_inpaints(tmp_path: Path) -> None:
    from core.batch_jobs import run_session_batch

    image_id = "batch-session"
    _write_session_png(tmp_path, image_id)
    mask = np.zeros((40, 40), dtype=np.uint8)
    mask[5:20, 5:20] = 255
    order: list[str] = []

    def fake_inpaint(**_kwargs: object) -> tuple[bytes, bytes, str]:
        order.append("inpaint")
        png = (tmp_path / f"{image_id}.png").read_bytes()
        return png, png, "png"

    def fake_glb(**_kwargs: object) -> bytes:
        order.append("glb")
        return b"glb"

    client = MagicMock()
    client.run_inpaint.side_effect = fake_inpaint
    client.run_generate_3d.side_effect = fake_glb

    patches = [
        patch("core.batch_jobs._discover_mask_jobs", return_value=[{"mask_id": "0", "mask": mask}]),
        patch("core.batch_jobs.get_inference_client", return_value=client),
        patch("core.batch_jobs.try_admit_inpaint", return_value=object()),
        patch("core.batch_jobs.acquire_canvas_writer"),
        patch("core.batch_jobs.release_canvas_writer"),
        patch("core.batch_jobs.drop_lease"),
        patch("core.batch_jobs.next_object_id", return_value=0),
        patch(
            "core.batch_jobs.build_object_metadata_for_inpaint",
            return_value=MagicMock(uuid="u1", object_id=0),
        ),
        patch("core.batch_jobs.save_object_metadata"),
        patch("core.batch_jobs.delete_candidate"),
        patch("core.batch_jobs.touch_session"),
        patch("core.batch_jobs.get_session_last_changed", return_value="t"),
        patch("core.batch_jobs._session_depth", return_value=np.ones((40, 40), dtype=np.float32)),
        patch(
            "core.batch_jobs.load_avroom_attr",
            side_effect=lambda name, module=None: (lambda *_a, **_k: [0]) if name == "peel_order" else MagicMock(),
        ),
        patch("core.batch_jobs.current_background_path", return_value=tmp_path / "bg.png"),
        patch("core.batch_jobs.object_cutout_path", return_value=tmp_path / "cut.png"),
        patch("core.batch_jobs.object_glb_path", return_value=tmp_path / "o.glb"),
        patch("core.batch_jobs.get_3d_storage_dir", return_value=tmp_path),
        patch("core.object_storage.resolve_object_cutout_path", return_value=tmp_path / f"{image_id}.png"),
    ]
    from contextlib import ExitStack

    with ExitStack() as stack:
        for item in patches:
            stack.enter_context(item)
        result = run_session_batch(
            image_id,
            BatchRequest(
                source=BatchBoxSource(x0=0, y0=0, x1=40, y1=40),
                then=["inpaint", "generate_3d"],
                verify="manual",
            ),  # type: ignore[arg-type]
            tmp_path,
        )

    assert result.objects[0].status == "created"
    assert order == ["inpaint", "glb"]
    assert result.glbs[0].ok is True


def test_batch_inpaint_only_skips_glb(tmp_path: Path) -> None:
    from core.batch_jobs import run_session_batch

    image_id = "batch-inpaint-only"
    _write_session_png(tmp_path, image_id)
    mask = np.zeros((40, 40), dtype=np.uint8)
    mask[5:20, 5:20] = 255
    order: list[str] = []

    def fake_inpaint(**_kwargs: object) -> tuple[bytes, bytes, str]:
        order.append("inpaint")
        png = (tmp_path / f"{image_id}.png").read_bytes()
        return png, png, "png"

    client = MagicMock()
    client.run_inpaint.side_effect = fake_inpaint
    client.run_generate_3d.side_effect = lambda **_kwargs: (_ for _ in ()).throw(
        AssertionError("generate_3d should not run")
    )

    patches = [
        patch("core.batch_jobs._discover_mask_jobs", return_value=[{"mask_id": "0", "mask": mask}]),
        patch("core.batch_jobs.get_inference_client", return_value=client),
        patch("core.batch_jobs.try_admit_inpaint", return_value=object()),
        patch("core.batch_jobs.acquire_canvas_writer"),
        patch("core.batch_jobs.release_canvas_writer"),
        patch("core.batch_jobs.drop_lease"),
        patch("core.batch_jobs.next_object_id", return_value=0),
        patch(
            "core.batch_jobs.build_object_metadata_for_inpaint",
            return_value=MagicMock(uuid="u1", object_id=0),
        ),
        patch("core.batch_jobs.save_object_metadata"),
        patch("core.batch_jobs.delete_candidate"),
        patch("core.batch_jobs.touch_session"),
        patch("core.batch_jobs.get_session_last_changed", return_value="t"),
        patch("core.batch_jobs._session_depth", return_value=np.ones((40, 40), dtype=np.float32)),
        patch(
            "core.batch_jobs.load_avroom_attr",
            side_effect=lambda name, module=None: (lambda *_a, **_k: [0]) if name == "peel_order" else MagicMock(),
        ),
        patch("core.batch_jobs.current_background_path", return_value=tmp_path / "bg.png"),
        patch("core.batch_jobs.object_cutout_path", return_value=tmp_path / "cut.png"),
        patch("core.batch_jobs.object_glb_path", return_value=tmp_path / "o.glb"),
        patch("core.batch_jobs.get_3d_storage_dir", return_value=tmp_path),
        patch("core.object_storage.resolve_object_cutout_path", return_value=tmp_path / f"{image_id}.png"),
    ]

    with ExitStack() as stack:
        for item in patches:
            stack.enter_context(item)
        result = run_session_batch(
            image_id,
            BatchRequest(source=BatchBoxSource(x0=0, y0=0, x1=40, y1=40), then=["inpaint"]),
            tmp_path,
        )

    assert result.objects[0].status == "created"
    assert order == ["inpaint"]
    assert result.glbs == []


def test_batch_glb_failure_does_not_block_next(tmp_path: Path) -> None:
    from core.batch_jobs import _generate_glb

    calls = {"n": 0}

    def flaky(**_kwargs: object) -> bytes:
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("boom")
        return b"ok"

    client = MagicMock()
    client.run_generate_3d.side_effect = flaky
    with (
        patch("core.batch_jobs.get_inference_client", return_value=client),
        patch("core.object_storage.resolve_object_cutout_path", return_value=tmp_path / "c.png"),
        patch("settings.get_image_storage_dir", return_value=tmp_path),
        patch("core.batch_jobs.get_3d_storage_dir", return_value=tmp_path),
        patch("core.batch_jobs.object_glb_path", return_value=tmp_path / "a.glb"),
        patch("core.batch_jobs.touch_session"),
    ):
        (tmp_path / "c.png").write_bytes(b"x")
        first = _generate_glb("s", 0)
        second = _generate_glb("s", 1)

    assert first.ok is False
    assert second.ok is True


def test_objects_source_skips_inpaint(tmp_path: Path) -> None:
    from core.batch_jobs import run_session_batch

    meta = MagicMock(session_id="sid", object_id=3, uuid="abc")
    with (
        patch("core.batch_jobs.get_object_by_uuid", return_value=meta),
            patch("core.batch_jobs._generate_glb", return_value=BatchGlbResult(object_id=3, ok=True)),
        patch("core.batch_jobs.get_session_last_changed", return_value="t"),
        patch("core.batch_jobs._discover_mask_jobs") as discover,
    ):
        result = run_session_batch(
            "sid",
            BatchRequest(source=BatchObjectsSource(uuids=["abc"]), then=["generate_3d"]),
            tmp_path,
        )

    discover.assert_not_called()
    assert result.objects[0].status == "glb_only"
    assert result.glbs[0].ok is True
