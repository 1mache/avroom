import { useEffect, useRef } from "react";
import type { Dispatch, RefObject, SetStateAction } from "react";

import type { ClickPosition } from "../types/session";
import { isLassoLargeEnough } from "../utils/lassoMask";
import { toNaturalPoint, type Rect, type Size } from "../utils/stageGeometry";

export interface LassoDraft {
  points: ClickPosition[];
}

interface UseLassoSelectOptions {
  lassoDraft: LassoDraft | null;
  setLassoDraft: Dispatch<SetStateAction<LassoDraft | null>>;
  naturalSize: Size | null;
  renderedRect: Rect | null;
  stageRef: RefObject<HTMLElement | null>;
  /** Called once on pointer-up when the lasso is large enough. */
  onLassoComplete: (polygon: ClickPosition[], shiftKey: boolean) => void;
}

/**
 * Freehand lasso while `lassoDraft` is set: tracks the pointer to grow the
 * polygon, then on release validates size and forwards the closed loop.
 */
export function useLassoSelect({
  lassoDraft,
  setLassoDraft,
  naturalSize,
  renderedRect,
  stageRef,
  onLassoComplete,
}: UseLassoSelectOptions) {
  const lassoDraftRef = useRef(lassoDraft);
  lassoDraftRef.current = lassoDraft;

  useEffect(() => {
    if (!lassoDraft || !naturalSize || !renderedRect) {
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
      setLassoDraft((prev) => {
        if (!prev) {
          return prev;
        }
        const last = prev.points[prev.points.length - 1];
        const dx = natural.x - last.x;
        const dy = natural.y - last.y;
        if (dx * dx + dy * dy < 4) {
          return prev;
        }
        return { points: [...prev.points, natural] };
      });
    };

    const handleUp = (event: PointerEvent) => {
      const draft = lassoDraftRef.current;
      setLassoDraft(null);
      if (!draft || !isLassoLargeEnough(draft.points)) {
        return;
      }
      onLassoComplete(draft.points, event.shiftKey);
    };

    window.addEventListener("pointermove", handleMove);
    window.addEventListener("pointerup", handleUp);
    return () => {
      window.removeEventListener("pointermove", handleMove);
      window.removeEventListener("pointerup", handleUp);
    };
  }, [
    lassoDraft,
    naturalSize,
    renderedRect,
    stageRef,
    onLassoComplete,
    setLassoDraft,
  ]);
}
