export interface SessionInfo {
  uid: string;
  name: string | null;
  last_changed: string | null;
}

export interface ImageUploadResponse {
  image_id: string;
  original_filename?: string | null;
  stored_path?: string | null;
  last_changed: string;
}

export type JobKind = "segment" | "inpaint" | "generate_3d";
export type JobStatus = "queued" | "running" | "done" | "failed" | "conflict";

// One durable queued-work row, as returned by GET /jobs/active and embedded
// in SessionSyncCheckResponse.jobs. See fastApi-app/schemas/jobs.py::JobInfo.
export interface JobInfo {
  job_id: string;
  session_id: string;
  kind: JobKind;
  status: JobStatus;
  error?: string | null;
  created_at: string;
  /** Target object id, present only for generate_3d jobs. */
  object_id?: number | null;
}

export interface SegmentMaskResult {
  mask_id: string;
  cutout_b64: string;
  format: string;
  cutout_bounds?: CutoutBounds | null;
}

// GET /jobs/{job_id}. `masks` is populated only for a done segment job.
export interface JobDetailResponse extends JobInfo {
  masks?: SegmentMaskResult[] | null;
}

export interface JobSubmitResponse {
  job_id: string;
}

export interface SubmitInpaintRequest {
  image_id: string;
  mask_id: string;
  from_job_id?: string | null;
}

export interface Generate3DJobRequest {
  uid: string;
  object_id: number;
}

export interface SessionSyncCheckResponse {
  last_changed: string;
  needs_refresh: boolean;
  jobs: JobInfo[];
}

// Mirrors backend processing options. Fields remain optional because frontend
// currently sends none of them in normal flow.
export interface ClickRequestOptions {
  output_format?: string;
  grayscale?: boolean;
}

export interface ClickRequest {
  image_id: string;
  x: number;
  y: number;
  options?: ClickRequestOptions;
}

export type SegmentRequest = ClickRequest;

export interface ClickResultResponse {
  image_id: string;
  background_b64: string;
  cutout_b64: string;
  format: string;
  // Tight visible-object bounds inside full cutout PNG. Used by drag clamp.
  cutout_bounds?: CutoutBounds | null;
}

export interface ObjectMetadataResponse {
  uuid: string;
  session_id: string;
  object_id: number;
  name: string | null;
  average_depth: number;
  source_elevation_deg?: number;
  content_hash: string;
  created_at: string;
  has_3d: boolean;
  cutout_bounds?: CutoutBounds | null;
  offset_x: number;
  offset_y: number;
}

// Every field optional: a caller sends only what it's actually changing
// (a drag-persist call never includes `name`, a rename call never includes
// the offset fields) so the backend's partial-update semantics apply.
export interface UpdateObjectRequest {
  name?: string | null;
  offset_x?: number;
  offset_y?: number;
}

export interface DuplicateObjectResponse {
  object_uuid: string;
}

export interface UidCacheStatusResponse {
  uid: string;
  name?: string | null;
  has_background: boolean;
  has_cutout: boolean;
  has_3d: boolean;
  cutout_bounds?: CutoutBounds | null;
}

export interface CutoutBounds {
  left: number;
  top: number;
  right: number;
  bottom: number;
  // Full PNG dimensions, needed because visible bounds alone are not enough to
  // map drag/clamp math back to original image space.
  natural_width: number;
  natural_height: number;
}

export interface ObjectInfo {
  object_id: number;
  uuid?: string | null;
  name?: string | null;
  average_depth?: number | null;
  source_elevation_deg?: number | null;
  cutout_b64: string;
  format: string;
  cutout_bounds?: CutoutBounds | null;
  has_3d: boolean;
  offset_x: number;
  offset_y: number;
}

export interface ObjectListResponse {
  uid: string;
  objects: ObjectInfo[];
}

export type AzimuthDirection = "CLOCKWISE" | "C_CLOCKWISE";
export type ElevationDirection = "UP" | "DOWN";
export type ZoomDirection = "ZOOM_IN" | "ZOOM_OUT";

export interface NovelViewRequest {
  uid: string;
  object_id: number;
  elevation_deg: number;
  azimuth_deg: number;
  azimuth_direction?: AzimuthDirection | null;
  relative_elevation_deg?: number;
  elevation_direction?: ElevationDirection | null;
  radius?: number;
  zoom_direction?: ZoomDirection | null;
}

export interface NovelViewPreviewCacheRequest {
  uid: string;
  object_id: number;
  azimuth_deg: number;
  relative_elevation_deg?: number;
  image_b64: string;
}

export interface NovelViewResponse {
  uid: string;
  object_id: number;
  image_b64: string;
  format: string;
  cutout_bounds?: CutoutBounds | null;
  elevation_deg: number;
  azimuth_deg: number;
  azimuth_direction?: AzimuthDirection | null;
  relative_elevation_deg: number;
  elevation_direction?: ElevationDirection | null;
  radius: number;
  zoom_direction?: ZoomDirection | null;
}

