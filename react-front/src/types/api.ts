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

export interface SessionSyncCheckRequest {
  client_last_changed: string | null;
}

export interface SessionSyncCheckResponse {
  last_changed: string;
  needs_refresh: boolean;
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

export interface SegmentMaskOption {
  mask_id: string;
  cutout_b64: string;
  format: string;
  cutout_bounds?: CutoutBounds | null;
}

export interface SegmentResponse {
  image_id: string;
  masks: SegmentMaskOption[];
}

export interface InpaintMaskRequest {
  image_id: string;
  mask_id: string;
}

export interface InpaintMaskResponse extends ClickResultResponse {
  object_id: number;
  object_uuid: string;
  source_elevation_deg?: number;
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
}

export interface SetObjectNameRequest {
  name: string | null;
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

