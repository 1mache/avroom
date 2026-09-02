import { useCallback, useEffect, useRef, useState } from "react";

import { setObjectDisplayScale } from "../api/images";
import { effectiveCutoutBounds, type ClickPosition, type CutoutObject } from "../types/session";
import {
  clampDisplayScale,
  getObjectScaleCenter,
  scaleFromHandleDrag,
  type ResizeHandle,
} from "../utils/stageGeometry";

interface ResizeState {
  objectId: number;
  handle: ResizeHandle;
  pointerId: number;
  startScale: number;
  startPointer: ClickPosition;
  center: ClickPosition;
}

interface UseObjectResizeOptions {
  objects: CutoutObject[];
  showOriginalIds: ReadonlySet<number>;
  clientToNatural: (clientX: number, clientY: number) => ClickPosition | null;
  naturalSize: { width: number; height: number } | null;
  updateDisplayScale: (objectId: number, scale: number) => void;
  onError: (error: unknown) => void;
  onSettled: () => void;
}

/**
 * Drag selection handles to resize a cutout uniformly via displayScale.
 * Live preview updates local state; pointer-up persists to the server.
 */
export function useObjectResize({
  objects,
  showOriginalIds,
  clientToNatural,
  naturalSize,
  updateDisplayScale,
  onError,
  onSettled,
}: UseObjectResizeOptions) {
  const resizeStateRef = useRef<ResizeState | null>(null);
  const [isResizing, setIsResizing] = useState(false);

  const objectsRef = useRef(objects);
  objectsRef.current = objects;
  const showOriginalIdsRef = useRef(showOriginalIds);
  showOriginalIdsRef.current = showOriginalIds;
  const clientToNaturalRef = useRef(clientToNatural);
  clientToNaturalRef.current = clientToNatural;
  const naturalSizeRef = useRef(naturalSize);
  naturalSizeRef.current = naturalSize;
  const updateDisplayScaleRef = useRef(updateDisplayScale);
  updateDisplayScaleRef.current = updateDisplayScale;
  const onErrorRef = useRef(onError);
  onErrorRef.current = onError;
  const onSettledRef = useRef(onSettled);
  onSettledRef.current = onSettled;

  const beginResize = useCallback(
    (objectId: number, handle: ResizeHandle, pointerId: number, startPointer: ClickPosition) => {
      const target = objectsRef.current.find((o) => o.objectId === objectId);
      const size = naturalSizeRef.current;
      if (!target || !size) {
        return;
      }

      const showOriginal = showOriginalIdsRef.current.has(objectId);
      const baseBounds = effectiveCutoutBounds(target, showOriginal);
      const center = getObjectScaleCenter(baseBounds, target.offset, size);

      document.body.classList.add("is-resizing-object");
      resizeStateRef.current = {
        objectId,
        handle,
        pointerId,
        startScale: target.displayScale,
        startPointer,
        center,
      };
      setIsResizing(true);
    },
    [],
  );

  useEffect(() => {
    if (!isResizing) {
      return;
    }

    const handlePointerMove = (event: PointerEvent) => {
      const resizeState = resizeStateRef.current;
      if (!resizeState || resizeState.pointerId !== event.pointerId) {
        return;
      }

      const currentPointer = clientToNaturalRef.current(event.clientX, event.clientY);
      if (!currentPointer) {
        return;
      }

      const nextScale = clampDisplayScale(
        scaleFromHandleDrag(
          resizeState.handle,
          resizeState.startPointer,
          currentPointer,
          resizeState.center,
          resizeState.startScale,
        ),
      );

      updateDisplayScaleRef.current(resizeState.objectId, nextScale);
    };

    const finishResize = (pointerId: number) => {
      if (resizeStateRef.current?.pointerId !== pointerId) {
        return;
      }

      const resizedObjectId = resizeStateRef.current.objectId;
      resizeStateRef.current = null;
      setIsResizing(false);
      document.body.classList.remove("is-resizing-object");
      onSettledRef.current();

      const resized = objectsRef.current.find((o) => o.objectId === resizedObjectId);
      if (resized?.uuid) {
        void setObjectDisplayScale(resized.uuid, resized.displayScale)
          .catch((err: unknown) => {
            onErrorRef.current(err);
          })
          .finally(() => {
            onSettledRef.current();
          });
      }
    };

    const handlePointerUp = (event: PointerEvent) => finishResize(event.pointerId);

    window.addEventListener("pointermove", handlePointerMove);
    window.addEventListener("pointerup", handlePointerUp);
    window.addEventListener("pointercancel", handlePointerUp);

    return () => {
      window.removeEventListener("pointermove", handlePointerMove);
      window.removeEventListener("pointerup", handlePointerUp);
      window.removeEventListener("pointercancel", handlePointerUp);
      document.body.classList.remove("is-resizing-object");
    };
  }, [isResizing]);

  return { isResizing, beginResize };
}
