import React from "react";
import { useCallback, useEffect, useRef, useState } from "react";

import {
  API_BASE_URL,
  deleteSession,
  fetchCached3DModel,
  generate3DModel,
  getSessionObjects,
  getUidCacheStatus,
  inpaintMask,
  segmentImage,
  setSessionName as saveSessionName,
  uploadImage,
} from "../../api/images";
import avroomLogo from "../../assets/avroom.png";
import type { CutoutBounds, SegmentMaskOption, SegmentRequest } from "../../types/api";
import { MaskPickerModal } from "../widgets/MaskPickerModal";
import { Model3DFrame } from "../widgets/Model3DFrame";
import { ObjectPanel } from "../widgets/ObjectPanel";
import { SessionPicker } from "../widgets/SessionPicker";
import { UploadFrame } from "../widgets/UploadFrame";

interface ClickPosition {
  x: number;
  y: number;
}

interface Size {
  width: number;
  height: number;
}

interface CutoutAlphaBounds {
  left: number;
  top: number;
  right: number;
  bottom: number;
  naturalWidth: number;
  naturalHeight: number;
}

interface DragState {
  objectId: number;
  pointerId: number;
  startClientX: number;
  startClientY: number;
  startOffsetX: number;
  startOffsetY: number;
}

interface CutoutObject {
  objectId: number;
  cutoutSrc: string;
  cutoutAlphaBounds: CutoutAlphaBounds | null;
  normalizedClickPos: ClickPosition | null;
  glbData: ArrayBuffer | null;
  // Per-object visibility toggle. Hidden objects render nothing and cannot be
  // selected/dragged; see ObjectPanel eye button.
  hidden: boolean;
  // Per-object drag offset, natural-image pixels. Every object stays composited
  // on the background simultaneously now, so position can no longer live in a
  // single shared piece of state.
  offset: ClickPosition;
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

const toCutoutAlphaBounds = (bounds: CutoutBounds | null | undefined): CutoutAlphaBounds | null => {
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

// Minimum alpha (0-255) that counts as "clicked the object" rather than
// transparent padding or an antialiased edge pixel.
const ALPHA_HIT_THRESHOLD = 10;

// Objects render back-to-front in array order (later = on top, see zIndex in
// getCutoutOverlayStyle), so hit-testing must walk topmost-first. The
// currently selected object is always drawn on top of everything else, so it
// is tested first regardless of its position in the array.
const buildHitTestOrder = (objects: CutoutObject[], selectedObjectId: number | null): CutoutObject[] => {
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

export const MainPage: React.FC = () => {
  const frameInputRef = useRef<HTMLInputElement>(null);
  const uploadOtherInputRef = useRef<HTMLInputElement>(null);
  const resultStageRef = useRef<HTMLDivElement>(null);
  const dragStateRef = useRef<DragState | null>(null);
  const backgroundNaturalSizeRef = useRef<Size | null>(null);
  const renderedBackgroundRectRef = useRef<ReturnType<typeof getContainedImageRect>>(null);
  const objectsRef = useRef<CutoutObject[]>([]);
  const hitCanvasesRef = useRef<Map<number, HitCanvasEntry>>(new Map());

  const [uploadedFile, setUploadedFile] = useState<File | null>(null);
  const [uploadedImageUrl, setUploadedImageUrl] = useState<string | null>(null);
  const [imageId, setImageId] = useState<string | null>(null);
  const [clickPosition, setClickPosition] = useState<ClickPosition | null>(null);
  const [naturalClickPos, setNaturalClickPos] = useState<ClickPosition | null>(null);
  const [normalizedClickPos, setNormalizedClickPos] = useState<ClickPosition | null>(null);
  const [backgroundSrc, setBackgroundSrc] = useState<string | null>(null);
  const [backgroundNaturalSize, setBackgroundNaturalSize] = useState<Size | null>(null);
  const [resultStageSize, setResultStageSize] = useState<Size | null>(null);
  const [show3D, setShow3D] = useState(false);
  const [maskOptions, setMaskOptions] = useState<SegmentMaskOption[]>([]);
  const [selectedMaskId, setSelectedMaskId] = useState<string | null>(null);
  const [isDraggingCutout, setIsDraggingCutout] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [isInpainting, setIsInpainting] = useState(false);
  const [isGenerating3D, setIsGenerating3D] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sessionName, setSessionName] = useState<string>("");
  const [sessionsRefreshKey, setSessionsRefreshKey] = useState(0);
  const [isDeleting, setIsDeleting] = useState(false);
  const [deleteConfirming, setDeleteConfirming] = useState(false);
  const deleteConfirmTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const [objects, setObjects] = useState<CutoutObject[]>([]);
  // No object is selected at the start of a session; selection is set by
  // clicking/dragging an object in the preview or clicking it in the panel.
  const [selectedObjectId, setSelectedObjectId] = useState<number | null>(null);
  const [isAddingObject, setIsAddingObject] = useState(false);
  const [objectPanelCollapsed, setObjectPanelCollapsed] = useState(false);

  const replaceUploadedImageUrl = useCallback((nextUrl: string | null) => {
    setUploadedImageUrl((previousUrl) => {
      if (previousUrl?.startsWith("blob:")) {
        URL.revokeObjectURL(previousUrl);
      }

      return nextUrl;
    });
  }, []);

  const resetWorkspaceState = useCallback(() => {
    setClickPosition(null);
    setNaturalClickPos(null);
    setNormalizedClickPos(null);
    setBackgroundSrc(null);
    setBackgroundNaturalSize(null);
    setResultStageSize(null);
    setShow3D(false);
    setMaskOptions([]);
    setSelectedMaskId(null);
    setIsDraggingCutout(false);
    dragStateRef.current = null;
    setObjects([]);
    setSelectedObjectId(null);
    setIsAddingObject(false);
    setError(null);
    if (deleteConfirmTimerRef.current) {
      clearTimeout(deleteConfirmTimerRef.current);
      deleteConfirmTimerRef.current = null;
    }
    setDeleteConfirming(false);
  }, []);

  // Derive selected-object values from the objects array. Only the selected
  // object may show a 3D model; every non-hidden object still renders on the
  // stage regardless of selection.
  const selectedObject = objects.find((o) => o.objectId === selectedObjectId) ?? null;
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
    resetWorkspaceState();
    replaceUploadedImageUrl(URL.createObjectURL(file));
  }, [replaceUploadedImageUrl, resetWorkspaceState]);

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
    resetWorkspaceState();
    replaceUploadedImageUrl(`${API_BASE_URL}/images/${uid}/original`);

    try {
      const status = await getUidCacheStatus(uid);
      setSessionName(status.name ?? uid);

      if (status.has_background) {
        setBackgroundSrc(`${API_BASE_URL}/images/${uid}/background`);
      }

      if (status.has_cutout) {
        const objList = await getSessionObjects(uid);
        if (objList.objects.length > 0) {
          const loadedObjects: CutoutObject[] = objList.objects.map((info) => ({
            objectId: info.object_id,
            cutoutSrc: `data:image/${info.format};base64,${info.cutout_b64}`,
            cutoutAlphaBounds: toCutoutAlphaBounds(info.cutout_bounds ?? null),
            normalizedClickPos: null,
            glbData: null,
            hidden: false,
            offset: { x: 0, y: 0 },
          }));
          setObjects(loadedObjects);
          // No selection on restore, same as a fresh upload — user picks an
          // object explicitly before it can be dragged or sent to 3D.
        }
      }
    } catch {
      // Non-fatal. User can rerun cutout.
      setSessionName(uid);
    }
  }, [replaceUploadedImageUrl, resetWorkspaceState]);

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
      setSessionsRefreshKey((k) => k + 1);
    } catch (uploadError) {
      const message =
        uploadError instanceof Error ? uploadError.message : "Unexpected upload error.";
      setError(message);
    } finally {
      setIsUploading(false);
    }
  }, [uploadedFile]);

  const handleCutOut = useCallback(async () => {
    if (!imageId) {
      setError("No uploaded image to process yet.");
      return;
    }

    if (!naturalClickPos) {
      setError("Please click on image to select point of interest.");
      return;
    }

    const payload: SegmentRequest = {
      image_id: imageId,
      x: naturalClickPos.x,
      y: naturalClickPos.y,
    };

    setIsProcessing(true);
    setError(null);

    try {
      const result = await segmentImage(payload);
      if (result.masks.length === 0) {
        throw new Error("No mask candidates returned.");
      }

      // Processing now has two phases: segmentation stops here so user can
      // decide subjective best mask before expensive inpainting runs.
      setMaskOptions(result.masks);
      setSelectedMaskId(null);
    } catch (processError) {
      const message =
        processError instanceof Error ? processError.message : "Unexpected processing error.";
      setError(message);
    } finally {
      setIsProcessing(false);
    }
  }, [imageId, naturalClickPos]);

  const handleMaskPickerClose = useCallback(() => {
    if (isInpainting) {
      return;
    }

    setMaskOptions([]);
    setSelectedMaskId(null);
  }, [isInpainting]);

  const handleMaskSelected = useCallback(async (maskId: string) => {
    if (!imageId || isInpainting) {
      return;
    }

    setSelectedMaskId(maskId);
    setIsInpainting(true);
    setError(null);

    try {
      const result = await inpaintMask({ image_id: imageId, mask_id: maskId });
      const base64Prefix = `data:image/${result.format};base64,`;

      const newObject: CutoutObject = {
        objectId: result.object_id,
        cutoutSrc: `${base64Prefix}${result.cutout_b64}`,
        cutoutAlphaBounds: toCutoutAlphaBounds(result.cutout_bounds),
        normalizedClickPos: normalizedClickPos,
        glbData: null,
        hidden: false,
        offset: { x: 0, y: 0 },
      };

      // Newly created object auto-selects — the user just made it, so it
      // becomes the one draggable / 3D-able object until they pick another.
      setObjects((prev) => [...prev, newObject]);
      setSelectedObjectId(result.object_id);
      setBackgroundSrc(`${base64Prefix}${result.background_b64}`);
      setIsAddingObject(false);
      setShow3D(false);
      setMaskOptions([]);
      setSelectedMaskId(null);
    } catch (processError) {
      const message =
        processError instanceof Error ? processError.message : "Unexpected inpainting error.";
      setError(message);
    } finally {
      setIsInpainting(false);
    }
  }, [imageId, isInpainting, normalizedClickPos]);

  const handleToggle3D = useCallback(async () => {
    if (show3D) {
      setShow3D(false);
      return;
    }

    if (!imageId || selectedObjectId === null) {
      setError("No object selected for 3D generation.");
      return;
    }

    if (glbData) {
      setShow3D(true);
      return;
    }

    // Snapshot the target id before any await so we write to the right object
    // even if the user switches selection while generation is in flight.
    const targetObjectId = selectedObjectId;
    setIsGenerating3D(true);
    setError(null);

    try {
      const cached = await fetchCached3DModel(imageId, targetObjectId);
      if (cached) {
        setObjects((prev) =>
          prev.map((o) => (o.objectId === targetObjectId ? { ...o, glbData: cached } : o))
        );
        // Only surface the 3D view if the user hasn't switched selection away.
        setSelectedObjectId((current) => {
          if (current === targetObjectId) setShow3D(true);
          return current;
        });
        return;
      }

      const buffer = await generate3DModel(imageId, targetObjectId);
      setObjects((prev) =>
        prev.map((o) => (o.objectId === targetObjectId ? { ...o, glbData: buffer } : o))
      );
      setSelectedObjectId((current) => {
        if (current === targetObjectId) setShow3D(true);
        return current;
      });
    } catch (genError) {
      const message =
        genError instanceof Error ? genError.message : "Unexpected 3D generation error.";
      setError(message);
      setShow3D(false);
    } finally {
      setIsGenerating3D(false);
    }
  }, [selectedObjectId, glbData, imageId, show3D]);

  const handleNameKeyDown = useCallback(async (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key !== "Enter" || !imageId || !sessionName.trim()) {
      return;
    }

    event.currentTarget.blur();

    try {
      await saveSessionName(imageId, sessionName.trim());
      setSessionsRefreshKey((k) => k + 1);
    } catch (nameError) {
      const message =
        nameError instanceof Error ? nameError.message : "Failed to save session name.";
      setError(message);
    }
  }, [imageId, sessionName]);

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
      resetWorkspaceState();
      setSessionName("");
      setSessionsRefreshKey((k) => k + 1);
    } catch (deleteError) {
      const message =
        deleteError instanceof Error ? deleteError.message : "Failed to delete session.";
      setError(message);
    } finally {
      setIsDeleting(false);
    }
  }, [deleteConfirming, imageId, replaceUploadedImageUrl, resetWorkspaceState]);

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
    if (!backgroundSrc) {
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
  }, [backgroundSrc, measureResultStage]);

  useEffect(() => {
    // Window-level listeners need fresh geometry without re-binding on every
    // mouse move, so keep latest derived values in refs.
    backgroundNaturalSizeRef.current = backgroundNaturalSize;
  }, [backgroundNaturalSize]);

  useEffect(() => {
    objectsRef.current = objects;
  }, [objects]);

  // Build (and prune) an offscreen per-object canvas so pointer-down hit
  // testing can sample real alpha instead of only a bounding box. Cheap no-op
  // for objects that already have a canvas (e.g. re-runs while dragging).
  useEffect(() => {
    const currentIds = new Set(objects.map((o) => o.objectId));
    hitCanvasesRef.current.forEach((_entry, id) => {
      if (!currentIds.has(id)) {
        hitCanvasesRef.current.delete(id);
      }
    });

    objects.forEach((obj) => {
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
  }, [objects]);

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
    setSelectedObjectId(objectId);
    // 3D is scoped to whichever object is selected — switching away hides it.
    setShow3D(false);
    setIsAddingObject(false);
    setClickPosition(null);
    setNaturalClickPos(null);
    setNormalizedClickPos(null);
  }, []);

  const handleToggleHidden = useCallback((objectId: number) => {
    const target = objects.find((o) => o.objectId === objectId);
    if (!target) {
      return;
    }
    const willBeHidden = !target.hidden;

    setObjects((prev) =>
      prev.map((o) => (o.objectId === objectId ? { ...o, hidden: willBeHidden } : o))
    );

    // Hiding the currently selected object clears selection, same as the
    // start-of-session state — a hidden object can't be interacted with.
    if (willBeHidden && selectedObjectId === objectId) {
      setSelectedObjectId(null);
      setShow3D(false);
    }
  }, [objects, selectedObjectId]);

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
    const hitOrder = buildHitTestOrder(objects, selectedObjectId).filter(
      (obj) => !(show3D && obj.objectId === selectedObjectId),
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
  }, [backgroundNaturalSize, renderedBackgroundRect, objects, selectedObjectId, show3D, sampleObjectAlpha, handleSelectObject]);

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

      const targetObject = objectsRef.current.find((o) => o.objectId === dragState.objectId);
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

      setObjects((prev) =>
        prev.map((o) => (o.objectId === dragState.objectId ? { ...o, offset: nextOffset } : o))
      );
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
  }, [isDraggingCutout]);

  const handleAddObject = useCallback(() => {
    setIsAddingObject(true);
    setClickPosition(null);
    setNaturalClickPos(null);
    setNormalizedClickPos(null);
    setShow3D(false);
  }, []);

  const handleToggleObjectPanel = useCallback(() => {
    setObjectPanelCollapsed((c) => !c);
  }, []);

  // Every visible cutout is rendered at the same contained rect as the
  // background, then shifted by its own offset — each object moves
  // independently instead of sharing one position.
  const getCutoutOverlayStyle = (obj: CutoutObject, zIndex: number): React.CSSProperties | undefined =>
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

  const visibleObjects = objects.filter((o) => !o.hidden);
  // While the selected object's 3D model is shown, its 2D cutout is hidden so
  // the 3D frame visually replaces it instead of stacking on top of it.
  const stageCutoutObjects = visibleObjects.filter(
    (obj) => !(show3D && obj.objectId === selectedObjectId),
  );

  // Position the 3D frame over roughly the same rect the selected object's 2D
  // cutout occupies (its alpha bounds + current drag offset), so swapping
  // between 2D and 3D doesn't jump the object to a different spot/scale.
  const model3DFrameStyle: React.CSSProperties | undefined =
    backgroundNaturalSize && renderedBackgroundRect && selectedObject
      ? (() => {
          const scaleX = renderedBackgroundRect.width / backgroundNaturalSize.width;
          const scaleY = renderedBackgroundRect.height / backgroundNaturalSize.height;
          const bounds = selectedObject.cutoutAlphaBounds;
          const left = bounds
            ? renderedBackgroundRect.x + (bounds.left + selectedObject.offset.x) * scaleX
            : renderedBackgroundRect.x;
          const top = bounds
            ? renderedBackgroundRect.y + (bounds.top + selectedObject.offset.y) * scaleY
            : renderedBackgroundRect.y;
          const width = bounds ? (bounds.right - bounds.left) * scaleX : renderedBackgroundRect.width;
          const height = bounds ? (bounds.bottom - bounds.top) * scaleY : renderedBackgroundRect.height;

          return {
            position: "absolute",
            left: `${left}px`,
            top: `${top}px`,
            width: `${width}px`,
            height: `${height}px`,
            // Above .result-interaction-overlay (z-index 100) so OrbitControls
            // receive pointer events instead of the 2D drag/hit-test layer.
            zIndex: 200,
            pointerEvents: "auto",
            touchAction: "none",
          } satisfies React.CSSProperties;
        })()
      : undefined;

  const isChoosingMask = maskOptions.length > 0;
  const uploadBusy = Boolean(imageId && !uploadedFile);
  // Clicking is enabled during initial upload (no background yet) or when explicitly adding a new object.
  const clickEnabled = Boolean(imageId && (!backgroundSrc || isAddingObject));
  const sessionStatus = isInpainting
    ? "Inpainting"
    : isChoosingMask
      ? "Choose mask"
      : isAddingObject
        ? "Adding object"
        : objects.length > 0
          ? `${objects.length} object${objects.length === 1 ? "" : "s"} removed`
          : backgroundSrc
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

      {isChoosingMask ? (
        <MaskPickerModal
          masks={maskOptions}
          selectedMaskId={selectedMaskId}
          isInpainting={isInpainting}
          onSelect={handleMaskSelected}
          onClose={handleMaskPickerClose}
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
              {!backgroundSrc || isAddingObject ? (
                <UploadFrame
                  ref={frameInputRef}
                  imageSrc={isAddingObject ? backgroundSrc : uploadedImageUrl}
                  clickPosition={clickPosition}
                  onFileSelected={handleFileSelected}
                  onImageClick={handleImageClick}
                  disabled={isUploading || isProcessing || isChoosingMask || isInpainting || isGenerating3D}
                  clickEnabled={clickEnabled}
                />
              ) : (
                <div className="frame upload-frame result-main-frame">
                  <div ref={resultStageRef} className="image-container result-image-stage">
                    <img
                      src={backgroundSrc}
                      alt="Background result"
                      className="frame-image"
                      onLoad={handleBackgroundLoad}
                    />

                    {stageCutoutObjects.map((obj, index) => (
                      <img
                        key={obj.objectId}
                        src={obj.cutoutSrc}
                        alt={`Object ${obj.objectId}`}
                        className="cutout-overlay"
                        style={getCutoutOverlayStyle(
                          obj,
                          obj.objectId === selectedObjectId ? stageCutoutObjects.length + 2 : index + 2,
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
                  </div>
                </div>
              )}
            </div>

            {imageId && objects.length > 0 ? (
              <ObjectPanel
                objects={objects}
                selectedObjectId={selectedObjectId}
                isAddingObject={isAddingObject}
                disabled={isInpainting || isGenerating3D}
                onSelectObject={handleSelectObject}
                onToggleHidden={handleToggleHidden}
                onAddObject={handleAddObject}
                collapsed={objectPanelCollapsed}
                onToggleCollapsed={handleToggleObjectPanel}
              />
            ) : null}
          </div>

          {backgroundSrc && !isAddingObject && objects.length > 0 ? (
            <div className="control-dashboard">
              <label className="dashboard-toggle">
                <input
                  type="checkbox"
                  checked={show3D}
                  onChange={handleToggle3D}
                  disabled={isGenerating3D || selectedObjectId === null}
                />
                <span>
                  {isGenerating3D
                    ? "Generating..."
                    : selectedObjectId === null
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
              disabled={isUploading || isProcessing || isChoosingMask || isInpainting || isGenerating3D || (!uploadBusy && !uploadedFile)}
            >
              {isUploading ? "Uploading..." : uploadBusy ? "Upload other" : "Upload"}
            </button>

            <button
              type="button"
              className="primary-button secondary"
              onClick={handleCutOut}
              disabled={!imageId || !clickPosition || (!isAddingObject && !!backgroundSrc) || isProcessing || isChoosingMask || isInpainting}
            >
              {isProcessing ? "Segmenting..." : isInpainting ? "Inpainting..." : "Cut Out"}
            </button>
          </div>
          {imageId ? (
            <div className="delete-row">
              <button
                type="button"
                className={`primary-button danger${deleteConfirming ? " confirming" : ""}`}
                onClick={handleDeleteSession}
                disabled={isDeleting || isUploading || isProcessing || isInpainting || isGenerating3D}
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
