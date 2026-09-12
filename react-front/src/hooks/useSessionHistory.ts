import { useCallback, useEffect, useState } from "react";
import type { RefObject } from "react";

import { getUidCacheStatus, redoSessionBackground, undoSessionBackground } from "../api/images";

export interface HistoryFlags {
  canUndo: boolean;
  canRedo: boolean;
}

interface UseSessionHistoryOptions {
  uid: string;
  /**
   * Live "a job is still in flight" flag.
   *
   * A ref rather than a plain boolean on purpose: it is read at click and
   * keypress time, so the window-level shortcut listener does not have to be
   * torn down and rebound every time a job changes state.
   */
  blockedRef: RefObject<boolean>;
  /**
   * Called after a step lands, to let the screen re-warm maps, re-capture the
   * dashboard thumbnail and refresh sync bookkeeping.
   *
   * Must be a stable function. The screen's own `handleMutated` calls back
   * into `refresh` below, so the two are mutually recursive and the caller
   * breaks the cycle by passing a ref-indirection here.
   */
  onStepComplete: () => void;
  onError: (message: string) => void;
}

/**
 * Room history: whether backtrack/forward are available, and taking a step.
 *
 * Owns the undo/redo availability flags, the in-flight guard, and the
 * Ctrl+Z / Ctrl+Shift+Z / Ctrl+Y shortcuts. Kept out of WorkspaceScreen
 * because none of it touches tools, objects or the stage -- it only needs a
 * session id and a way to say "something changed".
 */
export function useSessionHistory({
  uid,
  blockedRef,
  onStepComplete,
  onError,
}: UseSessionHistoryOptions) {
  const [canUndo, setCanUndo] = useState(false);
  const [canRedo, setCanRedo] = useState(false);
  const [busy, setBusy] = useState(false);

  /** Apply flags the caller already has in hand (a sync-check response). */
  const applyFlags = useCallback((flags: HistoryFlags) => {
    setCanUndo(flags.canUndo);
    setCanRedo(flags.canRedo);
  }, []);

  /** Re-read the flags from the server. */
  const refresh = useCallback(async () => {
    try {
      const status = await getUidCacheStatus(uid);
      setCanUndo(status.can_undo);
      setCanRedo(status.can_redo);
    } catch {
      // Non-fatal — toolbar buttons stay at their last known state.
    }
  }, [uid]);

  const runStep = useCallback(
    async (direction: "undo" | "redo") => {
      if (busy || blockedRef.current) {
        return;
      }
      setBusy(true);
      try {
        if (direction === "undo") {
          await undoSessionBackground(uid);
        } else {
          await redoSessionBackground(uid);
        }
        onStepComplete();
      } catch (stepError) {
        const fallback = `Failed to ${direction} room history.`;
        onError(stepError instanceof Error ? stepError.message || fallback : fallback);
      } finally {
        setBusy(false);
      }
    },
    [blockedRef, busy, onError, onStepComplete, uid],
  );

  const backtrack = useCallback(() => void runStep("undo"), [runStep]);
  const forward = useCallback(() => void runStep("redo"), [runStep]);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA")) {
        return;
      }
      if (!(event.ctrlKey || event.metaKey)) {
        return;
      }

      const blocked = busy || blockedRef.current;
      const wantsRedo =
        event.key === "y" || event.key === "Y" || (event.shiftKey && (event.key === "z" || event.key === "Z"));
      const wantsUndo = !event.shiftKey && (event.key === "z" || event.key === "Z");

      if (wantsRedo && canRedo && !blocked) {
        event.preventDefault();
        void runStep("redo");
      } else if (wantsUndo && canUndo && !blocked) {
        event.preventDefault();
        void runStep("undo");
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [blockedRef, busy, canRedo, canUndo, runStep]);

  return { canUndo, canRedo, busy, applyFlags, refresh, backtrack, forward };
}
