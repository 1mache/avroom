// Pure geometry helpers for the workspace stage. The photo is drawn with
// `object-fit: contain`, so almost every interaction (drag, hit-test, 3D frame
// placement) has to convert between three spaces: natural-image pixels, the
// rendered (letterboxed) rect, and stage-local CSS pixels.
import type { ClickPosition, CutoutAlphaBounds } from "../types/session";
import { isDrawnOnStage } from "../types/session";

export interface Size {
  width: number;
  height: number;
}

export interface Rect {
  x: number;
  y: number;
  width: number;
  height: number;
}

/** Where the contained image is actually painted inside its container box. */
export const getContainedImageRect = (
  containerSize: Size,
  imageSize: Size,
): Rect | null => {
  if (
    containerSize.width <= 0 ||
    containerSize.height <= 0 ||
    imageSize.width <= 0 ||
    imageSize.height <= 0
  ) {
    return null;
  }

  const containerRatio = containerSize.width / containerSize.height;
  const imageRatio = imageSize.width / imageSize.height;

  if (imageRatio > containerRatio) {
    const width = containerSize.width;
    const height = width / imageRatio;
    return { x: 0, y: (containerSize.height - height) / 2, width, height };
  }

  const height = containerSize.height;
  const width = height * imageRatio;
  return { x: (containerSize.width - width) / 2, y: 0, width, height };
};

export const loadImageElement = (src: string): Promise<HTMLImageElement> =>
  new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error("Failed to load image"));
    img.src = src;
  });

// The 3D viewer's WebGL canvas is sized to the object's tight on-stage rect in
// CSS pixels (see model3DFrameStyle) -- a much smaller, differently-scaled
// image than a real cutout, which is always a full-canvas PNG in
// natural-image pixels with its content sitting at the object's alpha bounds.
// Pasting the snapshot onto a matching full-canvas transparent frame at those
// same bounds makes the preview behave identically to a real cutout for
// rendering, drag-clamping, and alpha-precise hit-testing -- without this the
// preview renders wildly oversized and can't be dragged or clicked.
export const compositePreviewOntoCanvas = async (
  snapshotDataUrl: string,
  bounds: CutoutAlphaBounds | null,
  canvasSize: Size,
): Promise<string> => {
  const img = await loadImageElement(snapshotDataUrl);
  const canvas = document.createElement("canvas");
  canvas.width = canvasSize.width;
  canvas.height = canvasSize.height;
  const ctx = canvas.getContext("2d");
  if (!ctx) {
    return snapshotDataUrl;
  }

  const target = bounds ?? { left: 0, top: 0, right: canvasSize.width, bottom: canvasSize.height };
  ctx.drawImage(img, target.left, target.top, target.right - target.left, target.bottom - target.top);
  return canvas.toDataURL("image/png");
};

// Grows a rect around its own center. Used to give the 3D viewer canvas margin
// around the object's rect (MODEL_3D_FRAME_PADDING) and, when its snapshot is
// pasted back onto a cutout-sized canvas, to place that snapshot at the exact
// same enlarged region so the object doesn't shift or resize on commit.
export const inflateAroundCenter = <T extends { width: number; height: number }>(
  rect: T & { left: number; top: number },
  factor: number,
) => {
  const width = rect.width * factor;
  const height = rect.height * factor;
  return {
    left: rect.left - (width - rect.width) / 2,
    top: rect.top - (height - rect.height) / 2,
    width,
    height,
  };
};

export const inflateBounds = (bounds: CutoutAlphaBounds, factor: number): CutoutAlphaBounds => {
  const growX = ((bounds.right - bounds.left) * (factor - 1)) / 2;
  const growY = ((bounds.bottom - bounds.top) * (factor - 1)) / 2;
  return {
    ...bounds,
    left: bounds.left - growX,
    right: bounds.right + growX,
    top: bounds.top - growY,
    bottom: bounds.bottom + growY,
  };
};

/** Minimum opaque-bbox overlap with the Origin Photo (natural-image px). */
export const MIN_ON_PHOTO_PX = 8;

const clampAxis = (value: number, min: number, max: number): number => {
  if (min <= max) {
    return Math.min(Math.max(value, min), max);
  }
  // Photo smaller than the required sliver — pin to the only feasible point.
  return (min + max) / 2;
};

/**
 * Clamps a dragged cutout's offset so its alpha bbox keeps at least
 * {@link MIN_ON_PHOTO_PX} of overlap with the Origin Photo. The rest may hang
 * off the photo edge (clipped in the UI). Offsets are natural-image pixels.
 */
export const clampCutoutOffset = (
  offset: ClickPosition,
  alphaBounds: CutoutAlphaBounds | null,
  imageSize: Size | null,
): ClickPosition => {
  if (!imageSize || imageSize.width <= 0 || imageSize.height <= 0) {
    return { x: 0, y: 0 };
  }

  const effectiveBounds = alphaBounds ?? {
    left: 0,
    top: 0,
    right: imageSize.width,
    bottom: imageSize.height,
  };

  // Drag left until the cutout's right edge sits MIN_ON_PHOTO_PX inside the photo;
  // drag right until the left edge does the same on the opposite side.
  const minX = MIN_ON_PHOTO_PX - effectiveBounds.right;
  const maxX = imageSize.width - MIN_ON_PHOTO_PX - effectiveBounds.left;
  const minY = MIN_ON_PHOTO_PX - effectiveBounds.bottom;
  const maxY = imageSize.height - MIN_ON_PHOTO_PX - effectiveBounds.top;

  return {
    x: clampAxis(offset.x, minX, maxX),
    y: clampAxis(offset.y, minY, maxY),
  };
};

/** Center of the visible alpha bbox after drag offset — depth sample for smart paste. */
export const getObjectPlacementCenter = (
  bounds: CutoutAlphaBounds | null,
  offset: ClickPosition,
  imageSize: Size,
): ClickPosition => {
  const effectiveBounds = bounds ?? {
    left: 0,
    top: 0,
    right: imageSize.width,
    bottom: imageSize.height,
    naturalWidth: imageSize.width,
    naturalHeight: imageSize.height,
  };

  return {
    x: Math.round((effectiveBounds.left + effectiveBounds.right) / 2 + offset.x),
    y: Math.round((effectiveBounds.top + effectiveBounds.bottom) / 2 + offset.y),
  };
};

// Maps an object's alpha bounds (+ its drag offset) from natural-image pixels
// into on-stage CSS pixels, using the same contained-rect scale as the
// background/cutout images. Falls back to the full rendered rect when bounds
// are unknown (e.g. legacy session data).
export const getBoundsStageRect = (
  bounds: CutoutAlphaBounds | null,
  offset: ClickPosition,
  renderedRect: Rect,
  naturalSize: Size,
): { left: number; top: number; width: number; height: number } => {
  if (!bounds) {
    return {
      left: renderedRect.x,
      top: renderedRect.y,
      width: renderedRect.width,
      height: renderedRect.height,
    };
  }

  const scaleX = renderedRect.width / naturalSize.width;
  const scaleY = renderedRect.height / naturalSize.height;

  return {
    left: renderedRect.x + (bounds.left + offset.x) * scaleX,
    top: renderedRect.y + (bounds.top + offset.y) * scaleY,
    width: (bounds.right - bounds.left) * scaleX,
    height: (bounds.bottom - bounds.top) * scaleY,
  };
};

/** Map a point on a scaled object back into base cutout coordinates for alpha sampling. */
export const mapPointThroughInverseScale = (
  point: ClickPosition,
  bounds: CutoutAlphaBounds,
  displayScale: number,
): ClickPosition => {
  if (displayScale === 1) {
    return point;
  }
  const centerX = (bounds.left + bounds.right) / 2;
  const centerY = (bounds.top + bounds.bottom) / 2;
  return {
    x: centerX + (point.x - centerX) / displayScale,
    y: centerY + (point.y - centerY) / displayScale,
  };
};

export type ResizeHandle = "tl" | "tr" | "bl" | "br" | "t" | "r" | "b" | "l";

export const MIN_DISPLAY_SCALE = 0.05;
export const MAX_DISPLAY_SCALE = 8.0;

export const clampDisplayScale = (scale: number): number =>
  Math.min(MAX_DISPLAY_SCALE, Math.max(MIN_DISPLAY_SCALE, scale));

/** Natural-image center of an object's alpha bbox (CSS scale origin). */
export const getObjectScaleCenter = (
  bounds: CutoutAlphaBounds | null,
  offset: ClickPosition,
  imageSize: Size,
): ClickPosition => {
  const effectiveBounds = bounds ?? {
    left: 0,
    top: 0,
    right: imageSize.width,
    bottom: imageSize.height,
    naturalWidth: imageSize.width,
    naturalHeight: imageSize.height,
  };

  return {
    x: offset.x + (effectiveBounds.left + effectiveBounds.right) / 2,
    y: offset.y + (effectiveBounds.top + effectiveBounds.bottom) / 2,
  };
};

/** Uniform scale factor from a handle drag relative to *center*. */
export const scaleFromHandleDrag = (
  handle: ResizeHandle,
  startPointer: ClickPosition,
  currentPointer: ClickPosition,
  center: ClickPosition,
  startScale: number,
): number => {
  const isCorner = handle === "tl" || handle === "tr" || handle === "bl" || handle === "br";

  if (isCorner) {
    const startDist = Math.hypot(startPointer.x - center.x, startPointer.y - center.y);
    const currentDist = Math.hypot(currentPointer.x - center.x, currentPointer.y - center.y);
    if (startDist <= 0) {
      return startScale;
    }
    return startScale * (currentDist / startDist);
  }

  const isHorizontal = handle === "l" || handle === "r";
  const startExtent = isHorizontal
    ? Math.abs(startPointer.x - center.x)
    : Math.abs(startPointer.y - center.y);
  const currentExtent = isHorizontal
    ? Math.abs(currentPointer.x - center.x)
    : Math.abs(currentPointer.y - center.y);
  if (startExtent <= 0) {
    return startScale;
  }
  return startScale * (currentExtent / startExtent);
};

/** Minimum alpha (0-255) that counts as a hit rather than transparent padding. */
export const ALPHA_HIT_THRESHOLD = 10;

// Objects render back-to-front in array order (later = on top), so hit-testing
// must walk topmost-first. The selected object is always drawn above the rest,
// so it is tested first regardless of its position in the array.
export const buildHitTestOrder = <
  T extends { objectId: number; hidden: boolean; beyondStage: boolean; revealed: boolean },
>(
  objects: T[],
  selectedObjectId: number | null,
): T[] => {
  const visible = objects.filter(isDrawnOnStage);
  const topmostFirst = [...visible].reverse();

  if (selectedObjectId === null) {
    return topmostFirst;
  }

  const selectedIndex = topmostFirst.findIndex((o) => o.objectId === selectedObjectId);
  if (selectedIndex <= 0) {
    return topmostFirst;
  }

  const [selected] = topmostFirst.splice(selectedIndex, 1);
  return [selected, ...topmostFirst];
};

/** Default hold-Control magnification on the stage (CSS scale). */
export const STAGE_FOCUS_ZOOM = 2.5;
/** Scroll-wheel floor / ceiling while focus-zoom is armed. */
export const STAGE_FOCUS_ZOOM_MIN = 1.25;
export const STAGE_FOCUS_ZOOM_MAX = 6;

export const clampStageFocusZoom = (scale: number): number =>
  Math.min(STAGE_FOCUS_ZOOM_MAX, Math.max(STAGE_FOCUS_ZOOM_MIN, scale));

/**
 * Maps a stage-local pointer through an active CSS zoom back to unzoomed
 * stage-local coordinates. Origin is the frozen transform-origin; scale is
 * the CSS scale factor (1 = identity).
 */
export const unzoomStagePoint = (
  local: ClickPosition,
  origin: ClickPosition,
  scale: number,
): ClickPosition => {
  if (scale === 1) {
    return local;
  }
  return {
    x: origin.x + (local.x - origin.x) / scale,
    y: origin.y + (local.y - origin.y) / scale,
  };
};

/**
 * Converts a pointer event on the stage into natural-image coordinates, or
 * null when the pointer is on the letterbox rather than the photo.
 */
export const toNaturalPoint = (
  localX: number,
  localY: number,
  renderedRect: Rect,
  naturalSize: Size,
): ClickPosition | null => {
  const insideX = localX - renderedRect.x;
  const insideY = localY - renderedRect.y;
  if (
    insideX < 0 ||
    insideY < 0 ||
    insideX > renderedRect.width ||
    insideY > renderedRect.height
  ) {
    return null;
  }

  return {
    x: (insideX / renderedRect.width) * naturalSize.width,
    y: (insideY / renderedRect.height) * naturalSize.height,
  };
};

/** Stage-local CSS box for a natural-pixel batch rectangle. */
export const batchBoxStageStyle = (
  box: { x0: number; y0: number; x1: number; y1: number },
  renderedRect: Rect,
  naturalSize: Size,
): { left: string; top: string; width: string; height: string } => ({
  left: `${renderedRect.x + (box.x0 / naturalSize.width) * renderedRect.width}px`,
  top: `${renderedRect.y + (box.y0 / naturalSize.height) * renderedRect.height}px`,
  width: `${((box.x1 - box.x0) / naturalSize.width) * renderedRect.width}px`,
  height: `${((box.y1 - box.y0) / naturalSize.height) * renderedRect.height}px`,
});
