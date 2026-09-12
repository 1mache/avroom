import { useCallback, useMemo, useState } from "react";

export interface SmartPasteSettings {
  /** Master switch: drag-end runs the smart-paste pass at all. */
  enabled: boolean;
  /** Rescale the object from the depth map at the drop point. */
  scaleByPov: boolean;
  /** Re-orient the object from the surface normal at the drop point. */
  smartRotate: boolean;
  /** Queue 3D generation after each cutout. */
  autoGenerate3d: boolean;
  toggleEnabled: () => void;
  toggleScaleByPov: () => void;
  toggleSmartRotate: () => void;
  toggleAutoGenerate3d: () => void;
}

interface Options {
  /**
   * Called when smart paste is switched on. Smart paste needs the session's
   * depth and normal maps, so arming it is the cue to start warming them
   * rather than paying for it on the first drop.
   */
  onEnabled: () => void;
}

/**
 * The four independent switches behind the toolbar's smart-paste control.
 *
 * Grouped into one hook so the toolbar takes a single `smartPaste` prop
 * instead of eight flat ones, and so the defaults live in one place: paste
 * and 3D generation are off, the two placement refinements are on, matching
 * "smart paste does the smart thing once you ask for it".
 */
export function useSmartPasteSettings({ onEnabled }: Options): SmartPasteSettings {
  const [enabled, setEnabled] = useState(false);
  const [scaleByPov, setScaleByPov] = useState(true);
  const [smartRotate, setSmartRotate] = useState(true);
  const [autoGenerate3d, setAutoGenerate3d] = useState(false);

  const toggleEnabled = useCallback(() => {
    setEnabled((on) => {
      const next = !on;
      if (next) {
        onEnabled();
      }
      return next;
    });
  }, [onEnabled]);

  const toggleScaleByPov = useCallback(() => setScaleByPov((on) => !on), []);
  const toggleSmartRotate = useCallback(() => setSmartRotate((on) => !on), []);
  const toggleAutoGenerate3d = useCallback(() => setAutoGenerate3d((on) => !on), []);

  // Memoised so the object can be passed straight to a prop without making
  // every consumer re-render on unrelated state changes in the screen.
  return useMemo(
    () => ({
      enabled,
      scaleByPov,
      smartRotate,
      autoGenerate3d,
      toggleEnabled,
      toggleScaleByPov,
      toggleSmartRotate,
      toggleAutoGenerate3d,
    }),
    [
      enabled,
      scaleByPov,
      smartRotate,
      autoGenerate3d,
      toggleEnabled,
      toggleScaleByPov,
      toggleSmartRotate,
      toggleAutoGenerate3d,
    ],
  );
}
