import { useCallback, useEffect, useRef, useState } from "react";

import {
  deleteJob,
  deleteObject as deleteObjectRequest,
  deleteObject3d as deleteObject3dRequest,
  duplicateObject as duplicateObjectRequest,
  fetchCached3DModel,
  getJob,
  getSessionObjects,
  importObjectCutout,
  inpaintMask,
  runSessionBatch,
  segmentImage,
  setObjectName,
  resetObjectTransform as resetObjectTransformRequest,
  smartPasteObject,
  submitGenerate3D,
  synthesizeNovelView,
  waitForJobDone,
} from "../api/images";
import type {
  BatchRequest,
  CutoutBounds,
  JobInfo,
  ObjectInfo,
  SmartPasteResponse,
  VerifyMode,
} from "../types/api";
import type {
  ClickPosition,
  CutoutAlphaBounds,
  CutoutObject,
  RotationPose,
  SegmentPickerState,
} from "../types/session";

// Fallback when server metadata is unavailable (legacy sessions).
const FALLBACK_SOURCE_ELEVATION_DEG = 15;

// Zoom/radius delta is not exposed in the rotate UI -- always request the
// model's default camera distance.
const NO_RADIUS_DELTA = 0;

// A sync reconcile can pull a freshly committed object down from the server
// before the request that created it has even returned, so "add this object"
// has to mean upsert. Blind appends produce two rows with the same id.
const upsertObject = (objects: CutoutObject[], next: CutoutObject): CutoutObject[] => {
  const index = objects.findIndex((o) => o.objectId === next.objectId);
  if (index === -1) {
    return [...objects, next];
  }
  // Keep whatever local-only state the reconciled copy already accumulated
  // (drag offset, hidden flag, 3D model) rather than resetting it.
  const existing = objects[index];
  const merged = { ...next, offset: existing.offset, hidden: existing.hidden, glbData: existing.glbData ?? next.glbData };
  return objects.map((o, i) => (i === index ? merged : o));
};

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

// Contexts a 409-equivalent conflict can meaningfully arrive from. "generic"
// means: whatever this error is, it isn't a concurrency conflict — hand it
// straight to the page's existing error-modal path.
export type JobErrorContext = "segment" | "inpaint" | "rotate" | "generic";

interface UseSessionJobsOptions {
  onError: (error: unknown, context: JobErrorContext) => void;
  /** Fired after any successful mutating call so sync-check bookkeeping can
   * pick up the fresh server last_changed. */
  onMutated?: () => void;
  /** A queued segment/inpaint job resolved to a "conflict" (the mask/click
   * overlapped an in-flight removal). Fired once per job; the job row is
   * then dismissed automatically since the caller has already been told. */
  onConflict?: (job: JobInfo) => void;
}

/**
 * Owns per-session object state and the local view of this session's job
 * backlog. Segment and inpaint are both fire-and-forget now: submitting
 * returns a job id immediately (202) and the result — mask candidates for
 * segment, the finished object for inpaint — arrives later via `jobs`, fed
 * by useSessionSync's polling of POST /images/{uid}/sync-check. This means
 * work submitted just before navigating away from the session is never lost:
 * it's a durable row, not component state, so re-entering the session (or
 * the next sync tick) picks it back up.
 */
export function useSessionJobs(imageId: string | null, options: UseSessionJobsOptions) {
  const { onError, onMutated, onConflict } = options;

  const [objects, setObjects] = useState<CutoutObject[]>([]);
  const [selectedObjectId, setSelectedObjectId] = useState<number | null>(null);
  // Fed by useSessionSync from the sync-check response — server truth, no
  // local-only fields to preserve across updates (unlike `objects`).
  const [jobs, setJobs] = useState<JobInfo[]>([]);
  const [isBatching, setIsBatching] = useState(false);
  const batchingRef = useRef(false);
  const [segmentState, setSegmentState] = useState<SegmentPickerState>({ status: "idle" });
  const [backgroundSrc, setBackgroundSrc] = useState<string | null>(null);
  const [isDuplicating, setIsDuplicating] = useState(false);
  const [isImporting, setIsImporting] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);

  const imageIdRef = useRef(imageId);
  useEffect(() => {
    imageIdRef.current = imageId;
  }, [imageId]);

  const objectsRef = useRef(objects);
  useEffect(() => {
    objectsRef.current = objects;
  }, [objects]);

  const jobsRef = useRef(jobs);
  useEffect(() => {
    jobsRef.current = jobs;
  }, [jobs]);

  useEffect(() => {
    segmentChoosingJobIdRef.current =
      segmentState.status === "choosing" ? segmentState.jobId : null;
  }, [segmentState]);

  const applyServerJobs = useCallback((serverJobs: JobInfo[]) => {
    setJobs(
      serverJobs.filter((job) => !purgedSegmentJobIdsRef.current.has(job.job_id)),
    );
  }, []);

  // Only ever moves forward. The canvas writer lock serializes commits
  // server-side so object_id is a valid commit order; this guards purely
  // against out-of-order *network* delivery of concurrent responses.
  const highestCommittedObjectIdRef = useRef(-1);

  // Object ids with a DELETE request in flight. A reconcile can land between
  // the local removal and the server actually processing the delete, and
  // without this set that reconcile would resurrect the object from the
  // still-current server object list. Once the request settles (success or
  // failure) the id is dropped -- server truth takes over from there, so a
  // later object reusing the same freed id isn't permanently hidden.
  const deletedObjectIdsRef = useRef<Set<number>>(new Set());

  // Segment jobs the user closed the picker on without choosing a mask. The
  // server-side row (and its reserved candidate files) is untouched, so this
  // is purely a "not right now" — resets on remount, meaning re-entering the
  // session offers the same result again.
  const dismissedSegmentJobIdsRef = useRef<Set<string>>(new Set());
  // Segment jobs the user discarded via Close — hidden locally until DELETE
  // settles so sync-check can't resurrect the row mid-flight.
  const purgedSegmentJobIdsRef = useRef<Set<string>>(new Set());
  const segmentChoosingJobIdRef = useRef<string | null>(null);
  // Guards the picker-chain effect against re-fetching the same head job
  // while its GET /jobs/{id} inflate call is still in flight.
  const inflatingJobIdRef = useRef<string | null>(null);
  // Conflict jobs already surfaced to onConflict, so a job row that lingers
  // for one extra render (before its own dismissal completes) can't double-fire.
  const notifiedConflictIdsRef = useRef<Set<string>>(new Set());

  const resetSession = useCallback(() => {
    setObjects([]);
    setSelectedObjectId(null);
    setJobs([]);
    setSegmentState({ status: "idle" });
    setBackgroundSrc(null);
    setIsDuplicating(false);
    setIsDeleting(false);
    highestCommittedObjectIdRef.current = -1;
    deletedObjectIdsRef.current = new Set();
    dismissedSegmentJobIdsRef.current = new Set();
    purgedSegmentJobIdsRef.current = new Set();
    segmentChoosingJobIdRef.current = null;
    notifiedConflictIdsRef.current = new Set();
  }, []);

  const isObjectDeleted = useCallback((objectId: number) => deletedObjectIdsRef.current.has(objectId), []);

  /**
   * Permanently deletes an object: calls DELETE /images/objects/{uuid}, then
   * removes it locally on success. Mirrors duplicateObject's shape (busy
   * flag, uuid lookup via objectsRef, imageIdRef guards around the await).
   */
  const deleteObject = useCallback(
    async (objectId: number) => {
      const currentImageId = imageIdRef.current;
      const target = objectsRef.current.find((o) => o.objectId === objectId);
      if (!currentImageId || !target?.uuid || isDeleting) {
        return;
      }

      deletedObjectIdsRef.current.add(objectId);
      setIsDeleting(true);
      try {
        await deleteObjectRequest(target.uuid);
        if (imageIdRef.current !== currentImageId) {
          return;
        }
        setObjects((prev) => prev.filter((o) => o.objectId !== objectId));
        setSelectedObjectId((current) => (current === objectId ? null : current));
        onMutated?.();
      } catch (err) {
        if (imageIdRef.current === currentImageId) {
          onError(err, "generic");
        }
      } finally {
        deletedObjectIdsRef.current.delete(objectId);
        if (imageIdRef.current === currentImageId) {
          setIsDeleting(false);
        }
      }
    },
    [isDeleting, onError, onMutated],
  );

  const clearObject3d = useCallback(
    async (objectId: number) => {
      const currentImageId = imageIdRef.current;
      const target = objectsRef.current.find((o) => o.objectId === objectId);
      if (!currentImageId || !target?.uuid) {
        return;
      }

      try {
        await deleteObject3dRequest(target.uuid);
        if (imageIdRef.current !== currentImageId) {
          return;
        }
        setObjects((prev) =>
          prev.map((o) =>
            o.objectId === objectId
              ? { ...o, glbData: null, has3d: false, rotation: null }
              : o,
          ),
        );
        onMutated?.();
      } catch (err) {
        if (imageIdRef.current === currentImageId) {
          onError(err, "generic");
        }
      }
    },
    [onError, onMutated],
  );

  const resetObjectChanges = useCallback(
    async (objectId: number) => {
      const currentImageId = imageIdRef.current;
      const target = objectsRef.current.find((o) => o.objectId === objectId);
      if (!currentImageId || !target?.uuid) {
        return;
      }

      try {
        await resetObjectTransformRequest(target.uuid);
        if (imageIdRef.current !== currentImageId) {
          return;
        }
        setObjects((prev) =>
          prev.map((o) =>
            o.objectId === objectId
              ? {
                  ...o,
                  offset: { x: 0, y: 0 },
                  displayScale: 1,
                  rotation: null,
                }
              : o,
          ),
        );
        onMutated?.();
      } catch (err) {
        if (imageIdRef.current === currentImageId) {
          onError(err, "generic");
        }
      }
    },
    [onError, onMutated],
  );

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
      offset: { x: info.offset_x ?? 0, y: info.offset_y ?? 0 },
      sourceElevationDeg: info.source_elevation_deg ?? FALLBACK_SOURCE_ELEVATION_DEG,
      displayScale: info.display_scale ?? 1,
      has3d: info.has_3d ?? false,
      cloneRootUuid: info.clone_root_uuid ?? null,
    }));
    setObjects(loaded);
    highestCommittedObjectIdRef.current = loaded.reduce(
      (max, o) => Math.max(max, o.objectId),
      -1,
    );
  }, []);

  const runBatch = useCallback(
    async (source: BatchRequest["source"]) => {
      const currentImageId = imageIdRef.current;
      if (!currentImageId || batchingRef.current) {
        return;
      }
      batchingRef.current = true;
      setIsBatching(true);
      try {
        await runSessionBatch(currentImageId, { source, verify: "auto" });
        if (imageIdRef.current === currentImageId) {
          onMutated?.();
        }
      } catch (err) {
        if (imageIdRef.current === currentImageId) {
          onError(err, "inpaint");
        }
      } finally {
        if (imageIdRef.current === currentImageId) {
          batchingRef.current = false;
          setIsBatching(false);
        }
      }
    },
    [onError, onMutated],
  );

  // Queues segmentation and returns immediately — no local loading state, and
  // no single-flight restriction: several segment clicks in a row all queue.
  // The result surfaces later through the picker-chain effect below, once it
  // shows up in `jobs`.
  const runSegment = useCallback(
    (
      x: number,
      y: number,
      verify: VerifyMode = "manual",
      points?: { x: number; y: number }[],
    ) => {
      const currentImageId = imageIdRef.current;
      if (!currentImageId) {
        return;
      }
      const payload: {
        image_id: string;
        x: number;
        y: number;
        verify: VerifyMode;
        points?: { x: number; y: number }[];
      } = { image_id: currentImageId, x, y, verify };
      if (points && points.length > 1) {
        payload.points = points;
      }
      segmentImage(payload)
        .then(() => onMutated?.())
        .catch((err) => onError(err, "segment"));
    },
    [onError, onMutated],
  );

  const deferMaskPicker = useCallback(() => {
    setSegmentState((prev) => {
      if (prev.status === "choosing") {
        dismissedSegmentJobIdsRef.current.add(prev.jobId);
      }
      return { status: "idle" };
    });
  }, []);

  const discardMaskPicker = useCallback(
    async (jobId: string) => {
      const currentImageId = imageIdRef.current;
      if (!currentImageId) {
        return;
      }

      purgedSegmentJobIdsRef.current.add(jobId);
      dismissedSegmentJobIdsRef.current.add(jobId);
      inflatingJobIdRef.current = null;
      setSegmentState({ status: "idle" });
      setJobs((prev) => prev.filter((job) => job.job_id !== jobId));

      try {
        await deleteJob(jobId);
        if (imageIdRef.current !== currentImageId) {
          return;
        }
        onMutated?.();
      } catch (err) {
        purgedSegmentJobIdsRef.current.delete(jobId);
        dismissedSegmentJobIdsRef.current.delete(jobId);
        if (imageIdRef.current === currentImageId) {
          onError(err, "generic");
        }
      }
    },
    [onError, onMutated],
  );

  // Consumes the segment job (from_job_id) atomically with the inpaint
  // submission and closes the picker. The created object isn't built here —
  // it arrives through the normal sync/reconcile path once the dispatcher
  // finishes the removal, exactly like a job that was still queued when the
  // user navigated away and back.
  const selectMask = useCallback(
    (jobId: string, maskId: string) => {
      const currentImageId = imageIdRef.current;
      dismissedSegmentJobIdsRef.current.add(jobId);
      setSegmentState({ status: "idle" });
      if (!currentImageId) {
        return;
      }

      inpaintMask({ image_id: currentImageId, mask_id: maskId, from_job_id: jobId })
        .then(() => onMutated?.())
        .catch((err) => {
          if (imageIdRef.current === currentImageId) {
            onError(err, "inpaint");
          }
        });
    },
    [onError, onMutated],
  );

  // Picker-chain: whenever the picker is idle, look for the oldest not-yet-
  // dismissed done segment job in this session and open it. Firing again
  // whenever `jobs` changes or the picker returns to idle is what makes
  // several queued results open one after another as each is resolved, and
  // what replays the same chain on session re-entry (dismissedSegmentJobIdsRef
  // is fresh on every mount).
  useEffect(() => {
    if (segmentState.status !== "idle") {
      return;
    }
    const currentImageId = imageIdRef.current;
    if (!currentImageId) {
      return;
    }

    const head = jobs
      .filter(
        (job) =>
          job.kind === "segment" &&
          job.status === "done" &&
          !dismissedSegmentJobIdsRef.current.has(job.job_id),
      )
      .sort((a, b) => a.created_at.localeCompare(b.created_at))[0];

    if (!head || inflatingJobIdRef.current === head.job_id) {
      return;
    }

    inflatingJobIdRef.current = head.job_id;
    getJob(head.job_id)
      .then((detail) => {
        inflatingJobIdRef.current = null;
        if (imageIdRef.current !== currentImageId) {
          return;
        }
        if (!detail.masks || detail.masks.length === 0) {
          // Nothing left to show (e.g. candidates expired) -- skip it so the
          // effect tries the next backlog entry on its next run.
          dismissedSegmentJobIdsRef.current.add(head.job_id);
          setSegmentState({ status: "idle" });
          return;
        }
        // Auto mode already had the backend narrow candidates down to its
        // one CLIP-picked winner (run_segment_job / verify=auto) -- the user
        // never chose to review candidates, so never show the picker for it.
        // Submit the winner straight through, same as a manual pick.
        if (detail.verify === "auto") {
          selectMask(detail.job_id, detail.masks[0].mask_id);
          return;
        }
        setSegmentState({ status: "choosing", jobId: head.job_id, maskOptions: detail.masks });
      })
      .catch(() => {
        inflatingJobIdRef.current = null;
      });
  }, [jobs, segmentState.status, selectMask]);

  // A queued segment/inpaint job that resolved to "conflict" (its mask/click
  // overlapped an in-flight removal) surfaces once via onConflict — the same
  // inline notice a synchronous 409 used to produce — then the job row is
  // dismissed so it can't linger or re-notify.
  useEffect(() => {
    for (const job of jobs) {
      if (job.status !== "conflict" || notifiedConflictIdsRef.current.has(job.job_id)) {
        continue;
      }
      notifiedConflictIdsRef.current.add(job.job_id);
      onConflict?.(job);
      deleteJob(job.job_id).catch(() => {
        // Non-fatal — worst case the row lingers until manually cleared.
      });
    }
  }, [jobs, onConflict]);

  const toggleHidden = useCallback(
    (objectId: number) => {
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
      onMutated?.();
    },
    [onMutated],
  );

  const updateOffset = useCallback((objectId: number, offset: ClickPosition) => {
    setObjects((prev) => prev.map((o) => (o.objectId === objectId ? { ...o, offset } : o)));
  }, []);

  // Fires the novel-view request detached, same pattern as before: the
  // object's `rotation` field itself is the pending-state marker. Re-rotating
  // an object simply overwrites its rotation -- always starting over from the
  // pristine cutout, since the backend never mutates that file. Unlike
  // segment/inpaint, rotation is not queued server-side (see plan) -- it
  // still lives entirely in this detached-request-plus-local-marker shape.
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

  /** Ensure this object's GLB exists, then mesh-render at an inferred pose. */
  const applyInferredRotation = useCallback(
    async (objectId: number, pose: RotationPose) => {
      const currentImageId = imageIdRef.current;
      if (!currentImageId) {
        return;
      }

      const target = objectsRef.current.find((o) => o.objectId === objectId);
      if (!target) {
        return;
      }

      try {
        let buffer = target.glbData;
        if (!buffer) {
          const cached = await fetchCached3DModel(currentImageId, objectId);
          buffer = cached;
          if (!buffer) {
            const existingJob = jobsRef.current.find(
              (job) =>
                job.kind === "generate_3d" &&
                job.object_id === objectId &&
                (job.status === "queued" || job.status === "running"),
            );
            const jobId = existingJob?.job_id ?? (await submitGenerate3D(currentImageId, objectId));
            await waitForJobDone(jobId);
            buffer = await fetchCached3DModel(currentImageId, objectId);
            if (!buffer) {
              throw new Error("3D generation finished but no model was found.");
            }
          }
          if (imageIdRef.current !== currentImageId) {
            return;
          }
          setObjects((prev) =>
            prev.map((o) => (o.objectId === objectId ? { ...o, glbData: buffer! } : o)),
          );
        }

        commitRotation(objectId, pose, target.cutoutSrc);
      } catch (err) {
        if (imageIdRef.current === currentImageId) {
          onError(err, "rotate");
        }
      }
    },
    [commitRotation, onError, setObjects],
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
          // Server-computed nudge (build_clone_metadata), not a raw copy of
          // source.offset -- the clone lands beside its source, not on it.
          offset: { x: info.offset_x ?? source.offset.x, y: info.offset_y ?? source.offset.y },
          displayScale: info.display_scale ?? source.displayScale ?? 1,
          sourceElevationDeg:
            info.source_elevation_deg ?? source.sourceElevationDeg ?? FALLBACK_SOURCE_ELEVATION_DEG,
          has3d: info.has_3d ?? source.has3d,
          cloneRootUuid: info.clone_root_uuid ?? source.uuid,
        };

        setObjects((prev) => upsertObject(prev, newObject));
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

  const importObject = useCallback(
    async (file: File) => {
      const currentImageId = imageIdRef.current;
      if (!currentImageId || isImporting) {
        return;
      }

      if (file.size === 0) {
        onError(new Error("PNG file is empty."), "generic");
        return;
      }

      const isPng =
        file.type === "image/png" || file.name.toLowerCase().endsWith(".png");
      if (!isPng) {
        onError(new Error("Only PNG cutouts can be imported."), "generic");
        return;
      }

      setIsImporting(true);
      try {
        const { object_uuid: importedUuid } = await importObjectCutout(currentImageId, file);
        if (imageIdRef.current !== currentImageId) {
          return;
        }

        const list = await getSessionObjects(currentImageId);
        if (imageIdRef.current !== currentImageId) {
          return;
        }

        const info = list.objects.find((o) => o.uuid === importedUuid);
        if (!info) {
          onMutated?.();
          return;
        }

        const newObject: CutoutObject = {
          objectId: info.object_id,
          uuid: info.uuid ?? importedUuid,
          name: info.name ?? null,
          cutoutSrc: `data:image/${info.format};base64,${info.cutout_b64}`,
          cutoutAlphaBounds: toCutoutAlphaBounds(info.cutout_bounds),
          normalizedClickPos: null,
          glbData: null,
          rotation: null,
          hidden: false,
          offset: { x: info.offset_x ?? 0, y: info.offset_y ?? 0 },
          displayScale: info.display_scale ?? 1,
          sourceElevationDeg: info.source_elevation_deg ?? FALLBACK_SOURCE_ELEVATION_DEG,
          has3d: info.has_3d ?? false,
          cloneRootUuid: info.clone_root_uuid ?? null,
        };

        setObjects((prev) => upsertObject(prev, newObject));
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
          setIsImporting(false);
        }
      }
    },
    [isImporting, onError, onMutated],
  );

  const applySmartPasteResult = useCallback(
    (objectId: number, result: SmartPasteResponse) => {
      setObjects((prev) =>
        prev.map((o) =>
          o.objectId === objectId
            ? {
                ...o,
                displayScale: result.display_scale,
                rotation: null,
              }
            : o,
        ),
      );
      onMutated?.();
    },
    [onMutated],
  );

  const runSmartPasteAfterDrag = useCallback(
    (objectId: number, x: number, y: number) => {
      const currentImageId = imageIdRef.current;
      const target = objectsRef.current.find((o) => o.objectId === objectId);
      if (!currentImageId || !target?.uuid) {
        return Promise.resolve(false);
      }

      return smartPasteObject(target.uuid, x, y)
        .then(async (result) => {
          if (imageIdRef.current !== currentImageId) {
            return false;
          }
          applySmartPasteResult(objectId, result);
          if (result.azimuth_deg != null && result.relative_elevation_deg != null) {
            await applyInferredRotation(objectId, {
              azimuthDeg: result.azimuth_deg,
              relativeElevationDeg: result.relative_elevation_deg,
            });
          }
          return true;
        })
        .catch((err) => {
          if (imageIdRef.current === currentImageId) {
            onError(err, "generic");
          }
          return false;
        });
    },
    [applyInferredRotation, applySmartPasteResult, onError],
  );

  return {
    objects,
    setObjects,
    selectedObjectId,
    setSelectedObjectId,
    jobs,
    setJobs,
    applyServerJobs,
    hasPendingWork:
      jobs.some((job) => job.status === "queued" || job.status === "running") ||
      isBatching ||
      isDuplicating ||
      isImporting ||
      isDeleting ||
      objects.some((o) => o.rotation?.status === "pending"),
    segmentState,
    isChoosingMask: segmentState.status === "choosing",
    maskOptions: segmentState.status === "choosing" ? segmentState.maskOptions : [],
    currentSegmentJobId: segmentState.status === "choosing" ? segmentState.jobId : null,
    backgroundSrc,
    setBackgroundSrc,
    isDuplicating,
    isImporting,
    runSegment,
    runBatch,
    isBatching,
    closeMaskPicker: deferMaskPicker,
    deferMaskPicker,
    discardMaskPicker,
    selectMask,
    commitRotation,
    toggleHidden,
    updateOffset,
    renameObject,
    duplicateObject,
    importObject,
    deleteObject,
    clearObject3d,
    resetObjectChanges,
    runSmartPasteAfterDrag,
    isDeleting,
    isObjectDeleted,
    resetSession,
    loadRestoredObjects,
  };
}
