// Builds composited room images: the inpainted background with every visible
// cutout at its current position — the room exactly as the user left it.
import { authedFetch } from "../api/authToken";
import type { ClickPosition } from "../types/session";
import {
  css3dTransform,
  hasCss3dPose,
  type Css3dPose,
} from "./css3dTransform";
import type { Size } from "./stageGeometry";

/** Long edge of the stored dashboard thumbnail. Cards never render larger than this. */
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
  /** Planar CSS 3D tilt; when set, the layer is drawn with the same transform. */
  cssPose?: Css3dPose | null;
}

// Cutouts are data: URLs, but the background is served from the API on a
// different origin. The stage's own <img src={photoSrc}> (no crossOrigin)
// loads that *exact same, cache-busted* URL moments before this runs --
// useSessionSync appends a fresh `?t=<lastChanged>` right after the mutation
// that also triggers dashboard capture. Chrome's HTTP cache is keyed by URL,
// not by request mode, so a plain 'cors' fetch of that identical URL can reuse
// the opaque (no-cors) cache entry the <img> just created -- an opaque
// response carries no CORS headers, so this fetch then fails CORS even
// though the server's real response has them (verified independently).
// `cache: "reload"` forces a fresh network round-trip, bypassing that
// cached entry entirely. Confirmed via browser devtools: this is the actual
// cause of "delete/duplicate/drag never update the dashboard thumbnail".
const loadForCanvas = async (src: string): Promise<HTMLImageElement> => {
  const response = await authedFetch(src, { mode: "cors", cache: "reload" });
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

const loadDataUrlForCanvas = (src: string): Promise<HTMLImageElement> =>
  new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error("Failed to decode snapshot layer"));
    img.src = src;
  });

const loadLayerImage = (src: string): Promise<HTMLImageElement> =>
  src.startsWith("data:") ? loadDataUrlForCanvas(src) : loadForCanvas(src);

const drawLayer = (
  ctx: CanvasRenderingContext2D,
  image: HTMLImageElement,
  layer: PreviewLayer,
  canvasWidth: number,
  canvasHeight: number,
  scale: number,
): void => {
  const offsetX = layer.offset.x * scale;
  const offsetY = layer.offset.y * scale;
  const displayScale = layer.displayScale ?? 1;
  const pose = layer.cssPose;
  const hasPose = pose != null && hasCss3dPose(pose);

  if ((displayScale !== 1 || hasPose) && layer.bounds) {
    const pivotX = offsetX + ((layer.bounds.left + layer.bounds.right) / 2) * scale;
    const pivotY = offsetY + ((layer.bounds.top + layer.bounds.bottom) / 2) * scale;
    ctx.save();
    ctx.translate(pivotX, pivotY);
    if (hasPose && pose && typeof DOMMatrix !== "undefined") {
      // Canvas 2D can't do true perspective; DOMMatrix flattens the CSS 3D
      // string into an affine approximation that still matches the tilt.
      const matrix = new DOMMatrix(css3dTransform(pose, displayScale));
      ctx.transform(matrix.a, matrix.b, matrix.c, matrix.d, matrix.e, matrix.f);
    } else if (displayScale !== 1) {
      ctx.scale(displayScale, displayScale);
    }
    ctx.translate(-pivotX, -pivotY);
    ctx.drawImage(image, offsetX, offsetY, canvasWidth, canvasHeight);
    ctx.restore();
    return;
  }

  ctx.drawImage(image, offsetX, offsetY, canvasWidth, canvasHeight);
};

async function drawComposedCanvas(
  backgroundSrc: string,
  layers: PreviewLayer[],
  naturalSize: Size,
  outputSize: Size,
): Promise<HTMLCanvasElement | null> {
  const canvas = document.createElement("canvas");
  canvas.width = Math.max(1, outputSize.width);
  canvas.height = Math.max(1, outputSize.height);

  const ctx = canvas.getContext("2d");
  if (!ctx) {
    return null;
  }

  const scale = outputSize.width / naturalSize.width;
  const background = await loadForCanvas(backgroundSrc);
  ctx.drawImage(background, 0, 0, canvas.width, canvas.height);

  // Layers are full-canvas transparent PNGs shifted by their drag offset, so
  // each one is drawn at the same size as the background, just displaced.
  for (const layer of layers) {
    const image = await loadLayerImage(layer.src);
    drawLayer(ctx, image, layer, canvas.width, canvas.height, scale);
  }

  return canvas;
}

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
    const outputSize = {
      width: Math.max(1, Math.round(naturalSize.width * scale)),
      height: Math.max(1, Math.round(naturalSize.height * scale)),
    };
    const canvas = await drawComposedCanvas(backgroundSrc, layers, naturalSize, outputSize);
    if (!canvas) {
      return null;
    }
    return canvas.toDataURL("image/jpeg", PREVIEW_QUALITY).split(",")[1] ?? null;
  } catch (err) {
    console.warn("composeSessionPreview failed; dashboard thumbnail not updated.", err);
    return null;
  }
}

/** Full-resolution PNG of the stage as the user sees it (background + cutouts). */
export async function composeStageSnapshot(
  backgroundSrc: string,
  layers: PreviewLayer[],
  naturalSize: Size,
): Promise<Blob | null> {
  const canvas = await drawComposedCanvas(backgroundSrc, layers, naturalSize, naturalSize);
  if (!canvas) {
    return null;
  }

  return new Promise<Blob | null>((resolve) => {
    canvas.toBlob((blob) => resolve(blob), "image/png");
  });
}

export function triggerBlobDownload(blob: Blob, filename: string): void {
  const objectUrl = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = objectUrl;
  anchor.download = filename;
  anchor.rel = "noopener";
  anchor.style.display = "none";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(objectUrl);
}

export function snapshotDownloadFilename(name: string | null, uid: string): string {
  const base = (name?.trim() || uid).replace(/[<>:"/\\|?*]/g, "_").slice(0, 80);
  return `${base}_snapshot.png`;
}
