export interface ImageUploadResponse {
  image_id: string;
  original_filename?: string | null;
  stored_path?: string | null;
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

export interface ClickResultResponse {
  image_id: string;
  background_b64: string;
  cutout_b64: string;
  format: string;
  // Tight visible-object bounds inside full cutout PNG. Used by drag clamp.
  cutout_bounds?: CutoutBounds | null;
}

export interface UidCacheStatusResponse {
  uid: string;
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

