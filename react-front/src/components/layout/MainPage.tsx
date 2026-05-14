import React from "react";
import { useCallback, useEffect, useRef, useState } from "react";

import {
  API_BASE_URL,
  clickImage,
  fetchCached3DModel,
  generate3DModel,
  getUidCacheStatus,
  uploadImage,
} from "../../api/images";
import avroomLogo from "../../assets/avroom.png";
import type { ClickRequest, CutoutBounds } from "../../types/api";
import { Model3DFrame } from "../widgets/Model3DFrame";
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
  pointerId: number;
  startClientX: number;
  startClientY: number;
  startOffsetX: number;
  startOffsetY: number;
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

export const MainPage: React.FC = () => {
  const frameInputRef = useRef<HTMLInputElement>(null);
  const uploadOtherInputRef = useRef<HTMLInputElement>(null);
  const resultStageRef = useRef<HTMLDivElement>(null);
  const dragStateRef = useRef<DragState | null>(null);
  const backgroundNaturalSizeRef = useRef<Size | null>(null);
  const cutoutAlphaBoundsRef = useRef<CutoutAlphaBounds | null>(null);
  const renderedBackgroundRectRef = useRef<ReturnType<typeof getContainedImageRect>>(null);

  const [uploadedFile, setUploadedFile] = useState<File | null>(null);
  const [uploadedImageUrl, setUploadedImageUrl] = useState<string | null>(null);
  const [imageId, setImageId] = useState<string | null>(null);
  const [clickPosition, setClickPosition] = useState<ClickPosition | null>(null);
  const [naturalClickPos, setNaturalClickPos] = useState<ClickPosition | null>(null);
  const [normalizedClickPos, setNormalizedClickPos] = useState<ClickPosition | null>(null);
  const [backgroundSrc, setBackgroundSrc] = useState<string | null>(null);
  const [cutoutSrc, setCutoutSrc] = useState<string | null>(null);
  const [backgroundNaturalSize, setBackgroundNaturalSize] = useState<Size | null>(null);
  const [resultStageSize, setResultStageSize] = useState<Size | null>(null);
  const [cutoutAlphaBounds, setCutoutAlphaBounds] = useState<CutoutAlphaBounds | null>(null);
  const [cutoutOffset, setCutoutOffset] = useState<ClickPosition>({ x: 0, y: 0 });
  const [sessionLocked, setSessionLocked] = useState(false);
  const [showCutout, setShowCutout] = useState(false);
  const [show3D, setShow3D] = useState(false);
  const [isDraggingCutout, setIsDraggingCutout] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [isGenerating3D, setIsGenerating3D] = useState(false);
  const [glbData, setGlbData] = useState<ArrayBuffer | null>(null);
  const [error, setError] = useState<string | null>(null);

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
    setCutoutSrc(null);
    setBackgroundNaturalSize(null);
    setResultStageSize(null);
    setCutoutAlphaBounds(null);
    setCutoutOffset({ x: 0, y: 0 });
    setSessionLocked(false);
    setShowCutout(false);
    setShow3D(false);
    setIsDraggingCutout(false);
    dragStateRef.current = null;
    setGlbData(null);
    setError(null);
  }, []);

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
      if (status.has_background && status.has_cutout) {
        setBackgroundSrc(`${API_BASE_URL}/images/${uid}/background`);
        setCutoutSrc(`${API_BASE_URL}/images/${uid}/cutout`);
        setCutoutAlphaBounds(toCutoutAlphaBounds(status.cutout_bounds));
        setSessionLocked(true);
      }
    } catch {
      // Non-fatal. User can rerun cutout.
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
      setUploadedFile(null);
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

    const payload: ClickRequest = {
      image_id: imageId,
      x: naturalClickPos.x,
      y: naturalClickPos.y,
    };

    setIsProcessing(true);
    setError(null);

    try {
      const result = await clickImage(payload);
      const base64Prefix = `data:image/${result.format};base64,`;
      setBackgroundSrc(`${base64Prefix}${result.background_b64}`);
      setCutoutSrc(`${base64Prefix}${result.cutout_b64}`);
      setCutoutAlphaBounds(toCutoutAlphaBounds(result.cutout_bounds));
      setSessionLocked(true);
      setShowCutout(false);
      setShow3D(false);
      setGlbData(null);
    } catch (processError) {
      const message =
        processError instanceof Error ? processError.message : "Unexpected processing error.";
      setError(message);
    } finally {
      setIsProcessing(false);
    }
  }, [imageId, naturalClickPos]);

  const handleToggle3D = useCallback(async () => {
    if (show3D) {
      setShow3D(false);
      return;
    }

    if (!imageId) {
      setError("No uploaded image to process yet.");
      return;
    }

    if (glbData) {
      setShow3D(true);
      return;
    }

    setIsGenerating3D(true);
    setError(null);

    try {
      const cached = await fetchCached3DModel(imageId);
      if (cached) {
        setGlbData(cached);
        setShow3D(true);
        return;
      }

      const buffer = await generate3DModel(imageId);
      setGlbData(buffer);
      setShow3D(true);
    } catch (genError) {
      const message =
        genError instanceof Error ? genError.message : "Unexpected 3D generation error.";
      setError(message);
      setShow3D(false);
    } finally {
      setIsGenerating3D(false);
    }
  }, [glbData, imageId, show3D]);

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
    if (showCutout) {
      return;
    }

    dragStateRef.current = null;
    setIsDraggingCutout(false);
  }, [showCutout]);

  useEffect(() => {
    const naturalSize = backgroundNaturalSize
      ?? (cutoutAlphaBounds
        ? {
            width: cutoutAlphaBounds.naturalWidth,
            height: cutoutAlphaBounds.naturalHeight,
          }
        : null);

    // Session restore can load bounds before background metrics are known.
    // Clamp again whenever either side changes so stored offsets stay valid.
    setCutoutOffset((previousOffset) => {
      const nextOffset = clampCutoutOffset(previousOffset, cutoutAlphaBounds, naturalSize);
      if (nextOffset.x === previousOffset.x && nextOffset.y === previousOffset.y) {
        return previousOffset;
      }

      return nextOffset;
    });
  }, [backgroundNaturalSize, cutoutAlphaBounds]);

  useEffect(() => {
    // Window-level listeners need fresh geometry without re-binding on every
    // mouse move, so keep latest derived values in refs.
    backgroundNaturalSizeRef.current = backgroundNaturalSize;
  }, [backgroundNaturalSize]);

  useEffect(() => {
    cutoutAlphaBoundsRef.current = cutoutAlphaBounds;
  }, [cutoutAlphaBounds]);

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

  const handleCutoutPointerDown: React.PointerEventHandler<HTMLImageElement> = useCallback((event) => {
    if (!backgroundNaturalSize || !renderedBackgroundRect) {
      return;
    }

    event.preventDefault();
    document.body.classList.add("cutout-dragging");
    dragStateRef.current = {
      pointerId: event.pointerId,
      startClientX: event.clientX,
      startClientY: event.clientY,
      startOffsetX: cutoutOffset.x,
      startOffsetY: cutoutOffset.y,
    };
    setIsDraggingCutout(true);
  }, [backgroundNaturalSize, cutoutOffset.x, cutoutOffset.y, renderedBackgroundRect]);

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

      // Mouse delta arrives in screen pixels. Convert back into natural-image
      // pixels so drag behavior stays stable under responsive resize.
      const nextOffset = clampCutoutOffset(
        {
          x: dragState.startOffsetX + (event.clientX - dragState.startClientX) / scaleX,
          y: dragState.startOffsetY + (event.clientY - dragState.startClientY) / scaleY,
        },
        cutoutAlphaBoundsRef.current,
        naturalSize,
      );

      setCutoutOffset(nextOffset);
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

  const cutoutOverlayStyle: React.CSSProperties | undefined =
    backgroundNaturalSize && renderedBackgroundRect
      ? {
          // Render cutout at exactly same contained rect as background, then
          // shift inside that rect using scaled natural-image offset.
          left: `${renderedBackgroundRect.x + cutoutOffset.x * (renderedBackgroundRect.width / backgroundNaturalSize.width)}px`,
          top: `${renderedBackgroundRect.y + cutoutOffset.y * (renderedBackgroundRect.height / backgroundNaturalSize.height)}px`,
          width: `${renderedBackgroundRect.width}px`,
          height: `${renderedBackgroundRect.height}px`,
          cursor: isDraggingCutout ? "grabbing" : "grab",
        }
      : undefined;

  const uploadBusy = Boolean(imageId && !uploadedFile);
  const clickEnabled = Boolean(imageId && !sessionLocked);
  const sessionStatus = backgroundSrc
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
          <SessionPicker onSessionSelect={handleSessionSelect} />
        </section>

        <section className="workspace-panel">
          <div className="main-frame-container">
            {!backgroundSrc ? (
              <UploadFrame
                ref={frameInputRef}
                imageSrc={uploadedImageUrl}
                clickPosition={clickPosition}
                onFileSelected={handleFileSelected}
                onImageClick={handleImageClick}
                disabled={isUploading || isProcessing || isGenerating3D}
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

                  {showCutout && cutoutSrc ? (
                    <img
                      src={cutoutSrc}
                      alt="Cutout result"
                      className="cutout-overlay"
                      style={cutoutOverlayStyle}
                      onPointerDown={handleCutoutPointerDown}
                      onDragStart={(event) => event.preventDefault()}
                    />
                  ) : null}

                  {show3D && glbData ? (
                    <Model3DFrame
                      glbData={glbData}
                      clickNormalizedPos={normalizedClickPos}
                      className="overlay-absolute model-overlay"
                      backgroundImage={null}
                    />
                  ) : null}
                </div>
              </div>
            )}
          </div>

          {backgroundSrc ? (
            <div className="control-dashboard">
              <label className="dashboard-toggle">
                <input
                  type="checkbox"
                  checked={showCutout}
                  onChange={() => setShowCutout((value) => !value)}
                />
                <span>Show cutout</span>
                {cutoutSrc ? (
                  <img src={cutoutSrc} alt="Cutout preview" className="toggle-preview" />
                ) : null}
              </label>

              <label className="dashboard-toggle">
                <input
                  type="checkbox"
                  checked={show3D}
                  onChange={handleToggle3D}
                  disabled={isGenerating3D}
                />
                <span>{isGenerating3D ? "Generating..." : "Show 3D model"}</span>
              </label>
            </div>
          ) : null}

          <div className="action-row">
            <button
              type="button"
              className={`primary-button${uploadBusy ? " ghost" : ""}`}
              onClick={uploadBusy ? triggerFileInput : handleUpload}
              disabled={isUploading || isProcessing || isGenerating3D || (!uploadBusy && !uploadedFile)}
            >
              {isUploading ? "Uploading..." : uploadBusy ? "Upload other" : "Upload"}
            </button>

            <button
              type="button"
              className="primary-button secondary"
              onClick={handleCutOut}
              disabled={!imageId || !clickPosition || sessionLocked || isProcessing}
            >
              {isProcessing ? "Running..." : "Cut Out"}
            </button>
          </div>
        </section>
      </main>
    </div>
  );
};
