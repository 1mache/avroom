import type { ClickPosition } from "../types/session";

const MIN_BOX_PX = 8;

function polygonBounds(polygon: ClickPosition[]): {
  minX: number;
  minY: number;
  maxX: number;
  maxY: number;
} | null {
  if (polygon.length === 0) {
    return null;
  }
  let minX = polygon[0].x;
  let minY = polygon[0].y;
  let maxX = polygon[0].x;
  let maxY = polygon[0].y;
  for (const point of polygon) {
    minX = Math.min(minX, point.x);
    minY = Math.min(minY, point.y);
    maxX = Math.max(maxX, point.x);
    maxY = Math.max(maxY, point.y);
  }
  return { minX, minY, maxX, maxY };
}

/** True when the lasso bounding box meets the minimum drag size. */
export function isLassoLargeEnough(polygon: ClickPosition[]): boolean {
  const bounds = polygonBounds(polygon);
  if (!bounds) {
    return false;
  }
  return (
    bounds.maxX - bounds.minX >= MIN_BOX_PX && bounds.maxY - bounds.minY >= MIN_BOX_PX
  );
}

function fillPolygon(
  ctx: CanvasRenderingContext2D,
  polygon: ClickPosition[],
): void {
  if (polygon.length < 3) {
    return;
  }
  ctx.beginPath();
  ctx.moveTo(polygon[0].x, polygon[0].y);
  for (let index = 1; index < polygon.length; index += 1) {
    ctx.lineTo(polygon[index].x, polygon[index].y);
  }
  ctx.closePath();
  ctx.fill();
}

function canvasToBase64Png(canvas: HTMLCanvasElement): string {
  const dataUrl = canvas.toDataURL("image/png");
  const comma = dataUrl.indexOf(",");
  return comma >= 0 ? dataUrl.slice(comma + 1) : dataUrl;
}

/**
 * Rasterize one or more closed lasso polygons into a full-frame erase mask PNG
 * (white foreground on black). Returns base64 ASCII suitable for POST /images/erase.
 */
export function rasterizeEraseMask(
  width: number,
  height: number,
  regions: ClickPosition[][],
): string | null {
  if (regions.length === 0 || width <= 0 || height <= 0) {
    return null;
  }

  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d");
  if (!ctx) {
    return null;
  }

  ctx.fillStyle = "#000000";
  ctx.fillRect(0, 0, width, height);
  ctx.fillStyle = "#ffffff";

  for (const polygon of regions) {
    if (isLassoLargeEnough(polygon)) {
      fillPolygon(ctx, polygon);
    }
  }

  const pixels = ctx.getImageData(0, 0, width, height).data;
  let hasForeground = false;
  for (let index = 0; index < pixels.length; index += 4) {
    if (pixels[index] > 0) {
      hasForeground = true;
      break;
    }
  }
  if (!hasForeground) {
    return null;
  }

  return canvasToBase64Png(canvas);
}
