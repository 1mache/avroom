// App-level view models for the result stage. These are derived from API DTOs
// (see types/api.ts) but carry client-only state (drag offset, hidden flag,
// glbData) that the backend never sees.
import type { SegmentMaskResult } from "./api";

export interface ClickPosition {
  x: number;
  y: number;
}

export interface CutoutAlphaBounds {
  left: number;
  top: number;
  right: number;
  bottom: number;
  naturalWidth: number;
  naturalHeight: number;
}

export interface RotationPose {
  azimuthDeg: number;
  relativeElevationDeg: number;
}

// One requested rotation for an object. `previewSrc` is a snapshot of the 3D
// viewer taken at commit time, shown immediately while the real novel-view
// synthesis (`src`) is still in flight. Re-rotating overwrites this in place
// -- rotation always starts over from the pristine (unrotated) cutout, since
// the backend never mutates that file.
export interface ObjectRotation {
  pose: RotationPose;
  previewSrc: string;
  src: string | null;
  bounds: CutoutAlphaBounds | null;
  status: "pending" | "ready" | "error";
}

export interface CutoutObject {
  objectId: number;
  // Server-generated UUID, primary key for rename/rescale/novel-view calls.
  // Null only for pre-UUID legacy session data.
  uuid: string | null;
  name: string | null;
  cutoutSrc: string;
  cutoutAlphaBounds: CutoutAlphaBounds | null;
  normalizedClickPos: ClickPosition | null;
  glbData: ArrayBuffer | null;
  // Local-only, like glbData -- the backend caches novel views on disk but
  // exposes no GET for them, so this is lost on session restore.
  rotation: ObjectRotation | null;
  // Per-object visibility toggle. Hidden objects render nothing and cannot be
  // selected/dragged; see ObjectPanel eye button.
  hidden: boolean;
  // Per-object drag offset, natural-image pixels. Every object stays composited
  // on the background simultaneously, so position can't live in shared state.
  offset: ClickPosition;
  // Cumulative UI display scale; cutout PNG stays at original resolution.
  displayScale: number;
  // Server-estimated Zero123 source elevation (degrees); used for novel-view.
  sourceElevationDeg: number;
  /** Whether a GLB exists on disk for this object. */
  has3d: boolean;
  /** UUID of the clone root when this object was duplicated from another. */
  cloneRootUuid: string | null;
}

/** True when *obj* shares a clone lineage with at least one other object. */
export function hasCloneSiblings(
  obj: Pick<CutoutObject, "uuid" | "cloneRootUuid">,
  objects: ReadonlyArray<Pick<CutoutObject, "uuid" | "cloneRootUuid">>,
): boolean {
  if (!obj.uuid) {
    return false;
  }
  const root = obj.cloneRootUuid ?? obj.uuid;
  return objects.some(
    (other) =>
      other.uuid &&
      other.uuid !== obj.uuid &&
      (other.cloneRootUuid ?? other.uuid) === root,
  );
}

// Which image should currently represent an object on the stage: its rotated
// view (synthesized result, or the in-flight snapshot while waiting), or the
// original cutout when the user asked to see it / no rotation exists yet.
// Narrowed to just the fields needed (rather than the full CutoutObject) so
// callers like ObjectPanel's structurally-typed thumbnail entries can use it.
export function effectiveCutoutSrc(
  obj: { cutoutSrc: string; rotation: ObjectRotation | null },
  showOriginal: boolean,
): string {
  if (showOriginal || !obj.rotation) {
    return obj.cutoutSrc;
  }
  return obj.rotation.src ?? obj.rotation.previewSrc;
}

// Bounds paired with effectiveCutoutSrc. The in-flight preview snapshot is
// framed to the object's existing rect, so it reuses cutoutAlphaBounds; only a
// landed synthesis result gets its own server-reported bounds.
export function effectiveCutoutBounds(
  obj: { cutoutAlphaBounds: CutoutAlphaBounds | null; rotation: ObjectRotation | null },
  showOriginal: boolean,
): CutoutAlphaBounds | null {
  if (showOriginal || !obj.rotation) {
    return obj.cutoutAlphaBounds;
  }
  if (obj.rotation.status === "ready" && obj.rotation.bounds) {
    return obj.rotation.bounds;
  }
  return obj.cutoutAlphaBounds;
}

// Logical on-stage bounds after UI display scale is applied. Base alpha bounds
// come from the untouched cutout PNG; displayScale is persisted separately.
export function effectiveDisplayBounds(
  obj: {
    cutoutAlphaBounds: CutoutAlphaBounds | null;
    displayScale: number;
    rotation: ObjectRotation | null;
  },
  showOriginal: boolean,
): CutoutAlphaBounds | null {
  const base = effectiveCutoutBounds(obj, showOriginal);
  if (!base || obj.displayScale === 1) {
    return base;
  }
  const growX = ((base.right - base.left) * (obj.displayScale - 1)) / 2;
  const growY = ((base.bottom - base.top) * (obj.displayScale - 1)) / 2;
  return {
    ...base,
    left: base.left - growX,
    right: base.right + growX,
    top: base.top - growY,
    bottom: base.bottom + growY,
  };
}

// Driven by the head of the session's server-side segment-job backlog (see
// useSessionJobs' segmentQueue effect), not by a single in-flight request —
// multiple segment results can be waiting at once, consumed one at a time.
// `jobId` is threaded through to selectMask (as SubmitInpaintRequest.from_job_id,
// so the source job row is consumed atomically) and to dismissal.
export type SegmentPickerState =
  | { status: "idle" }
  | { status: "choosing"; jobId: string; maskOptions: SegmentMaskResult[] };
