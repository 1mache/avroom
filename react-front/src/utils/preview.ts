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
  displayScale?: number;
  bounds?: {
    left: number;
    top: number;
    right: number;
    bottom: number;
  } | null;
}

// Cutouts are data: URLs, but the background is served from the API on a
// different origin. The stage's own <img src={photoSrc}> (no crossOrigin)
// loads that *exact same, cache-busted* URL moments before this runs --
// useSessionSync appends a fresh `?t=<lastChanged>` right after the mutation
// that also triggers this capture. Chrome's HTTP cache is keyed by URL, not
// by request mode, so a plain 'cors' fetch of that identical URL can reuse
// the opaque (no-cors) cache entry the <img> just created -- an opaque
// response carries no CORS headers, so this fetch then fails CORS even
// though the server's real response has them (verified independently).
// `cache: "reload"` forces a fresh network round-trip, bypassing that
// cached entry entirely. Confirmed via browser devtools: this is the actual
// cause of "delete/duplicate/drag never update the dashboard thumbnail".
const loadForCanvas = async (src: string): Promise<HTMLImageElement> => {
  const response = await fetch(src, { mode: "cors", cache: "reload" });
  if (!response.ok) {
    throw new Error(`Failed to fetch ${src}: ${response.status}`);
  }
  const blob = await response.blob();
  const objectUrl = URL.createObjectURL(blob);
  try {
    return await new Promise<HTMLImageElement>((resolve, reject) => {
      const img = new Image();
      img.onload = () => resolve(img);
      img.onerror = () => reject(new Error(`Failed to decode ${src}`));
      img.src = objectUrl;
    });
  } finally {
    // Safe once the Image has decoded -- drawImage below reads the already
    // rasterized bitmap, not the URL.
    URL.revokeObjectURL(objectUrl);
  }
};

/**
 * Returns base64 JPEG (no data: prefix, matching the API's `*_b64` fields), or
 * null when the canvas can't be read — a missing thumbnail is never worth
 * interrupting an edit for. Failures are logged (not thrown) so a silently
 * broken preview pipeline is at least visible in devtools.
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
      const offsetX = layer.offset.x * scale;
      const offsetY = layer.offset.y * scale;
      const displayScale = layer.displayScale ?? 1;

      if (displayScale !== 1 && layer.bounds) {
        const centerX = ((layer.bounds.left + layer.bounds.right) / 2) * scale;
        const centerY = ((layer.bounds.top + layer.bounds.bottom) / 2) * scale;
        ctx.save();
        ctx.translate(offsetX + centerX, offsetY + centerY);
        ctx.scale(displayScale, displayScale);
        ctx.translate(-centerX, -centerY);
        ctx.drawImage(image, offsetX, offsetY, canvas.width, canvas.height);
        ctx.restore();
      } else {
        ctx.drawImage(image, offsetX, offsetY, canvas.width, canvas.height);
      }
    }

    return canvas.toDataURL("image/jpeg", PREVIEW_QUALITY).split(",")[1] ?? null;
  } catch (err) {
    console.warn("composeSessionPreview failed; dashboard thumbnail not updated.", err);
    return null;
  }
}
