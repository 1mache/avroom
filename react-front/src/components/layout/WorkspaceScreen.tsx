import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  API_BASE_URL,
  PREVIEW_API_READY,
  fetchCached3DModel,
  generate3DModel,
  getSessionObjects,
  getUidCacheStatus,
  saveSessionPreview,
  setObjectOffset,
  setSessionName as saveSessionName,
  warmSessionMaps,
} from "../../api/images";
import { useConflictNotices, type ConflictContext } from "../../hooks/useConflictNotices";
import { useSessionJobs, type JobErrorContext } from "../../hooks/useSessionJobs";
import { useSessionSync } from "../../hooks/useSessionSync";
import type { VerifyMode } from "../../types/api";
import {
  effectiveCutoutBounds,
  effectiveCutoutSrc,
  effectiveDisplayBounds,
  type ClickPosition,
  type CutoutObject,
} from "../../types/session";
import { composeSessionPreview } from "../../utils/preview";
import {
  ALPHA_HIT_THRESHOLD,
  buildHitTestOrder,
  clampCutoutOffset,
  compositePreviewOntoCanvas,
  getBoundsStageRect,
  getContainedImageRect,
  getObjectPlacementCenter,
  inflateAroundCenter,
  inflateBounds,
  mapPointThroughInverseScale,
  toNaturalPoint,
  type Rect,
  type Size,
} from "../../utils/stageGeometry";
import { ConfirmDialog } from "../widgets/ConfirmDialog";
import { MaskPickerModal } from "../widgets/MaskPickerModal";
import {
  MODEL_3D_FRAME_PADDING,
  Model3DFrame,
  type Model3DFrameHandle,
} from "../widgets/Model3DFrame";
import { ObjectRail } from "../workspace/ObjectRail";
import { Toolbar } from "../workspace/Toolbar";

interface DragState {
  objectId: number;
  pointerId: number;
  startClientX: number;
  startClientY: number;
  startOffsetX: number;
  startOffsetY: number;
}

interface HitCanvasEntry {
  canvas: HTMLCanvasElement;
  width: number;
  height: number;
  // The src this canvas was built from. Rotation swaps an object's effective
  // src in place without changing its objectId, so the cache must invalidate
  // on src change, not just track which ids exist.
  src: string;
  displayScale: number;
}

const errorMessage = (error: unknown, fallback: string): string =>
  error instanceof Error ? error.message : fallback;

// How long to wait after the last edit before storing a fresh dashboard
// thumbnail — several mutations often land together (an inpaint plus its sync
// reconcile), and only the settled result is worth compositing.
const PREVIEW_DEBOUNCE_MS = 500;

export interface WorkspaceScreenProps {
  /** Session to edit. The workspace never picks one itself. */
  uid: string;
  onExit: () => void;
}

/**
 * The editor: a photo at full size with a permanent toolbar above it and the
 * object rail parked in the right edge. Session-level concerns (choosing,
 * creating, deleting) belong to the dashboard, so none of them appear here.
 */
export const WorkspaceScreen: React.FC<WorkspaceScreenProps> = ({ uid, onExit }) => {
  const stageRef = useRef<HTMLDivElement>(null);
  const dragStateRef = useRef<DragState | null>(null);
  const naturalSizeRef = useRef<Size | null>(null);
  const renderedRectRef = useRef<Rect | null>(null);
  const hitCanvasesRef = useRef<Map<number, HitCanvasEntry>>(new Map());
  const model3DFrameRef = useRef<Model3DFrameHandle>(null);

  // The session is fixed for this screen's lifetime (App remounts on change),
  // so imageId is simply the prop — no picking, no null state.
  const imageId = uid;
  const [sessionName, setSessionName] = useState("");
  const [originalSrc, setOriginalSrc] = useState<string | null>(null);
  const [mapsWarming, setMapsWarming] = useState(true);
  const mapsWarmGenerationRef = useRef(0);

  const [naturalSize, setNaturalSize] = useState<Size | null>(null);
  const [stageSize, setStageSize] = useState<Size | null>(null);

  // cutMode: scissors is armed and the next click on the photo starts a cutout.
  // pickPoint: that click, in natural-image pixels, kept on screen while the
  // mask picker is open so the user can see what they aimed at.
  const [cutMode, setCutMode] = useState(false);
  const [areaMode, setAreaMode] = useState(false);
  const [areaDraft, setAreaDraft] = useState<{
    start: ClickPosition;
    current: ClickPosition;
  } | null>(null);
  const [batchUuids, setBatchUuids] = useState<Set<string>>(new Set());
  const [pickPoint, setPickPoint] = useState<ClickPosition | null>(null);
  const [verifyMode, setVerifyMode] = useState<VerifyMode>("manual");

  // rotateMode: the 3D angle picker replaces the selected object's cutout.
  // isPreparing3D: blocking wait while its GLB is fetched or generated.
  const [rotateMode, setRotateMode] = useState(false);
  const [isPreparing3D, setIsPreparing3D] = useState(false);
  // Per-object: show the pristine cutout instead of the rotated result.
  const [showOriginalIds, setShowOriginalIds] = useState<ReadonlySet<number>>(new Set());

  const [smartPaste, setSmartPaste] = useState(false);
  const smartPasteRef = useRef(false);
  const [isSmartPasting, setIsSmartPasting] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Object id awaiting delete confirmation. Deletion is permanent (the
  // background keeps its inpainted hole), so the trash button arms this
  // instead of deleting directly.
  const [pendingDeleteObjectId, setPendingDeleteObjectId] = useState<number | null>(null);

  const conflictNotices = useConflictNotices();

  // 409s from segment/inpaint are expected concurrency traffic — routed to the
  // inline notice stack. Everything else is a real failure and opens the modal.
  const handleJobError = useCallback(
    (jobError: unknown, context: JobErrorContext) => {
      if (context === "generic") {
        setError(errorMessage(jobError, "Unexpected error."));
        return;
      }
      try {
        conflictNotices.notify(jobError, context as ConflictContext);
      } catch (rethrown) {
        setError(errorMessage(rethrown, "Unexpected error."));
      }
    },
    [conflictNotices],
  );

  // useSessionSync needs jobs' setters, and jobs' onMutated needs to trigger a
  // sync check — a ref breaks the circular dependency between the two hooks.
  const recordLocalMutationRef = useRef<() => void>(() => {});
  // Same trick for the dashboard thumbnail: capturing it needs state declared
  // further down, but onMutated has to be passed into useSessionJobs up here.
  const capturePreviewRef = useRef<() => void>(() => {});
  const handleMutated = useCallback(() => {
    recordLocalMutationRef.current();
    capturePreviewRef.current();
  }, []);

  const jobs = useSessionJobs(imageId, { onError: handleJobError, onMutated: handleMutated });

  const sync = useSessionSync({
    imageId,
    hasPendingWork: jobs.hasPendingWork,
    objects: jobs.objects,
    setObjects: jobs.setObjects,
    selectedObjectId: jobs.selectedObjectId,
    setSelectedObjectId: jobs.setSelectedObjectId,
    setBackgroundSrc: jobs.setBackgroundSrc,
    isDeleted: jobs.isObjectDeleted,
  });

  useEffect(() => {
    recordLocalMutationRef.current = sync.recordLocalMutation;
  }, [sync.recordLocalMutation]);

  const selectedObject = jobs.objects.find((o) => o.objectId === jobs.selectedObjectId) ?? null;
  const glbData = selectedObject?.glbData ?? null;

  const isShowingOriginal = useCallback(
    (obj: { objectId: number }) => showOriginalIds.has(obj.objectId),
    [showOriginalIds],
  );

  // --- session map warm ----------------------------------------------------

  const startMapsWarm = useCallback(() => {
    const generation = ++mapsWarmGenerationRef.current;
    setMapsWarming(true);
    void warmSessionMaps(uid)
      .catch((err: unknown) => {
        console.warn("Session map warm failed (non-fatal); first cut may be slower.", err);
      })
      .finally(() => {
        if (mapsWarmGenerationRef.current === generation) {
          setMapsWarming(false);
        }
      });
  }, [uid]);

  const handleToggleSmartPaste = useCallback(() => {
    setSmartPaste((on) => {
      const next = !on;
      if (next) {
        startMapsWarm();
      }
      return next;
    });
  }, [startMapsWarm]);

  // --- session load -------------------------------------------------------

  useEffect(() => {
    let cancelled = false;
    setOriginalSrc(`${API_BASE_URL}/images/${uid}/original`);
    startMapsWarm();

    const load = async () => {
      try {
        const status = await getUidCacheStatus(uid);
        if (cancelled) {
          return;
        }
        setSessionName(status.name ?? uid);

        if (status.has_background) {
          jobs.setBackgroundSrc(`${API_BASE_URL}/images/${uid}/background`);
        }

        if (status.has_cutout) {
          const objList = await getSessionObjects(uid);
          if (!cancelled && objList.objects.length > 0) {
            jobs.loadRestoredObjects(objList.objects);
          }
        }

        // Seed sync bookkeeping now rather than waiting for a poll tick, and
        // pick up anything that changed since the last visit.
        recordLocalMutationRef.current();
      } catch {
        // Non-fatal: the session still opens, the name falls back to its id.
        if (!cancelled) {
          setSessionName(uid);
        }
      }
    };

    void load();
    return () => {
      cancelled = true;
    };
    // Runs once per session: App remounts this screen when uid changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [uid, startMapsWarm]);

  // --- dashboard thumbnail -------------------------------------------------
  // dashboard preview. Detached and failure-swallowing: a missing thumbnail is
  // never worth interrupting an edit for. No-ops until the preview endpoints
  // exist (see PREVIEW_API_READY in api/images.ts).
  const previewTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const previewInputsRef = useRef({
    backgroundSrc: null as string | null,
    objects: [] as CutoutObject[],
    naturalSize: null as Size | null,
    showOriginalIds: new Set<number>() as ReadonlySet<number>,
  });

  useEffect(() => {
    previewInputsRef.current = {
      // Falls back to the original photo so a session never inpainted yet
      // still gets a thumbnail rather than composing nothing.
      backgroundSrc: jobs.backgroundSrc ?? originalSrc,
      objects: jobs.objects,
      naturalSize,
      showOriginalIds,
    };
  }, [jobs.backgroundSrc, originalSrc, jobs.objects, naturalSize, showOriginalIds]);

  useEffect(() => {
    smartPasteRef.current = smartPaste;
  }, [smartPaste]);

  useEffect(() => {
    capturePreviewRef.current = () => {
      if (!PREVIEW_API_READY) {
        return;
      }

      if (previewTimerRef.current) {
        clearTimeout(previewTimerRef.current);
      }

      previewTimerRef.current = setTimeout(async () => {
        const { backgroundSrc, objects, naturalSize: size, showOriginalIds: shown } =
          previewInputsRef.current;
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
    };
  }, [uid]);

  useEffect(() => {
    return () => {
      if (previewTimerRef.current) {
        clearTimeout(previewTimerRef.current);
      }
    };
  }, []);

  // --- stage geometry -----------------------------------------------------

  const measureStage = useCallback(() => {
    const stage = stageRef.current;
    if (!stage) {
      return;
    }

    const next = { width: stage.clientWidth, height: stage.clientHeight };
    setStageSize((previous) =>
      previous && previous.width === next.width && previous.height === next.height
        ? previous
        : next,
    );
  }, []);

  useEffect(() => {
    const stage = stageRef.current;
    if (!stage) {
      return;
    }

    measureStage();
    const observer = new ResizeObserver(measureStage);
    observer.observe(stage);
    return () => observer.disconnect();
  }, [measureStage, imageId]);

  const handleImageLoad: React.ReactEventHandler<HTMLImageElement> = useCallback(
    (event) => {
      setNaturalSize({
        width: event.currentTarget.naturalWidth,
        height: event.currentTarget.naturalHeight,
      });
      measureStage();
    },
    [measureStage],
  );

  const renderedRect = useMemo(
    () => (stageSize && naturalSize ? getContainedImageRect(stageSize, naturalSize) : null),
    [stageSize, naturalSize],
  );

  useEffect(() => {
    naturalSizeRef.current = naturalSize;
  }, [naturalSize]);

  useEffect(() => {
    renderedRectRef.current = renderedRect;
  }, [renderedRect]);

  // --- alpha-precise hit testing -----------------------------------------

  useEffect(() => {
    const currentIds = new Set(jobs.objects.map((o) => o.objectId));
    hitCanvasesRef.current.forEach((_entry, id) => {
      if (!currentIds.has(id)) {
        hitCanvasesRef.current.delete(id);
      }
    });

    jobs.objects.forEach((obj) => {
      const src = effectiveCutoutSrc(obj, isShowingOriginal(obj));
      const existing = hitCanvasesRef.current.get(obj.objectId);
      if (existing && existing.src === src && existing.displayScale === obj.displayScale) {
        return;
      }

      const img = new Image();
      img.onload = () => {
        const canvas = document.createElement("canvas");
        canvas.width = img.naturalWidth;
        canvas.height = img.naturalHeight;
        const ctx = canvas.getContext("2d", { willReadFrequently: true });
        if (!ctx) {
          return;
        }
        ctx.drawImage(img, 0, 0);
        hitCanvasesRef.current.set(obj.objectId, {
          canvas,
          width: img.naturalWidth,
          height: img.naturalHeight,
          src,
          displayScale: obj.displayScale,
        });
      };
      img.src = src;
    });
  }, [jobs.objects, isShowingOriginal]);

  const sampleObjectAlpha = useCallback((objectId: number, localX: number, localY: number): number => {
    const entry = hitCanvasesRef.current.get(objectId);
    if (!entry) {
      // Canvas not built yet (object just created). Treat as opaque so the
      // object stays clickable immediately; the bounds check above already
      // filtered out obviously-empty space.
      return 255;
    }

    if (localX < 0 || localY < 0 || localX >= entry.width || localY >= entry.height) {
      return 0;
    }

    const ctx = entry.canvas.getContext("2d", { willReadFrequently: true });
    if (!ctx) {
      return 255;
    }

    return ctx.getImageData(Math.floor(localX), Math.floor(localY), 1, 1).data[3];
  }, []);

  // --- selection & tools --------------------------------------------------

  const selectObject = useCallback(
    (objectId: number) => {
      jobs.setSelectedObjectId(objectId);
      // Rotation is scoped to whichever object is selected — switching away
      // closes the angle picker.
      setRotateMode(false);
      setCutMode(false);
      setPickPoint(null);
    },
    [jobs.setSelectedObjectId],
  );

  const handleToggleHidden = useCallback(
    (objectId: number) => {
      const wasSelected = jobs.selectedObjectId === objectId;
      jobs.toggleHidden(objectId);
      if (wasSelected) {
        setRotateMode(false);
      }
    },
    [jobs.selectedObjectId, jobs.toggleHidden],
  );

  const handleToggleShowOriginal = useCallback((objectId: number) => {
    setShowOriginalIds((prev) => {
      const next = new Set(prev);
      if (!next.delete(objectId)) {
        next.add(objectId);
      }
      return next;
    });
  }, []);

  const handleCut = useCallback(() => {
    setRotateMode(false);
    setAreaMode(false);
    setPickPoint(null);
    setCutMode((armed) => !armed);
  }, []);

  const handleArea = useCallback(() => {
    setRotateMode(false);
    setCutMode(false);
    setPickPoint(null);
    setAreaMode((armed) => !armed);
  }, []);

  const handleMaskSelected = useCallback(
    (maskId: string) => {
      const normalized =
        pickPoint && naturalSize
          ? { x: pickPoint.x / naturalSize.width, y: pickPoint.y / naturalSize.height }
          : null;
      jobs.selectMask(maskId, normalized, verifyMode);
      setPickPoint(null);
    },
    [jobs.selectMask, pickPoint, naturalSize, verifyMode],
  );

  const handleMaskPickerClosed = useCallback(() => {
    jobs.closeMaskPicker();
    setPickPoint(null);
  }, [jobs.closeMaskPicker]);

  // Commits the current orbit as a rotation request: captures the angle delta
  // plus a snapshot of the viewer, fires the (detached) novel-view job, and
  // closes the picker. The object shows the snapshot immediately and swaps to
  // the synthesized result when the response lands.
  const commitCurrentRotation = useCallback(async () => {
    if (jobs.selectedObjectId === null) {
      setRotateMode(false);
      return;
    }

    // Capture synchronously (reads the live WebGL canvas) before closing the
    // picker — everything after this works from the extracted data URL.
    const capture = model3DFrameRef.current?.capture();
    const targetObjectId = jobs.selectedObjectId;
    // The snapshot spans the inflated viewer canvas, not the object's tight
    // rect, so it must be pasted back over that same inflated region.
    const bounds = selectedObject?.cutoutAlphaBounds
      ? inflateBounds(selectedObject.cutoutAlphaBounds, MODEL_3D_FRAME_PADDING)
      : null;
    setRotateMode(false);
    setShowOriginalIds((prev) => {
      if (!prev.has(targetObjectId)) {
        return prev;
      }
      const next = new Set(prev);
      next.delete(targetObjectId);
      return next;
    });

    if (!capture) {
      return;
    }

    const pose = {
      azimuthDeg: capture.azimuthDeg,
      relativeElevationDeg: capture.relativeElevationDeg,
    };

    if (naturalSize) {
      try {
        const previewSrc = await compositePreviewOntoCanvas(
          capture.snapshotDataUrl,
          bounds,
          naturalSize,
        );
        jobs.commitRotation(targetObjectId, pose, previewSrc);
        return;
      } catch {
        // Compositing failed — fall through to the raw (mis-scaled) snapshot
        // rather than losing the rotation request entirely.
      }
    }

    jobs.commitRotation(targetObjectId, pose, capture.snapshotDataUrl);
  }, [jobs.selectedObjectId, jobs.commitRotation, selectedObject, naturalSize]);

  // Opens the angle picker for the selected object. Pressing rotate again
  // while it's open commits instead — this branch only runs the GLB ladder.
  const handleRotate = useCallback(async () => {
    if (rotateMode) {
      void commitCurrentRotation();
      return;
    }

    if (!imageId || jobs.selectedObjectId === null) {
      return;
    }

    setCutMode(false);

    if (glbData) {
      setRotateMode(true);
      return;
    }

    // Snapshot the target id before any await so the model attaches to the
    // right object even if selection changes while generation is in flight.
    const targetObjectId = jobs.selectedObjectId;
    setIsPreparing3D(true);

    try {
      const cached = await fetchCached3DModel(imageId, targetObjectId);
      const buffer = cached ?? (await generate3DModel(imageId, targetObjectId));
      jobs.setObjects((prev) =>
        prev.map((o) => (o.objectId === targetObjectId ? { ...o, glbData: buffer } : o)),
      );
      // Only surface the picker if the user hasn't switched selection away.
      jobs.setSelectedObjectId((current) => {
        if (current === targetObjectId) setRotateMode(true);
        return current;
      });
    } catch (genError) {
      setError(errorMessage(genError, "Unexpected 3D generation error."));
      setRotateMode(false);
    } finally {
      setIsPreparing3D(false);
    }
  }, [
    rotateMode,
    commitCurrentRotation,
    imageId,
    jobs.selectedObjectId,
    jobs.setObjects,
    jobs.setSelectedObjectId,
    glbData,
  ]);

  const handleCopy = useCallback(() => {
    if (jobs.selectedObjectId === null) {
      return;
    }
    // Objects segmented before server-side UUID tracking was added have no
    // uuid, and duplication is keyed on it — surface that instead of a silent
    // no-op (see useSessionJobs.duplicateObject).
    if (!selectedObject?.uuid) {
      setError("This object is from an older session and can't be duplicated.");
      return;
    }
    void jobs.duplicateObject(jobs.selectedObjectId);
  }, [jobs.duplicateObject, jobs.selectedObjectId, selectedObject]);

  // Arms the confirm dialog; the actual DELETE fires from
  // handleConfirmDeleteObject once the user confirms.
  const handleDeleteObject = useCallback(() => {
    if (jobs.selectedObjectId === null) {
      return;
    }
    // Same uuid precondition as duplicate — deletion is keyed on it too.
    if (!selectedObject?.uuid) {
      setError("This object is from an older session and can't be deleted.");
      return;
    }
    setRotateMode(false);
    setPendingDeleteObjectId(jobs.selectedObjectId);
  }, [jobs.selectedObjectId, selectedObject]);

  const pendingDeleteObject =
    jobs.objects.find((o) => o.objectId === pendingDeleteObjectId) ?? null;

  const handleConfirmDeleteObject = useCallback(async () => {
    if (pendingDeleteObjectId === null) {
      return;
    }
    await jobs.deleteObject(pendingDeleteObjectId);
    setPendingDeleteObjectId(null);
  }, [jobs.deleteObject, pendingDeleteObjectId]);

  const handleCancelDeleteObject = useCallback(() => {
    setPendingDeleteObjectId(null);
  }, []);

  const handleRenameObject = useCallback(
    (objectId: number, uuid: string, name: string | null) => {
      void jobs.renameObject(objectId, uuid, name);
    },
    [jobs.renameObject],
  );

  const handleSessionNameKeyDown = useCallback(
    async (event: React.KeyboardEvent<HTMLInputElement>) => {
      if (event.key !== "Enter" || !imageId || !sessionName.trim()) {
        return;
      }

      event.currentTarget.blur();

      try {
        await saveSessionName(imageId, sessionName.trim());
        recordLocalMutationRef.current();
      } catch (nameError) {
        // A 409 here means the name is taken — a real, user-facing conflict,
        // distinct from segment/inpaint concurrency, so it opens the modal.
        setError(errorMessage(nameError, "Failed to save session name."));
      }
    },
    [imageId, sessionName],
  );

  // Enter commits the rotation (same as pressing rotate again); Escape backs
  // out of whichever mode is armed. Both bail while a text field owns focus.
  useEffect(() => {
    if (!rotateMode && !cutMode && !areaMode) {
      return;
    }

    const handleKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA")) {
        return;
      }

      if (event.key === "Escape") {
        event.preventDefault();
        setRotateMode(false);
        setCutMode(false);
        setAreaMode(false);
        setAreaDraft(null);
        setPickPoint(null);
      } else if (event.key === "Enter" && rotateMode) {
        event.preventDefault();
        void commitCurrentRotation();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [rotateMode, cutMode, areaMode, commitCurrentRotation]);

  // --- pointer interaction on the photo -----------------------------------

  const handleStagePointerDown: React.PointerEventHandler<HTMLDivElement> = useCallback(
    (event) => {
      if (!naturalSize || !renderedRect) {
        return;
      }

      const stageRect = event.currentTarget.getBoundingClientRect();
      const localX = event.clientX - stageRect.left;
      const localY = event.clientY - stageRect.top;
      const natural = toNaturalPoint(localX, localY, renderedRect, naturalSize);
      if (!natural) {
        return;
      }

      // Scissors armed: this click is the segmentation seed, not a selection.
      if (areaMode) {
        event.preventDefault();
        setAreaDraft({ start: natural, current: natural });
        return;
      }

      if (cutMode) {
        event.preventDefault();
        setPickPoint(natural);
        setCutMode(false);
        void jobs.runSegment(
          Math.round(natural.x),
          Math.round(natural.y),
          verifyMode,
          { x: natural.x / naturalSize.width, y: natural.y / naturalSize.height },
        );
        return;
      }

      // While the selected object's 3D model is shown, its 2D cutout is hidden
      // and that region belongs to the (higher z-index) 3D frame instead.
      const hitOrder = buildHitTestOrder(jobs.objects, jobs.selectedObjectId).filter(
        (obj) => !(rotateMode && obj.objectId === jobs.selectedObjectId),
      );

      for (const obj of hitOrder) {
        const localObjX = natural.x - obj.offset.x;
        const localObjY = natural.y - obj.offset.y;
        const showOriginal = isShowingOriginal(obj);
        const baseBounds = effectiveCutoutBounds(obj, showOriginal);
        const bounds = effectiveDisplayBounds(obj, showOriginal);

        if (
          bounds &&
          (localObjX < bounds.left ||
            localObjX > bounds.right ||
            localObjY < bounds.top ||
            localObjY > bounds.bottom)
        ) {
          continue;
        }

        const samplePoint =
          baseBounds && obj.displayScale !== 1
            ? mapPointThroughInverseScale(
                { x: localObjX, y: localObjY },
                baseBounds,
                obj.displayScale,
              )
            : { x: localObjX, y: localObjY };

        if (
          sampleObjectAlpha(obj.objectId, samplePoint.x, samplePoint.y) <= ALPHA_HIT_THRESHOLD
        ) {
          continue;
        }

        event.preventDefault();
        document.body.classList.add("is-dragging-object");
        dragStateRef.current = {
          objectId: obj.objectId,
          pointerId: event.pointerId,
          startClientX: event.clientX,
          startClientY: event.clientY,
          startOffsetX: obj.offset.x,
          startOffsetY: obj.offset.y,
        };
        setIsDragging(true);
        selectObject(obj.objectId);
        return;
      }
      // No object under the pointer: keep the current selection unchanged.
    },
    [
      naturalSize,
      renderedRect,
      cutMode,
      areaMode,
      verifyMode,
      jobs.runSegment,
      jobs.objects,
      jobs.selectedObjectId,
      rotateMode,
      isShowingOriginal,
      sampleObjectAlpha,
      selectObject,
    ],
  );

  useEffect(() => {
    if (!areaDraft || !naturalSize || !renderedRect) {
      return;
    }
    const handleMove = (event: PointerEvent) => {
      const stage = stageRef.current;
      if (!stage) {
        return;
      }
      const stageRect = stage.getBoundingClientRect();
      const natural = toNaturalPoint(
        event.clientX - stageRect.left,
        event.clientY - stageRect.top,
        renderedRect,
        naturalSize,
      );
      if (!natural) {
        return;
      }
      setAreaDraft((prev) => (prev ? { ...prev, current: natural } : prev));
    };
    const handleUp = () => {
      setAreaDraft((prev) => {
        if (!prev) {
          return null;
        }
        const x0 = Math.round(Math.min(prev.start.x, prev.current.x));
        const y0 = Math.round(Math.min(prev.start.y, prev.current.y));
        const x1 = Math.round(Math.max(prev.start.x, prev.current.x));
        const y1 = Math.round(Math.max(prev.start.y, prev.current.y));
        if (x1 - x0 >= 8 && y1 - y0 >= 8 && !jobs.isBatching) {
          void jobs.runBatch({ kind: "box", x0, y0, x1, y1 });
        }
        return null;
      });
      setAreaMode(false);
    };
    window.addEventListener("pointermove", handleMove);
    window.addEventListener("pointerup", handleUp);
    return () => {
      window.removeEventListener("pointermove", handleMove);
      window.removeEventListener("pointerup", handleUp);
    };
  }, [areaDraft, naturalSize, renderedRect, jobs]);

  useEffect(() => {
    if (!isDragging) {
      return;
    }

    const handlePointerMove = (event: PointerEvent) => {
      const dragState = dragStateRef.current;
      const size = naturalSizeRef.current;
      const rect = renderedRectRef.current;
      if (!dragState || !size || !rect || dragState.pointerId !== event.pointerId) {
        return;
      }

      const scaleX = rect.width / size.width;
      const scaleY = rect.height / size.height;
      if (scaleX <= 0 || scaleY <= 0) {
        return;
      }

      const target = jobs.objects.find((o) => o.objectId === dragState.objectId);
      const bounds = target
        ? effectiveDisplayBounds(target, showOriginalIds.has(target.objectId))
        : null;

      // Mouse delta arrives in screen pixels; convert back to natural-image
      // pixels so drag behavior stays stable under responsive resize.
      const nextOffset = clampCutoutOffset(
        {
          x: dragState.startOffsetX + (event.clientX - dragState.startClientX) / scaleX,
          y: dragState.startOffsetY + (event.clientY - dragState.startClientY) / scaleY,
        },
        bounds,
        size,
      );

      jobs.updateOffset(dragState.objectId, nextOffset);
    };

    const finishDrag = (pointerId: number) => {
      if (dragStateRef.current?.pointerId !== pointerId) {
        return;
      }
      const draggedObjectId = dragStateRef.current.objectId;
      dragStateRef.current = null;
      setIsDragging(false);
      document.body.classList.remove("is-dragging-object");
      // A drag reposition never goes through useSessionJobs, so it's the one
      // mutation onMutated doesn't cover — capture the dashboard thumbnail
      // directly once the object settles.
      capturePreviewRef.current();

      // Persist the final position so it survives a session close/reopen.
      // previewInputsRef, not this effect's stale jobs.objects closure
      // (it only re-subscribes on isDragging, not on every object update),
      // always reflects the latest render's object state.
      const dragged = previewInputsRef.current.objects.find(
        (o) => o.objectId === draggedObjectId,
      );
      if (dragged?.uuid) {
        void setObjectOffset(dragged.uuid, dragged.offset.x, dragged.offset.y).catch(
          (err: unknown) => {
            console.warn("setObjectOffset failed; position won't survive reload.", err);
          },
        );

        if (smartPasteRef.current) {
          const size = previewInputsRef.current.naturalSize;
          if (size) {
            const bounds = effectiveDisplayBounds(
              dragged,
              previewInputsRef.current.showOriginalIds.has(dragged.objectId),
            );
            const placement = getObjectPlacementCenter(bounds, dragged.offset, size);
            setIsSmartPasting(true);
            void jobs
              .runSmartPasteAfterDrag(draggedObjectId, placement.x, placement.y)
              .then((applied) => {
                if (applied) {
                  capturePreviewRef.current();
                }
              })
              .finally(() => {
                setIsSmartPasting(false);
              });
          }
        }
      }
    };

    const handlePointerUp = (event: PointerEvent) => finishDrag(event.pointerId);

    window.addEventListener("pointermove", handlePointerMove);
    window.addEventListener("pointerup", handlePointerUp);
    window.addEventListener("pointercancel", handlePointerUp);

    return () => {
      window.removeEventListener("pointermove", handlePointerMove);
      window.removeEventListener("pointerup", handlePointerUp);
      window.removeEventListener("pointercancel", handlePointerUp);
      document.body.classList.remove("is-dragging-object");
    };
    // jobs.objects is intentionally omitted: handlePointerMove reads the target
    // object fresh on every move, but re-subscribing on every offset update
    // would tear the listeners down mid-drag. jobs.updateOffset is stable.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isDragging]);

  // --- derived render values ---------------------------------------------

  const visibleObjects = jobs.objects.filter((o) => !o.hidden);
  // While the selected object's 3D model is shown, its 2D cutout is skipped so
  // the 3D frame replaces it rather than stacking on top of it.
  const stageObjects = visibleObjects.filter(
    (obj) => !(rotateMode && obj.objectId === jobs.selectedObjectId),
  );

  const cutoutStyle = (
    obj: CutoutObject,
    showOriginal: boolean,
    zIndex: number,
  ): React.CSSProperties | undefined => {
    if (!naturalSize || !renderedRect) {
      return undefined;
    }

    const baseBounds = effectiveCutoutBounds(obj, showOriginal);
    const transformOrigin =
      baseBounds && naturalSize.width > 0 && naturalSize.height > 0
        ? `${(((baseBounds.left + baseBounds.right) / 2 / naturalSize.width) * 100).toFixed(4)}% ${(((baseBounds.top + baseBounds.bottom) / 2 / naturalSize.height) * 100).toFixed(4)}%`
        : "50% 50%";

    return {
      left: `${renderedRect.x + obj.offset.x * (renderedRect.width / naturalSize.width)}px`,
      top: `${renderedRect.y + obj.offset.y * (renderedRect.height / naturalSize.height)}px`,
      width: `${renderedRect.width}px`,
      height: `${renderedRect.height}px`,
      zIndex,
      transform: obj.displayScale !== 1 ? `scale(${obj.displayScale})` : undefined,
      transformOrigin,
    };
  };

  const rectStyle = (rect: {
    left: number;
    top: number;
    width: number;
    height: number;
  }): React.CSSProperties => ({
    position: "absolute",
    left: `${rect.left}px`,
    top: `${rect.top}px`,
    width: `${rect.width}px`,
    height: `${rect.height}px`,
  });

  // On-stage rect the selected object occupies (alpha bounds + drag offset).
  // Both the 3D frame and the selection frame are placed against this, so
  // neither jumps relative to the 2D cutout.
  const selectedRect =
    naturalSize && renderedRect && selectedObject
      ? getBoundsStageRect(
          effectiveDisplayBounds(selectedObject, isShowingOriginal(selectedObject)),
          selectedObject.offset,
          renderedRect,
          naturalSize,
        )
      : null;

  const model3DFrameStyle: React.CSSProperties | undefined = selectedRect
    ? {
        ...rectStyle(inflateAroundCenter(selectedRect, MODEL_3D_FRAME_PADDING)),
        // Above the interaction overlay so OrbitControls receive the pointer.
        zIndex: 200,
        pointerEvents: "auto",
        touchAction: "none",
      }
    : undefined;

  const photoSrc = jobs.backgroundSrc ?? originalSrc;

  const status = jobs.isBatching
    ? "batch cutting"
    : isSmartPasting
      ? "smart pasting"
    : jobs.isSegmenting
    ? "finding masks"
    : jobs.pendingJobs.length > 0
      ? `removing ${jobs.pendingJobs.length}`
      : jobs.objects.some((o) => o.rotation?.status === "pending")
        ? "rotating"
        : jobs.isDuplicating
          ? "copying"
          : jobs.isDeleting
            ? "deleting"
            : mapsWarming
              ? "preparing maps"
              : null;

  return (
    <div className="workspace">
      <Toolbar
        sessionName={sessionName}
        onSessionNameChange={setSessionName}
        onSessionNameKeyDown={handleSessionNameKeyDown}
        onBack={onExit}
        hasSelection={jobs.selectedObjectId !== null}
        cutMode={cutMode}
        onCut={handleCut}
        areaMode={areaMode}
        onArea={handleArea}
        batchBusy={jobs.isBatching}
        verifyMode={verifyMode}
        onVerifyModeChange={setVerifyMode}
        rotateMode={rotateMode}
        isPreparing3D={isPreparing3D}
        onRotate={handleRotate}
        isDuplicating={jobs.isDuplicating}
        onCopy={handleCopy}
        smartPaste={smartPaste}
        onToggleSmartPaste={handleToggleSmartPaste}
        isDeleting={jobs.isDeleting}
        onDeleteObject={handleDeleteObject}
        status={status}
      />

      <main
        ref={stageRef}
        className={`stage${cutMode || areaMode ? " is-picking" : ""}${isDragging ? " is-dragging" : ""}`}
      >
        {photoSrc ? (
          <>
            {/* The canvas edge, drawn on the letterbox — the photo's own
                boundary is the only frame in this screen. */}
            {renderedRect ? (
              <div
                className="stage-canvas-edge"
                style={rectStyle({
                  left: renderedRect.x,
                  top: renderedRect.y,
                  width: renderedRect.width,
                  height: renderedRect.height,
                })}
              />
            ) : null}

            <img src={photoSrc} alt="" className="stage-photo" onLoad={handleImageLoad} />

            {stageObjects.map((obj, index) => (
              <img
                key={obj.objectId}
                src={effectiveCutoutSrc(obj, isShowingOriginal(obj))}
                alt=""
                className="stage-cutout"
                style={cutoutStyle(
                  obj,
                  isShowingOriginal(obj),
                  obj.objectId === jobs.selectedObjectId ? stageObjects.length + 2 : index + 2,
                )}
                draggable={false}
              />
            ))}

            {/* Cutouts are full-size transparent PNGs, so a topmost overlay
                would swallow every click; this transparent layer owns pointer
                input and hit-tests against real alpha instead. */}
            <div className="stage-input" onPointerDown={handleStagePointerDown} />

            {areaDraft && renderedRect && naturalSize ? (
              <div
                className="stage-area-box"
                style={{
                  left: `${renderedRect.x + (Math.min(areaDraft.start.x, areaDraft.current.x) / naturalSize.width) * renderedRect.width}px`,
                  top: `${renderedRect.y + (Math.min(areaDraft.start.y, areaDraft.current.y) / naturalSize.height) * renderedRect.height}px`,
                  width: `${(Math.abs(areaDraft.current.x - areaDraft.start.x) / naturalSize.width) * renderedRect.width}px`,
                  height: `${(Math.abs(areaDraft.current.y - areaDraft.start.y) / naturalSize.height) * renderedRect.height}px`,
                }}
              />
            ) : null}

            {pickPoint && renderedRect && naturalSize ? (
              <span
                className="stage-pick-marker"
                style={{
                  left: `${renderedRect.x + (pickPoint.x / naturalSize.width) * renderedRect.width}px`,
                  top: `${renderedRect.y + (pickPoint.y / naturalSize.height) * renderedRect.height}px`,
                }}
              />
            ) : null}

            {rotateMode && glbData ? (
              <Model3DFrame ref={model3DFrameRef} glbData={glbData} style={model3DFrameStyle} />
            ) : null}

            {selectedRect ? (
              <div className="selection-frame" style={{ ...rectStyle(selectedRect), zIndex: 210 }}>
                <span className="selection-corner tl" />
                <span className="selection-corner tr" />
                <span className="selection-corner bl" />
                <span className="selection-corner br" />
              </div>
            ) : null}
          </>
        ) : (
          <div className="stage-message">
            {mapsWarming ? <span className="stage-warm-spinner tool-spinner" aria-hidden="true" /> : null}
            <p className="stage-message-line">Opening the session</p>
          </div>
        )}

        {mapsWarming && photoSrc ? (
          <div
            className="stage-warm-overlay"
            aria-live="polite"
            aria-busy="true"
            aria-label="Preparing depth and normal maps"
          >
            <span className="stage-warm-spinner tool-spinner" aria-hidden="true" />
            <p className="stage-message-line">Preparing depth maps</p>
          </div>
        ) : null}

        {rotateMode ? (
          <p className="stage-hint">Drag to orbit · Enter applies · Esc cancels</p>
        ) : areaMode ? (
          <p className="stage-hint">Drag a box around the furniture · Esc cancels</p>
        ) : cutMode ? (
          <p className="stage-hint">Click the object you want to cut out · Esc cancels</p>
        ) : null}

        {conflictNotices.notices.length > 0 ? (
          <div className="notice-stack">
            {conflictNotices.notices.map((notice) => (
              <div key={notice.id} className="notice">
                <span>{notice.message}</span>
                <button
                  type="button"
                  className="notice-dismiss"
                  onClick={() => conflictNotices.dismiss(notice.id)}
                  aria-label="Dismiss"
                >
                  ×
                </button>
              </div>
            ))}
          </div>
        ) : null}

        {imageId ? (
          <ObjectRail
            objects={jobs.objects}
            pending={jobs.pendingJobs}
            selectedObjectId={jobs.selectedObjectId}
            showOriginalIds={showOriginalIds}
            disabled={isPreparing3D}
            onSelectObject={selectObject}
            onToggleBatchUuid={(uuid, on) => {
              setBatchUuids((prev) => {
                const next = new Set(prev);
                if (on) {
                  next.add(uuid);
                } else {
                  next.delete(uuid);
                }
                return next;
              });
            }}
            batchUuids={batchUuids}
            onGenerate3D={() => {
              const uuids = [...batchUuids];
              if (uuids.length === 0) {
                const selected = jobs.objects.find((o) => o.objectId === jobs.selectedObjectId);
                if (selected?.uuid) {
                  uuids.push(selected.uuid);
                }
              }
              if (uuids.length > 0) {
                void jobs.runBatch({ kind: "objects", uuids });
              }
            }}
            generate3DDisabled={jobs.isBatching}
            onToggleHidden={handleToggleHidden}
            onToggleShowOriginal={handleToggleShowOriginal}
            onRenameObject={handleRenameObject}
          />
        ) : null}
      </main>

      {jobs.isChoosingMask ? (
        <MaskPickerModal
          masks={jobs.maskOptions}
          onSelect={handleMaskSelected}
          onClose={handleMaskPickerClosed}
        />
      ) : null}

      {pendingDeleteObject ? (
        <ConfirmDialog
          title="Delete this object?"
          body={
            <>
              <strong>{pendingDeleteObject.name ?? `Object ${pendingDeleteObject.objectId}`}</strong>{" "}
              will be removed for good. The background keeps its spot filled in — this can&rsquo;t
              be undone.
            </>
          }
          confirmLabel="Delete"
          destructive
          busy={jobs.isDeleting}
          onConfirm={() => void handleConfirmDeleteObject()}
          onCancel={handleCancelDeleteObject}
        />
      ) : null}

      {error ? (
        <div className="modal-backdrop" role="presentation" onClick={() => setError(null)}>
          <div
            className="modal is-error"
            role="alertdialog"
            aria-modal="true"
            aria-labelledby="error-title"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="modal-head">
              <h2 id="error-title">Request failed</h2>
              <button type="button" className="modal-close" onClick={() => setError(null)}>
                Close
              </button>
            </div>
            <pre className="modal-body">{error}</pre>
          </div>
        </div>
      ) : null}
    </div>
  );
};
