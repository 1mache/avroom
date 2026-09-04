import { useEffect, useRef } from "react";
import type { Dispatch, SetStateAction } from "react";

import type { ClickPosition } from "../types/session";
import { isLassoLargeEnough } from "../utils/lassoMask";

export interface LassoDraft {
  points: ClickPosition[];
}

interface UseLassoSelectOptions {
  lassoDraft: LassoDraft | null;
  setLassoDraft: Dispatch<SetStateAction<LassoDraft | null>>;
  /** Client → natural-image (must apply any active stage zoom). */
  clientToNatural: (clientX: number, clientY: number) => ClickPosition | null;
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
  clientToNatural,
  onLassoComplete,
}: UseLassoSelectOptions) {
  const lassoDraftRef = useRef(lassoDraft);
  lassoDraftRef.current = lassoDraft;
  const clientToNaturalRef = useRef(clientToNatural);
  clientToNaturalRef.current = clientToNatural;

  useEffect(() => {
    if (!lassoDraft) {
      return;
    }

    const handleMove = (event: PointerEvent) => {
      const natural = clientToNaturalRef.current(event.clientX, event.clientY);
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
  }, [lassoDraft, onLassoComplete, setLassoDraft]);
}
