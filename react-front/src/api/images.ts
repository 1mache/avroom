import type { ClickRequest, ClickResultResponse, ImageUploadResponse } from "../types/api";

const API_BASE_URL =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "http://127.0.0.1:8000";

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

