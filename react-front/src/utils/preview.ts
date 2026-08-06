// Builds the dashboard thumbnail for a session: the inpainted background with
// every visible cutout composited back on top at its current position — i.e.
// the room exactly as the user left it, not the original photo.
import type { ClickPosition } from "../types/session";
import type { Size } from "./stageGeometry";

/** Long edge of the stored thumbnail. Cards never render larger than this. */
export const PREVIEW_MAX_WIDTH = 640;

const PREVIEW_QUALITY = 0.82;

export interface PreviewLayer {
  src: string;
  offset: ClickPosition;
}

// Cutouts are data: URLs, but the background is usually served from the API on
// a different origin — without crossOrigin the canvas taints and toDataURL
// throws instead of returning pixels.
const loadForCanvas = (src: string): Promise<HTMLImageElement> =>
  new Promise((resolve, reject) => {
    const img = new Image();
    img.crossOrigin = "anonymous";
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error(`Failed to load ${src}`));
    img.src = src;
  });

/**
 * Returns base64 JPEG (no data: prefix, matching the API's `*_b64` fields), or
 * null when the canvas can't be read — a missing thumbnail is never worth
 * interrupting an edit for.
 */
export async function composeSessionPreview(
  backgroundSrc: string,
  layers: PreviewLayer[],
  naturalSize: Size,
): Promise<string | null> {
  try {
    const scale = Math.min(1, PREVIEW_MAX_WIDTH / naturalSize.width);
    const canvas = document.createElement("canvas");
    canvas.width = Math.max(1, Math.round(naturalSize.width * scale));
    canvas.height = Math.max(1, Math.round(naturalSize.height * scale));

    const ctx = canvas.getContext("2d");
    if (!ctx) {
      return null;
    }

    const background = await loadForCanvas(backgroundSrc);
    ctx.drawImage(background, 0, 0, canvas.width, canvas.height);

    // Layers are full-canvas transparent PNGs shifted by their drag offset, so
    // each one is drawn at the same size as the background, just displaced.
    for (const layer of layers) {
      const image = await loadForCanvas(layer.src);
      ctx.drawImage(
        image,
        layer.offset.x * scale,
        layer.offset.y * scale,
        canvas.width,
        canvas.height,
      );
    }

    return canvas.toDataURL("image/jpeg", PREVIEW_QUALITY).split(",")[1] ?? null;
  } catch {
    return null;
  }
}
