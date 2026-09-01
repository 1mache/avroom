import type {
  DuplicateObjectResponse,
  Generate3DJobRequest,
  ImageUploadResponse,
  ImportObjectResponse,
  JobDetailResponse,
  JobInfo,
  JobSubmitResponse,
  NovelViewRequest,
  NovelViewResponse,
  ObjectListResponse,
  ObjectMetadataResponse,
  SegmentRequest,
  SessionInfo,
  SessionSyncCheckResponse,
  SmartPasteRequest,
  SmartPasteResponse,
  SubmitInpaintRequest,
  SubmitEraseRequest,
  WarmSessionMapsResponse,
  UidCacheStatusResponse,
  UpdateObjectRequest,
  BatchRequest,
  BatchResponse,
} from "../types/api";

export const API_BASE_URL =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "http://127.0.0.1:8000";

const DEFAULT_FETCH_TIMEOUT_MS = 15_000;

async function fetchWithTimeout(
  input: RequestInfo | URL,
  init?: RequestInit,
  timeoutMs: number = DEFAULT_FETCH_TIMEOUT_MS,
): Promise<Response> {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(input, { ...init, signal: controller.signal });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new ApiError(0, "Request timed out — is the image service running?");
    }
    throw err;
  } finally {
    window.clearTimeout(timeoutId);
  }
}

// Carries the HTTP status through so callers can distinguish e.g. 409
// (expected concurrency conflict) from 404/500 (real failure) instead of
// string-matching the message. `detail` is the raw FastAPI error body text
// (usually the `detail` field unwrapped, sometimes just raw text).
export class ApiError extends Error {
  readonly status: number;
  readonly detail: string;

  constructor(status: number, detail: string) {
    super(detail || `Request failed with status ${status}`);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

// Extracts a readable message from a FastAPI error body. FastAPI's default
// error envelope is `{"detail": "..."}`; fall back to raw text for anything
// else (proxy errors, plain-text 500s, etc).
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

async function throwApiError(response: Response): Promise<never> {
  const detail = await extractErrorDetail(response);
  throw new ApiError(response.status, detail);
}

// Central JSON error mapping so screens can treat backend error bodies as
// typed ApiErrors instead of generic network failures.
async function handleJsonResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    return throwApiError(response);
  }

  return (await response.json()) as T;
}

export async function uploadImage(file: File): Promise<ImageUploadResponse> {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch(`${API_BASE_URL}/images/upload`, {
    method: "POST",
    body: formData,
  });

  return handleJsonResponse<ImageUploadResponse>(response);
}

// Queues GLB generation and returns its job id immediately (202) — the
// backend no longer blocks the request on the model run. Callers await
// completion via waitForJobDone, then fetch the GLB via fetchCached3DModel.
export async function submitGenerate3D(uid: string, objectId: number): Promise<string> {
  const response = await fetch(`${API_BASE_URL}/3d/test-3d`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ uid, object_id: objectId } satisfies Generate3DJobRequest),
  });

  const body = await handleJsonResponse<JobSubmitResponse>(response);
  return body.job_id;
}

export async function getSessions(): Promise<SessionInfo[]> {
  const response = await fetchWithTimeout(`${API_BASE_URL}/images/sessions`);
  return handleJsonResponse<SessionInfo[]>(response);
}

// --- Session previews (dashboard thumbnails) -------------------------------
// The dashboard shows each session as the user left it. GET/POST
// /images/{uid}/preview are live on the backend: the GET serves a JPEG (404
// with a placeholder fallback when a session has none yet), and the POST
// stores a client-composited thumbnail, best-effort.
export const PREVIEW_API_READY = true;

/**
 * Thumbnail URL for a session. `lastChanged` is used as a cache-buster so a
 * session edited in another tab doesn't keep showing a stale preview.
 */
export function sessionPreviewUrl(uid: string, lastChanged: string | null): string {
  const bust = lastChanged ? `?t=${encodeURIComponent(lastChanged)}` : "";
  return `${API_BASE_URL}/images/${uid}/preview${bust}`;
}

/**
 * Stores the composed canvas as the session's dashboard thumbnail. Best-effort
 * and detached — a failure here must never affect the edit that triggered it.
 */
export async function saveSessionPreview(uid: string, imageB64: string): Promise<void> {
  if (!PREVIEW_API_READY) {
    return;
  }

  const response = await fetch(`${API_BASE_URL}/images/${uid}/preview`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ image_b64: imageB64 }),
  });

  if (!response.ok) {
    return throwApiError(response);
  }
}

export async function setSessionName(uid: string, name: string): Promise<SessionInfo> {
  const response = await fetch(`${API_BASE_URL}/images/${uid}/name`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ name }),
  });

  return handleJsonResponse<SessionInfo>(response);
}

export async function getUidCacheStatus(uid: string): Promise<UidCacheStatusResponse> {
  const response = await fetch(`${API_BASE_URL}/images/${uid}/cache`);
  return handleJsonResponse<UidCacheStatusResponse>(response);
}

export async function warmSessionMaps(uid: string): Promise<WarmSessionMapsResponse> {
  const response = await fetch(`${API_BASE_URL}/images/${uid}/warm-maps`, {
    method: "POST",
  });
  return handleJsonResponse<WarmSessionMapsResponse>(response);
}

// Queues segmentation and returns its job id immediately (202). The result
// (mask candidates) shows up later in the session's jobs list (see
// syncCheckSession) once the dispatcher finishes it.
export async function segmentImage(payload: SegmentRequest): Promise<JobSubmitResponse> {
  const response = await fetch(`${API_BASE_URL}/images/segment`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  return handleJsonResponse<JobSubmitResponse>(response);
}

// Queues inpainting and returns its job id immediately (202).
export async function inpaintMask(payload: SubmitInpaintRequest): Promise<JobSubmitResponse> {
  const response = await fetch(`${API_BASE_URL}/images/inpaint`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  return handleJsonResponse<JobSubmitResponse>(response);
}

// Queues erase inpainting and returns the first job id immediately (202).
export async function eraseMask(payload: SubmitEraseRequest): Promise<JobSubmitResponse> {
  const response = await fetch(`${API_BASE_URL}/images/erase`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  return handleJsonResponse<JobSubmitResponse>(response);
}

// --- Job queue ---------------------------------------------------------

export async function getActiveJobs(): Promise<JobInfo[]> {
  const response = await fetchWithTimeout(`${API_BASE_URL}/jobs/active`);
  return handleJsonResponse<JobInfo[]>(response);
}

export async function getJob(jobId: string): Promise<JobDetailResponse> {
  const response = await fetch(`${API_BASE_URL}/jobs/${jobId}`);
  return handleJsonResponse<JobDetailResponse>(response);
}

/** Dismiss a failed/conflict job, or discard an unconsumed segment result. */
export async function deleteJob(jobId: string): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/jobs/${jobId}`, { method: "DELETE" });
  if (!response.ok) {
    return throwApiError(response);
  }
}

const JOB_POLL_INTERVAL_MS = 800;
const JOB_POLL_TIMEOUT_MS = 5 * 60 * 1000;

/**
 * Polls a job until it leaves `queued`/`running`. Used only by the 3D-rotate
 * flow, which (unlike segment/inpaint) directly awaits one specific job
 * rather than watching the session's job list.
 *
 * A 404 here is treated as success, not a fresh failure: a successful
 * generate_3d job's row is deleted by the dispatcher (its real result is the
 * GLB file on disk, already written by the time the row disappears) — same
 * as inpaint. This is only safe because callers poll a job id currently
 * `queued`/`running` in `jobs.jobs` (whether just submitted, or attached to
 * after exiting mid-generation and returning — see WorkspaceScreen's
 * handleRotate); polling an id after it's already been dismissed once would
 * misread "gone because dismissed" as success.
 */
export async function waitForJobDone(jobId: string): Promise<void> {
  const deadline = Date.now() + JOB_POLL_TIMEOUT_MS;
  for (;;) {
    let job: JobDetailResponse;
    try {
      job = await getJob(jobId);
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        return;
      }
      throw err;
    }

    if (job.status === "done") {
      return;
    }
    if (job.status === "failed" || job.status === "conflict") {
      throw new ApiError(422, job.error ?? "Job failed.");
    }
    if (Date.now() > deadline) {
      throw new Error("Timed out waiting for job to finish.");
    }
    await new Promise((resolve) => setTimeout(resolve, JOB_POLL_INTERVAL_MS));
  }
}

export async function deleteSession(uid: string): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/images/${uid}`, {
    method: "DELETE",
  });

  if (!response.ok) {
    return throwApiError(response);
  }
}

// 404 means "model not generated yet", not an exceptional transport failure.
export async function fetchCached3DModel(uid: string, objectId: number): Promise<ArrayBuffer | null> {
  const response = await fetch(`${API_BASE_URL}/3d/${uid}/${objectId}`);
  if (response.status === 404) return null;
  if (!response.ok) {
    return throwApiError(response);
  }
  return response.arrayBuffer();
}

export async function getSessionObjects(uid: string): Promise<ObjectListResponse> {
  const response = await fetch(`${API_BASE_URL}/images/${uid}/objects`);
  return handleJsonResponse<ObjectListResponse>(response);
}

export async function setObjectName(
  objectUuid: string,
  name: string | null,
): Promise<ObjectMetadataResponse> {
  const response = await fetch(`${API_BASE_URL}/images/objects/${objectUuid}`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ name } satisfies UpdateObjectRequest),
  });

  return handleJsonResponse<ObjectMetadataResponse>(response);
}

/**
 * Persists an object's drag offset. Fires from drag-end so the position
 * survives a session close/reopen -- omits `name` entirely (not `name:
 * null`) so the backend's partial-update semantics leave it untouched.
 */
export async function resetObjectTransform(
  objectUuid: string,
): Promise<ObjectMetadataResponse> {
  const response = await fetch(
    `${API_BASE_URL}/images/objects/${objectUuid}/reset-transform`,
    {
      method: "POST",
    },
  );

  return handleJsonResponse<ObjectMetadataResponse>(response);
}

export async function setObjectOffset(
  objectUuid: string,
  offsetX: number,
  offsetY: number,
): Promise<ObjectMetadataResponse> {
  const response = await fetch(`${API_BASE_URL}/images/objects/${objectUuid}`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      offset_x: offsetX,
      offset_y: offsetY,
    } satisfies UpdateObjectRequest),
  });

  return handleJsonResponse<ObjectMetadataResponse>(response);
}

export async function setObjectDisplayScale(
  objectUuid: string,
  displayScale: number,
): Promise<ObjectMetadataResponse> {
  const response = await fetch(`${API_BASE_URL}/images/objects/${objectUuid}`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      display_scale: displayScale,
    } satisfies UpdateObjectRequest),
  });

  return handleJsonResponse<ObjectMetadataResponse>(response);
}

export async function smartPasteObject(
  objectUuid: string,
  x: number,
  y: number,
): Promise<SmartPasteResponse> {
  const response = await fetch(`${API_BASE_URL}/images/objects/${objectUuid}/smart-paste`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ x, y } satisfies SmartPasteRequest),
  });

  return handleJsonResponse<SmartPasteResponse>(response);
}

export async function runSessionBatch(uid: string, payload: BatchRequest): Promise<BatchResponse> {
  const response = await fetch(`${API_BASE_URL}/images/${uid}/batch`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ ...payload, verify: "auto" }),
  });
  return handleJsonResponse<BatchResponse>(response);
}

export async function duplicateObject(objectUuid: string): Promise<DuplicateObjectResponse> {
  const response = await fetch(`${API_BASE_URL}/images/objects/${objectUuid}/duplicate`, {
    method: "POST",
  });

  return handleJsonResponse<DuplicateObjectResponse>(response);
}

export async function importObjectCutout(uid: string, file: File): Promise<ImportObjectResponse> {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch(`${API_BASE_URL}/images/${uid}/objects/import`, {
    method: "POST",
    body: formData,
  });

  return handleJsonResponse<ImportObjectResponse>(response);
}

/**
 * Permanently deletes one object and all its per-object artifacts (cutout,
 * GLB, novel-view caches, metadata). The background canvas keeps the
 * inpainted hole -- this never restores the object's original pixels.
 */
export async function deleteObject(objectUuid: string): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/images/objects/${objectUuid}`, {
    method: "DELETE",
  });

  if (!response.ok) {
    return throwApiError(response);
  }
}

/** Removes this object's cached GLB only; cutout and metadata stay intact. */
export async function deleteObject3d(objectUuid: string): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/images/objects/${objectUuid}/3d`, {
    method: "DELETE",
  });

  if (!response.ok) {
    return throwApiError(response);
  }
}

// Compares a client-held last_changed timestamp against server truth so a
// session that changed elsewhere (another tab, another client) can be
// detected without unconditionally re-fetching everything.
export async function syncCheckSession(
  uid: string,
  clientLastChanged: string | null,
): Promise<SessionSyncCheckResponse> {
  const response = await fetch(`${API_BASE_URL}/images/${uid}/sync-check`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ client_last_changed: clientLastChanged }),
  });

  return handleJsonResponse<SessionSyncCheckResponse>(response);
}

export async function synthesizeNovelView(payload: NovelViewRequest): Promise<NovelViewResponse> {
  const response = await fetch(`${API_BASE_URL}/images/novel-view`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  return handleJsonResponse<NovelViewResponse>(response);
}

