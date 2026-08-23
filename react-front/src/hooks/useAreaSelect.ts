import { useEffect } from "react";
import type { Dispatch, RefObject, SetStateAction } from "react";

import type { BatchRequest } from "../types/api";
import type { ClickPosition } from "../types/session";
import { toNaturalPoint, type Rect, type Size } from "../utils/stageGeometry";

export interface AreaDraft {
  start: ClickPosition;
  current: ClickPosition;
}

interface UseAreaSelectOptions {
  areaDraft: AreaDraft | null;
  setAreaDraft: Dispatch<SetStateAction<AreaDraft | null>>;
  setAreaMode: Dispatch<SetStateAction<boolean>>;
  naturalSize: Size | null;
  renderedRect: Rect | null;
  stageRef: RefObject<HTMLElement | null>;
  isBatching: boolean;
  runBatch: (source: BatchRequest["source"]) => void | Promise<void>;
}

/**
 * Drag-a-box batch-select: while `areaDraft` is set, tracks the pointer to
 * grow the box, then on release fires a box-source batch cut (min 8x8px) and
 * disarms area mode.
 */
export function useAreaSelect({
  areaDraft,
  setAreaDraft,
  setAreaMode,
  naturalSize,
  renderedRect,
  stageRef,
  isBatching,
  runBatch,
}: UseAreaSelectOptions) {
  useEffect(() => {
    if (!areaDraft || !naturalSize || !renderedRect) {
      return;
    }
    const handleMove = (event: PointerEvent) => {
      const stage = stageRef.current;
      if (!stage) {
        return;
      }
      const stageRect = stage.getBoundingClientRect();
      const natural = toNaturalPoint(
        event.clientX - stageRect.left,
        event.clientY - stageRect.top,
        renderedRect,
        naturalSize,
      );
      if (!natural) {
        return;
      }
      setAreaDraft((prev) => (prev ? { ...prev, current: natural } : prev));
    };
    const handleUp = () => {
      setAreaDraft((prev) => {
        if (!prev) {
          return null;
        }
        const x0 = Math.round(Math.min(prev.start.x, prev.current.x));
        const y0 = Math.round(Math.min(prev.start.y, prev.current.y));
        const x1 = Math.round(Math.max(prev.start.x, prev.current.x));
        const y1 = Math.round(Math.max(prev.start.y, prev.current.y));
        if (x1 - x0 >= 8 && y1 - y0 >= 8 && !isBatching) {
          void runBatch({ kind: "box", x0, y0, x1, y1 });
        }
        return null;
      });
      setAreaMode(false);
    };
    window.addEventListener("pointermove", handleMove);
    window.addEventListener("pointerup", handleUp);
    return () => {
      window.removeEventListener("pointermove", handleMove);
      window.removeEventListener("pointerup", handleUp);
    };
  }, [areaDraft, naturalSize, renderedRect, stageRef, isBatching, runBatch, setAreaDraft, setAreaMode]);
}
