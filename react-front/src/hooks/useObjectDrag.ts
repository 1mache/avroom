import { useCallback, useEffect, useRef, useState } from "react";

import { setObjectOffset } from "../api/images";
import { effectiveDisplayBounds, type ClickPosition, type CutoutObject } from "../types/session";
import { clampCutoutOffset, getObjectPlacementCenter, type Rect, type Size } from "../utils/stageGeometry";

interface DragState {
  objectId: number;
  pointerId: number;
  startClientX: number;
  startClientY: number;
  startOffsetX: number;
  startOffsetY: number;
}

interface UseObjectDragOptions {
  objects: CutoutObject[];
  naturalSize: Size | null;
  renderedRect: Rect | null;
  showOriginalIds: ReadonlySet<number>;
  smartPasteEnabled: boolean;
  updateOffset: (objectId: number, offset: ClickPosition) => void;
  runSmartPasteAfterDrag: (objectId: number, x: number, y: number) => Promise<boolean>;
  /** Fired once a drag (or a post-drag smart paste) settles — the dashboard
   * thumbnail capture, since drags never go through useSessionJobs. */
  onSettled: () => void;
}

/**
 * Drag-to-reposition for a selected cutout. Pointer-move updates its offset
 * (clamped, in natural-image pixels, converted from screen-pixel deltas);
 * pointer-up persists the final position server-side and, if smart paste is
 * armed, fires the post-drag smart-paste request.
 */
export function useObjectDrag({
  objects,
  naturalSize,
  renderedRect,
  showOriginalIds,
  smartPasteEnabled,
  updateOffset,
  runSmartPasteAfterDrag,
  onSettled,
}: UseObjectDragOptions) {
  const dragStateRef = useRef<DragState | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [isSmartPasting, setIsSmartPasting] = useState(false);

  // Latest-value refs, kept fresh every render (not just while dragging) so
  // the pointermove/pointerup listeners below — subscribed only for the
  // duration of a drag, see the effect's deps — never read a stale closure.
  const objectsRef = useRef(objects);
  objectsRef.current = objects;
  const naturalSizeRef = useRef(naturalSize);
  naturalSizeRef.current = naturalSize;
  const renderedRectRef = useRef(renderedRect);
  renderedRectRef.current = renderedRect;
  const showOriginalIdsRef = useRef(showOriginalIds);
  showOriginalIdsRef.current = showOriginalIds;
  const smartPasteRef = useRef(smartPasteEnabled);
  smartPasteRef.current = smartPasteEnabled;
  const updateOffsetRef = useRef(updateOffset);
  updateOffsetRef.current = updateOffset;
  const runSmartPasteAfterDragRef = useRef(runSmartPasteAfterDrag);
  runSmartPasteAfterDragRef.current = runSmartPasteAfterDrag;
  const onSettledRef = useRef(onSettled);
  onSettledRef.current = onSettled;

  const beginDrag = useCallback(
    (objectId: number, pointerId: number, clientX: number, clientY: number, offset: ClickPosition) => {
      document.body.classList.add("is-dragging-object");
      dragStateRef.current = {
        objectId,
        pointerId,
        startClientX: clientX,
        startClientY: clientY,
        startOffsetX: offset.x,
        startOffsetY: offset.y,
      };
      setIsDragging(true);
    },
    [],
  );

  useEffect(() => {
    if (!isDragging) {
      return;
    }

    const handlePointerMove = (event: PointerEvent) => {
      const dragState = dragStateRef.current;
      const size = naturalSizeRef.current;
      const rect = renderedRectRef.current;
      if (!dragState || !size || !rect || dragState.pointerId !== event.pointerId) {
        return;
      }

      const scaleX = rect.width / size.width;
      const scaleY = rect.height / size.height;
      if (scaleX <= 0 || scaleY <= 0) {
        return;
      }

      const target = objectsRef.current.find((o) => o.objectId === dragState.objectId);
      const bounds = target
        ? effectiveDisplayBounds(target, showOriginalIdsRef.current.has(target.objectId))
        : null;

      // Mouse delta arrives in screen pixels; convert back to natural-image
      // pixels so drag behavior stays stable under responsive resize.
      const nextOffset = clampCutoutOffset(
        {
          x: dragState.startOffsetX + (event.clientX - dragState.startClientX) / scaleX,
          y: dragState.startOffsetY + (event.clientY - dragState.startClientY) / scaleY,
        },
        bounds,
        size,
      );

      updateOffsetRef.current(dragState.objectId, nextOffset);
    };

    const finishDrag = (pointerId: number) => {
      if (dragStateRef.current?.pointerId !== pointerId) {
        return;
      }
      const draggedObjectId = dragStateRef.current.objectId;
      dragStateRef.current = null;
      setIsDragging(false);
      document.body.classList.remove("is-dragging-object");
      onSettledRef.current();

      const dragged = objectsRef.current.find((o) => o.objectId === draggedObjectId);
      if (dragged?.uuid) {
        // Persist the final position so it survives a session close/reopen.
        void setObjectOffset(dragged.uuid, dragged.offset.x, dragged.offset.y).catch((err: unknown) => {
          console.warn("setObjectOffset failed; position won't survive reload.", err);
        });

        if (smartPasteRef.current) {
          const size = naturalSizeRef.current;
          if (size) {
            const bounds = effectiveDisplayBounds(dragged, showOriginalIdsRef.current.has(dragged.objectId));
            const placement = getObjectPlacementCenter(bounds, dragged.offset, size);
            setIsSmartPasting(true);
            void runSmartPasteAfterDragRef
              .current(draggedObjectId, placement.x, placement.y)
              .then((applied) => {
                if (applied) {
                  onSettledRef.current();
                }
              })
              .finally(() => {
                setIsSmartPasting(false);
              });
          }
        }
      }
    };

    const handlePointerUp = (event: PointerEvent) => finishDrag(event.pointerId);

    window.addEventListener("pointermove", handlePointerMove);
    window.addEventListener("pointerup", handlePointerUp);
    window.addEventListener("pointercancel", handlePointerUp);

    return () => {
      window.removeEventListener("pointermove", handlePointerMove);
      window.removeEventListener("pointerup", handlePointerUp);
      window.removeEventListener("pointercancel", handlePointerUp);
      document.body.classList.remove("is-dragging-object");
    };
    // Only re-subscribes on isDragging: every other input is read through a
    // ref kept fresh above, so a mid-drag object/offset update never tears
    // down and re-adds these listeners.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isDragging]);

  return { isDragging, isSmartPasting, beginDrag };
}
