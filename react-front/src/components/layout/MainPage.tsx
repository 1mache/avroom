import React from "react";
import { useCallback, useEffect, useState } from "react";

import { clickImage, generate3DModel, uploadImage } from "../../api/images";
import type { ClickRequest } from "../../types/api";
import { Model3DFrame } from "../widgets/Model3DFrame";
import { ResultFrame } from "../widgets/ResultFrame";
import { UploadFrame } from "../widgets/UploadFrame";

interface ClickPosition {
  x: number;
  y: number;
}

export const MainPage: React.FC = () => {
  const [uploadedFile, setUploadedFile] = useState<File | null>(null);
  const [uploadedImageUrl, setUploadedImageUrl] = useState<string | null>(null);
  const [imageId, setImageId] = useState<string | null>(null);
  const [clickPosition, setClickPosition] = useState<ClickPosition | null>(null);
  const [naturalClickPos, setNaturalClickPos] = useState<ClickPosition | null>(null);
  const [normalizedClickPos, setNormalizedClickPos] = useState<ClickPosition | null>(null);
  const [backgroundSrc, setBackgroundSrc] = useState<string | null>(null);
  const [cutoutSrc, setCutoutSrc] = useState<string | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [glbData, setGlbData] = useState<ArrayBuffer | null>(null);
  const [isGenerating3D, setIsGenerating3D] = useState(false);

  useEffect(() => {
    return () => {
      if (uploadedImageUrl) {
        URL.revokeObjectURL(uploadedImageUrl);
      }
    };
  }, [uploadedImageUrl]);

  const handleFileSelected = useCallback((file: File) => {
    setUploadedFile(file);
    setImageId(null);
    setClickPosition(null);
    setNaturalClickPos(null);
    setNormalizedClickPos(null);
    setBackgroundSrc(null);
    setCutoutSrc(null);
    setError(null);

    const objectUrl = URL.createObjectURL(file);
    setUploadedImageUrl((previousUrl) => {
      if (previousUrl) {
        URL.revokeObjectURL(previousUrl);
      }

      return objectUrl;
    });
  }, []);

  const handleImageClick = useCallback((displayPos: ClickPosition, naturalPos: ClickPosition, normalizedPos: ClickPosition) => {
    setClickPosition(displayPos);
    setNaturalClickPos(naturalPos);
    setNormalizedClickPos(normalizedPos);
  }, []);

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
    } catch (uploadError) {
      const message =
        uploadError instanceof Error ? uploadError.message : "Unexpected upload error.";
      setError(message);
    } finally {
      setIsUploading(false);
    }
  }, [uploadedFile]);

  const handleRun = useCallback(async () => {
    if (!imageId) {
      setError("No uploaded image to process yet.");
      return;
    }

    if (!naturalClickPos) {
      setError("Please click on the image to select a point of interest.");
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
    } catch (processError) {
      const message =
        processError instanceof Error ? processError.message : "Unexpected processing error.";
      setError(message);
    } finally {
      setIsProcessing(false);
    }
  }, [naturalClickPos, imageId]);

  const handleGenerate3D = useCallback(async () => {
    setIsGenerating3D(true);
    setError(null);
    try {
      const buffer = await generate3DModel();
      setGlbData(buffer);
    } catch (genError) {
      const message = genError instanceof Error ? genError.message : "Unexpected 3D generation error.";
      setError(message);
    } finally {
      setIsGenerating3D(false);
    }
  }, []);

  const isBusy = isUploading || isProcessing;

  return (
    <div className="page">
      <header className="page-header">
        <h1>Image Click Segmentation MVP</h1>
        <p className="page-subtitle">
          Upload an image, click on it, then run to see background and cutout results.
        </p>
      </header>

      <main className="page-main">
        <section className="top-frame-section">
          <UploadFrame
            imageSrc={uploadedImageUrl}
            clickPosition={clickPosition}
            onFileSelected={handleFileSelected}
            onImageClick={handleImageClick}
            disabled={isBusy}
          />
        </section>

        <section className="bottom-frame-section">
          <ResultFrame title="Background" imageSrc={backgroundSrc} />

          <div className="action-column">
            <button
              type="button"
              className="primary-button"
              onClick={handleUpload}
              disabled={isUploading || !uploadedFile}
            >
              {isUploading ? "Uploading..." : "Upload"}
            </button>

            <button
              type="button"
              className="primary-button secondary"
              onClick={handleRun}
              disabled={isProcessing || !imageId || !clickPosition}
            >
              {isProcessing ? "Running..." : "Run"}
            </button>

            {error ? <p className="error-text">{error}</p> : null}
          </div>

          <ResultFrame title="Cutout" imageSrc={cutoutSrc} />
        </section>

        <section className="bottom-frame-section">
          <Model3DFrame glbData={glbData} backgroundImage={uploadedImageUrl} clickNormalizedPos={normalizedClickPos} />
        </section>

        <section className="bottom-frame-section">
          <button
            type="button"
            className="primary-button"
            onClick={handleGenerate3D}
            disabled={isGenerating3D}
          >
            {isGenerating3D ? "Generating..." : "Generate 3D"}
          </button>
        </section>
      </main>
    </div>
  );
};

