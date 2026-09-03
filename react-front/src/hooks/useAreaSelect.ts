import { useEffect, useRef } from "react";
import type { Dispatch, SetStateAction } from "react";

import type { BatchSource } from "../types/api";
import type { ClickPosition } from "../types/session";

const MIN_BOX_PX = 8;

export function boxBoundsFromDraft(draft: AreaDraft): Extract<BatchSource, { kind: "box" }> {
  return {
    kind: "box",
    x0: Math.round(Math.min(draft.start.x, draft.current.x)),
    y0: Math.round(Math.min(draft.start.y, draft.current.y)),
    x1: Math.round(Math.max(draft.start.x, draft.current.x)),
    y1: Math.round(Math.max(draft.start.y, draft.current.y)),
  };
}

export function boxSourceFromDraft(draft: AreaDraft): BatchSource | null {
  const box = boxBoundsFromDraft(draft);
  if (box.x1 - box.x0 < MIN_BOX_PX || box.y1 - box.y0 < MIN_BOX_PX) {
    return null;
  }
  return box;
}

export interface AreaDraft {
  start: ClickPosition;
  current: ClickPosition;
}

interface UseAreaSelectOptions {
  areaDraft: AreaDraft | null;
  setAreaDraft: Dispatch<SetStateAction<AreaDraft | null>>;
  setAreaMode: Dispatch<SetStateAction<boolean>>;
  /** Client → natural-image (must apply any active stage zoom). */
  clientToNatural: (clientX: number, clientY: number) => ClickPosition | null;
  /** Called once on pointer-up when the box is large enough — does not submit. */
  onBoxReady: (source: BatchSource) => void;
}

/**
 * Drag-a-box batch-select: while `areaDraft` is set, tracks the pointer to
 * grow the box, then on release stages the box source for a later submit (min 8x8px).
 */
export function useAreaSelect({
  areaDraft,
  setAreaDraft,
  setAreaMode,
  clientToNatural,
  onBoxReady,
}: UseAreaSelectOptions) {
  const areaDraftRef = useRef(areaDraft);
  areaDraftRef.current = areaDraft;
  const clientToNaturalRef = useRef(clientToNatural);
  clientToNaturalRef.current = clientToNatural;

  useEffect(() => {
    if (!areaDraft) {
      return;
    }
    const handleMove = (event: PointerEvent) => {
      const natural = clientToNaturalRef.current(event.clientX, event.clientY);
      if (!natural) {
        return;
      }
      setAreaDraft((prev) => (prev ? { ...prev, current: natural } : prev));
    };
    const handleUp = () => {
      const draft = areaDraftRef.current;
      setAreaDraft(null);
      setAreaMode(false);
      if (!draft) {
        return;
      }
      const source = boxSourceFromDraft(draft);
      if (source) {
        onBoxReady(source);
      }
    };
    window.addEventListener("pointermove", handleMove);
    window.addEventListener("pointerup", handleUp);
    return () => {
      window.removeEventListener("pointermove", handleMove);
      window.removeEventListener("pointerup", handleUp);
    };
  }, [areaDraft, onBoxReady, setAreaDraft, setAreaMode]);
}
