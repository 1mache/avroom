import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  API_BASE_URL,
  ApiError,
  deleteJob,
  getSessionObjects,
  getUidCacheStatus,
  setSessionName as saveSessionName,
  warmSessionMaps,
} from "../../api/images";
import { useAreaSelect } from "../../hooks/useAreaSelect";
import { useConflictNotices, type ConflictContext } from "../../hooks/useConflictNotices";
import { useDashboardPreview } from "../../hooks/useDashboardPreview";
import { useHitTesting } from "../../hooks/useHitTesting";
import { useObjectDrag } from "../../hooks/useObjectDrag";
import { useRotationController } from "../../hooks/useRotationController";
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
import {
  ALPHA_HIT_THRESHOLD,
  buildHitTestOrder,
  getBoundsStageRect,
  getContainedImageRect,
  inflateAroundCenter,
  mapPointThroughInverseScale,
  toNaturalPoint,
  type Rect,
  type Size,
} from "../../utils/stageGeometry";
import { ConfirmDialog } from "../widgets/ConfirmDialog";
import { MaskPickerModal } from "../widgets/MaskPickerModal";
import { MODEL_3D_FRAME_PADDING, Model3DFrame } from "../widgets/Model3DFrame";
import { ObjectRail } from "../workspace/ObjectRail";
import { Toolbar } from "../workspace/Toolbar";

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

  // Per-object: show the pristine cutout instead of the rotated result.
  const [showOriginalIds, setShowOriginalIds] = useState<ReadonlySet<number>>(new Set());

  const [smartPaste, setSmartPaste] = useState(false);
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
    // A mutation (inpaint, most commonly) can change the canvas the depth/
    // normal maps were warmed for — forget the "already warm" mark so the
    // next reentry re-warms instead of skipping a now-stale cache.
    warmedSessionIds.delete(uid);
    recordLocalMutationRef.current();
    capturePreviewRef.current();
  }, [uid]);

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
  });

  const sync = useSessionSync({
    imageId,
    hasPendingWork: jobs.hasPendingWork,
    objects: jobs.objects,
    setObjects: jobs.setObjects,
    selectedObjectId: jobs.selectedObjectId,
    setSelectedObjectId: jobs.setSelectedObjectId,
    setBackgroundSrc: jobs.setBackgroundSrc,
    setJobs: jobs.setJobs,
    isDeleted: jobs.isObjectDeleted,
  });

  useEffect(() => {
    recordLocalMutationRef.current = sync.recordLocalMutation;
  }, [sync.recordLocalMutation]);

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
    runSmartPasteAfterDrag: jobs.runSmartPasteAfterDrag,
    onSettled: capturePreview,
  });

  // --- drag-a-box batch select -----------------------------------------------

  useAreaSelect({
    areaDraft,
    setAreaDraft,
    setAreaMode,
    naturalSize,
    renderedRect,
    stageRef,
    isBatching: jobs.isBatching,
    runBatch: jobs.runBatch,
  });

  // --- selection & tools --------------------------------------------------

  const selectObject = useCallback(
    (objectId: number) => {
      jobs.setSelectedObjectId(objectId);
      // Rotation is scoped to whichever object is selected — switching away
      // closes the angle picker.
      rotation.setRotateMode(false);
      setCutMode(false);
      setPickPoint(null);
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

  const handleCut = useCallback(() => {
    rotation.setRotateMode(false);
    setAreaMode(false);
    setPickPoint(null);
    setCutMode((armed) => !armed);
  }, [rotation.setRotateMode]);

  const handleArea = useCallback(() => {
    rotation.setRotateMode(false);
    setCutMode(false);
    setPickPoint(null);
    setAreaMode((armed) => !armed);
  }, [rotation.setRotateMode]);

  const handleMaskSelected = useCallback(
    (maskId: string) => {
      if (jobs.currentSegmentJobId) {
        jobs.selectMask(jobs.currentSegmentJobId, maskId);
      }
      setPickPoint(null);
    },
    [jobs.selectMask, jobs.currentSegmentJobId],
  );

  const handleMaskPickerClosed = useCallback(() => {
    jobs.closeMaskPicker();
    setPickPoint(null);
  }, [jobs.closeMaskPicker]);

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
    rotation.setRotateMode(false);
    setPendingDeleteObjectId(jobs.selectedObjectId);
  }, [jobs.selectedObjectId, selectedObject, rotation.setRotateMode]);

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
    if (!rotation.rotateMode && !cutMode && !areaMode) {
      return;
    }

    const handleKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA")) {
        return;
      }

      if (event.key === "Escape") {
        event.preventDefault();
        rotation.setRotateMode(false);
        setCutMode(false);
        setAreaMode(false);
        setAreaDraft(null);
        setPickPoint(null);
      } else if (event.key === "Enter" && rotation.rotateMode) {
        event.preventDefault();
        void rotation.commitCurrentRotation();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [rotation.rotateMode, cutMode, areaMode, rotation.commitCurrentRotation, rotation.setRotateMode]);

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
      rotation.rotateMode,
      isShowingOriginal,
      sampleObjectAlpha,
      objectDrag,
      selectObject,
    ],
  );

  // --- derived render values ---------------------------------------------

  const visibleObjects = jobs.objects.filter((o) => !o.hidden);
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

  const photoSrc = jobs.backgroundSrc ?? originalSrc;

  const activeJobs = jobs.jobs.filter((job) => job.status === "queued" || job.status === "running");
  const segmentingCount = activeJobs.filter((job) => job.kind === "segment").length;
  const removingCount = activeJobs.filter((job) => job.kind === "inpaint").length;

  const status = jobs.isBatching
    ? "batch cutting"
    : objectDrag.isSmartPasting
      ? "smart pasting"
      : segmentingCount > 0
        ? `finding masks${segmentingCount > 1 ? ` (${segmentingCount})` : ""}`
        : removingCount > 0
          ? `removing ${removingCount}`
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
        rotateMode={rotation.rotateMode}
        isPreparing3D={rotation.isPreparing3D || Boolean(rotation.activeGenerate3DJobId)}
        onRotate={rotation.handleRotate}
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
        className={`stage${cutMode || areaMode ? " is-picking" : ""}${objectDrag.isDragging ? " is-dragging" : ""}`}
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

            {rotation.rotateMode && rotation.glbData ? (
              <Model3DFrame ref={rotation.model3DFrameRef} glbData={rotation.glbData} style={model3DFrameStyle} />
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

        {rotation.rotateMode ? (
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
            jobs={jobs.jobs}
            selectedObjectId={jobs.selectedObjectId}
            showOriginalIds={showOriginalIds}
            disabled={rotation.isPreparing3D}
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
            onDismissJob={handleDismissJob}
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
