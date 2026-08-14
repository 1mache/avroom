// Mirrors fastApi-app/schemas/debug.py and the query params on
// fastApi-app/api/debug_vision.py. Used only by the Pipeline Debug screen —
// kept separate from types/api.ts, which is session-scoped.

export interface DebugCheckResult {
  name: string;
  passed: boolean;
  score: number | null;
  message: string;
}

export interface DebugValidationResponse {
  ok: boolean;
  technical_ok: boolean;
  content_ok: boolean | null;
  technical: DebugCheckResult[];
  content: DebugCheckResult[];
  content_skipped_reason: string | null;
  elapsed_ms: number;
}

export type DepthStrategy = "anything" | "blended" | "enhanced_edge";
export type DepthColormap = "none" | "inferno" | "magma" | "turbo" | "jet";
export type SamSource = "depth" | "rgb";

export interface DepthMapOptions {
  strategy: DepthStrategy;
  model: string;
  colormap: DepthColormap;
}

export interface SamEverythingOptions {
  source: SamSource;
  depthStrategy: DepthStrategy;
  depthModel: string;
  pointsPerSide: number;
  predIouThresh: number;
  stabilityScoreThresh: number;
  minMaskRegionArea: number;
  alpha: number;
}

// A rendered PNG result from either debug image endpoint. `objectUrl` is
// created via URL.createObjectURL — callers own revoking it.
export interface DebugImageResult {
  objectUrl: string;
  elapsedMs: number | null;
  maskCount: number | null;
}
