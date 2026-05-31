import type {
  ClickRequest,
  ClickResultResponse,
  ImageUploadResponse,
  InpaintMaskRequest,
  InpaintMaskResponse,
  SegmentRequest,
  SegmentResponse,
  UidCacheStatusResponse,
} from "../types/api";

export const API_BASE_URL =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "http://127.0.0.1:8000";

// Central JSON error mapping so screens can treat backend text bodies as useful
// user-facing errors instead of generic network failures.
async function handleJsonResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed with status ${response.status}`);
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

export async function clickImage(payload: ClickRequest): Promise<ClickResultResponse> {
  const response = await fetch(`${API_BASE_URL}/images/click`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  return handleJsonResponse<ClickResultResponse>(response);
}

export async function generate3DModel(uid: string): Promise<ArrayBuffer> {
  const response = await fetch(`${API_BASE_URL}/objects/test-3d`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ uid }),
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed with status ${response.status}`);
  }

  return response.arrayBuffer();
}

export async function getSessions(): Promise<string[]> {
  const response = await fetch(`${API_BASE_URL}/images/sessions`);
  return handleJsonResponse<string[]>(response);
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

// 404 means "model not generated yet", not an exceptional transport failure.
export async function fetchCached3DModel(uid: string): Promise<ArrayBuffer | null> {
  const response = await fetch(`${API_BASE_URL}/objects/${uid}`);
  if (response.status === 404) return null;
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed with status ${response.status}`);
  }
  return response.arrayBuffer();
}

