import { API_BASE_URL, ApiError } from "./images";
import type {
  DebugImageResult,
  DebugValidationResponse,
  DepthMapOptions,
  SamEverythingOptions,
} from "../types/debug";

// Backs the Pipeline Debug screen (components/layout/DebugScreen.tsx). Kept
// out of images.ts, which is session-scoped — nothing here creates or
// touches a session; every call is a stateless POST against fastApi-app's
// /debug router (core/debug_vision.py, api/debug_vision.py).

async function extractErrorDetail(response: Response): Promise<string> {
  const text = await response.text();
  if (!text) {
    return "";
  }
  try {
    const parsed = JSON.parse(text) as { detail?: unknown };
    if (typeof parsed.detail === "string") {
      return parsed.detail;
    }
  } catch {
    // Not JSON — fall through to raw text.
  }
  return text;
}

async function throwDebugApiError(response: Response): Promise<never> {
  const detail = await extractErrorDetail(response);
  throw new ApiError(response.status, detail);
}

export async function validateImageDebug(file: File): Promise<DebugValidationResponse> {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch(`${API_BASE_URL}/debug/validate`, {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    return throwDebugApiError(response);
  }
  return (await response.json()) as DebugValidationResponse;
}

// Both PNG endpoints below read the response as a blob and hand back an
// object URL. The caller owns that URL: revoke the previous one before
// re-running a panel, and revoke every held URL on unmount, or each run
// leaks a full-resolution decoded bitmap.
async function postForDebugImage(url: string, file: File): Promise<DebugImageResult> {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch(url, { method: "POST", body: formData });
  if (!response.ok) {
    return throwDebugApiError(response);
  }

  const maskCountHeader = response.headers.get("X-Mask-Count");
  const elapsedHeader = response.headers.get("X-Elapsed-Ms");
  const blob = await response.blob();

  return {
    objectUrl: URL.createObjectURL(blob),
    elapsedMs: elapsedHeader !== null ? Number(elapsedHeader) : null,
    maskCount: maskCountHeader !== null ? Number(maskCountHeader) : null,
  };
}

export async function debugDepthMap(
  file: File,
  options: DepthMapOptions,
): Promise<DebugImageResult> {
  const params = new URLSearchParams({
    strategy: options.strategy,
    model: options.model,
    colormap: options.colormap,
  });
  return postForDebugImage(`${API_BASE_URL}/debug/depth-map?${params.toString()}`, file);
}

export async function debugSamEverything(
  file: File,
  options: SamEverythingOptions,
): Promise<DebugImageResult> {
  const params = new URLSearchParams({
    source: options.source,
    depth_strategy: options.depthStrategy,
    depth_model: options.depthModel,
    points_per_side: String(options.pointsPerSide),
    pred_iou_thresh: String(options.predIouThresh),
    stability_score_thresh: String(options.stabilityScoreThresh),
    min_mask_region_area: String(options.minMaskRegionArea),
    alpha: String(options.alpha),
  });
  return postForDebugImage(`${API_BASE_URL}/debug/sam-everything?${params.toString()}`, file);
}
