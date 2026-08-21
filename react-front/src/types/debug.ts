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
export type NormalHubModel =
  | "metric3d_vit_small"
  | "metric3d_vit_large"
  | "metric3d_vit_giant2";

export interface DepthMapOptions {
  strategy: DepthStrategy;
  model: string;
  colormap: DepthColormap;
}

export interface NormalMapOptions {
  hubModel: NormalHubModel;
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

export interface DebugMaskCandidate {
  index: number;
  score: number;
  reason: string;
  clip_checks: Record<string, number> | null;
  preview_b64: string;
  clip_crop_b64: string | null;
  cutout_b64: string;
}

export interface DebugAutoMaskPickResponse {
  click_xy: [number, number] | number[];
  threshold: number;
  winner_index: number | null;
  finalist_indices: number[];
  tiebreak_method: string;
  tiebreak_reason: string | null;
  candidates: DebugMaskCandidate[];
  elapsed_ms: number;
}

export interface DebugSdParams {
  prompt: string;
  negative_prompt: string;
  strength: number;
  num_inference_steps: number;
  guidance_scale: number;
  mask_dilate_pixels?: number;
  compose_dilate_pixels?: number;
}

export interface DebugInpaintAttempt {
  attempt_index: number;
  ok: boolean;
  sd_skipped: boolean;
  scores: Record<string, number>;
  winner_label: string;
  params: DebugSdParams;
  param_fixes_json: string;
  mask_dilate_pixels?: number;
  compose_dilate_pixels?: number;
  mask_pixel_count?: number;
  next_params?: DebugSdParams | null;
  candidate_b64: string;
  clip_crop_b64: string;
  verify_original_crop_b64?: string | null;
}

export interface DebugInpaintVerifyResponse {
  click_xy: [number, number] | number[];
  mask_index: number;
  preview_b64: string;
  cutout_b64: string;
  passed: boolean;
  retries_exhausted: boolean;
  lama_b64: string | null;
  final_b64: string;
  attempts: DebugInpaintAttempt[];
  elapsed_ms: number;
}
