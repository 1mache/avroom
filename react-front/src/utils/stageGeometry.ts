// Pure geometry helpers for the workspace stage. The photo is drawn with
// `object-fit: contain`, so almost every interaction (drag, hit-test, 3D frame
// placement) has to convert between three spaces: natural-image pixels, the
// rendered (letterboxed) rect, and stage-local CSS pixels.
import type { ClickPosition, CutoutAlphaBounds } from "../types/session";

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

/**
 * Keeps a dragged object's opaque pixels inside the photo. Offsets live in
 * natural-image pixels and are clamped against the object's visible bounds, so
 * transparent padding may leave the frame while the object itself cannot.
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

  const minX = -effectiveBounds.left;
  const maxX = imageSize.width - effectiveBounds.right;
  const minY = -effectiveBounds.top;
  const maxY = imageSize.height - effectiveBounds.bottom;

  return {
    x: Math.min(Math.max(offset.x, minX), maxX),
    y: Math.min(Math.max(offset.y, minY), maxY),
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

/** Minimum alpha (0-255) that counts as a hit rather than transparent padding. */
export const ALPHA_HIT_THRESHOLD = 10;

// Objects render back-to-front in array order (later = on top), so hit-testing
// must walk topmost-first. The selected object is always drawn above the rest,
// so it is tested first regardless of its position in the array.
export const buildHitTestOrder = <T extends { objectId: number; hidden: boolean }>(
  objects: T[],
  selectedObjectId: number | null,
): T[] => {
  const visible = objects.filter((o) => !o.hidden);
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
