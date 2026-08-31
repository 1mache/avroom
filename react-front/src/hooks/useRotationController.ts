import { useCallback, useRef, useState } from "react";
import type { Dispatch, SetStateAction } from "react";

import { fetchCached3DModel, submitGenerate3D, waitForJobDone } from "../api/images";
import { MODEL_3D_FRAME_PADDING, type Model3DFrameHandle } from "../components/widgets/Model3DFrame";
import type { JobInfo } from "../types/api";
import type { CutoutObject, RotationPose } from "../types/session";
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

/**
 * Owns the 3D angle-picker lifecycle for the selected object: arming
 * (fetch-or-generate its GLB, then show the picker) and committing (capture
 * the orbit delta plus a viewer snapshot, fire the detached novel-view
 * request via `commitRotation`, close the picker). See CLAUDE.md's
 * "Rotation flow" — the object's `rotation` field itself is the pending-state
 * marker; nothing rotation-specific is duplicated here.
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
  const model3DFrameRef = useRef<Model3DFrameHandle>(null);

  const glbData = selectedObject?.glbData ?? null;

  // Commits the current orbit as a rotation request: captures the angle delta
  // plus a snapshot of the viewer, fires the (detached) novel-view job via
  // commitRotation, and closes the picker. The object shows the snapshot
  // immediately and swaps to the synthesized result when the response lands.
  const commitCurrentRotation = useCallback(async () => {
    if (selectedObjectId === null) {
      setRotateMode(false);
      return;
    }

    // Capture synchronously (reads the live WebGL canvas) before closing the
    // picker — everything after this works from the extracted data URL.
    const capture = model3DFrameRef.current?.capture();
    const targetObjectId = selectedObjectId;
    // The snapshot spans the inflated viewer canvas, not the object's tight
    // rect, so it must be pasted back over that same inflated region.
    const bounds = selectedObject?.cutoutAlphaBounds
      ? inflateBounds(selectedObject.cutoutAlphaBounds, MODEL_3D_FRAME_PADDING)
      : null;
    setRotateMode(false);
    clearShowOriginal(targetObjectId);

    if (!capture) {
      return;
    }

    const pose = {
      azimuthDeg: capture.azimuthDeg,
      relativeElevationDeg: capture.relativeElevationDeg,
    };

    if (naturalSize) {
      try {
        const previewSrc = await compositePreviewOntoCanvas(capture.snapshotDataUrl, bounds, naturalSize);
        commitRotation(targetObjectId, pose, previewSrc);
        return;
      } catch {
        // Compositing failed — fall through to the raw (mis-scaled) snapshot
        // rather than losing the rotation request entirely.
      }
    }

    commitRotation(targetObjectId, pose, capture.snapshotDataUrl);
  }, [selectedObjectId, selectedObject, naturalSize, commitRotation, clearShowOriginal]);

  // Opens the angle picker for the selected object. Pressing rotate again
  // while it's open commits instead — this branch only runs the GLB ladder.
  const handleRotate = useCallback(async () => {
    if (rotateMode) {
      void commitCurrentRotation();
      return;
    }

    if (!imageId || selectedObjectId === null) {
      return;
    }

    disarmOtherTools();

    if (glbData) {
      setRotateMode(true);
      return;
    }

    // Snapshot the target id before any await so the model attaches to the
    // right object even if selection changes while generation is in flight.
    const targetObjectId = selectedObjectId;
    setIsPreparing3D(true);

    try {
      const cached = await fetchCached3DModel(imageId, targetObjectId);
      let buffer = cached;
      if (!buffer) {
        // Queued now instead of one blocking request: submit, wait for the
        // dispatcher to finish it, then read the GLB it wrote to disk. If a
        // generate_3d job for this object is already queued/running (the
        // user exited mid-generation and clicked Rotate again on return),
        // attach to that job instead of submitting a duplicate.
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
      // Only surface the picker if the user hasn't switched selection away.
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
    setObjects,
    setSelectedObjectId,
    jobsList,
    glbData,
    disarmOtherTools,
    onError,
  ]);

  // Rotate's spinner has to survive exit/return: unlike segment/inpaint,
  // generate_3d isn't watched through local pending state at all — handleRotate
  // awaits it directly above — so without this, exiting mid-generation and
  // coming back shows the button idle even though a generate_3d job is still
  // queued/running server-side for this object.
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
    activeGenerate3DJobId,
  };
}
