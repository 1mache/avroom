import { useCallback, useEffect, useRef, useState } from "react";

import { inpaintMask, segmentImage, setObjectName } from "../api/images";
import type { CutoutBounds, ObjectInfo, SegmentRequest } from "../types/api";
import type {
  ClickPosition,
  CutoutAlphaBounds,
  CutoutObject,
  PendingInpaintJob,
  SegmentPickerState,
} from "../types/session";

let pendingJobCounter = 0;
const nextPendingJobId = (): string => `pending-${++pendingJobCounter}`;

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
export type JobErrorContext = "segment" | "inpaint" | "generic";

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

  const imageIdRef = useRef(imageId);
  useEffect(() => {
    imageIdRef.current = imageId;
  }, [imageId]);

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
      hidden: false,
      offset: { x: 0, y: 0 },
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
            hidden: false,
            offset: { x: 0, y: 0 },
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

  return {
    objects,
    setObjects,
    selectedObjectId,
    setSelectedObjectId,
    pendingJobs,
    hasPendingWork: pendingJobs.length > 0,
    segmentState,
    isSegmenting: segmentState.status === "loading",
    isChoosingMask: segmentState.status === "choosing",
    maskOptions: segmentState.status === "choosing" ? segmentState.maskOptions : [],
    backgroundSrc,
    setBackgroundSrc,
    runSegment,
    closeMaskPicker,
    selectMask,
    toggleHidden,
    updateOffset,
    renameObject,
    resetSession,
    loadRestoredObjects,
  };
}
