import React from "react";
import { useCallback, useEffect, useRef, useState } from "react";

import {
  API_BASE_URL,
  deleteSession,
  fetchCached3DModel,
  generate3DModel,
  getSessionObjects,
  getUidCacheStatus,
  setSessionName as saveSessionName,
  uploadImage,
} from "../../api/images";
import avroomLogo from "../../assets/avroom.png";
import { useConflictNotices, type ConflictContext } from "../../hooks/useConflictNotices";
import { useSessionJobs, type JobErrorContext } from "../../hooks/useSessionJobs";
import { useSessionSync } from "../../hooks/useSessionSync";
import type { ClickPosition, CutoutAlphaBounds } from "../../types/session";
import { MaskPickerModal } from "../widgets/MaskPickerModal";
import { Model3DFrame } from "../widgets/Model3DFrame";
import { ObjectPanel } from "../widgets/ObjectPanel";
import { SessionPicker } from "../widgets/SessionPicker";
import { UploadFrame } from "../widgets/UploadFrame";

interface Size {
  width: number;
  height: number;
}

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
}

// `object-fit: contain` means visible image may not fill stage. Drag math must
// operate inside rendered image rect, not full frame box.
const getContainedImageRect = (containerSize: Size, imageSize: Size) => {
  if (containerSize.width <= 0 || containerSize.height <= 0 || imageSize.width <= 0 || imageSize.height <= 0) {
    return null;
  }

  const containerRatio = containerSize.width / containerSize.height;
  const imageRatio = imageSize.width / imageSize.height;

  if (imageRatio > containerRatio) {
    const width = containerSize.width;
    const height = width / imageRatio;
    return {
      x: 0,
      y: (containerSize.height - height) / 2,
      width,
      height,
    };
  }

  const height = containerSize.height;
  const width = height * imageRatio;
  return {
    x: (containerSize.width - width) / 2,
    y: 0,
    width,
    height,
  };
};

const clampCutoutOffset = (
  offset: ClickPosition,
  alphaBounds: CutoutAlphaBounds | null,
  imageSize: Size | null,
): ClickPosition => {
  if (!imageSize || imageSize.width <= 0 || imageSize.height <= 0) {
    return { x: 0, y: 0 };
  }

  const effectiveBounds = alphaBounds ?? {
    left: 0,
    top: 0,
    right: imageSize.width,
    bottom: imageSize.height,
  };

  // Offset lives in natural-image pixels. Clamp against visible-object bounds so
  // transparent padding may leave frame while opaque object stays inside it.
  const minX = -effectiveBounds.left;
  const maxX = imageSize.width - effectiveBounds.right;
  const minY = -effectiveBounds.top;
  const maxY = imageSize.height - effectiveBounds.bottom;

  return {
    x: Math.min(Math.max(offset.x, minX), maxX),
    y: Math.min(Math.max(offset.y, minY), maxY),
  };
};

// Maps an object's alpha bounds (+ its drag offset) from natural-image pixels
// into on-stage CSS pixels, using the same contained-rect scale as the
// background/cutout images. Falls back to the full rendered rect when bounds
// are unknown (e.g. legacy session data).
const getBoundsStageRect = (
  bounds: CutoutAlphaBounds | null,
  offset: ClickPosition,
  renderedRect: { x: number; y: number; width: number; height: number },
  naturalSize: Size,
): { left: number; top: number; width: number; height: number } => {
  if (!bounds) {
    return { left: renderedRect.x, top: renderedRect.y, width: renderedRect.width, height: renderedRect.height };
  }

  const scaleX = renderedRect.width / naturalSize.width;
  const scaleY = renderedRect.height / naturalSize.height;

  return {
    left: renderedRect.x + (bounds.left + offset.x) * scaleX,
    top: renderedRect.y + (bounds.top + offset.y) * scaleY,
    width: (bounds.right - bounds.left) * scaleX,
    height: (bounds.bottom - bounds.top) * scaleY,
  };
};

// Minimum alpha (0-255) that counts as "clicked the object" rather than
// transparent padding or an antialiased edge pixel.
const ALPHA_HIT_THRESHOLD = 10;

// Objects render back-to-front in array order (later = on top, see zIndex in
// getCutoutOverlayStyle), so hit-testing must walk topmost-first. The
// currently selected object is always drawn on top of everything else, so it
// is tested first regardless of its position in the array.
const buildHitTestOrder = <T extends { objectId: number; hidden: boolean }>(
  objects: T[],
  selectedObjectId: number | null,
): T[] => {
  const visible = objects.filter((o) => !o.hidden);
  const topmostFirst = [...visible].reverse();

  if (selectedObjectId === null) {
    return topmostFirst;
  }

  const selectedIndex = topmostFirst.findIndex((o) => o.objectId === selectedObjectId);
  if (selectedIndex <= 0) {
    return topmostFirst;
  }

  const [selected] = topmostFirst.splice(selectedIndex, 1);
  return [selected, ...topmostFirst];
};

const DELETE_CONFIRM_SECONDS = 2;

const errorMessage = (error: unknown, fallback: string): string =>
  error instanceof Error ? error.message : fallback;

export const MainPage: React.FC = () => {
  const frameInputRef = useRef<HTMLInputElement>(null);
  const uploadOtherInputRef = useRef<HTMLInputElement>(null);
  const resultStageRef = useRef<HTMLDivElement>(null);
  const dragStateRef = useRef<DragState | null>(null);
  const backgroundNaturalSizeRef = useRef<Size | null>(null);
  const renderedBackgroundRectRef = useRef<ReturnType<typeof getContainedImageRect>>(null);
  const hitCanvasesRef = useRef<Map<number, HitCanvasEntry>>(new Map());

  const [uploadedFile, setUploadedFile] = useState<File | null>(null);
  const [uploadedImageUrl, setUploadedImageUrl] = useState<string | null>(null);
  const [imageId, setImageId] = useState<string | null>(null);
  const [clickPosition, setClickPosition] = useState<ClickPosition | null>(null);
  const [naturalClickPos, setNaturalClickPos] = useState<ClickPosition | null>(null);
  const [normalizedClickPos, setNormalizedClickPos] = useState<ClickPosition | null>(null);
  const [backgroundNaturalSize, setBackgroundNaturalSize] = useState<Size | null>(null);
  const [resultStageSize, setResultStageSize] = useState<Size | null>(null);
  const [show3D, setShow3D] = useState(false);
  const [isDraggingCutout, setIsDraggingCutout] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [isGenerating3D, setIsGenerating3D] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sessionName, setSessionName] = useState<string>("");
  const [sessionsRefreshKey, setSessionsRefreshKey] = useState(0);
  const [isDeleting, setIsDeleting] = useState(false);
  const [deleteConfirming, setDeleteConfirming] = useState(false);
  const deleteConfirmTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // No object is selected at the start of a session; selection is set by
  // clicking/dragging an object in the preview or clicking it in the panel.
  const [isAddingObject, setIsAddingObject] = useState(false);
  const [objectPanelCollapsed, setObjectPanelCollapsed] = useState(false);

  const conflictNotices = useConflictNotices();

  // 409s from segment/inpaint are expected concurrency traffic — routed to
  // the inline notice stack. Everything else (including non-409 ApiErrors)
  // is a real failure and opens the modal error dialog.
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
  const handleMutated = useCallback(() => {
    recordLocalMutationRef.current();
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
  });

  useEffect(() => {
    recordLocalMutationRef.current = sync.recordLocalMutation;
  }, [sync.recordLocalMutation]);

  const replaceUploadedImageUrl = useCallback((nextUrl: string | null) => {
    setUploadedImageUrl((previousUrl) => {
      if (previousUrl?.startsWith("blob:")) {
        URL.revokeObjectURL(previousUrl);
      }

      return nextUrl;
    });
  }, []);

  // The pending click is tracked in three coordinate spaces at once (display /
  // natural / normalized), so they are always cleared together.
  const clearClickState = useCallback(() => {
    setClickPosition(null);
    setNaturalClickPos(null);
    setNormalizedClickPos(null);
  }, []);

  // Local UI-only state (click intent, drag, geometry). Object/job/background
  // state lives in useSessionJobs and is reset separately below.
  const resetWorkspaceState = useCallback(() => {
    clearClickState();
    setBackgroundNaturalSize(null);
    setResultStageSize(null);
    setShow3D(false);
    setIsDraggingCutout(false);
    dragStateRef.current = null;
    setIsAddingObject(false);
    setError(null);
    if (deleteConfirmTimerRef.current) {
      clearTimeout(deleteConfirmTimerRef.current);
      deleteConfirmTimerRef.current = null;
    }
    setDeleteConfirming(false);
  }, [clearClickState]);

  const resetForNewSession = useCallback(() => {
    resetWorkspaceState();
    jobs.resetSession();
    sync.seedLastChanged(null);
  }, [resetWorkspaceState, jobs.resetSession, sync.seedLastChanged]);

  // Derive selected-object values from the objects array. Only the selected
  // object may show a 3D model; every non-hidden object still renders on the
  // stage regardless of selection.
  const selectedObject = jobs.objects.find((o) => o.objectId === jobs.selectedObjectId) ?? null;
  const glbData = selectedObject?.glbData ?? null;

  useEffect(() => {
    return () => {
      if (uploadedImageUrl?.startsWith("blob:")) {
        URL.revokeObjectURL(uploadedImageUrl);
      }
    };
  }, [uploadedImageUrl]);

  const handleFileSelected = useCallback((file: File) => {
    setUploadedFile(file);
    setImageId(null);
    resetForNewSession();
    replaceUploadedImageUrl(URL.createObjectURL(file));
  }, [replaceUploadedImageUrl, resetForNewSession]);

  const handleUploadOtherSelected: React.ChangeEventHandler<HTMLInputElement> = useCallback((event) => {
    const file = event.target.files?.[0];
    if (file) {
      handleFileSelected(file);
      event.target.value = "";
    }
  }, [handleFileSelected]);

  const handleImageClick = useCallback((
    displayPos: ClickPosition,
    naturalPos: ClickPosition,
    normalizedPos: ClickPosition,
  ) => {
    setClickPosition(displayPos);
    setNaturalClickPos(naturalPos);
    setNormalizedClickPos(normalizedPos);
  }, []);

  const measureResultStage = useCallback(() => {
    const stage = resultStageRef.current;
    if (!stage) {
      return;
    }

    const nextSize = {
      width: stage.clientWidth,
      height: stage.clientHeight,
    };

    setResultStageSize((previousSize) => {
      if (
        previousSize &&
        previousSize.width === nextSize.width &&
        previousSize.height === nextSize.height
      ) {
        return previousSize;
      }

      return nextSize;
    });
  }, []);

  const handleSessionSelect = useCallback(async (uid: string) => {
    setImageId(uid);
    setUploadedFile(null);
    resetForNewSession();
    replaceUploadedImageUrl(`${API_BASE_URL}/images/${uid}/original`);

    try {
      const status = await getUidCacheStatus(uid);
      setSessionName(status.name ?? uid);

      if (status.has_background) {
        jobs.setBackgroundSrc(`${API_BASE_URL}/images/${uid}/background`);
      }

      if (status.has_cutout) {
        const objList = await getSessionObjects(uid);
        if (objList.objects.length > 0) {
          jobs.loadRestoredObjects(objList.objects);
        }
      }

      // Seed sync bookkeeping immediately, without waiting for a poll tick or
      // focus event, and pick up anything that changed since last visit.
      recordLocalMutationRef.current();
    } catch {
      // Non-fatal. User can rerun cutout.
      setSessionName(uid);
    }
  }, [replaceUploadedImageUrl, resetForNewSession, jobs.setBackgroundSrc, jobs.loadRestoredObjects]);

  const handleUpload = useCallback(async () => {
    if (!uploadedFile) {
      setError("Please choose an image to upload.");
      return;
    }

    setIsUploading(true);
    setError(null);

    try {
      const response = await uploadImage(uploadedFile);
      setImageId(response.image_id);
      setSessionName(response.image_id);
      setUploadedFile(null);
      sync.seedLastChanged(response.last_changed);
      setSessionsRefreshKey((k) => k + 1);
    } catch (uploadError) {
      setError(errorMessage(uploadError, "Unexpected upload error."));
    } finally {
      setIsUploading(false);
    }
  }, [uploadedFile, sync.seedLastChanged]);

  const handleCutOut = useCallback(async () => {
    if (!imageId) {
      setError("No uploaded image to process yet.");
      return;
    }

    if (!naturalClickPos) {
      setError("Please click on image to select point of interest.");
      return;
    }

    await jobs.runSegment(naturalClickPos.x, naturalClickPos.y);
  }, [imageId, naturalClickPos, jobs.runSegment]);

  // Selecting a mask closes the picker immediately (see MaskPickerModal) and
  // fires inpainting detached — the user is free to click a new point right
  // away and start a second removal while this one is still running.
  const handleMaskSelected = useCallback((maskId: string) => {
    jobs.selectMask(maskId, normalizedClickPos);
    setIsAddingObject(false);
    setShow3D(false);
    clearClickState();
  }, [jobs.selectMask, normalizedClickPos, clearClickState]);

  const handleToggle3D = useCallback(async () => {
    if (show3D) {
      setShow3D(false);
      return;
    }

    if (!imageId || jobs.selectedObjectId === null) {
      setError("No object selected for 3D generation.");
      return;
    }

    if (glbData) {
      setShow3D(true);
      return;
    }

    // Snapshot the target id before any await so we write to the right object
    // even if the user switches selection while generation is in flight.
    const targetObjectId = jobs.selectedObjectId;
    setIsGenerating3D(true);
    setError(null);

    try {
      const cached = await fetchCached3DModel(imageId, targetObjectId);
      if (cached) {
        jobs.setObjects((prev) =>
          prev.map((o) => (o.objectId === targetObjectId ? { ...o, glbData: cached } : o))
        );
        // Only surface the 3D view if the user hasn't switched selection away.
        jobs.setSelectedObjectId((current) => {
          if (current === targetObjectId) setShow3D(true);
          return current;
        });
        return;
      }

      const buffer = await generate3DModel(imageId, targetObjectId);
      jobs.setObjects((prev) =>
        prev.map((o) => (o.objectId === targetObjectId ? { ...o, glbData: buffer } : o))
      );
      jobs.setSelectedObjectId((current) => {
        if (current === targetObjectId) setShow3D(true);
        return current;
      });
    } catch (genError) {
      setError(errorMessage(genError, "Unexpected 3D generation error."));
      setShow3D(false);
    } finally {
      setIsGenerating3D(false);
    }
  }, [jobs.selectedObjectId, jobs.setObjects, jobs.setSelectedObjectId, glbData, imageId, show3D]);

  const handleNameKeyDown = useCallback(async (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key !== "Enter" || !imageId || !sessionName.trim()) {
      return;
    }

    event.currentTarget.blur();

    try {
      await saveSessionName(imageId, sessionName.trim());
      recordLocalMutationRef.current();
      setSessionsRefreshKey((k) => k + 1);
    } catch (nameError) {
      // A 409 here means the name is already taken by another session — a
      // real, user-facing conflict distinct from segment/inpaint concurrency,
      // so it always goes to the error modal rather than an inline notice.
      setError(errorMessage(nameError, "Failed to save session name."));
    }
  }, [imageId, sessionName]);

  const handleRenameObject = useCallback(
    (objectId: number, uuid: string, name: string | null) => {
      void jobs.renameObject(objectId, uuid, name);
    },
    [jobs.renameObject],
  );

  const handleDeleteSession = useCallback(async () => {
    if (!imageId) {
      return;
    }

    if (!deleteConfirming) {
      setDeleteConfirming(true);
      deleteConfirmTimerRef.current = setTimeout(() => {
        setDeleteConfirming(false);
      }, DELETE_CONFIRM_SECONDS * 1000);
      return;
    }

    if (deleteConfirmTimerRef.current) {
      clearTimeout(deleteConfirmTimerRef.current);
      deleteConfirmTimerRef.current = null;
    }
    setDeleteConfirming(false);
    setIsDeleting(true);

    try {
      await deleteSession(imageId);
      setImageId(null);
      setUploadedFile(null);
      replaceUploadedImageUrl(null);
      resetForNewSession();
      setSessionName("");
      setSessionsRefreshKey((k) => k + 1);
    } catch (deleteError) {
      setError(errorMessage(deleteError, "Failed to delete session."));
    } finally {
      setIsDeleting(false);
    }
  }, [deleteConfirming, imageId, replaceUploadedImageUrl, resetForNewSession]);

  useEffect(() => {
    return () => {
      if (deleteConfirmTimerRef.current) {
        clearTimeout(deleteConfirmTimerRef.current);
      }
    };
  }, []);

  const triggerFileInput = useCallback(() => {
    if (frameInputRef.current) {
      frameInputRef.current.click();
      return;
    }

    uploadOtherInputRef.current?.click();
  }, []);

  useEffect(() => {
    if (!jobs.backgroundSrc) {
      return;
    }

    const stage = resultStageRef.current;
    if (!stage) {
      return;
    }

    measureResultStage();
    const observer = new ResizeObserver(() => {
      measureResultStage();
    });
    observer.observe(stage);

    return () => {
      observer.disconnect();
    };
  }, [jobs.backgroundSrc, measureResultStage]);

  useEffect(() => {
    // Window-level listeners need fresh geometry without re-binding on every
    // mouse move, so keep latest derived values in refs.
    backgroundNaturalSizeRef.current = backgroundNaturalSize;
  }, [backgroundNaturalSize]);

  // Build (and prune) an offscreen per-object canvas so pointer-down hit
  // testing can sample real alpha instead of only a bounding box. Cheap no-op
  // for objects that already have a canvas (e.g. re-runs while dragging).
  useEffect(() => {
    const currentIds = new Set(jobs.objects.map((o) => o.objectId));
    hitCanvasesRef.current.forEach((_entry, id) => {
      if (!currentIds.has(id)) {
        hitCanvasesRef.current.delete(id);
      }
    });

    jobs.objects.forEach((obj) => {
      if (hitCanvasesRef.current.has(obj.objectId)) {
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
        });
      };
      img.src = obj.cutoutSrc;
    });
  }, [jobs.objects]);

  const sampleObjectAlpha = useCallback((objectId: number, localX: number, localY: number): number => {
    const entry = hitCanvasesRef.current.get(objectId);
    if (!entry) {
      // Canvas not built yet (object just created). Treat as opaque so the
      // object stays clickable immediately; the alpha-bounds bbox check
      // already filters out obviously-empty space before this runs.
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

  const handleBackgroundLoad: React.ReactEventHandler<HTMLImageElement> = useCallback((event) => {
    setBackgroundNaturalSize({
      width: event.currentTarget.naturalWidth,
      height: event.currentTarget.naturalHeight,
    });
    measureResultStage();
  }, [measureResultStage]);

  const renderedBackgroundRect =
    resultStageSize && backgroundNaturalSize
      ? getContainedImageRect(resultStageSize, backgroundNaturalSize)
      : null;

  useEffect(() => {
    renderedBackgroundRectRef.current = renderedBackgroundRect;
  }, [renderedBackgroundRect]);

  const handleSelectObject = useCallback((objectId: number) => {
    jobs.setSelectedObjectId(objectId);
    // 3D is scoped to whichever object is selected — switching away hides it.
    setShow3D(false);
    setIsAddingObject(false);
    clearClickState();
  }, [jobs.setSelectedObjectId, clearClickState]);

  const handleToggleHidden = useCallback((objectId: number) => {
    // Hiding the currently selected object clears its selection (see
    // useSessionJobs.toggleHidden) — mirror that here to also drop 3D, since
    // a hidden object can never be the selected one.
    const wasSelected = jobs.selectedObjectId === objectId;
    jobs.toggleHidden(objectId);
    if (wasSelected) {
      setShow3D(false);
    }
  }, [jobs.selectedObjectId, jobs.toggleHidden]);

  // Pointer down anywhere on the result stage: alpha-precise hit-test against
  // every visible object (topmost/selected first), select whichever object was
  // hit, and arm it for dragging. A miss leaves the current selection alone.
  const handleStagePointerDown: React.PointerEventHandler<HTMLDivElement> = useCallback((event) => {
    if (!backgroundNaturalSize || !renderedBackgroundRect) {
      return;
    }

    const stageRect = event.currentTarget.getBoundingClientRect();
    const localX = event.clientX - stageRect.left;
    const localY = event.clientY - stageRect.top;
    const scaleX = renderedBackgroundRect.width / backgroundNaturalSize.width;
    const scaleY = renderedBackgroundRect.height / backgroundNaturalSize.height;
    if (scaleX <= 0 || scaleY <= 0) {
      return;
    }

    const naturalX = localX / scaleX;
    const naturalY = localY / scaleY;

    // While the selected object's 3D model is shown, its 2D cutout is hidden
    // and that screen region belongs to the (higher z-index) 3D frame instead.
    const hitOrder = buildHitTestOrder(jobs.objects, jobs.selectedObjectId).filter(
      (obj) => !(show3D && obj.objectId === jobs.selectedObjectId),
    );
    for (const obj of hitOrder) {
      const localObjX = naturalX - obj.offset.x;
      const localObjY = naturalY - obj.offset.y;

      if (obj.cutoutAlphaBounds) {
        const bounds = obj.cutoutAlphaBounds;
        if (
          localObjX < bounds.left ||
          localObjX > bounds.right ||
          localObjY < bounds.top ||
          localObjY > bounds.bottom
        ) {
          continue;
        }
      }

      if (sampleObjectAlpha(obj.objectId, localObjX, localObjY) <= ALPHA_HIT_THRESHOLD) {
        continue;
      }

      event.preventDefault();
      document.body.classList.add("cutout-dragging");
      dragStateRef.current = {
        objectId: obj.objectId,
        pointerId: event.pointerId,
        startClientX: event.clientX,
        startClientY: event.clientY,
        startOffsetX: obj.offset.x,
        startOffsetY: obj.offset.y,
      };
      setIsDraggingCutout(true);
      handleSelectObject(obj.objectId);
      return;
    }
    // No object under the pointer: keep the current selection unchanged.
  }, [backgroundNaturalSize, renderedBackgroundRect, jobs.objects, jobs.selectedObjectId, show3D, sampleObjectAlpha, handleSelectObject]);

  useEffect(() => {
    if (!isDraggingCutout) {
      return;
    }

    const handlePointerMove = (event: PointerEvent) => {
      const dragState = dragStateRef.current;
      const naturalSize = backgroundNaturalSizeRef.current;
      const renderedRect = renderedBackgroundRectRef.current;
      if (!dragState || !naturalSize || !renderedRect) {
        return;
      }

      if (dragState.pointerId !== event.pointerId) {
        return;
      }

      const scaleX = renderedRect.width / naturalSize.width;
      const scaleY = renderedRect.height / naturalSize.height;
      if (scaleX <= 0 || scaleY <= 0) {
        return;
      }

      const targetObject = jobs.objects.find((o) => o.objectId === dragState.objectId);
      const bounds = targetObject?.cutoutAlphaBounds ?? null;

      // Mouse delta arrives in screen pixels. Convert back into natural-image
      // pixels so drag behavior stays stable under responsive resize.
      const nextOffset = clampCutoutOffset(
        {
          x: dragState.startOffsetX + (event.clientX - dragState.startClientX) / scaleX,
          y: dragState.startOffsetY + (event.clientY - dragState.startClientY) / scaleY,
        },
        bounds,
        naturalSize,
      );

      jobs.updateOffset(dragState.objectId, nextOffset);
    };

    const finishDrag = (pointerId: number) => {
      if (dragStateRef.current?.pointerId !== pointerId) {
        return;
      }

      dragStateRef.current = null;
      setIsDraggingCutout(false);
      document.body.classList.remove("cutout-dragging");
    };

    const handlePointerUp = (event: PointerEvent) => {
      finishDrag(event.pointerId);
    };

    const handlePointerCancel = (event: PointerEvent) => {
      finishDrag(event.pointerId);
    };

    window.addEventListener("pointermove", handlePointerMove);
    window.addEventListener("pointerup", handlePointerUp);
    window.addEventListener("pointercancel", handlePointerCancel);

    return () => {
      window.removeEventListener("pointermove", handlePointerMove);
      window.removeEventListener("pointerup", handlePointerUp);
      window.removeEventListener("pointercancel", handlePointerCancel);
      document.body.classList.remove("cutout-dragging");
    };
    // jobs.objects intentionally omitted: handlePointerMove reads the target
    // object's bounds fresh via jobs.objects.find on every move event, but
    // re-subscribing window listeners on every offset update (which changes
    // jobs.objects) would tear down and rebuild mid-drag. jobs.updateOffset is
    // stable across renders (see useSessionJobs), so this is safe.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isDraggingCutout]);

  const handleAddObject = useCallback(() => {
    setIsAddingObject(true);
    clearClickState();
    setShow3D(false);
  }, [clearClickState]);

  const handleToggleObjectPanel = useCallback(() => {
    setObjectPanelCollapsed((c) => !c);
  }, []);

  // Every visible cutout is rendered at the same contained rect as the
  // background, then shifted by its own offset — each object moves
  // independently instead of sharing one position.
  const getCutoutOverlayStyle = (obj: { offset: ClickPosition }, zIndex: number): React.CSSProperties | undefined =>
    backgroundNaturalSize && renderedBackgroundRect
      ? {
          left: `${renderedBackgroundRect.x + obj.offset.x * (renderedBackgroundRect.width / backgroundNaturalSize.width)}px`,
          top: `${renderedBackgroundRect.y + obj.offset.y * (renderedBackgroundRect.height / backgroundNaturalSize.height)}px`,
          width: `${renderedBackgroundRect.width}px`,
          height: `${renderedBackgroundRect.height}px`,
          zIndex,
        }
      : undefined;

  // Transparent hit-testing layer sized to the contained background rect. The
  // cutout <img>s themselves are pointer-events:none (see style.css) because
  // they're full-image-sized and would otherwise swallow every click.
  const interactionOverlayStyle: React.CSSProperties | undefined =
    backgroundNaturalSize && renderedBackgroundRect
      ? {
          left: `${renderedBackgroundRect.x}px`,
          top: `${renderedBackgroundRect.y}px`,
          width: `${renderedBackgroundRect.width}px`,
          height: `${renderedBackgroundRect.height}px`,
          cursor: isDraggingCutout ? "grabbing" : "grab",
        }
      : undefined;

  const visibleObjects = jobs.objects.filter((o) => !o.hidden);
  // While the selected object's 3D model is shown, its 2D cutout is hidden so
  // the 3D frame visually replaces it instead of stacking on top of it.
  const stageCutoutObjects = visibleObjects.filter(
    (obj) => !(show3D && obj.objectId === jobs.selectedObjectId),
  );

  // On-stage rect the selected object's 2D cutout occupies (its alpha bounds +
  // current drag offset). Both the 3D frame and the selection ring are placed
  // against this same rect, so neither jumps relative to the 2D cutout.
  const selectedObjectStageRect =
    backgroundNaturalSize && renderedBackgroundRect && selectedObject
      ? getBoundsStageRect(
          selectedObject.cutoutAlphaBounds,
          selectedObject.offset,
          renderedBackgroundRect,
          backgroundNaturalSize,
        )
      : null;

  const positionOverSelected = (rect: {
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

  // The 3D model replaces the selected object's 2D cutout in place, so swapping
  // between 2D and 3D doesn't jump the object to a different spot/scale.
  const model3DFrameStyle: React.CSSProperties | undefined = selectedObjectStageRect
    ? {
        ...positionOverSelected(selectedObjectStageRect),
        // Above .result-interaction-overlay (z-index 100) so OrbitControls
        // receive pointer events instead of the 2D drag/hit-test layer.
        zIndex: 200,
        pointerEvents: "auto",
        touchAction: "none",
      }
    : undefined;

  // Highlight ring traced around whichever object is currently selected (2D or
  // 3D), so the panel's "is-active" thumbnail has an on-canvas counterpart.
  // Non-interactive: sits above everything but never intercepts pointer events.
  const selectionHighlightStyle: React.CSSProperties | undefined =
    selectedObjectStageRect && !isAddingObject
      ? {
          ...positionOverSelected(selectedObjectStageRect),
          zIndex: 210,
          pointerEvents: "none",
        }
      : undefined;

  const uploadBusy = Boolean(imageId && !uploadedFile);
  // Clicking is enabled during initial upload (no background yet) or when explicitly adding a new object.
  const clickEnabled = Boolean(imageId && (!jobs.backgroundSrc || isAddingObject));
  const sessionStatus = jobs.hasPendingWork
    ? `Removing ${jobs.pendingJobs.length} object${jobs.pendingJobs.length === 1 ? "" : "s"}...`
    : jobs.isChoosingMask
      ? "Choose mask"
      : isAddingObject
        ? "Adding object"
        : jobs.backgroundSrc
          ? "Results ready"
          : imageId
            ? "Image uploaded"
            : "Awaiting upload";

  return (
    <div className="page">
      {error ? (
        <div className="error-modal-backdrop" role="presentation" onClick={() => setError(null)}>
          <div
            className="error-modal"
            role="alertdialog"
            aria-modal="true"
            aria-labelledby="error-modal-title"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="error-modal-header">
              <h2 id="error-modal-title">Request error</h2>
              <button
                type="button"
                className="error-modal-close"
                onClick={() => setError(null)}
                aria-label="Close error dialog"
              >
                Close
              </button>
            </div>
            <pre className="error-modal-body">{error}</pre>
          </div>
        </div>
      ) : null}

      {jobs.isChoosingMask ? (
        <MaskPickerModal
          masks={jobs.maskOptions}
          onSelect={handleMaskSelected}
          onClose={jobs.closeMaskPicker}
        />
      ) : null}

      <input
        ref={uploadOtherInputRef}
        type="file"
        accept="image/*"
        className="file-input"
        onChange={handleUploadOtherSelected}
        aria-label="Upload another image"
      />

      <header className="page-header">
        <div className="brand-mark">
          <img src={avroomLogo} alt="AVRoom logo" className="brand-logo" />
        </div>

        <div className="brand-copy">
          <h1>Avroom demo</h1>
          <p className="page-subtitle">Object segmentation and 3d reconstruction</p>
        </div>

        <div className="status-pulse">{sessionStatus}</div>
      </header>

      <main className="page-main">
        <section className="workspace-rail">
          <SessionPicker onSessionSelect={handleSessionSelect} refreshKey={sessionsRefreshKey} />
        </section>

        <section className="workspace-panel">
          {imageId ? (
            <div className="session-name-row">
              <input
                type="text"
                className="session-name-input"
                value={sessionName}
                onChange={(e) => setSessionName(e.target.value)}
                onKeyDown={handleNameKeyDown}
                placeholder="Session name (Enter to save)"
                aria-label="Session name"
              />
            </div>
          ) : null}

          <div className="main-frame-container">
            <div className="main-frame-image-area">
              {!jobs.backgroundSrc || isAddingObject ? (
                <UploadFrame
                  ref={frameInputRef}
                  imageSrc={isAddingObject ? jobs.backgroundSrc : uploadedImageUrl}
                  clickPosition={clickPosition}
                  onFileSelected={handleFileSelected}
                  onImageClick={handleImageClick}
                  disabled={isUploading || jobs.isSegmenting || jobs.isChoosingMask || isGenerating3D}
                  clickEnabled={clickEnabled}
                />
              ) : (
                <div className="frame upload-frame result-main-frame">
                  <div ref={resultStageRef} className="image-container result-image-stage">
                    <img
                      src={jobs.backgroundSrc}
                      alt="Background result"
                      className="frame-image"
                      onLoad={handleBackgroundLoad}
                    />

                    {stageCutoutObjects.map((obj, index) => (
                      <img
                        key={obj.objectId}
                        src={obj.cutoutSrc}
                        alt={obj.name ?? `Object ${obj.objectId}`}
                        className="cutout-overlay"
                        style={getCutoutOverlayStyle(
                          obj,
                          obj.objectId === jobs.selectedObjectId ? stageCutoutObjects.length + 2 : index + 2,
                        )}
                        draggable={false}
                      />
                    ))}

                    <div
                      className="result-interaction-overlay"
                      style={interactionOverlayStyle}
                      onPointerDown={handleStagePointerDown}
                    />

                    {show3D && glbData ? (
                      <Model3DFrame
                        glbData={glbData}
                        clickNormalizedPos={selectedObject?.normalizedClickPos ?? null}
                        style={model3DFrameStyle}
                        backgroundImage={null}
                      />
                    ) : null}

                    {selectionHighlightStyle ? (
                      <div className="selection-highlight" style={selectionHighlightStyle} />
                    ) : null}
                  </div>
                </div>
              )}

              {/* Rendered regardless of which branch above is active — a
                  conflict can fire while adding a new object (UploadFrame
                  branch), not just once results exist. */}
              {conflictNotices.notices.length > 0 ? (
                <div className="conflict-notice-stack">
                  {conflictNotices.notices.map((notice) => (
                    <div key={notice.id} className="conflict-notice">
                      <span>{notice.message}</span>
                      <button
                        type="button"
                        className="conflict-notice-dismiss"
                        onClick={() => conflictNotices.dismiss(notice.id)}
                        aria-label="Dismiss"
                      >
                        ×
                      </button>
                    </div>
                  ))}
                </div>
              ) : null}
            </div>

            {imageId && (jobs.objects.length > 0 || jobs.pendingJobs.length > 0) ? (
              <ObjectPanel
                objects={jobs.objects}
                pending={jobs.pendingJobs}
                selectedObjectId={jobs.selectedObjectId}
                isAddingObject={isAddingObject}
                disabled={isGenerating3D}
                onSelectObject={handleSelectObject}
                onToggleHidden={handleToggleHidden}
                onAddObject={handleAddObject}
                onRenameObject={handleRenameObject}
                collapsed={objectPanelCollapsed}
                onToggleCollapsed={handleToggleObjectPanel}
              />
            ) : null}
          </div>

          {jobs.backgroundSrc && !isAddingObject && jobs.objects.length > 0 ? (
            <div className="control-dashboard">
              <label className="dashboard-toggle">
                <input
                  type="checkbox"
                  checked={show3D}
                  onChange={handleToggle3D}
                  disabled={isGenerating3D || jobs.selectedObjectId === null}
                />
                <span>
                  {isGenerating3D
                    ? "Generating..."
                    : jobs.selectedObjectId === null
                      ? "Select an object to view its 3D model"
                      : "Show 3D model"}
                </span>
              </label>
            </div>
          ) : null}

          <div className="action-row">
            <button
              type="button"
              className={`primary-button${uploadBusy ? " ghost" : ""}`}
              onClick={uploadBusy ? triggerFileInput : handleUpload}
              disabled={isUploading || jobs.isSegmenting || isGenerating3D || (!uploadBusy && !uploadedFile)}
            >
              {isUploading ? "Uploading..." : uploadBusy ? "Upload other" : "Upload"}
            </button>

            <button
              type="button"
              className="primary-button secondary"
              onClick={handleCutOut}
              disabled={!imageId || !clickPosition || (!isAddingObject && !!jobs.backgroundSrc) || jobs.isSegmenting || jobs.isChoosingMask}
            >
              {jobs.isSegmenting ? "Segmenting..." : "Cut Out"}
            </button>
          </div>
          {imageId ? (
            <div className="delete-row">
              <button
                type="button"
                className={`primary-button danger${deleteConfirming ? " confirming" : ""}`}
                onClick={handleDeleteSession}
                disabled={isDeleting || isUploading || isGenerating3D}
              >
                {isDeleting ? "Deleting..." : deleteConfirming ? "Confirm delete?" : "Delete session"}
              </button>
            </div>
          ) : null}
        </section>
      </main>
    </div>
  );
};
