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
import type { ClickRequest } from "../../types/api";
import { Model3DFrame } from "../widgets/Model3DFrame";
import { SessionPicker } from "../widgets/SessionPicker";
import { UploadFrame } from "../widgets/UploadFrame";

interface ClickPosition {
  x: number;
  y: number;
}

export const MainPage: React.FC = () => {
  const frameInputRef = useRef<HTMLInputElement>(null);
  const uploadOtherInputRef = useRef<HTMLInputElement>(null);

  const [uploadedFile, setUploadedFile] = useState<File | null>(null);
  const [uploadedImageUrl, setUploadedImageUrl] = useState<string | null>(null);
  const [imageId, setImageId] = useState<string | null>(null);
  const [clickPosition, setClickPosition] = useState<ClickPosition | null>(null);
  const [naturalClickPos, setNaturalClickPos] = useState<ClickPosition | null>(null);
  const [normalizedClickPos, setNormalizedClickPos] = useState<ClickPosition | null>(null);
  const [backgroundSrc, setBackgroundSrc] = useState<string | null>(null);
  const [cutoutSrc, setCutoutSrc] = useState<string | null>(null);
  const [sessionLocked, setSessionLocked] = useState(false);
  const [showCutout, setShowCutout] = useState(false);
  const [show3D, setShow3D] = useState(false);
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
    setSessionLocked(false);
    setShowCutout(false);
    setShow3D(false);
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
                <img src={backgroundSrc} alt="Background result" className="frame-image" />

                {showCutout && cutoutSrc ? (
                  <img
                    src={cutoutSrc}
                    alt="Cutout result"
                    className="frame-image overlay-absolute"
                  />
                ) : null}

                {show3D && glbData ? (
                  <Model3DFrame
                    glbData={glbData}
                    clickNormalizedPos={normalizedClickPos}
                    className="overlay-absolute"
                    backgroundImage={null}
                  />
                ) : null}
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
