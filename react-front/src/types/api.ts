export interface ImageUploadResponse {
  image_id: string;
  original_filename?: string | null;
  stored_path?: string | null;
}

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
}

