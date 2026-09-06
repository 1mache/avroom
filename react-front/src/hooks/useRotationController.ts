import { useCallback, useRef, useState } from "react";
import type { Dispatch, SetStateAction } from "react";

import { fetchCached3DModel, setObjectCssTransform, submitGenerate3D, waitForJobDone } from "../api/images";
import { MODEL_3D_FRAME_PADDING, type Model3DFrameHandle } from "../components/widgets/Model3DFrame";
import type { JobInfo } from "../types/api";
import type { CutoutObject, RotationPose } from "../types/session";
import {
  DEFAULT_CSS_PERSPECTIVE_PX,
  IDENTITY_CSS_POSE,
  isVolumetricObject,
  type Css3dPose,
} from "../utils/css3dTransform";
import { compositePreviewOntoCanvas, inflateBounds, type Size } from "../utils/stageGeometry";

interface UseRotationControllerOptions {
  imageId: string;
  selectedObjectId: number | null;
  selectedObject: CutoutObject | null;
  naturalSize: Size | null;
  jobsList: JobInfo[];
  commitRotation: (objectId: number, pose: RotationPose, previewSrc: string) => void;
  setObjects: Dispatch<SetStateAction<CutoutObject[]>>;
  setSelectedObjectId: Dispatch<SetStateAction<number | null>>;
  /** Clears the "show original" override for one object (rotating again
   * always starts over from the pristine cutout, so a stale override must
   * not linger once a new rotation lands). */
  clearShowOriginal: (objectId: number) => void;
  /** Disarms whichever other stage tool (cutout) is armed before opening the
   * angle picker — mirrors handleCut/handleArea's own resets. */
  disarmOtherTools: () => void;
  onError: (error: unknown) => void;
}

/** Last committed mesh-xyz (X=pitch Y=yaw Z=roll). Volumetric last rotation
 * lives on `rotation.pose`; planar lives on the CSS fields. */
function poseFromObject(obj: CutoutObject | null): Css3dPose {
  if (!obj) {
    return { ...IDENTITY_CSS_POSE };
  }
  const perspectivePx = obj.cssPerspectivePx || DEFAULT_CSS_PERSPECTIVE_PX;
  if (isVolumetricObject(obj.is3d) && obj.rotation?.pose) {
    const pose = obj.rotation.pose;
    return {
      rotateXDeg: pose.relativeElevationDeg,
      rotateYDeg: pose.azimuthDeg,
      rotateZDeg: pose.rollDeg ?? 0,
      perspectivePx,
    };
  }
  return {
    rotateXDeg: obj.cssRotateXDeg,
    rotateYDeg: obj.cssRotateYDeg,
    rotateZDeg: obj.cssRotateZDeg,
    perspectivePx,
  };
}

/**
 * Owns the angle-picker lifecycle for the selected object.
 *
 * Volumetric: fetch-or-generate GLB, show Model3DFrame driven by X/Y sliders,
 * commit via novel-view.
 * Planar: skip GLB; sliders drive live CSS 3D; commit via PATCH.
 */
export function useRotationController({
  imageId,
  selectedObjectId,
  selectedObject,
  naturalSize,
  jobsList,
  commitRotation,
  setObjects,
  setSelectedObjectId,
  clearShowOriginal,
  disarmOtherTools,
  onError,
}: UseRotationControllerOptions) {
  const [rotateMode, setRotateMode] = useState(false);
  const [isPreparing3D, setIsPreparing3D] = useState(false);
  const [draftCssPose, setDraftCssPose] = useState<Css3dPose>(IDENTITY_CSS_POSE);
  const model3DFrameRef = useRef<Model3DFrameHandle>(null);
  /** Snapshot of CSS pose when planar rotate was armed — Escape restores it. */
  const planarBaselineRef = useRef<Css3dPose>(IDENTITY_CSS_POSE);

  const glbData = selectedObject?.glbData ?? null;
  const volumetric = isVolumetricObject(selectedObject?.is3d ?? null);

  const commitCurrentRotation = useCallback(async () => {
    if (selectedObjectId === null) {
      setRotateMode(false);
      return;
    }

    const targetObjectId = selectedObjectId;
    clearShowOriginal(targetObjectId);

    // Planar: persist CSS angles; Source Cutout untouched; no novel-view.
    if (!isVolumetricObject(selectedObject?.is3d ?? null)) {
      const uuid = selectedObject?.uuid;
      setRotateMode(false);
      if (!uuid) {
        return;
      }
      const pose = draftCssPose;
      setObjects((prev) =>
        prev.map((o) =>
          o.objectId === targetObjectId
            ? {
                ...o,
                cssRotateXDeg: pose.rotateXDeg,
                cssRotateYDeg: pose.rotateYDeg,
                cssRotateZDeg: pose.rotateZDeg,
                cssPerspectivePx: pose.perspectivePx,
                rotation: null,
              }
            : o,
        ),
      );
      try {
        await setObjectCssTransform(uuid, {
          css_rotate_x_deg: pose.rotateXDeg,
          css_rotate_y_deg: pose.rotateYDeg,
          css_rotate_z_deg: pose.rotateZDeg,
          css_perspective_px: pose.perspectivePx,
        });
      } catch (err) {
        onError(err);
      }
      return;
    }

    // Volumetric: capture mesh viewer + novel-view as before.
    const capture = model3DFrameRef.current?.capture();
    const bounds = selectedObject?.cutoutAlphaBounds
      ? inflateBounds(selectedObject.cutoutAlphaBounds, MODEL_3D_FRAME_PADDING)
      : null;
    setRotateMode(false);

    if (!capture) {
      return;
    }

    const pose = {
      azimuthDeg: capture.azimuthDeg,
      relativeElevationDeg: capture.relativeElevationDeg,
      rollDeg: draftCssPose.rotateZDeg,
    };

    if (naturalSize) {
      try {
        const previewSrc = await compositePreviewOntoCanvas(capture.snapshotDataUrl, bounds, naturalSize);
        commitRotation(targetObjectId, pose, previewSrc);
        return;
      } catch {
        // Compositing failed — fall through to the raw snapshot.
      }
    }

    commitRotation(targetObjectId, pose, capture.snapshotDataUrl);
  }, [
    selectedObjectId,
    selectedObject,
    naturalSize,
    commitRotation,
    clearShowOriginal,
    draftCssPose,
    setObjects,
    onError,
  ]);

  const cancelRotation = useCallback(() => {
    if (!rotateMode) {
      return;
    }
    // Planar: restore baseline CSS pose that was present when Rotate was armed.
    if (!volumetric && selectedObjectId !== null) {
      const baseline = planarBaselineRef.current;
      setDraftCssPose(baseline);
      setObjects((prev) =>
        prev.map((o) =>
          o.objectId === selectedObjectId
            ? {
                ...o,
                cssRotateXDeg: baseline.rotateXDeg,
                cssRotateYDeg: baseline.rotateYDeg,
                cssRotateZDeg: baseline.rotateZDeg,
                cssPerspectivePx: baseline.perspectivePx,
              }
            : o,
        ),
      );
    }
    setRotateMode(false);
  }, [rotateMode, volumetric, selectedObjectId, setObjects]);

  const updateDraftCssPose = useCallback(
    (next: Css3dPose) => {
      setDraftCssPose(next);
      if (!volumetric && selectedObjectId !== null) {
        // Live preview on the cutout while armed.
        setObjects((prev) =>
          prev.map((o) =>
            o.objectId === selectedObjectId
              ? {
                  ...o,
                  cssRotateXDeg: next.rotateXDeg,
                  cssRotateYDeg: next.rotateYDeg,
                  cssRotateZDeg: next.rotateZDeg,
                  cssPerspectivePx: next.perspectivePx,
                }
              : o,
          ),
        );
      }
    },
    [volumetric, selectedObjectId, setObjects],
  );

  /** Sync X/Y draft from mesh grab (OrbitControls); leave Z untouched. */
  const syncOrbitFromDrag = useCallback((azimuthDeg: number, elevationDeg: number) => {
    setDraftCssPose((prev) => ({
      ...prev,
      rotateYDeg: azimuthDeg,
      rotateXDeg: elevationDeg,
    }));
  }, []);

  const handleRotate = useCallback(async () => {
    if (rotateMode) {
      void commitCurrentRotation();
      return;
    }

    if (!imageId || selectedObjectId === null || !selectedObject) {
      return;
    }

    disarmOtherTools();

    const baseline = poseFromObject(selectedObject);

    // Planar: arm sliders immediately — no GLB.
    if (!isVolumetricObject(selectedObject.is3d)) {
      planarBaselineRef.current = baseline;
      setDraftCssPose(baseline);
      setRotateMode(true);
      return;
    }

    // Volumetric: restore last rotation, then GLB ladder.
    setDraftCssPose(baseline);

    if (glbData) {
      setRotateMode(true);
      return;
    }

    const targetObjectId = selectedObjectId;
    setIsPreparing3D(true);

    try {
      const cached = await fetchCached3DModel(imageId, targetObjectId);
      let buffer = cached;
      if (!buffer) {
        const jobId =
          jobsList.find(
            (job) =>
              job.kind === "generate_3d" &&
              job.object_id === targetObjectId &&
              (job.status === "queued" || job.status === "running"),
          )?.job_id ?? (await submitGenerate3D(imageId, targetObjectId));
        await waitForJobDone(jobId);
        buffer = await fetchCached3DModel(imageId, targetObjectId);
        if (!buffer) {
          throw new Error("3D generation finished but no model was found.");
        }
      }
      setObjects((prev) =>
        prev.map((o) =>
          o.objectId === targetObjectId ? { ...o, glbData: buffer, has3d: true } : o,
        ),
      );
      setSelectedObjectId((current) => {
        if (current === targetObjectId) setRotateMode(true);
        return current;
      });
    } catch (genError) {
      onError(genError);
      setRotateMode(false);
    } finally {
      setIsPreparing3D(false);
    }
  }, [
    rotateMode,
    commitCurrentRotation,
    imageId,
    selectedObjectId,
    selectedObject,
    setObjects,
    setSelectedObjectId,
    jobsList,
    glbData,
    disarmOtherTools,
    onError,
  ]);

  const activeGenerate3DJobId = jobsList.find(
    (job) =>
      (job.status === "queued" || job.status === "running") &&
      job.kind === "generate_3d" &&
      job.object_id === selectedObjectId,
  )?.job_id;

  return {
    rotateMode,
    setRotateMode,
    isPreparing3D,
    model3DFrameRef,
    glbData,
    handleRotate,
    commitCurrentRotation,
    cancelRotation,
    draftCssPose,
    updateDraftCssPose,
    syncOrbitFromDrag,
    volumetric,
    activeGenerate3DJobId,
  };
}
