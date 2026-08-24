import { useCallback, useEffect, useRef } from "react";

import { effectiveCutoutSrc, type CutoutObject } from "../types/session";

interface HitCanvasEntry {
  canvas: HTMLCanvasElement;
  width: number;
  height: number;
  // The src this canvas was built from. Rotation swaps an object's effective
  // src in place without changing its objectId, so the cache must invalidate
  // on src change, not just track which ids exist.
  src: string;
  displayScale: number;
}

/**
 * Alpha-precise hit testing: cutout PNGs are full-image-sized with
 * transparency outside the object, so a topmost DOM overlay would swallow
 * every click. This builds an offscreen canvas per object (rebuilt whenever
 * its effective src or displayScale changes) and samples pixel alpha on
 * demand.
 */
export function useHitTesting(
  objects: CutoutObject[],
  isShowingOriginal: (obj: { objectId: number }) => boolean,
) {
  const hitCanvasesRef = useRef<Map<number, HitCanvasEntry>>(new Map());

  useEffect(() => {
    const currentIds = new Set(objects.map((o) => o.objectId));
    hitCanvasesRef.current.forEach((_entry, id) => {
      if (!currentIds.has(id)) {
        hitCanvasesRef.current.delete(id);
      }
    });

    objects.forEach((obj) => {
      const src = effectiveCutoutSrc(obj, isShowingOriginal(obj));
      const existing = hitCanvasesRef.current.get(obj.objectId);
      if (existing && existing.src === src && existing.displayScale === obj.displayScale) {
        return;
      }

      const img = new Image();
      img.onload = () => {
        const canvas = document.createElement("canvas");
        canvas.width = img.naturalWidth;
        canvas.height = img.naturalHeight;
        const ctx = canvas.getContext("2d", { willReadFrequently: true });
        if (!ctx) {
          return;
        }
        ctx.drawImage(img, 0, 0);
        hitCanvasesRef.current.set(obj.objectId, {
          canvas,
          width: img.naturalWidth,
          height: img.naturalHeight,
          src,
          displayScale: obj.displayScale,
        });
      };
      img.src = src;
    });
  }, [objects, isShowingOriginal]);

  const sampleObjectAlpha = useCallback((objectId: number, localX: number, localY: number): number => {
    const entry = hitCanvasesRef.current.get(objectId);
    if (!entry) {
      // Canvas not built yet (object just created). Treat as opaque so the
      // object stays clickable immediately; the bounds check upstream
      // already filtered out obviously-empty space.
      return 255;
    }

    if (localX < 0 || localY < 0 || localX >= entry.width || localY >= entry.height) {
      return 0;
    }

    const ctx = entry.canvas.getContext("2d", { willReadFrequently: true });
    if (!ctx) {
      return 255;
    }

    return ctx.getImageData(Math.floor(localX), Math.floor(localY), 1, 1).data[3];
  }, []);

  return { sampleObjectAlpha };
}
