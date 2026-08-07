import type {
  DuplicateObjectResponse,
  ImageUploadResponse,
  InpaintMaskRequest,
  InpaintMaskResponse,
  NovelViewPreviewCacheRequest,
  NovelViewRequest,
  NovelViewResponse,
  ObjectListResponse,
  ObjectMetadataResponse,
  SegmentRequest,
  SegmentResponse,
  SessionInfo,
  SessionSyncCheckResponse,
  UidCacheStatusResponse,
  UpdateObjectRequest,
} from "../types/api";

export const API_BASE_URL =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "http://127.0.0.1:8000";

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

export async function generate3DModel(uid: string, objectId: number): Promise<ArrayBuffer> {
  const response = await fetch(`${API_BASE_URL}/3d/test-3d`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ uid, object_id: objectId }),
  });

  if (!response.ok) {
    return throwApiError(response);
  }

  return response.arrayBuffer();
}

export async function getSessions(): Promise<SessionInfo[]> {
  const response = await fetch(`${API_BASE_URL}/images/sessions`);
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
 * and detached, like cacheNovelViewPreview — a failure here must never affect
 * the edit that triggered it.
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

export async function segmentImage(payload: SegmentRequest): Promise<SegmentResponse> {
  const response = await fetch(`${API_BASE_URL}/images/segment`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  return handleJsonResponse<SegmentResponse>(response);
}

export async function inpaintMask(payload: InpaintMaskRequest): Promise<InpaintMaskResponse> {
  const response = await fetch(`${API_BASE_URL}/images/inpaint`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  return handleJsonResponse<InpaintMaskResponse>(response);
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

export async function duplicateObject(objectUuid: string): Promise<DuplicateObjectResponse> {
  const response = await fetch(`${API_BASE_URL}/images/objects/${objectUuid}/duplicate`, {
    method: "POST",
  });

  return handleJsonResponse<DuplicateObjectResponse>(response);
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

// Best-effort: persists the client-rendered rotation preview so it survives
// on disk as a fallback if the real synthesis request never completes. Fired
// detached alongside synthesizeNovelView; callers should swallow failures.
export async function cacheNovelViewPreview(payload: NovelViewPreviewCacheRequest): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/images/novel-view/preview-cache`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    return throwApiError(response);
  }
}

