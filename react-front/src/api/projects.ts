import type { ProjectInfo } from "../types/api";
import { authedFetch } from "./authToken";
import { API_BASE_URL, handleJsonResponse, throwApiError } from "./images";

export async function getProjects(): Promise<ProjectInfo[]> {
  const response = await authedFetch(`${API_BASE_URL}/projects`);
  return handleJsonResponse<ProjectInfo[]>(response);
}

export async function createProject(name: string): Promise<ProjectInfo> {
  const response = await authedFetch(`${API_BASE_URL}/projects`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  return handleJsonResponse<ProjectInfo>(response);
}

export async function renameProject(id: string, name: string): Promise<ProjectInfo> {
  const response = await authedFetch(`${API_BASE_URL}/projects/${id}/name`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  return handleJsonResponse<ProjectInfo>(response);
}

export async function deleteProject(id: string): Promise<void> {
  const response = await authedFetch(`${API_BASE_URL}/projects/${id}`, { method: "DELETE" });
  if (!response.ok) {
    return throwApiError(response);
  }
}

// Both of these skip fetchWithTimeout's 15s default — a project's zip can be
// tens of MB of cutouts/GLBs, and there's no reason to abort a slow-but-live
// upload/download.

export async function exportProject(id: string): Promise<Blob> {
  const response = await authedFetch(`${API_BASE_URL}/projects/${id}/export`);
  if (!response.ok) {
    return throwApiError(response);
  }
  return response.blob();
}

export async function importProject(file: File): Promise<ProjectInfo> {
  const formData = new FormData();
  formData.append("file", file);
  const response = await authedFetch(`${API_BASE_URL}/projects/import`, {
    method: "POST",
    body: formData,
  });
  return handleJsonResponse<ProjectInfo>(response);
}
