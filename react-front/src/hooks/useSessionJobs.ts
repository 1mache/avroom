import { useCallback, useEffect, useRef, useState } from "react";

import {
  cacheNovelViewPreview,
  duplicateObject as duplicateObjectRequest,
  getSessionObjects,
  inpaintMask,
  segmentImage,
  setObjectName,
  synthesizeNovelView,
} from "../api/images";
import type { CutoutBounds, ObjectInfo, SegmentRequest } from "../types/api";
import type {
  ClickPosition,
  CutoutAlphaBounds,
  CutoutObject,
  PendingInpaintJob,
  RotationPose,
  SegmentPickerState,
} from "../types/session";

let pendingJobCounter = 0;
const nextPendingJobId = (): string => `pending-${++pendingJobCounter}`;

// Fallback when server metadata is unavailable (legacy sessions).
const FALLBACK_SOURCE_ELEVATION_DEG = 15;

// Zoom/radius delta is not exposed in the rotate UI -- always request the
// model's default camera distance.
const NO_RADIUS_DELTA = 0;

export const toCutoutAlphaBounds = (
  bounds: CutoutBounds | null | undefined,
): CutoutAlphaBounds | null => {
  if (!bounds) {
    return null;
  }

  return {
    left: bounds.left,
    top: bounds.top,
    right: bounds.right,
    bottom: bounds.bottom,
    naturalWidth: bounds.natural_width,
    naturalHeight: bounds.natural_height,
  };
};

// Contexts a 409 can meaningfully arrive from. "generic" means: whatever this
// error is, it isn't a concurrency conflict — hand it straight to the page's
// existing error-modal path.
export type JobErrorContext = "segment" | "inpaint" | "rotate" | "generic";

interface UseSessionJobsOptions {
  onError: (error: unknown, context: JobErrorContext) => void;
  /** Fired after any successful mutating call so sync-check bookkeeping can
   * pick up the fresh server last_changed. */
  onMutated?: () => void;
}

/**
 * Owns per-session object state and job concurrency: one in-flight segment at
 * a time (it drives a single interactive picker), but N concurrent inpaints —
 * the backend's canvas-writer lock plus region leases make it safe for a
 * second non-overlapping removal to run while the first is still inpainting.
 */
export function useSessionJobs(imageId: string | null, options: UseSessionJobsOptions) {
  const { onError, onMutated } = options;

  const [objects, setObjects] = useState<CutoutObject[]>([]);
  const [selectedObjectId, setSelectedObjectId] = useState<number | null>(null);
  const [pendingJobs, setPendingJobs] = useState<PendingInpaintJob[]>([]);
  const [segmentState, setSegmentState] = useState<SegmentPickerState>({ status: "idle" });
  const [backgroundSrc, setBackgroundSrc] = useState<string | null>(null);
  const [isDuplicating, setIsDuplicating] = useState(false);

  const imageIdRef = useRef(imageId);
  useEffect(() => {
    imageIdRef.current = imageId;
  }, [imageId]);

  const objectsRef = useRef(objects);
  useEffect(() => {
    objectsRef.current = objects;
  }, [objects]);

  // Only ever moves forward. The canvas writer lock serializes commits
  // server-side so object_id is a valid commit order; this guards purely
  // against out-of-order *network* delivery of concurrent responses.
  const highestCommittedObjectIdRef = useRef(-1);

  const resetSession = useCallback(() => {
    setObjects([]);
    setSelectedObjectId(null);
    setPendingJobs([]);
    setSegmentState({ status: "idle" });
    setBackgroundSrc(null);
    setIsDuplicating(false);
    highestCommittedObjectIdRef.current = -1;
  }, []);

  const loadRestoredObjects = useCallback((restored: ObjectInfo[]) => {
    const loaded: CutoutObject[] = restored.map((info) => ({
      objectId: info.object_id,
      uuid: info.uuid ?? null,
      name: info.name ?? null,
      cutoutSrc: `data:image/${info.format};base64,${info.cutout_b64}`,
      cutoutAlphaBounds: toCutoutAlphaBounds(info.cutout_bounds),
      normalizedClickPos: null,
      glbData: null,
      rotation: null,
      hidden: false,
      offset: { x: 0, y: 0 },
      sourceElevationDeg: info.source_elevation_deg ?? FALLBACK_SOURCE_ELEVATION_DEG,
    }));
    setObjects(loaded);
    highestCommittedObjectIdRef.current = loaded.reduce(
      (max, o) => Math.max(max, o.objectId),
      -1,
    );
  }, []);

  const runSegment = useCallback(
    async (x: number, y: number) => {
      const currentImageId = imageIdRef.current;
      if (!currentImageId) {
        return;
      }

      setSegmentState({ status: "loading" });

      const payload: SegmentRequest = { image_id: currentImageId, x, y };

      try {
        const result = await segmentImage(payload);
        // The user may have switched to a different session while this was
        // in flight — don't let a stale result populate the wrong picker.
        if (imageIdRef.current !== currentImageId) {
          return;
        }
        if (result.masks.length === 0) {
          throw new Error("No mask candidates returned.");
        }
        setSegmentState({ status: "choosing", maskOptions: result.masks });
      } catch (err) {
        if (imageIdRef.current === currentImageId) {
          setSegmentState({ status: "idle" });
        }
        onError(err, "segment");
      }
    },
    [onError],
  );

  const closeMaskPicker = useCallback(() => {
    setSegmentState({ status: "idle" });
  }, []);

  // Closes the picker and fires the inpaint call detached: a pending
  // placeholder stands in for the object until the response lands, so the
  // caller is immediately free to click a new point and start another
  // segment/inpaint elsewhere while this one is still running.
  const selectMask = useCallback(
    (maskId: string, normalizedClickPos: ClickPosition | null) => {
      const currentImageId = imageIdRef.current;
      setSegmentState({ status: "idle" });
      if (!currentImageId) {
        return;
      }

      const jobId = nextPendingJobId();
      setPendingJobs((prev) => [
        ...prev,
        { jobId, maskId, normalizedClickPos, startedAt: Date.now() },
      ]);

      inpaintMask({ image_id: currentImageId, mask_id: maskId })
        .then((result) => {
          setPendingJobs((prev) => prev.filter((j) => j.jobId !== jobId));

          // The user may have switched to a different session while this was
          // in flight — don't let a stale result attach to the wrong one.
          if (imageIdRef.current !== currentImageId) {
            return;
          }

          const newObject: CutoutObject = {
            objectId: result.object_id,
            uuid: result.object_uuid,
            name: null,
            cutoutSrc: `data:image/${result.format};base64,${result.cutout_b64}`,
            cutoutAlphaBounds: toCutoutAlphaBounds(result.cutout_bounds),
            normalizedClickPos,
            glbData: null,
            rotation: null,
            hidden: false,
            offset: { x: 0, y: 0 },
            sourceElevationDeg:
              result.source_elevation_deg ?? FALLBACK_SOURCE_ELEVATION_DEG,
          };

          // Newly created object auto-selects — the user just made it.
          setObjects((prev) => [...prev, newObject]);
          setSelectedObjectId(result.object_id);

          if (result.object_id > highestCommittedObjectIdRef.current) {
            highestCommittedObjectIdRef.current = result.object_id;
            setBackgroundSrc(`data:image/${result.format};base64,${result.background_b64}`);
          }

          onMutated?.();
        })
        .catch((err) => {
          setPendingJobs((prev) => prev.filter((j) => j.jobId !== jobId));
          if (imageIdRef.current === currentImageId) {
            onError(err, "inpaint");
          }
        });
    },
    [onError, onMutated],
  );

  const toggleHidden = useCallback((objectId: number) => {
    setObjects((prev) => {
      const target = prev.find((o) => o.objectId === objectId);
      if (!target) {
        return prev;
      }
      const willBeHidden = !target.hidden;
      if (willBeHidden) {
        setSelectedObjectId((current) => (current === objectId ? null : current));
      }
      return prev.map((o) => (o.objectId === objectId ? { ...o, hidden: willBeHidden } : o));
    });
  }, []);

  const updateOffset = useCallback((objectId: number, offset: ClickPosition) => {
    setObjects((prev) => prev.map((o) => (o.objectId === objectId ? { ...o, offset } : o)));
  }, []);

  // Fires the novel-view request detached, same pattern as selectMask: the
  // object's `rotation` field itself is the pending-state marker (no separate
  // pendingJobs entry needed, since the object already exists). Re-rotating
  // an object simply overwrites its rotation -- always starting over from the
  // pristine cutout, since the backend never mutates that file.
  const commitRotation = useCallback(
    (objectId: number, pose: RotationPose, previewSrc: string) => {
      const currentImageId = imageIdRef.current;
      if (!currentImageId) {
        return;
      }

      const target = objectsRef.current.find((o) => o.objectId === objectId);
      const sourceElevationDeg = target?.sourceElevationDeg ?? FALLBACK_SOURCE_ELEVATION_DEG;

      setObjects((prev) =>
        prev.map((o) =>
          o.objectId === objectId
            ? { ...o, rotation: { pose, previewSrc, src: null, bounds: null, status: "pending" } }
            : o,
        ),
      );

      // Best-effort persistence of the preview so something survives on disk
      // if the real synthesis below never completes. Detached and swallowed
      // -- a failure here must never affect the rotation itself.
      const previewBase64 = previewSrc.split(",")[1] ?? "";
      if (previewBase64) {
        cacheNovelViewPreview({
          uid: currentImageId,
          object_id: objectId,
          azimuth_deg: pose.azimuthDeg,
          relative_elevation_deg: pose.relativeElevationDeg,
          image_b64: previewBase64,
        }).catch(() => {
          // Non-fatal -- the preview simply won't have a server-side fallback.
        });
      }

      synthesizeNovelView({
        uid: currentImageId,
        object_id: objectId,
        elevation_deg: sourceElevationDeg,
        azimuth_deg: pose.azimuthDeg,
        relative_elevation_deg: pose.relativeElevationDeg,
        radius: NO_RADIUS_DELTA,
      })
        .then((result) => {
          if (imageIdRef.current !== currentImageId) {
            return;
          }

          setObjects((prev) =>
            prev.map((o) =>
              o.objectId === objectId
                ? {
                    ...o,
                    rotation: {
                      pose: {
                        azimuthDeg: result.azimuth_deg,
                        relativeElevationDeg: result.relative_elevation_deg,
                      },
                      previewSrc,
                      src: `data:image/${result.format};base64,${result.image_b64}`,
                      bounds: toCutoutAlphaBounds(result.cutout_bounds),
                      status: "ready",
                    },
                  }
                : o,
            ),
          );
          onMutated?.();
        })
        .catch((err) => {
          if (imageIdRef.current !== currentImageId) {
            return;
          }
          setObjects((prev) =>
            prev.map((o) =>
              o.objectId === objectId && o.rotation
                ? { ...o, rotation: { ...o.rotation, status: "error" } }
                : o,
            ),
          );
          onError(err, "rotate");
        });
    },
    [onError, onMutated],
  );

  const renameObject = useCallback(
    async (objectId: number, uuid: string, name: string | null) => {
      try {
        const updated = await setObjectName(uuid, name);
        setObjects((prev) =>
          prev.map((o) => (o.objectId === objectId ? { ...o, name: updated.name ?? null } : o)),
        );
        onMutated?.();
      } catch (err) {
        onError(err, "generic");
      }
    },
    [onError, onMutated],
  );

  const duplicateObject = useCallback(
    async (objectId: number) => {
      const currentImageId = imageIdRef.current;
      const source = objectsRef.current.find((o) => o.objectId === objectId);
      if (!currentImageId || !source?.uuid || isDuplicating) {
        return;
      }

      setIsDuplicating(true);
      try {
        const { object_uuid: cloneUuid } = await duplicateObjectRequest(source.uuid);
        if (imageIdRef.current !== currentImageId) {
          return;
        }

        const list = await getSessionObjects(currentImageId);
        if (imageIdRef.current !== currentImageId) {
          return;
        }

        const info = list.objects.find((o) => o.uuid === cloneUuid);
        if (!info) {
          onMutated?.();
          return;
        }

        const newObject: CutoutObject = {
          objectId: info.object_id,
          uuid: info.uuid ?? cloneUuid,
          name: info.name ?? null,
          cutoutSrc: `data:image/${info.format};base64,${info.cutout_b64}`,
          cutoutAlphaBounds: toCutoutAlphaBounds(info.cutout_bounds),
          normalizedClickPos: source.normalizedClickPos,
          // Server copied the GLB; reuse in-memory bytes so Rotate works immediately.
          glbData: source.glbData,
          rotation: null,
          hidden: false,
          offset: { ...source.offset },
          sourceElevationDeg:
            info.source_elevation_deg ?? source.sourceElevationDeg ?? FALLBACK_SOURCE_ELEVATION_DEG,
        };

        setObjects((prev) => [...prev, newObject]);
        setSelectedObjectId(info.object_id);
        if (info.object_id > highestCommittedObjectIdRef.current) {
          highestCommittedObjectIdRef.current = info.object_id;
        }
        onMutated?.();
      } catch (err) {
        if (imageIdRef.current === currentImageId) {
          onError(err, "generic");
        }
      } finally {
        if (imageIdRef.current === currentImageId) {
          setIsDuplicating(false);
        }
      }
    },
    [isDuplicating, onError, onMutated],
  );

  return {
    objects,
    setObjects,
    selectedObjectId,
    setSelectedObjectId,
    pendingJobs,
    hasPendingWork:
      pendingJobs.length > 0 ||
      isDuplicating ||
      objects.some((o) => o.rotation?.status === "pending"),
    segmentState,
    isSegmenting: segmentState.status === "loading",
    isChoosingMask: segmentState.status === "choosing",
    maskOptions: segmentState.status === "choosing" ? segmentState.maskOptions : [],
    backgroundSrc,
    setBackgroundSrc,
    isDuplicating,
    runSegment,
    closeMaskPicker,
    selectMask,
    commitRotation,
    toggleHidden,
    updateOffset,
    renameObject,
    duplicateObject,
    resetSession,
    loadRestoredObjects,
  };
}
