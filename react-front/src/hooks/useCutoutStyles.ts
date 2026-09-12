import { useCallback } from "react";
import type React from "react";

import { effectiveCutoutBounds } from "../types/session";
import type { CutoutObject } from "../types/session";
import {
  css3dTransform,
  cssPoseOf,
  hasCss3dPose,
  isVolumetricObject,
} from "../utils/css3dTransform";
import type { Rect, Size } from "../utils/stageGeometry";

interface UseCutoutStylesOptions {
  /** Natural pixel size of the Origin Photo, null until it has loaded. */
  naturalSize: Size | null;
  /** Where the contain-fit photo actually renders inside the stage. */
  renderedRect: Rect | null;
  /** Whether this object is currently pinned to its pristine cutout. */
  isShowingOriginal: (obj: CutoutObject) => boolean;
  rotateMode: boolean;
  selectedObjectId: number | null;
}

/**
 * Turns one object's placement metadata into the inline styles the stage
 * renders it with.
 *
 * This is the only place that knows how a cutout's natural-pixel offset,
 * alpha bounds, display scale and CSS-3D pose combine into `left/top/
 * width/height/transform`. It lives apart from WorkspaceScreen because it is
 * pure geometry -- no state of its own, nothing to do with tools, jobs or
 * pointer handling -- and because every one of these four functions has to
 * agree with the others about the planar-vs-flat decision.
 */
export function useCutoutStyles({
  naturalSize,
  renderedRect,
  isShowingOriginal,
  rotateMode,
  selectedObjectId,
}: UseCutoutStylesOptions) {
  /**
   * Whether this object is drawn as a tight CSS-3D plane rather than a
   * full-frame image. Volumetric objects never are (the mesh path owns them),
   * and neither does an object pinned to its original cutout.
   */
  const usesPlanarCss3d = useCallback(
    (obj: CutoutObject): boolean => {
      if (isVolumetricObject(obj.is3d)) {
        return false;
      }
      if (isShowingOriginal(obj)) {
        return false;
      }
      if (rotateMode && obj.objectId === selectedObjectId) {
        return true;
      }
      return hasCss3dPose(cssPoseOf(obj));
    },
    [isShowingOriginal, rotateMode, selectedObjectId],
  );

  const cutoutStyle = useCallback(
    (
      obj: CutoutObject,
      showOriginal: boolean,
      zIndex: number,
    ): React.CSSProperties | undefined => {
      if (!naturalSize || !renderedRect) {
        return undefined;
      }

      const baseBounds = effectiveCutoutBounds(obj, showOriginal);
      const scaleX = renderedRect.width / naturalSize.width;
      const scaleY = renderedRect.height / naturalSize.height;

      // Positions are relative to .stage-cutout-clip (rendered-rect origin),
      // not the stage — do not add renderedRect.x/y.
      if (usesPlanarCss3d(obj) && baseBounds) {
        return {
          left: `${(obj.offset.x + baseBounds.left) * scaleX}px`,
          top: `${(obj.offset.y + baseBounds.top) * scaleY}px`,
          width: `${(baseBounds.right - baseBounds.left) * scaleX}px`,
          height: `${(baseBounds.bottom - baseBounds.top) * scaleY}px`,
          zIndex,
          transform: css3dTransform(cssPoseOf(obj), obj.displayScale),
          transformOrigin: "50% 50%",
          transformStyle: "preserve-3d",
        };
      }

      const transformOrigin =
        baseBounds && naturalSize.width > 0 && naturalSize.height > 0
          ? `${(((baseBounds.left + baseBounds.right) / 2 / naturalSize.width) * 100).toFixed(4)}% ${(((baseBounds.top + baseBounds.bottom) / 2 / naturalSize.height) * 100).toFixed(4)}%`
          : "50% 50%";

      return {
        left: `${obj.offset.x * scaleX}px`,
        top: `${obj.offset.y * scaleY}px`,
        width: `${renderedRect.width}px`,
        height: `${renderedRect.height}px`,
        zIndex,
        transform: obj.displayScale !== 1 ? `scale(${obj.displayScale})` : undefined,
        transformOrigin,
      };
    },
    [naturalSize, renderedRect, usesPlanarCss3d],
  );

  /** Inner img offset when the cutout sits in a tight CSS-3D wrapper. */
  const planarCutoutImgStyle = useCallback(
    (obj: CutoutObject, showOriginal: boolean): React.CSSProperties | undefined => {
      if (!naturalSize || !renderedRect) {
        return undefined;
      }
      const baseBounds = effectiveCutoutBounds(obj, showOriginal);
      if (!baseBounds || !usesPlanarCss3d(obj)) {
        return undefined;
      }
      const scaleX = renderedRect.width / naturalSize.width;
      const scaleY = renderedRect.height / naturalSize.height;
      return {
        position: "absolute",
        left: `${-baseBounds.left * scaleX}px`,
        top: `${-baseBounds.top * scaleY}px`,
        width: `${renderedRect.width}px`,
        height: `${renderedRect.height}px`,
        objectFit: "contain",
        pointerEvents: "none",
      };
    },
    [naturalSize, renderedRect, usesPlanarCss3d],
  );

  return { usesPlanarCss3d, cutoutStyle, planarCutoutImgStyle };
}
