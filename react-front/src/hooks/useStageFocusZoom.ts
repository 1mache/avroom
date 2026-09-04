import { useCallback, useEffect, useRef, useState } from "react";
import type { PointerEvent as ReactPointerEvent, RefObject } from "react";

import type { ClickPosition } from "../types/session";
import {
  STAGE_FOCUS_ZOOM,
  clampStageFocusZoom,
  type Rect,
} from "../utils/stageGeometry";

/** Delay before zoom engages so Ctrl+Z / Ctrl+Y does not flash the stage. */
const ZOOM_ARM_MS = 120;

/** Multiplicative scroll sensitivity (deltaY in CSS pixels). */
const WHEEL_ZOOM_SENSITIVITY = 0.0018;

export interface StageFocusZoomState {
  active: boolean;
  origin: ClickPosition;
  scale: number;
}

interface UseStageFocusZoomOptions {
  stageRef: RefObject<HTMLElement | null>;
  renderedRect: Rect | null;
  /** When true, Control never arms zoom (rotate picker, drag, resize, …). */
  blocked: boolean;
}

/**
 * Hold Control: after a short delay, scale the stage around the pointer's
 * frozen origin. Scroll while holding Control adjusts the magnification.
 * Release Control (or blur / leave the photo) to unzoom. Control only — Cmd
 * stays free for undo shortcuts.
 */
export function useStageFocusZoom({
  stageRef,
  renderedRect,
  blocked,
}: UseStageFocusZoomOptions): StageFocusZoomState & {
  onStagePointerMove: (event: ReactPointerEvent) => void;
  onStagePointerLeave: () => void;
} {
  const [active, setActive] = useState(false);
  const [origin, setOrigin] = useState<ClickPosition>({ x: 0, y: 0 });
  // Remembers the last chosen magnification across Control holds.
  const [focusScale, setFocusScale] = useState(STAGE_FOCUS_ZOOM);

  const lastPointerRef = useRef<ClickPosition | null>(null);
  const pointerOverPhotoRef = useRef(false);
  const armTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const controlHeldRef = useRef(false);
  const blockedRef = useRef(blocked);
  blockedRef.current = blocked;
  const renderedRectRef = useRef(renderedRect);
  renderedRectRef.current = renderedRect;
  const activeRef = useRef(active);
  activeRef.current = active;
  const focusScaleRef = useRef(focusScale);
  focusScaleRef.current = focusScale;

  const clearArmTimer = useCallback(() => {
    if (armTimerRef.current !== null) {
      clearTimeout(armTimerRef.current);
      armTimerRef.current = null;
    }
  }, []);

  const deactivate = useCallback(() => {
    clearArmTimer();
    controlHeldRef.current = false;
    if (activeRef.current) {
      setActive(false);
    }
  }, [clearArmTimer]);

  const activateAtPointer = useCallback(() => {
    const pointer = lastPointerRef.current;
    if (!pointer || blockedRef.current || !pointerOverPhotoRef.current) {
      return false;
    }
    setOrigin(pointer);
    setActive(true);
    return true;
  }, []);

  const tryArmZoom = useCallback(() => {
    clearArmTimer();
    if (blockedRef.current || !pointerOverPhotoRef.current) {
      return;
    }
    if (!lastPointerRef.current) {
      return;
    }
    armTimerRef.current = setTimeout(() => {
      armTimerRef.current = null;
      if (
        !controlHeldRef.current ||
        blockedRef.current ||
        !pointerOverPhotoRef.current ||
        !lastPointerRef.current
      ) {
        return;
      }
      setOrigin(lastPointerRef.current);
      setActive(true);
    }, ZOOM_ARM_MS);
  }, [clearArmTimer]);

  const onStagePointerMove = useCallback(
    (event: ReactPointerEvent) => {
      const stage = stageRef.current;
      const rect = renderedRectRef.current;
      if (!stage || !rect) {
        pointerOverPhotoRef.current = false;
        return;
      }
      const stageRect = stage.getBoundingClientRect();
      const localX = event.clientX - stageRect.left;
      const localY = event.clientY - stageRect.top;
      const inside =
        localX >= rect.x &&
        localY >= rect.y &&
        localX <= rect.x + rect.width &&
        localY <= rect.y + rect.height;
      pointerOverPhotoRef.current = inside;
      if (!inside) {
        if (activeRef.current) {
          setActive(false);
        }
        clearArmTimer();
        return;
      }
      lastPointerRef.current = { x: localX, y: localY };
      if (controlHeldRef.current && !activeRef.current && !blockedRef.current) {
        tryArmZoom();
      }
    },
    [stageRef, clearArmTimer, tryArmZoom],
  );

  const onStagePointerLeave = useCallback(() => {
    pointerOverPhotoRef.current = false;
    if (activeRef.current) {
      setActive(false);
    }
    clearArmTimer();
  }, [clearArmTimer]);

  // Native wheel listener (passive: false) so Ctrl+wheel can preventDefault
  // and adjust magnification instead of zooming the browser page.
  useEffect(() => {
    const stage = stageRef.current;
    if (!stage) {
      return;
    }

    const handleWheel = (event: WheelEvent) => {
      if (!controlHeldRef.current || blockedRef.current || !pointerOverPhotoRef.current) {
        return;
      }
      event.preventDefault();
      clearArmTimer();

      const next = clampStageFocusZoom(
        focusScaleRef.current * Math.exp(-event.deltaY * WHEEL_ZOOM_SENSITIVITY),
      );
      setFocusScale(next);

      if (!activeRef.current) {
        activateAtPointer();
      }
    };

    stage.addEventListener("wheel", handleWheel, { passive: false });
    return () => {
      stage.removeEventListener("wheel", handleWheel);
    };
  }, [stageRef, clearArmTimer, activateAtPointer]);

  useEffect(() => {
    if (blocked && activeRef.current) {
      deactivate();
    }
  }, [blocked, deactivate]);

  useEffect(() => {
    const isTextField = (target: EventTarget | null): boolean => {
      if (!(target instanceof HTMLElement)) {
        return false;
      }
      const tag = target.tagName;
      return tag === "INPUT" || tag === "TEXTAREA" || target.isContentEditable;
    };

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Control" || event.repeat) {
        // Any other key while arming (Ctrl+Z, etc.) cancels the pending zoom.
        if (event.key !== "Control") {
          clearArmTimer();
          if (activeRef.current) {
            setActive(false);
          }
        }
        return;
      }
      if (isTextField(event.target) || blockedRef.current) {
        return;
      }
      controlHeldRef.current = true;
      tryArmZoom();
    };

    const handleKeyUp = (event: KeyboardEvent) => {
      if (event.key !== "Control") {
        return;
      }
      deactivate();
    };

    const handleBlur = () => {
      deactivate();
    };

    const handleContextMenu = (event: MouseEvent) => {
      // Mac: Control+click opens the context menu; suppress while focusing so
      // the click can still place a segmentation seed.
      if (controlHeldRef.current || activeRef.current) {
        event.preventDefault();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    window.addEventListener("keyup", handleKeyUp);
    window.addEventListener("blur", handleBlur);
    window.addEventListener("contextmenu", handleContextMenu);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
      window.removeEventListener("keyup", handleKeyUp);
      window.removeEventListener("blur", handleBlur);
      window.removeEventListener("contextmenu", handleContextMenu);
      clearArmTimer();
    };
  }, [clearArmTimer, deactivate, tryArmZoom]);

  return {
    active,
    origin,
    scale: active ? focusScale : 1,
    onStagePointerMove,
    onStagePointerLeave,
  };
}
