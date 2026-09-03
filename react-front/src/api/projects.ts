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
