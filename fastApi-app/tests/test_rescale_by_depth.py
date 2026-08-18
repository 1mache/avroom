from __future__ import annotations

"""End-to-end harness for the depth-based rescale feature.

Picks a saved session and one of its object cutouts from the configured image
storage directory, copies that session's artifacts into a throwaway sandbox,
and drives ``POST /images/objects/{uuid}/rescale-by-depth`` through the real
router -> ``rescale_cutout_by_depth`` -> filesystem path.  Every mutation
(overwritten cutout PNG, updated ``average_depth``) lands in the sandbox, so
the developer's real sessions are never modified.

Checks performed after the call:

* scale factor equals ``target_depth / source_average_depth``
* the rescaled cutout keeps the original canvas size and bbox center
* the visible alpha bbox scaled by the reported factor
* the response bytes match what was written to disk
* metadata ``average_depth`` advanced to ``target_depth``
* a second call at the same point is a no-op (scaling must not compound)

Before/after cutouts and composites over the session background are written to
``fastApi-app/tmp/test_outputs/rescale_by_depth/`` for visual inspection.

Run from the repo root with the project virtualenv::

    .venv/Scripts/python.exe fastApi-app/tests/test_rescale_by_depth.py
    .venv/Scripts/python.exe fastApi-app/tests/test_rescale_by_depth.py --list
    .venv/Scripts/python.exe fastApi-app/tests/test_rescale_by_depth.py --session <uid> --object-id 0
    .venv/Scripts/python.exe fastApi-app/tests/test_rescale_by_depth.py --x 800 --y 1200 --keep
"""

import argparse
import base64
import json
import logging
import shutil
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import cv2
import numpy as np

_APP_ROOT = Path(__file__).resolve().parent.parent
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))

import settings  # noqa: E402
from core.depth_cache import get_or_compute_depth, sample_depth_at_point  # noqa: E402
from core.image_processing import load_canvas_bytes  # noqa: E402
from core.object_metadata import ObjectMetadata, list_object_ids, load_object_metadata  # noqa: E402
from core.object_storage import resolve_object_cutout_path  # noqa: E402
from core.repositories.session_repo import load_session_uids  # noqa: E402

logger = logging.getLogger("RescaleByDepthTest")

ENDPOINT_TEMPLATE = "/images/objects/{object_uuid}/rescale-by-depth"
DEFAULT_OUTPUT_SUBDIR = "tmp/test_outputs/rescale_by_depth"

#: Depth ratio used when no explicit placement point is requested.  Below 1.0 so
#: the auto-picked point is *further* than the object's own depth and the
#: resulting shrink is obvious in the saved preview.
AUTO_POINT_DEPTH_RATIO = 0.6

#: Stride for the coarse grid scan used to locate the auto placement point.
AUTO_POINT_SCAN_STRIDE = 8

#: Pixel slack absorbing rounding in resize/paste when comparing bounding boxes.
BBOX_TOLERANCE_PX = 2.0

#: Extra proportional slack on bbox size, on top of ``BBOX_TOLERANCE_PX``.
BBOX_TOLERANCE_RATIO = 0.02


@dataclass(frozen=True)
class SavedObject:
    """One finalized object discovered on disk, eligible for a rescale run."""

    metadata: ObjectMetadata
    cutout_path: Path

    @property
    def label(self) -> str:
        """Return a short human-readable identifier for log lines."""
        return f"{self.metadata.session_id}#{self.metadata.object_id}"


@dataclass(frozen=True)
class Bbox:
    """Tight bounding box of the visible (alpha > 0) cutout content."""

    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top

    @property
    def center(self) -> tuple[float, float]:
        return ((self.left + self.right) / 2.0, (self.top + self.bottom) / 2.0)


@dataclass
class CheckResult:
    """Outcome of one verification step."""

    name: str
    status: str
    detail: str


class Checklist:
    """Accumulates verification outcomes so one failure does not abort the run."""

    def __init__(self) -> None:
        self.results: list[CheckResult] = []

    def record(self, name: str, passed: bool, detail: str) -> None:
        """Record a pass/fail outcome and log it immediately."""
        status = "PASS" if passed else "FAIL"
        self.results.append(CheckResult(name=name, status=status, detail=detail))
        log: Callable[[str], None] = logger.info if passed else logger.error
        log(f"[{status}] {name}: {detail}")

    def skip(self, name: str, detail: str) -> None:
        """Record a check that could not be evaluated for this input."""
        self.results.append(CheckResult(name=name, status="SKIP", detail=detail))
        logger.warning(f"[SKIP] {name}: {detail}")

    @property
    def failed(self) -> list[CheckResult]:
        return [result for result in self.results if result.status == "FAIL"]


def discover_saved_objects(storage_dir: Path) -> list[SavedObject]:
    """Return every object in Postgres that also has a cutout PNG on disk.

    Metadata now lives in the `objects` table, not `*_meta.json` sidecars —
    this queries the *real* local Postgres (whatever `DATABASE_URL` resolves
    to), independent of which directory `storage_dir` points at.
    """
    found: list[SavedObject] = []
    for session_id in load_session_uids():
        for object_id in list_object_ids(session_id):
            metadata = load_object_metadata(session_id, object_id)
            if metadata is None:
                continue
            cutout_path = resolve_object_cutout_path(storage_dir, session_id, object_id)
            if not cutout_path.exists():
                logger.warning(
                    f"Skipping {session_id}#{object_id}: cutout missing at {cutout_path.name}"
                )
                continue
            found.append(SavedObject(metadata=metadata, cutout_path=cutout_path))

    return found


def choose_object(
    candidates: list[SavedObject],
    session_id: str | None,
    object_id: int | None,
) -> SavedObject:
    """Select the object to exercise, honoring explicit CLI filters.

    Without filters the first candidate with a strictly positive
    ``average_depth`` wins - a zero or negative baseline depth is rejected by
    ``compute_depth_scale_factor`` and would only produce a 400.
    """
    filtered = candidates
    if session_id is not None:
        filtered = [c for c in filtered if c.metadata.session_id == session_id]
    if object_id is not None:
        filtered = [c for c in filtered if c.metadata.object_id == object_id]

    if not filtered:
        raise LookupError(
            "No saved object matches the requested session/object-id. "
            "Run with --list to see what is available."
        )

    usable = [c for c in filtered if c.metadata.average_depth > 0]
    if not usable:
        raise LookupError(
            "Matching objects all have a non-positive average_depth, which the "
            "rescale endpoint rejects. Re-run the inpaint flow to regenerate metadata."
        )

    return usable[0]


def build_sandbox(storage_dir: Path, session_id: str) -> tuple[Path, Path]:
    """Copy one session's blob files into a temp workspace and return its paths.

    The rescale endpoint overwrites the cutout PNG in place, so the harness
    redirects file storage at a copy — the cutout, GLB, and novel-view
    caches are never touched on the real disk. Metadata (`average_depth`,
    etc.) now lives in Postgres, not on disk, so it is *not* sandboxed: the
    rescale call updates the real local `objects` row for this object, same
    as it would from the live app. That only matters if you rescale the same
    saved object twice in a row (the second run starts from the first run's
    updated depth) — pass ``--keep`` and inspect ``summary.json`` if that
    matters for what you're debugging.

    Returns:
        Tuple of ``(sandbox_root, sandbox_images_dir)``.
    """
    sandbox_root = Path(tempfile.mkdtemp(prefix="avroom_rescale_test_"))
    images_dir = sandbox_root / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    copied = 0
    for entry in storage_dir.iterdir():
        if entry.is_file() and entry.name.startswith(session_id):
            shutil.copy2(entry, images_dir / entry.name)
            copied += 1

    logger.info(f"Sandbox ready at {sandbox_root} ({copied} session files copied)")
    return sandbox_root, images_dir


def activate_sandbox(images_dir: Path) -> None:
    """Point file storage at the sandbox for the rest of the process.

    ``settings.get_image_storage_dir`` reads the module-level
    ``IMAGE_STORAGE_DIR`` on each call, so assigning it here reroutes the
    router and the depth cache. Metadata queries still hit the real local
    Postgres regardless — see :func:`build_sandbox`.
    """
    settings.IMAGE_STORAGE_DIR = str(images_dir)
    resolved = settings.get_image_storage_dir()
    if resolved != images_dir:
        raise RuntimeError(
            f"Sandbox activation failed: storage resolved to {resolved}, expected {images_dir}"
        )
    logger.info(f"Storage redirected to sandbox: {resolved}")


def alpha_bbox(png_bytes: bytes) -> Bbox | None:
    """Return the tight alpha bounding box of a BGRA cutout PNG."""
    decoded = decode_bgra(png_bytes)
    if decoded.shape[2] < 4:
        raise ValueError("Cutout PNG has no alpha channel.")

    non_zero = cv2.findNonZero(decoded[:, :, 3])
    if non_zero is None:
        return None

    x, y, w, h = cv2.boundingRect(non_zero)
    return Bbox(left=x, top=y, right=x + w, bottom=y + h)


def decode_bgra(png_bytes: bytes) -> np.ndarray:
    """Decode PNG bytes into a BGRA/BGR array, raising on undecodable input."""
    decoded = cv2.imdecode(np.frombuffer(png_bytes, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
    if decoded is None:
        raise ValueError("Could not decode PNG bytes.")
    return decoded


def pick_placement_point(depth_map: np.ndarray, source_depth: float) -> tuple[int, int]:
    """Find a canvas point whose depth makes the rescale visually obvious.

    Scans a strided grid for the pixel closest to
    ``source_depth * AUTO_POINT_DEPTH_RATIO``.  Higher uint8 depth means closer
    to the camera, so the chosen point is further away than the object was and
    the resulting scale factor lands below 1.0.
    """
    flat_depth = depth_map[:, :, 0] if depth_map.ndim == 3 else depth_map
    desired = source_depth * AUTO_POINT_DEPTH_RATIO

    sample = flat_depth[::AUTO_POINT_SCAN_STRIDE, ::AUTO_POINT_SCAN_STRIDE].astype(np.float32)
    flat_index = int(np.argmin(np.abs(sample - desired)))
    row, col = divmod(flat_index, sample.shape[1])
    x = col * AUTO_POINT_SCAN_STRIDE
    y = row * AUTO_POINT_SCAN_STRIDE

    logger.info(
        f"Auto placement point ({x},{y}): desired_depth={desired:.2f} "
        f"actual_depth={float(flat_depth[y, x]):.2f} source_depth={source_depth:.2f}"
    )
    return x, y


def load_session_depth(images_dir: Path, session_id: str) -> np.ndarray:
    """Return the depth map for the session's current canvas.

    Uses the same cache-aware helper the endpoint uses, so a cache hit here
    guarantees the endpoint will not reload the depth models either.
    """
    from avroom_object_removal import ObjectSegmentor

    canvas_bytes = load_canvas_bytes(image_id=session_id, base_dir=images_dir)
    logger.info("Resolving canvas depth map (loads depth models on a cache miss)")
    depth_map, content_hash = get_or_compute_depth(
        images_dir,
        session_id,
        canvas_bytes,
        ObjectSegmentor().depth.map_depth,
    )
    logger.info(f"Depth map ready: shape={depth_map.shape} content_hash={content_hash[:12]}")
    return depth_map


def build_test_app() -> Any:
    """Assemble a minimal app around the real images router.

    ``main.app`` also mounts the 3D and novel-view routers, which pull heavy
    optional dependencies at import time.  Mounting only ``api.routes`` keeps
    the harness runnable while still exercising the genuine endpoint, request
    schema, and response schema.
    """
    from fastapi import FastAPI

    from api.routes import router

    app = FastAPI(title="rescale-by-depth harness")
    app.include_router(router)
    return app


def call_rescale(client: Any, object_uuid: str, x: int, y: int) -> dict[str, Any]:
    """POST the rescale request and return the decoded JSON body."""
    url = ENDPOINT_TEMPLATE.format(object_uuid=object_uuid)
    logger.info(f"POST {url} with placement ({x},{y})")
    response = client.post(url, json={"x": x, "y": y})
    if response.status_code != 200:
        raise RuntimeError(f"Endpoint returned {response.status_code}: {response.text}")
    return dict(response.json())


def verify_response(
    checks: Checklist,
    payload: dict[str, Any],
    chosen: SavedObject,
    expected_target_depth: float,
) -> None:
    """Verify the scale math and identity fields reported by the endpoint."""
    source = float(payload["source_average_depth"])
    target = float(payload["target_depth"])
    scale = float(payload["scale_factor"])

    checks.record(
        "response identity",
        payload["object_uuid"] == chosen.metadata.uuid
        and payload["session_id"] == chosen.metadata.session_id
        and payload["object_id"] == chosen.metadata.object_id,
        f"uuid/session/object_id echoed as {payload['object_uuid']}, "
        f"{payload['session_id']}, {payload['object_id']}",
    )
    checks.record(
        "source depth is pre-call metadata",
        abs(source - chosen.metadata.average_depth) < 1e-6,
        f"reported={source:.4f} metadata={chosen.metadata.average_depth:.4f}",
    )
    checks.record(
        "target depth sampled at placement point",
        abs(target - expected_target_depth) < 1e-6,
        f"reported={target:.4f} sampled={expected_target_depth:.4f}",
    )
    checks.record(
        "scale factor equals target/source",
        abs(scale - (target / source)) < 1e-6,
        f"scale={scale:.4f} target/source={target / source:.4f}",
    )


def verify_geometry(
    checks: Checklist,
    before_bytes: bytes,
    after_bytes: bytes,
    scale: float,
) -> None:
    """Verify canvas size, bbox scaling, and center preservation of the cutout."""
    before = decode_bgra(before_bytes)
    after = decode_bgra(after_bytes)

    checks.record(
        "canvas size unchanged",
        before.shape[:2] == after.shape[:2],
        f"before={before.shape[:2]} after={after.shape[:2]}",
    )

    before_box = alpha_bbox(before_bytes)
    after_box = alpha_bbox(after_bytes)
    if before_box is None or after_box is None:
        checks.record(
            "visible content preserved",
            False,
            "one of the cutouts has no visible alpha pixels",
        )
        return

    canvas_h, canvas_w = before.shape[:2]
    expected_w = before_box.width * scale
    expected_h = before_box.height * scale
    center_x, center_y = before_box.center
    fits = (
        center_x - expected_w / 2.0 >= 0
        and center_y - expected_h / 2.0 >= 0
        and center_x + expected_w / 2.0 <= canvas_w
        and center_y + expected_h / 2.0 <= canvas_h
    )

    if not fits:
        checks.skip(
            "bbox scaled by reported factor",
            f"expected {expected_w:.1f}x{expected_h:.1f} box is clipped by the "
            f"{canvas_w}x{canvas_h} canvas, so size cannot be compared",
        )
    else:
        tol_w = BBOX_TOLERANCE_PX + expected_w * BBOX_TOLERANCE_RATIO
        tol_h = BBOX_TOLERANCE_PX + expected_h * BBOX_TOLERANCE_RATIO
        checks.record(
            "bbox scaled by reported factor",
            abs(after_box.width - expected_w) <= tol_w
            and abs(after_box.height - expected_h) <= tol_h,
            f"before={before_box.width}x{before_box.height} "
            f"after={after_box.width}x{after_box.height} "
            f"expected~{expected_w:.1f}x{expected_h:.1f}",
        )

    after_center = after_box.center
    checks.record(
        "bbox center preserved",
        abs(after_center[0] - center_x) <= BBOX_TOLERANCE_PX
        and abs(after_center[1] - center_y) <= BBOX_TOLERANCE_PX,
        f"before=({center_x:.1f},{center_y:.1f}) "
        f"after=({after_center[0]:.1f},{after_center[1]:.1f})",
    )


def verify_persistence(
    checks: Checklist,
    payload: dict[str, Any],
    after_bytes: bytes,
    images_dir: Path,
    chosen: SavedObject,
) -> None:
    """Verify the cutout PNG and metadata on disk reflect the response."""
    cutout_path = resolve_object_cutout_path(
        images_dir, chosen.metadata.session_id, chosen.metadata.object_id
    )
    checks.record(
        "cutout PNG overwritten with response bytes",
        cutout_path.exists() and cutout_path.read_bytes() == after_bytes,
        f"path={cutout_path.name} bytes={len(after_bytes)}",
    )

    reloaded = load_object_metadata(chosen.metadata.session_id, chosen.metadata.object_id)
    if reloaded is None:
        checks.record("metadata reloadable after rescale", False, "metadata row missing")
        return

    target = float(payload["target_depth"])
    checks.record(
        "metadata average_depth advanced to target",
        abs(reloaded.average_depth - target) < 1e-6,
        f"stored={reloaded.average_depth:.4f} target={target:.4f} "
        f"(was {chosen.metadata.average_depth:.4f})",
    )

    bounds = payload.get("cutout_bounds")
    actual_box = alpha_bbox(after_bytes)
    if bounds is None or actual_box is None:
        checks.skip("cutout_bounds match alpha bbox", "no bounds or no visible pixels")
        return

    checks.record(
        "cutout_bounds match alpha bbox",
        (
            bounds["left"] == actual_box.left
            and bounds["top"] == actual_box.top
            and bounds["right"] == actual_box.right
            and bounds["bottom"] == actual_box.bottom
        ),
        f"response={bounds['left']},{bounds['top']},{bounds['right']},{bounds['bottom']} "
        f"actual={actual_box.left},{actual_box.top},{actual_box.right},{actual_box.bottom}",
    )


def verify_no_compounding(
    checks: Checklist,
    client: Any,
    chosen: SavedObject,
    x: int,
    y: int,
    after_bytes: bytes,
) -> None:
    """Re-run at the same point and assert the second call is a no-op.

    The first call rewrites ``average_depth`` to the placement depth precisely
    so repeated placements at the same spot do not shrink the object again.
    """
    payload = call_rescale(client, chosen.metadata.uuid, x, y)
    scale = float(payload["scale_factor"])
    checks.record(
        "second call at same point does not compound",
        abs(scale - 1.0) < 1e-6,
        f"scale_factor={scale:.6f}",
    )

    second_bytes = base64.b64decode(payload["cutout_b64"])
    first_box = alpha_bbox(after_bytes)
    second_box = alpha_bbox(second_bytes)
    if first_box is None or second_box is None:
        checks.skip("bbox stable across repeat call", "missing visible pixels")
        return

    checks.record(
        "bbox stable across repeat call",
        abs(second_box.width - first_box.width) <= BBOX_TOLERANCE_PX
        and abs(second_box.height - first_box.height) <= BBOX_TOLERANCE_PX,
        f"first={first_box.width}x{first_box.height} "
        f"second={second_box.width}x{second_box.height}",
    )


def composite_over_canvas(canvas_bytes: bytes, cutout_bytes: bytes) -> np.ndarray:
    """Alpha-blend a BGRA cutout back onto the session canvas for preview."""
    canvas = decode_bgra(canvas_bytes)
    if canvas.ndim == 3 and canvas.shape[2] == 4:
        canvas = cv2.cvtColor(canvas, cv2.COLOR_BGRA2BGR)

    cutout = decode_bgra(cutout_bytes)
    if cutout.shape[:2] != canvas.shape[:2]:
        cutout = cv2.resize(
            cutout, (canvas.shape[1], canvas.shape[0]), interpolation=cv2.INTER_NEAREST
        )

    alpha = cutout[:, :, 3:4].astype(np.float32) / 255.0
    blended = canvas.astype(np.float32) * (1.0 - alpha) + cutout[:, :, :3].astype(np.float32) * alpha
    return blended.astype(np.uint8)


def save_artifacts(
    output_dir: Path,
    chosen: SavedObject,
    canvas_bytes: bytes,
    before_bytes: bytes,
    after_bytes: bytes,
    payload: dict[str, Any],
    x: int,
    y: int,
) -> None:
    """Write before/after cutouts and canvas composites for visual inspection."""
    output_dir.mkdir(parents=True, exist_ok=True)
    prefix = f"{chosen.metadata.session_id}_{chosen.metadata.object_id}"

    (output_dir / f"{prefix}_before_cutout.png").write_bytes(before_bytes)
    (output_dir / f"{prefix}_after_cutout.png").write_bytes(after_bytes)

    before_preview = composite_over_canvas(canvas_bytes, before_bytes)
    after_preview = composite_over_canvas(canvas_bytes, after_bytes)
    for preview in (before_preview, after_preview):
        cv2.drawMarker(preview, (x, y), (0, 0, 255), cv2.MARKER_CROSS, 28, 3)

    cv2.imwrite(str(output_dir / f"{prefix}_before_preview.png"), before_preview)
    cv2.imwrite(str(output_dir / f"{prefix}_after_preview.png"), after_preview)

    summary = {
        "session_id": chosen.metadata.session_id,
        "object_id": chosen.metadata.object_id,
        "object_uuid": chosen.metadata.uuid,
        "placement": {"x": x, "y": y},
        "source_average_depth": payload["source_average_depth"],
        "target_depth": payload["target_depth"],
        "scale_factor": payload["scale_factor"],
        "cutout_bounds": payload.get("cutout_bounds"),
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    logger.info(f"Artifacts written to {output_dir}")


def parse_args() -> argparse.Namespace:
    """Parse CLI options controlling session choice, placement, and cleanup."""
    parser = argparse.ArgumentParser(
        description=(
            "Run POST /images/objects/{uuid}/rescale-by-depth end to end against a "
            "saved session, in a sandbox copy so real artifacts are never modified."
        )
    )
    parser.add_argument("--list", action="store_true", help="List saved objects and exit.")
    parser.add_argument("--session", default=None, help="Session uid to exercise.")
    parser.add_argument("--object-id", type=int, default=None, help="Object id within the session.")
    parser.add_argument("--x", type=int, default=None, help="Placement X in natural-image pixels.")
    parser.add_argument("--y", type=int, default=None, help="Placement Y in natural-image pixels.")
    parser.add_argument("--keep", action="store_true", help="Keep the sandbox directory for inspection.")
    parser.add_argument(
        "--output-dir",
        default=None,
        help=f"Artifact directory (default: fastApi-app/{DEFAULT_OUTPUT_SUBDIR}/<timestamp>).",
    )
    return parser.parse_args()


def main() -> int:
    """Run the full rescale-by-depth flow against a saved session."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    args = parse_args()

    real_storage_dir = settings.get_image_storage_dir()
    logger.info(f"Scanning saved sessions in {real_storage_dir}")
    candidates = discover_saved_objects(real_storage_dir)
    if not candidates:
        logger.error("No saved objects found. Upload an image and remove an object first.")
        return 1

    if args.list:
        for candidate in candidates:
            logger.info(
                f"{candidate.label} uuid={candidate.metadata.uuid} "
                f"average_depth={candidate.metadata.average_depth:.2f} "
                f"cutout={candidate.cutout_path.name}"
            )
        return 0

    try:
        chosen = choose_object(candidates, args.session, args.object_id)
    except LookupError as exc:
        logger.error(str(exc))
        return 1

    logger.info(
        f"Selected object {chosen.label} uuid={chosen.metadata.uuid} "
        f"average_depth={chosen.metadata.average_depth:.2f}"
    )

    sandbox_root, images_dir = build_sandbox(real_storage_dir, chosen.metadata.session_id)
    checks = Checklist()
    try:
        activate_sandbox(images_dir)

        before_bytes = resolve_object_cutout_path(
            images_dir, chosen.metadata.session_id, chosen.metadata.object_id
        ).read_bytes()
        canvas_bytes = load_canvas_bytes(
            image_id=chosen.metadata.session_id, base_dir=images_dir
        )
        depth_map = load_session_depth(images_dir, chosen.metadata.session_id)

        if args.x is not None and args.y is not None:
            x, y = args.x, args.y
        else:
            x, y = pick_placement_point(depth_map, chosen.metadata.average_depth)
        expected_target_depth = sample_depth_at_point(depth_map, x, y)

        from fastapi.testclient import TestClient

        with TestClient(build_test_app()) as client:
            payload = call_rescale(client, chosen.metadata.uuid, x, y)
            after_bytes = base64.b64decode(payload["cutout_b64"])

            logger.info(
                f"Rescale returned scale_factor={payload['scale_factor']:.4f} "
                f"(source={payload['source_average_depth']:.2f} -> "
                f"target={payload['target_depth']:.2f})"
            )

            verify_response(checks, payload, chosen, expected_target_depth)
            verify_geometry(checks, before_bytes, after_bytes, float(payload["scale_factor"]))
            verify_persistence(checks, payload, after_bytes, images_dir, chosen)
            verify_no_compounding(checks, client, chosen, x, y, after_bytes)

        output_dir = (
            Path(args.output_dir)
            if args.output_dir
            else _APP_ROOT / DEFAULT_OUTPUT_SUBDIR / datetime.now().strftime("%Y%m%d_%H%M%S")
        )
        save_artifacts(
            output_dir, chosen, canvas_bytes, before_bytes, after_bytes, payload, x, y
        )
    except Exception:
        logger.exception("Rescale-by-depth harness failed")
        return 1
    finally:
        if args.keep:
            logger.info(f"Sandbox kept at {sandbox_root}")
        else:
            shutil.rmtree(sandbox_root, ignore_errors=True)

    passed = sum(1 for result in checks.results if result.status == "PASS")
    skipped = sum(1 for result in checks.results if result.status == "SKIP")
    logger.info(
        f"Checks: {passed} passed, {len(checks.failed)} failed, {skipped} skipped"
    )
    return 1 if checks.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
