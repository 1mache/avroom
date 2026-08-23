import { useCallback, useEffect, useRef } from "react";

import { PREVIEW_API_READY, saveSessionPreview } from "../api/images";
import { effectiveCutoutBounds, effectiveCutoutSrc, type CutoutObject } from "../types/session";
import { composeSessionPreview } from "../utils/preview";
import type { Size } from "../utils/stageGeometry";

// How long to wait after the last edit before storing a fresh dashboard
// thumbnail — several mutations often land together (an inpaint plus its sync
// reconcile), and only the settled result is worth compositing.
const PREVIEW_DEBOUNCE_MS = 500;

interface PreviewInputs {
  backgroundSrc: string | null;
  objects: CutoutObject[];
  naturalSize: Size | null;
  showOriginalIds: ReadonlySet<number>;
}

/**
 * Dashboard-card thumbnail capture. Composites background + every visible
 * cutout at its current offset, debounced so a burst of edits only saves the
 * settled result once. Detached and failure-swallowing: a missing thumbnail
 * is never worth interrupting an edit for. No-ops until the preview
 * endpoints exist (PREVIEW_API_READY).
 *
 * Returns a stable `capturePreview` callback (identity only depends on
 * `uid`) so callers defined before this hook runs can still reach it via a
 * ref, same pattern WorkspaceScreen already uses for the circular dependency
 * between useSessionJobs and useSessionSync.
 */
export function useDashboardPreview(uid: string, inputs: PreviewInputs) {
  const inputsRef = useRef(inputs);
  useEffect(() => {
    inputsRef.current = inputs;
  }, [inputs.backgroundSrc, inputs.objects, inputs.naturalSize, inputs.showOriginalIds]);

  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const capturePreview = useCallback(() => {
    if (!PREVIEW_API_READY) {
      return;
    }

    if (timerRef.current) {
      clearTimeout(timerRef.current);
    }

    timerRef.current = setTimeout(async () => {
      const { backgroundSrc, objects, naturalSize: size, showOriginalIds: shown } = inputsRef.current;
      if (!backgroundSrc || !size) {
        return;
      }

      const layers = objects
        .filter((obj) => !obj.hidden)
        .map((obj) => ({
          src: effectiveCutoutSrc(obj, shown.has(obj.objectId)),
          offset: obj.offset,
          displayScale: obj.displayScale,
          bounds: effectiveCutoutBounds(obj, shown.has(obj.objectId)),
        }));

      const composed = await composeSessionPreview(backgroundSrc, layers, size);
      if (composed) {
        await saveSessionPreview(uid, composed).catch((err: unknown) => {
          // Best-effort: the card just keeps its previous thumbnail. Still
          // logged so a broken preview pipeline doesn't fail silently.
          console.warn("saveSessionPreview failed; dashboard thumbnail not updated.", err);
        });
      }
    }, PREVIEW_DEBOUNCE_MS);
  }, [uid]);

  useEffect(() => {
    return () => {
      if (timerRef.current) {
        clearTimeout(timerRef.current);
      }
    };
  }, []);

  return capturePreview;
}
