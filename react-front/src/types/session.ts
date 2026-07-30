// App-level view models for the result stage. These are derived from API DTOs
// (see types/api.ts) but carry client-only state (drag offset, hidden flag,
// glbData) that the backend never sees.
import type { SegmentMaskOption } from "./api";

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
  // Per-object visibility toggle. Hidden objects render nothing and cannot be
  // selected/dragged; see ObjectPanel eye button.
  hidden: boolean;
  // Per-object drag offset, natural-image pixels. Every object stays composited
  // on the background simultaneously, so position can't live in shared state.
  offset: ClickPosition;
}

// One in-flight inpaint. Captured at mask-selection time — not read from live
// UI state at resolution time — because the user may click a new point (and
// start a second concurrent job) before this one's response lands.
export interface PendingInpaintJob {
  jobId: string;
  maskId: string;
  normalizedClickPos: ClickPosition | null;
  startedAt: number;
}

export type SegmentPickerState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "choosing"; maskOptions: SegmentMaskOption[] };
