import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { withAuthParam } from "../../api/authToken";
import {
  API_BASE_URL,
  ApiError,
  deleteJob,
  getSessionObjects,
  getUidCacheStatus,
  redoSessionBackground,
  setSessionName as saveSessionName,
  undoSessionBackground,
  warmSessionMaps,
} from "../../api/images";
import { boxBoundsFromDraft, useAreaSelect } from "../../hooks/useAreaSelect";
import { useArmedBatch } from "../../hooks/useArmedBatch";
import { useLassoSelect, type LassoDraft } from "../../hooks/useLassoSelect";
import { useConflictNotices, type ConflictContext } from "../../hooks/useConflictNotices";
import { useDashboardPreview } from "../../hooks/useDashboardPreview";
import { useHitTesting } from "../../hooks/useHitTesting";
import { useObjectDrag } from "../../hooks/useObjectDrag";
import { useObjectResize } from "../../hooks/useObjectResize";
import { useRotationController } from "../../hooks/useRotationController";
import { useSessionJobs, type JobErrorContext } from "../../hooks/useSessionJobs";
import { useSessionSync } from "../../hooks/useSessionSync";
import type { BatchSource, VerifyMode } from "../../types/api";
import type { ArmedJobSource } from "../../types/armedBatch";
import {
  effectiveCutoutBounds,
  effectiveCutoutSrc,
  effectiveDisplayBounds,
  hasCloneSiblings,
  isDrawnOnStage,
  type ClickPosition,
  type CutoutObject,
} from "../../types/session";
import {
  ALPHA_HIT_THRESHOLD,
  batchBoxStageStyle,
  buildHitTestOrder,
  compositePreviewOntoCanvas,
  getBoundsStageRect,
  getContainedImageRect,
  inflateAroundCenter,
  inflateBounds,
  mapPointThroughInverseScale,
  toNaturalPoint,
  type Rect,
  type ResizeHandle,
  type Size,
} from "../../utils/stageGeometry";
import {
  composeStageSnapshot,
  snapshotDownloadFilename,
  triggerBlobDownload,
} from "../../utils/preview";
import { rasterizeEraseMask } from "../../utils/lassoMask";
import { ConfirmDialog } from "../widgets/ConfirmDialog";
import { MaskPickerModal } from "../widgets/MaskPickerModal";
import { MODEL_3D_FRAME_PADDING, Model3DFrame } from "../widgets/Model3DFrame";
import { BatchQueuePanel } from "../workspace/BatchQueuePanel";
import { ObjectRail } from "../workspace/ObjectRail";
import { Toolbar } from "../workspace/Toolbar";

const MAX_SEGMENT_SEEDS = 8;

function lassoPolygonStagePoints(
  polygon: ClickPosition[],
  renderedRect: Rect,
  naturalSize: Size,
): string {
  return polygon
    .map((point) => {
      const x = renderedRect.x + (point.x / naturalSize.width) * renderedRect.width;
      const y = renderedRect.y + (point.y / naturalSize.height) * renderedRect.height;
      return `${x},${y}`;
    })
    .join(" ");
}

const errorMessage = (error: unknown, fallback: string): string =>
  error instanceof Error ? error.message : fallback;

// Module-scope, not component state: WorkspaceScreen fully unmounts on every
// dashboard round-trip (key={uid}), so a ref/state here would reset each time
// and re-fire the warm-maps request + its full-screen spinner on every
// reentry even though the backend already cached the maps last visit.
const warmedSessionIds = new Set<string>();

export interface WorkspaceScreenProps {
  /** Session to edit. The workspace never picks one itself. */
  uid: string;
  onExit: () => void;
}

/**
 * The editor: a photo at full size with a permanent toolbar above it and the
 * object rail parked in the right edge. Session-level concerns (choosing,
 * creating, deleting) belong to the dashboard, so none of them appear here.
 *
 * Several stage-interaction concerns live in dedicated hooks (hooks/) rather
 * than inline: alpha-precise hit testing (useHitTesting), drag-to-reposition
 * (useObjectDrag), the drag-a-box batch select (useAreaSelect), the 3D
 * angle-picker lifecycle (useRotationController), and the debounced dashboard
 * thumbnail capture (useDashboardPreview). This screen wires them together
 * and owns everything else: tool arming, selection, pointer-down dispatch,
 * and the stage/toolbar/rail render.
 */
export const WorkspaceScreen: React.FC<WorkspaceScreenProps> = ({ uid, onExit }) => {
  const stageRef = useRef<HTMLDivElement>(null);
  const renderedRectRef = useRef<Rect | null>(null);

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
  // pendingSeeds: foreground clicks in natural-image pixels — shown while
  // collecting multi-point seeds and kept on screen until the mask picker closes.
  const [cutMode, setCutMode] = useState(false);
  const [eraserMode, setEraserMode] = useState(false);
  const [areaMode, setAreaMode] = useState(false);
  const [areaDraft, setAreaDraft] = useState<{
    start: ClickPosition;
    current: ClickPosition;
  } | null>(null);
  const [pendingBatchSource, setPendingBatchSource] = useState<BatchSource | null>(null);
  const [batchUuids, setBatchUuids] = useState<Set<string>>(new Set());
  const [pendingSeeds, setPendingSeeds] = useState<ClickPosition[]>([]);
  const [lassoDraft, setLassoDraft] = useState<LassoDraft | null>(null);
  const [pendingEraseRegions, setPendingEraseRegions] = useState<ClickPosition[][]>([]);
  const [multiPoint, setMultiPoint] = useState(false);
  const [verifyMode, setVerifyMode] = useState<VerifyMode>("manual");

  // Per-object: show the pristine cutout instead of the rotated result.
  const [showOriginalIds, setShowOriginalIds] = useState<ReadonlySet<number>>(new Set());

  const [smartPaste, setSmartPaste] = useState(false);
  const [scaleByPov, setScaleByPov] = useState(true);
  const [smartRotate, setSmartRotate] = useState(true);
  const [autoGenerate3d, setAutoGenerate3d] = useState(false);
  const [canUndo, setCanUndo] = useState(false);
  const [canRedo, setCanRedo] = useState(false);
  const [historyBusy, setHistoryBusy] = useState(false);
  const [isSavingSnapshot, setIsSavingSnapshot] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Object id awaiting delete confirmation. Deletion is permanent (the
  // background keeps its inpainted hole), so the trash button arms this
  // instead of deleting directly.
  const [pendingDeleteObjectId, setPendingDeleteObjectId] = useState<number | null>(null);
  const stageInputRef = useRef<HTMLDivElement | null>(null);

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
  const applyHistoryFlags = useCallback((flags: { canUndo: boolean; canRedo: boolean }) => {
    setCanUndo(flags.canUndo);
    setCanRedo(flags.canRedo);
  }, []);
  const refreshHistoryFlags = useCallback(async () => {
    try {
      const status = await getUidCacheStatus(uid);
      applyHistoryFlags({ canUndo: status.can_undo, canRedo: status.can_redo });
    } catch {
      // Non-fatal — toolbar buttons stay at their last known state.
    }
  }, [uid, applyHistoryFlags]);
  const handleMutated = useCallback(() => {
    // A mutation (inpaint, most commonly) can change the canvas the depth/
    // normal maps were warmed for — forget the "already warm" mark and
    // re-warm right away in the background. Deferring the re-warm to the
    // next session entry (the old behavior) meant the recompute instead blocked
    // that later entry behind the full-screen "Preparing depth maps" overlay,
    // which read as "regenerating for no reason" since the edit that actually
    // invalidated the cache had happened a session ago.
    warmedSessionIds.delete(uid);
    void warmSessionMaps(uid)
      .then(() => {
        warmedSessionIds.add(uid);
      })
      .catch((err: unknown) => {
        console.warn("Background session map re-warm failed (non-fatal).", err);
      });
    recordLocalMutationRef.current();
    capturePreviewRef.current();
    void refreshHistoryFlags();
  }, [uid, refreshHistoryFlags]);

  // A queued segment/inpaint job resolving to "conflict" (its mask/click
  // overlapped an in-flight removal) reuses the same inline notice a
  // synchronous 409 used to produce, by constructing the ApiError shape
  // conflictNotices.notify expects.
  const handleJobConflict = useCallback(
    (job: { kind: string; error?: string | null }) => {
      const context: ConflictContext = job.kind === "segment" ? "segment" : "inpaint";
      try {
        conflictNotices.notify(new ApiError(409, job.error ?? ""), context);
      } catch (rethrown) {
        setError(errorMessage(rethrown, "Unexpected error."));
      }
    },
    [conflictNotices],
  );

  const jobs = useSessionJobs(imageId, {
    onError: handleJobError,
    onMutated: handleMutated,
    onConflict: handleJobConflict,
    autoGenerate3d,
  });

  const armedBatch = useArmedBatch({
    imageId,
    naturalSize,
    autoGenerate3d,
    onMutated: handleMutated,
    onError: handleJobError,
  });

  const sync = useSessionSync({
    imageId,
    hasPendingWork: jobs.hasPendingWork,
    objects: jobs.objects,
    setObjects: jobs.setObjects,
    selectedObjectId: jobs.selectedObjectId,
    setSelectedObjectId: jobs.setSelectedObjectId,
    setBackgroundSrc: jobs.setBackgroundSrc,
    applyServerJobs: jobs.applyServerJobs,
    isDeleted: jobs.isObjectDeleted,
    applyHistoryFlags,
  });

  useEffect(() => {
    recordLocalMutationRef.current = sync.recordLocalMutation;
  }, [sync.recordLocalMutation]);

  // Polling stops when hasPendingWork flips false — often the same tick the
  // erase/inpaint job lands. Reconcile may have already run, but if polling
  // ended before needs_refresh was seen, refresh history flags once here.
  const hadPendingWorkRef = useRef(jobs.hasPendingWork);
  useEffect(() => {
    if (hadPendingWorkRef.current && !jobs.hasPendingWork) {
      void refreshHistoryFlags();
      recordLocalMutationRef.current();
    }
    hadPendingWorkRef.current = jobs.hasPendingWork;
  }, [jobs.hasPendingWork, refreshHistoryFlags]);

  const selectedObject = jobs.objects.find((o) => o.objectId === jobs.selectedObjectId) ?? null;

  const isShowingOriginal = useCallback(
    (obj: { objectId: number }) => showOriginalIds.has(obj.objectId),
    [showOriginalIds],
  );

  const clearShowOriginal = useCallback((objectId: number) => {
    setShowOriginalIds((prev) => {
      if (!prev.has(objectId)) {
        return prev;
      }
      const next = new Set(prev);
      next.delete(objectId);
      return next;
    });
  }, []);

  // --- session map warm ----------------------------------------------------

  const startMapsWarm = useCallback(() => {
    if (warmedSessionIds.has(uid)) {
      setMapsWarming(false);
      return;
    }
    const generation = ++mapsWarmGenerationRef.current;
    setMapsWarming(true);
    void warmSessionMaps(uid)
      .then(() => {
        warmedSessionIds.add(uid);
      })
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

  const handleToggleScaleByPov = useCallback(() => {
    setScaleByPov((on) => !on);
  }, []);

  const handleToggleSmartRotate = useCallback(() => {
    setSmartRotate((on) => !on);
  }, []);

  const runSmartPasteAfterDrag = useCallback(
    (objectId: number, x: number, y: number) =>
      jobs.runSmartPasteAfterDrag(objectId, x, y, { scaleByPov, smartRotate }),
    [jobs.runSmartPasteAfterDrag, scaleByPov, smartRotate],
  );

  // --- session load -------------------------------------------------------

  useEffect(() => {
    let cancelled = false;
    setOriginalSrc(withAuthParam(`${API_BASE_URL}/images/${uid}/original`));
    startMapsWarm();

    const load = async () => {
      try {
        const status = await getUidCacheStatus(uid);
        if (cancelled) {
          return;
        }
        setSessionName(status.name ?? uid);
        setCanUndo(status.can_undo);
        setCanRedo(status.can_redo);

        if (status.has_background) {
          jobs.setBackgroundSrc(withAuthParam(`${API_BASE_URL}/images/${uid}/background`));
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
    renderedRectRef.current = renderedRect;
  }, [renderedRect]);

  // --- dashboard thumbnail --------------------------------------------------

  const capturePreview = useDashboardPreview(uid, {
    // Falls back to the original photo so a session never inpainted yet
    // still gets a thumbnail rather than composing nothing.
    backgroundSrc: jobs.backgroundSrc ?? originalSrc,
    objects: jobs.objects,
    naturalSize,
    showOriginalIds,
  });
  useEffect(() => {
    capturePreviewRef.current = capturePreview;
  }, [capturePreview]);

  // --- alpha-precise hit testing -------------------------------------------

  const { sampleObjectAlpha } = useHitTesting(jobs.objects, isShowingOriginal);

  // --- 3D angle picker ------------------------------------------------------

  const rotation = useRotationController({
    imageId,
    selectedObjectId: jobs.selectedObjectId,
    selectedObject,
    naturalSize,
    jobsList: jobs.jobs,
    commitRotation: jobs.commitRotation,
    setObjects: jobs.setObjects,
    setSelectedObjectId: jobs.setSelectedObjectId,
    clearShowOriginal,
    disarmOtherTools: () => setCutMode(false),
    onError: (err) => setError(errorMessage(err, "Unexpected 3D generation error.")),
  });

  // --- drag-to-reposition ----------------------------------------------------

  const objectDrag = useObjectDrag({
    objects: jobs.objects,
    naturalSize,
    renderedRect,
    showOriginalIds,
    smartPasteEnabled: smartPaste,
    updateOffset: jobs.updateOffset,
    runSmartPasteAfterDrag,
    onSettled: capturePreview,
  });

  const clientToNatural = useCallback(
    (clientX: number, clientY: number) => {
      if (!naturalSize || !renderedRect || !stageInputRef.current) {
        return null;
      }
      const stageRect = stageInputRef.current.getBoundingClientRect();
      return toNaturalPoint(
        clientX - stageRect.left,
        clientY - stageRect.top,
        renderedRect,
        naturalSize,
      );
    },
    [naturalSize, renderedRect],
  );

  const objectResize = useObjectResize({
    objects: jobs.objects,
    showOriginalIds,
    clientToNatural,
    naturalSize,
    updateDisplayScale: jobs.updateDisplayScale,
    onError: (err) => setError(errorMessage(err, "Failed to save object size.")),
    onSettled: capturePreview,
  });

  // --- drag-a-box batch select (hook wired after handlers below) -----------

  const selectObject = useCallback(
    (objectId: number | null) => {
      jobs.setSelectedObjectId(objectId);
      // Rotation is scoped to whichever object is selected — switching away
      // closes the angle picker.
      rotation.setRotateMode(false);
      setCutMode(false);
      setPendingSeeds([]);
    },
    [jobs.setSelectedObjectId, rotation.setRotateMode],
  );

  const handleToggleHidden = useCallback(
    (objectId: number) => {
      const wasSelected = jobs.selectedObjectId === objectId;
      jobs.toggleHidden(objectId);
      if (wasSelected) {
        rotation.setRotateMode(false);
      }
    },
    [jobs.selectedObjectId, jobs.toggleHidden, rotation.setRotateMode],
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

  const fireSegmentFromSeeds = useCallback(
    (seeds: ClickPosition[]) => {
      if (seeds.length === 0) {
        return;
      }
      if (armedBatch.batchModeRef.current) {
        armedBatch.appendClicks(seeds);
        setPendingSeeds([]);
        setCutMode(false);
        return;
      }
      const rounded = seeds.map((seed) => ({
        x: Math.round(seed.x),
        y: Math.round(seed.y),
      }));
      // Clear seeds now that the job is submitted — leaving them set kept the
      // checkmark armed and Enter/checkmark live, letting either resubmit the
      // same seeds as a second job, and left the numbered marker on screen
      // (visible even for a single-point click, which fires through here too).
      setPendingSeeds([]);
      setCutMode(false);
      jobs.runSegment(rounded[0].x, rounded[0].y, verifyMode, rounded);
    },
    [armedBatch.appendClicks, armedBatch.batchModeRef, jobs.runSegment, verifyMode],
  );

  const handleCut = useCallback(() => {
    rotation.setRotateMode(false);
    setAreaMode(false);
    setEraserMode(false);
    setLassoDraft(null);
    setPendingEraseRegions([]);
    if (!armedBatch.batchMode) {
      setPendingBatchSource(null);
    }
    setPendingSeeds([]);
    setCutMode((armed) => !armed);
  }, [armedBatch.batchMode, rotation.setRotateMode]);

  const handleEraser = useCallback(() => {
    rotation.setRotateMode(false);
    setCutMode(false);
    setAreaMode(false);
    if (!armedBatch.batchMode) {
      setPendingBatchSource(null);
    }
    setPendingSeeds([]);
    setEraserMode((armed) => {
      if (armed) {
        setLassoDraft(null);
        setPendingEraseRegions([]);
      }
      return !armed;
    });
  }, [armedBatch.batchMode, rotation.setRotateMode]);

  const handleArea = useCallback(() => {
    rotation.setRotateMode(false);
    setCutMode(false);
    setEraserMode(false);
    setLassoDraft(null);
    setPendingEraseRegions([]);
    setPendingSeeds([]);
    setAreaMode((armed) => !armed);
  }, [rotation.setRotateMode]);

  const handleToggleBatchMode = useCallback(() => {
    armedBatch.setBatchMode((on) => !on);
  }, [armedBatch.setBatchMode]);

  const handleToggleMultiPoint = useCallback(() => {
    setMultiPoint((on) => !on);
  }, []);

  const handleUndoLastSeed = useCallback(() => {
    setPendingSeeds((prev) => (prev.length > 0 ? prev.slice(0, -1) : prev));
  }, []);

  const handleBoxReady = useCallback(
    (source: BatchSource) => {
      if (armedBatch.batchModeRef.current && source.kind === "box") {
        armedBatch.appendJob(source);
        return;
      }
      setPendingBatchSource(source);
    },
    [armedBatch.appendJob, armedBatch.batchModeRef],
  );

  const submitEraseRegions = useCallback(
    (regions: ClickPosition[][]) => {
      if (!naturalSize || regions.length === 0) {
        return;
      }
      if (armedBatch.batchModeRef.current) {
        armedBatch.appendJob({ kind: "lasso", regions });
        setPendingEraseRegions([]);
        setEraserMode(false);
        return;
      }
      const maskB64 = rasterizeEraseMask(naturalSize.width, naturalSize.height, regions);
      if (!maskB64) {
        return;
      }
      setPendingEraseRegions([]);
      setEraserMode(false);
      jobs.runErase(maskB64);
    },
    [armedBatch.appendJob, armedBatch.batchModeRef, jobs.runErase, naturalSize],
  );

  const handleLassoComplete = useCallback(
    (polygon: ClickPosition[], shiftKey: boolean) => {
      if (armedBatch.batchModeRef.current) {
        armedBatch.appendJob({ kind: "lasso", regions: [polygon] });
        return;
      }
      if (shiftKey) {
        setPendingEraseRegions((prev) => [...prev, polygon]);
        return;
      }
      const regions =
        pendingEraseRegions.length > 0 ? [...pendingEraseRegions, polygon] : [polygon];
      submitEraseRegions(regions);
    },
    [armedBatch.appendJob, armedBatch.batchModeRef, pendingEraseRegions, submitEraseRegions],
  );

  const handleSubmitPendingBatch = useCallback(() => {
    if (armedBatch.batchModeRef.current) {
      if (pendingSeeds.length > 0) {
        armedBatch.appendClicks(pendingSeeds);
        setPendingSeeds([]);
      }
      void armedBatch.approve();
      return;
    }
    if (pendingEraseRegions.length > 0) {
      submitEraseRegions(pendingEraseRegions);
      return;
    }
    if (pendingSeeds.length > 0) {
      fireSegmentFromSeeds(pendingSeeds);
      return;
    }
    if (!pendingBatchSource || jobs.isBatching) {
      return;
    }
    const source = pendingBatchSource;
    setPendingBatchSource(null);
    void jobs.runBatch(source);
  }, [
    armedBatch.appendClicks,
    armedBatch.approve,
    armedBatch.batchModeRef,
    fireSegmentFromSeeds,
    jobs.isBatching,
    jobs.runBatch,
    pendingBatchSource,
    pendingEraseRegions,
    pendingSeeds,
    submitEraseRegions,
  ]);

  useLassoSelect({
    lassoDraft,
    setLassoDraft,
    naturalSize,
    renderedRect,
    stageRef,
    onLassoComplete: handleLassoComplete,
  });

  useAreaSelect({
    areaDraft,
    setAreaDraft,
    setAreaMode,
    naturalSize,
    renderedRect,
    stageRef,
    onBoxReady: handleBoxReady,
  });

  const handleMaskSelected = useCallback(
    (maskId: string) => {
      if (jobs.currentSegmentJobId) {
        jobs.selectMask(jobs.currentSegmentJobId, maskId);
      }
      setPendingSeeds([]);
    },
    [jobs.selectMask, jobs.currentSegmentJobId],
  );

  const handleMaskPickerDeferred = useCallback(() => {
    jobs.deferMaskPicker();
    setPendingSeeds([]);
  }, [jobs.deferMaskPicker]);

  const handleMaskPickerDiscarded = useCallback(() => {
    const jobId = jobs.currentSegmentJobId;
    if (!jobId) {
      return;
    }
    void jobs.discardMaskPicker(jobId);
    setPendingSeeds([]);
  }, [jobs.currentSegmentJobId, jobs.discardMaskPicker]);

  const handleCopy = useCallback(() => {
    if (jobs.selectedObjectId === null) {
      return;
    }
    if (!selectedObject?.uuid) {
      setError("This object is from an older room and can't be duplicated.");
      return;
    }
    void jobs.duplicateObject(jobs.selectedObjectId);
  }, [jobs.duplicateObject, jobs.selectedObjectId, selectedObject]);

  const requestDeleteObject = useCallback(
    (objectId: number) => {
      const target = jobs.objects.find((o) => o.objectId === objectId);
      if (!target?.uuid) {
        setError("This object is from an older room and can't be deleted.");
        return;
      }
      rotation.setRotateMode(false);
      if (hasCloneSiblings(target, jobs.objects)) {
        void jobs.deleteObject(objectId);
        return;
      }
      setPendingDeleteObjectId(objectId);
    },
    [jobs.deleteObject, jobs.objects, rotation.setRotateMode],
  );

  const handleDeleteObject = useCallback(() => {
    if (jobs.selectedObjectId === null) {
      return;
    }
    requestDeleteObject(jobs.selectedObjectId);
  }, [jobs.selectedObjectId, requestDeleteObject]);

  const handleClearObject3d = useCallback(
    (objectId: number) => {
      if (jobs.selectedObjectId === objectId) {
        rotation.setRotateMode(false);
      }
      void jobs.clearObject3d(objectId);
    },
    [jobs.clearObject3d, jobs.selectedObjectId, rotation.setRotateMode],
  );

  const handleResetObjectChanges = useCallback(
    (objectId: number) => {
      if (jobs.selectedObjectId === objectId) {
        rotation.setRotateMode(false);
      }
      setShowOriginalIds((prev) => {
        if (!prev.has(objectId)) {
          return prev;
        }
        const next = new Set(prev);
        next.delete(objectId);
        return next;
      });
      void jobs.resetObjectChanges(objectId);
    },
    [jobs.resetObjectChanges, jobs.selectedObjectId, rotation.setRotateMode],
  );

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
        setError(errorMessage(nameError, "Failed to save room name."));
      }
    },
    [imageId, sessionName],
  );

  // Enter commits the rotation (same as pressing rotate again); Escape backs
  // out of whichever mode is armed. Both bail while a text field owns focus.
  useEffect(() => {
    if (
      !jobs.isChoosingMask &&
      !rotation.rotateMode &&
      !cutMode &&
      !areaMode &&
      !eraserMode &&
      pendingSeeds.length === 0 &&
      pendingEraseRegions.length === 0
    ) {
      return;
    }

    const handleKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA")) {
        return;
      }

      if (event.key === "Escape") {
        event.preventDefault();
        if (jobs.isChoosingMask) {
          handleMaskPickerDeferred();
          return;
        }
        rotation.setRotateMode(false);
        setCutMode(false);
        setAreaMode(false);
        setEraserMode(false);
        setAreaDraft(null);
        setLassoDraft(null);
        setPendingBatchSource(null);
        setPendingSeeds([]);
        setPendingEraseRegions([]);
      } else if (event.key === "Enter" && rotation.rotateMode) {
        event.preventDefault();
        void rotation.commitCurrentRotation();
      } else if (event.key === "Enter" && pendingEraseRegions.length > 0) {
        event.preventDefault();
        submitEraseRegions(pendingEraseRegions);
      } else if (event.key === "Enter" && pendingSeeds.length > 0) {
        event.preventDefault();
        if (armedBatch.batchModeRef.current) {
          armedBatch.appendClicks(pendingSeeds);
          setPendingSeeds([]);
        } else {
          fireSegmentFromSeeds(pendingSeeds);
        }
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [
    jobs.isChoosingMask,
    handleMaskPickerDeferred,
    rotation.rotateMode,
    cutMode,
    areaMode,
    eraserMode,
    pendingSeeds,
    pendingEraseRegions,
    fireSegmentFromSeeds,
    submitEraseRegions,
    armedBatch.appendClicks,
    armedBatch.batchModeRef,
    rotation.commitCurrentRotation,
    rotation.setRotateMode,
  ]);

  // --- pointer interaction on the photo -----------------------------------

  const handleStagePointerDown: React.PointerEventHandler<HTMLDivElement> = useCallback(
    (event) => {
      if (!naturalSize || !renderedRect || objectResize.isResizing) {
        return;
      }

      const stageRect = event.currentTarget.getBoundingClientRect();
      const localX = event.clientX - stageRect.left;
      const localY = event.clientY - stageRect.top;
      const natural = toNaturalPoint(localX, localY, renderedRect, naturalSize);
      if (!natural) {
        return;
      }

      // Eraser armed: pointer-down starts a freehand lasso, not a selection.
      if (eraserMode) {
        event.preventDefault();
        setLassoDraft({ points: [natural] });
        return;
      }

      // Scissors armed: this click is the segmentation seed, not a selection.
      if (areaMode) {
        event.preventDefault();
        setAreaDraft({ start: natural, current: natural });
        return;
      }

      // Shift+click arms scissors and drops a seed — no need to press scissors first.
      if (event.shiftKey && !cutMode && !rotation.rotateMode && !eraserMode) {
        event.preventDefault();
        setCutMode(true);
        if (pendingSeeds.length >= MAX_SEGMENT_SEEDS) {
          return;
        }
        setPendingSeeds((prev) => [...prev, natural]);
        return;
      }

      if (cutMode) {
        event.preventDefault();
        const collectMode = multiPoint || event.shiftKey;

        if (collectMode) {
          if (pendingSeeds.length >= MAX_SEGMENT_SEEDS) {
            return;
          }
          setPendingSeeds((prev) => [...prev, natural]);
          return;
        }

        // Single-point mode: stage the seed instead of firing immediately —
        // shows where the click landed and lets a re-click move it before
        // the checkmark/Enter actually submits.
        setPendingSeeds([natural]);
        return;
      }

      // While the selected object's 3D model is shown, its 2D cutout is hidden
      // and that region belongs to the (higher z-index) 3D frame instead.
      const hitOrder = buildHitTestOrder(jobs.objects, jobs.selectedObjectId).filter(
        (obj) => !(rotation.rotateMode && obj.objectId === jobs.selectedObjectId),
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
        objectDrag.beginDrag(obj.objectId, event.pointerId, event.clientX, event.clientY, obj.offset);
        selectObject(obj.objectId);
        return;
      }
      // No object under the pointer: clicking empty stage area clears selection.
      if (jobs.selectedObjectId !== null) {
        event.preventDefault();
        selectObject(null);
      }
    },
    [
      naturalSize,
      renderedRect,
      cutMode,
      eraserMode,
      areaMode,
      multiPoint,
      pendingSeeds.length,
      jobs.objects,
      jobs.selectedObjectId,
      rotation.rotateMode,
      isShowingOriginal,
      sampleObjectAlpha,
      objectDrag,
      objectResize.isResizing,
      selectObject,
    ],
  );

  // --- derived render values ---------------------------------------------

  const visibleObjects = jobs.objects.filter(isDrawnOnStage);
  // While the selected object's 3D model is shown, its 2D cutout is skipped so
  // the 3D frame replaces it rather than stacking on top of it.
  const stageObjects = visibleObjects.filter(
    (obj) => !(rotation.rotateMode && obj.objectId === jobs.selectedObjectId),
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

  const canResize =
    Boolean(selectedObject?.uuid) &&
    !rotation.rotateMode &&
    !cutMode &&
    !objectDrag.isDragging &&
    !objectResize.isResizing;

  const handleResizePointerDown = useCallback(
    (handle: ResizeHandle) => (event: React.PointerEvent<HTMLElement>) => {
      event.stopPropagation();
      event.preventDefault();
      if (!canResize || jobs.selectedObjectId === null) {
        return;
      }
      const natural = clientToNatural(event.clientX, event.clientY);
      if (!natural) {
        return;
      }
      event.currentTarget.setPointerCapture(event.pointerId);
      objectResize.beginResize(jobs.selectedObjectId, handle, event.pointerId, natural);
    },
    [canResize, clientToNatural, jobs.selectedObjectId, objectResize],
  );

  const photoSrc = jobs.backgroundSrc ?? originalSrc;

  const displayedBatchBox = areaDraft
    ? boxBoundsFromDraft(areaDraft)
    : pendingBatchSource?.kind === "box"
      ? pendingBatchSource
      : null;
  const batchBoxIsPending = displayedBatchBox !== null && pendingBatchSource !== null && !areaDraft;

  const armedBoxes = useMemo(() => {
    const boxes: {
      id: string;
      box: Extract<ArmedJobSource, { kind: "box" }>;
      selected: boolean;
    }[] = [];
    for (const job of armedBatch.jobs) {
      if (job.source.kind === "box") {
        boxes.push({
          id: job.id,
          box: job.source,
          selected: job.id === armedBatch.selectedJobId,
        });
      }
    }
    return boxes;
  }, [armedBatch.jobs, armedBatch.selectedJobId]);

  const armedLassos = useMemo(() => {
    const lassos: {
      id: string;
      polygon: ClickPosition[];
      selected: boolean;
    }[] = [];
    for (const job of armedBatch.jobs) {
      if (job.source.kind !== "lasso") {
        continue;
      }
      job.source.regions.forEach((polygon, index) => {
        lassos.push({
          id: `${job.id}-${index}`,
          polygon,
          selected: job.id === armedBatch.selectedJobId,
        });
      });
    }
    return lassos;
  }, [armedBatch.jobs, armedBatch.selectedJobId]);

  const armedSeeds = useMemo(() => {
    const seeds: {
      id: string;
      point: ClickPosition;
      selected: boolean;
    }[] = [];
    for (const job of armedBatch.jobs) {
      if (job.source.kind !== "clicks") {
        continue;
      }
      job.source.points.forEach((point, index) => {
        seeds.push({
          id: `${job.id}-${index}`,
          point,
          selected: job.id === armedBatch.selectedJobId,
        });
      });
    }
    return seeds;
  }, [armedBatch.jobs, armedBatch.selectedJobId]);

  const activeJobs = jobs.jobs.filter((job) => job.status === "queued" || job.status === "running");
  const segmentingCount = activeJobs.filter((job) => job.kind === "segment").length;
  const removingCount = activeJobs.filter((job) => job.kind === "inpaint").length;
  const erasingCount = activeJobs.filter((job) => job.kind === "erase").length;
  const canvasWorkCount = removingCount + erasingCount;

  const status = armedBatch.isApproving
    ? "approving batch"
    : jobs.isBatching
    ? "batch cutting"
    : objectDrag.isSmartPasting
      ? "smart pasting"
      : segmentingCount > 0
        ? `finding masks${segmentingCount > 1 ? ` (${segmentingCount})` : ""}`
        : canvasWorkCount > 0
          ? `removing ${canvasWorkCount}`
      : jobs.objects.some((o) => o.rotation?.status === "pending")
        ? "rotating"
        : jobs.isDuplicating
          ? "copying"
          : jobs.isDeleting
            ? "deleting"
            : mapsWarming
              ? "preparing maps"
              : null;

  const handleDismissJob = useCallback((jobId: string) => {
    jobs.setJobs((prev) => prev.filter((job) => job.job_id !== jobId));
    void deleteJob(jobId).catch(() => {
      // Non-fatal — worst case the entry reappears on the next sync tick.
    });
  }, [jobs.setJobs]);

  const runHistoryStep = useCallback(
    async (direction: "undo" | "redo") => {
      if (historyBusy || jobs.hasPendingWork) {
        return;
      }
      setHistoryBusy(true);
      try {
        if (direction === "undo") {
          await undoSessionBackground(uid);
        } else {
          await redoSessionBackground(uid);
        }
        handleMutated();
      } catch (stepError) {
        setError(errorMessage(stepError, `Failed to ${direction} room history.`));
      } finally {
        setHistoryBusy(false);
      }
    },
    [historyBusy, jobs.hasPendingWork, uid, handleMutated],
  );

  const handleBacktrack = useCallback(() => {
    void runHistoryStep("undo");
  }, [runHistoryStep]);

  const handleForward = useCallback(() => {
    void runHistoryStep("redo");
  }, [runHistoryStep]);

  const handleDownloadSnapshot = useCallback(async () => {
    const backgroundSrc = jobs.backgroundSrc ?? originalSrc;
    if (!naturalSize || !backgroundSrc || isSavingSnapshot) {
      return;
    }

    setIsSavingSnapshot(true);
    try {
      const selectedId = jobs.selectedObjectId;
      const withoutSelected =
        selectedId !== null
          ? visibleObjects.filter((obj) => obj.objectId !== selectedId)
          : visibleObjects;
      const selected =
        selectedId !== null ? visibleObjects.find((obj) => obj.objectId === selectedId) : undefined;
      const paintOrder = selected ? [...withoutSelected, selected] : withoutSelected;

      const layers = await Promise.all(
        paintOrder.map(async (obj) => {
          const showOriginal = isShowingOriginal(obj);
          const isRotatePickerTarget =
            rotation.rotateMode && obj.objectId === selectedId;

          if (isRotatePickerTarget) {
            const capture = rotation.model3DFrameRef.current?.capture();
            if (!capture) {
              return null;
            }
            const bounds = obj.cutoutAlphaBounds
              ? inflateBounds(obj.cutoutAlphaBounds, MODEL_3D_FRAME_PADDING)
              : null;
            const src = await compositePreviewOntoCanvas(
              capture.snapshotDataUrl,
              bounds,
              naturalSize,
            );
            return {
              src,
              offset: obj.offset,
              displayScale: obj.displayScale,
              bounds: effectiveCutoutBounds(obj, showOriginal),
            };
          }

          return {
            src: effectiveCutoutSrc(obj, showOriginal),
            offset: obj.offset,
            displayScale: obj.displayScale,
            bounds: effectiveCutoutBounds(obj, showOriginal),
          };
        }),
      );

      const blob = await composeStageSnapshot(
        backgroundSrc,
        layers.filter((layer): layer is NonNullable<typeof layer> => layer !== null),
        naturalSize,
      );
      if (!blob) {
        setError("Could not build a snapshot of the room.");
        return;
      }

      triggerBlobDownload(blob, snapshotDownloadFilename(sessionName, uid));
    } catch (saveError) {
      setError(errorMessage(saveError, "Could not save the room snapshot."));
    } finally {
      setIsSavingSnapshot(false);
    }
  }, [
    isSavingSnapshot,
    isShowingOriginal,
    jobs.backgroundSrc,
    jobs.selectedObjectId,
    naturalSize,
    originalSrc,
    rotation.model3DFrameRef,
    rotation.rotateMode,
    sessionName,
    uid,
    visibleObjects,
  ]);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA")) {
        return;
      }
      const mod = event.ctrlKey || event.metaKey;
      if (!mod) {
        return;
      }
      if (event.key === "z" || event.key === "Z") {
        if (event.shiftKey) {
          if (canRedo && !historyBusy && !jobs.hasPendingWork) {
            event.preventDefault();
            void runHistoryStep("redo");
          }
        } else if (canUndo && !historyBusy && !jobs.hasPendingWork) {
          event.preventDefault();
          void runHistoryStep("undo");
        }
      } else if ((event.key === "y" || event.key === "Y") && canRedo && !historyBusy && !jobs.hasPendingWork) {
        event.preventDefault();
        void runHistoryStep("redo");
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [canRedo, canUndo, historyBusy, jobs.hasPendingWork, runHistoryStep]);

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
        multiPoint={multiPoint}
        onToggleMultiPoint={handleToggleMultiPoint}
        hasPendingSegmentSeeds={pendingSeeds.length > 0}
        onUndoLastSeed={handleUndoLastSeed}
        areaMode={areaMode}
        onArea={handleArea}
        eraserMode={eraserMode}
        onEraser={handleEraser}
        hasPendingEraseRegions={pendingEraseRegions.length > 0}
        batchMode={armedBatch.batchMode}
        onToggleBatchMode={handleToggleBatchMode}
        armedQueueCount={armedBatch.jobs.length}
        queuePanelOpen={armedBatch.panelOpen}
        onToggleQueuePanel={() => armedBatch.setPanelOpen((open) => !open)}
        batchBusy={jobs.isBatching || armedBatch.isApproving}
        hasPendingBatch={
          armedBatch.batchMode
            ? armedBatch.jobs.length > 0 || pendingSeeds.length > 0
            : pendingBatchSource !== null ||
              pendingSeeds.length > 0 ||
              pendingEraseRegions.length > 0
        }
        onSubmitBatch={handleSubmitPendingBatch}
        verifyMode={verifyMode}
        onVerifyModeChange={setVerifyMode}
        rotateMode={rotation.rotateMode}
        isPreparing3D={rotation.isPreparing3D || Boolean(rotation.activeGenerate3DJobId)}
        onRotate={rotation.handleRotate}
        isDuplicating={jobs.isDuplicating}
        onCopy={handleCopy}
        smartPaste={smartPaste}
        onToggleSmartPaste={handleToggleSmartPaste}
        scaleByPov={scaleByPov}
        onToggleScaleByPov={handleToggleScaleByPov}
        smartRotate={smartRotate}
        onToggleSmartRotate={handleToggleSmartRotate}
        autoGenerate3d={autoGenerate3d}
        onToggleAutoGenerate3d={() => setAutoGenerate3d((on) => !on)}
        isDeleting={jobs.isDeleting}
        onDeleteObject={handleDeleteObject}
        canUndo={canUndo}
        canRedo={canRedo}
        historyBusy={historyBusy}
        onBacktrack={handleBacktrack}
        onForward={handleForward}
        hasSnapshot={Boolean(naturalSize && (jobs.backgroundSrc ?? originalSrc))}
        isSavingSnapshot={isSavingSnapshot}
        onDownloadSnapshot={() => void handleDownloadSnapshot()}
        status={status}
      />

      <main
        ref={stageRef}
        className={`stage${cutMode || areaMode || eraserMode ? " is-picking" : ""}${objectDrag.isDragging ? " is-dragging" : ""}`}
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
            <div
              ref={stageInputRef}
              className="stage-input"
              onPointerDown={handleStagePointerDown}
            />

            {displayedBatchBox && renderedRect && naturalSize ? (
              <div
                className={`stage-area-box${batchBoxIsPending ? " is-pending" : ""}`}
                style={batchBoxStageStyle(displayedBatchBox, renderedRect, naturalSize)}
              />
            ) : null}

            {renderedRect && naturalSize
              ? armedBoxes.map(({ id, box, selected }) => (
                  <div
                    key={id}
                    className={`stage-area-box is-pending${selected ? " is-selected" : ""}`}
                    style={batchBoxStageStyle(box, renderedRect, naturalSize)}
                  />
                ))
              : null}

            {pendingSeeds.length > 0 && renderedRect && naturalSize ? (
              <div className="stage-seed-markers" aria-hidden="true">
                {pendingSeeds.map((seed, index) => (
                  <span
                    key={`${seed.x}-${seed.y}-${index}`}
                    className={`stage-pick-marker${cutMode ? " is-armed" : ""}`}
                    style={{
                      left: `${renderedRect.x + (seed.x / naturalSize.width) * renderedRect.width}px`,
                      top: `${renderedRect.y + (seed.y / naturalSize.height) * renderedRect.height}px`,
                    }}
                  >
                    <span className="stage-pick-marker-ring" />
                    {pendingSeeds.length > 1 ? (
                      <span className="stage-pick-marker-label">{index + 1}</span>
                    ) : null}
                  </span>
                ))}
              </div>
            ) : null}

            {renderedRect && naturalSize && armedSeeds.length > 0 ? (
              <div className="stage-seed-markers" aria-hidden="true">
                {armedSeeds.map((seed) => (
                  <span
                    key={seed.id}
                    className={`stage-pick-marker is-pending${seed.selected ? " is-selected" : ""}`}
                    style={{
                      left: `${renderedRect.x + (seed.point.x / naturalSize.width) * renderedRect.width}px`,
                      top: `${renderedRect.y + (seed.point.y / naturalSize.height) * renderedRect.height}px`,
                    }}
                  >
                    <span className="stage-pick-marker-ring" />
                  </span>
                ))}
              </div>
            ) : null}

            {renderedRect && naturalSize && (lassoDraft || pendingEraseRegions.length > 0 || armedLassos.length > 0) ? (
              <svg className="stage-lasso-layer" aria-hidden="true">
                {armedLassos.map((lasso) => (
                  <polygon
                    key={lasso.id}
                    className={`stage-lasso-path is-pending${lasso.selected ? " is-selected" : ""}`}
                    points={lassoPolygonStagePoints(lasso.polygon, renderedRect, naturalSize)}
                  />
                ))}
                {pendingEraseRegions.map((polygon, index) => (
                  <polygon
                    key={`pending-erase-${index}`}
                    className="stage-lasso-path is-pending"
                    points={lassoPolygonStagePoints(polygon, renderedRect, naturalSize)}
                  />
                ))}
                {lassoDraft ? (
                  <polyline
                    className="stage-lasso-path"
                    points={lassoPolygonStagePoints(lassoDraft.points, renderedRect, naturalSize)}
                  />
                ) : null}
              </svg>
            ) : null}

            {rotation.rotateMode && rotation.glbData ? (
              <Model3DFrame ref={rotation.model3DFrameRef} glbData={rotation.glbData} style={model3DFrameStyle} />
            ) : null}

            {selectedRect && !rotation.rotateMode ? (
              <div className="selection-frame" style={{ ...rectStyle(selectedRect), zIndex: 210 }}>
                {canResize ? (
                  <>
                    <button
                      type="button"
                      className="selection-handle selection-corner tl"
                      aria-label="Resize top left"
                      onPointerDown={handleResizePointerDown("tl")}
                    />
                    <button
                      type="button"
                      className="selection-handle selection-corner tr"
                      aria-label="Resize top right"
                      onPointerDown={handleResizePointerDown("tr")}
                    />
                    <button
                      type="button"
                      className="selection-handle selection-corner bl"
                      aria-label="Resize bottom left"
                      onPointerDown={handleResizePointerDown("bl")}
                    />
                    <button
                      type="button"
                      className="selection-handle selection-corner br"
                      aria-label="Resize bottom right"
                      onPointerDown={handleResizePointerDown("br")}
                    />
                    <button
                      type="button"
                      className="selection-handle selection-edge t"
                      aria-label="Resize top"
                      onPointerDown={handleResizePointerDown("t")}
                    />
                    <button
                      type="button"
                      className="selection-handle selection-edge r"
                      aria-label="Resize right"
                      onPointerDown={handleResizePointerDown("r")}
                    />
                    <button
                      type="button"
                      className="selection-handle selection-edge b"
                      aria-label="Resize bottom"
                      onPointerDown={handleResizePointerDown("b")}
                    />
                    <button
                      type="button"
                      className="selection-handle selection-edge l"
                      aria-label="Resize left"
                      onPointerDown={handleResizePointerDown("l")}
                    />
                  </>
                ) : null}
              </div>
            ) : null}
          </>
        ) : (
          <div className="stage-message">
            {mapsWarming ? <span className="stage-warm-spinner tool-spinner" aria-hidden="true" /> : null}
            <p className="stage-message-line">Opening the room</p>
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

        {rotation.rotateMode ? (
          <p className="stage-hint">Drag to orbit · Enter applies · Esc cancels</p>
        ) : eraserMode ? (
          <p className="stage-hint">
            {armedBatch.batchMode
              ? "Drag a loop to arm erase · Esc cancels"
              : pendingEraseRegions.length > 0
                ? `${pendingEraseRegions.length} region${pendingEraseRegions.length === 1 ? "" : "s"} · Shift-drag adds · Enter or checkmark runs · Esc cancels`
                : "Drag a loop to erase · Shift-drag stages · Esc cancels"}
          </p>
        ) : areaMode ? (
          <p className="stage-hint">
            {armedBatch.batchMode
              ? "Drag a box to arm cut · Esc cancels"
              : "Drag a box around the furniture · Esc cancels"}
          </p>
        ) : pendingBatchSource ? (
          <p className="stage-hint">Submit batch cut (checkmark) · Esc clears box</p>
        ) : pendingSeeds.length > 0 ? (
          <p className="stage-hint">
            {armedBatch.batchMode
              ? `${pendingSeeds.length} seed${pendingSeeds.length === 1 ? "" : "s"} · Enter or checkmark arms · Esc clears`
              : `${pendingSeeds.length} seed${pendingSeeds.length === 1 ? "" : "s"} placed · Shift+click adds · Enter or checkmark runs · Esc clears`}
          </p>
        ) : cutMode ? (
          <p className="stage-hint">
            {armedBatch.batchMode
              ? multiPoint
                ? "Click to add seeds · Enter or checkmark arms · Esc cancels"
                : "Click to arm cutout · Shift+click adds seeds · Esc cancels"
              : multiPoint
                ? "Click to add seeds · Enter or checkmark runs · Esc cancels"
                : "Click the object · Shift+click adds seeds · Esc cancels"}
          </p>
        ) : armedBatch.batchMode && armedBatch.jobs.length > 0 ? (
          <p className="stage-hint">
            {armedBatch.jobs.length} armed · checkmark approves · queue button to edit
          </p>
        ) : null}

        {armedBatch.panelOpen ? (
          <BatchQueuePanel
            jobs={armedBatch.jobs}
            selectedJobId={armedBatch.selectedJobId}
            busy={armedBatch.isApproving || jobs.isBatching}
            onSelectJob={armedBatch.setSelectedJobId}
            onActionChange={armedBatch.setJobAction}
            onMoveUp={(id) => armedBatch.moveJob(id, "up")}
            onMoveDown={(id) => armedBatch.moveJob(id, "down")}
            onRemove={armedBatch.removeJob}
            onApprove={() => {
              if (pendingSeeds.length > 0) {
                armedBatch.appendClicks(pendingSeeds);
                setPendingSeeds([]);
              }
              void armedBatch.approve();
            }}
            onClear={armedBatch.clearJobs}
            onClose={() => armedBatch.setPanelOpen(false)}
          />
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
            jobs={jobs.jobs}
            selectedObjectId={jobs.selectedObjectId}
            showOriginalIds={showOriginalIds}
            disabled={rotation.isPreparing3D}
            isDuplicating={jobs.isDuplicating}
            isDeleting={jobs.isDeleting}
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
                if (armedBatch.batchModeRef.current) {
                  armedBatch.appendJob({ kind: "objects", uuids });
                  setBatchUuids(new Set());
                  return;
                }
                void jobs.runBatch({ kind: "objects", uuids });
              }
            }}
            generate3DDisabled={jobs.isBatching || armedBatch.isApproving}
            onToggleHidden={handleToggleHidden}
            onToggleShowOriginal={handleToggleShowOriginal}
            onRenameObject={handleRenameObject}
            onDuplicateObject={(objectId) => {
              const target = jobs.objects.find((o) => o.objectId === objectId);
              if (!target?.uuid) {
                setError("This object is from an older room and can't be duplicated.");
                return;
              }
              void jobs.duplicateObject(objectId);
            }}
            onDeleteObject={requestDeleteObject}
            onClearObject3d={handleClearObject3d}
            onResetObjectChanges={handleResetObjectChanges}
            onImportObject={(file) => {
              void jobs.importObject(file);
            }}
            importDisabled={rotation.isPreparing3D || jobs.isImporting || jobs.isBatching || armedBatch.isApproving}
            onDismissJob={handleDismissJob}
          />
        ) : null}
      </main>

      {jobs.isChoosingMask ? (
        <MaskPickerModal
          masks={jobs.maskOptions}
          onSelect={handleMaskSelected}
          onDefer={handleMaskPickerDeferred}
          onDiscard={handleMaskPickerDiscarded}
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
