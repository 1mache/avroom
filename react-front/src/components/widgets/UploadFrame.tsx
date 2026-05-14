import React, { forwardRef, useRef } from "react";

export interface UploadFrameProps {
  imageSrc?: string | null;
  clickPosition?: { x: number; y: number } | null;
  onFileSelected: (file: File) => void;
  // Emits same click in three spaces so caller can use each one for a different
  // job: dot overlay, backend segmentation, and 3D camera bias.
  onImageClick: (
    displayPos: { x: number; y: number },
    naturalPos: { x: number; y: number },
    normalizedPos: { x: number; y: number },
  ) => void;
  disabled?: boolean;
  clickEnabled?: boolean;
}

export const UploadFrame = forwardRef<HTMLInputElement, UploadFrameProps>(({
  imageSrc,
  clickPosition,
  onFileSelected,
  onImageClick,
  disabled,
  clickEnabled = true,
}, forwardedRef) => {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const imageRef = useRef<HTMLImageElement | null>(null);

  // Component keeps local ref for hidden input while still exposing it to parent
  // so MainPage can trigger "Upload other" from outside this widget.
  const setInputRefs = (node: HTMLInputElement | null) => {
    inputRef.current = node;

    if (typeof forwardedRef === "function") {
      forwardedRef(node);
      return;
    }

    if (forwardedRef) {
      forwardedRef.current = node;
    }
  };

  const handleFileInputChange: React.ChangeEventHandler<HTMLInputElement> = (event) => {
    const file = event.target.files?.[0];
    if (file) {
      onFileSelected(file);
      event.target.value = "";
    }
  };

  const handleContainerClick: React.MouseEventHandler<HTMLDivElement | HTMLButtonElement> = (
    event,
  ) => {
    if (disabled) {
      return;
    }

    if (!imageSrc) {
      inputRef.current?.click();
      return;
    }

    if (!clickEnabled) {
      return;
    }

    const img = imageRef.current;
    if (!img) {
      return;
    }

    const rect = event.currentTarget.getBoundingClientRect();
    const imgRect = img.getBoundingClientRect();
    const clickXOnImg = event.clientX - imgRect.left;
    const clickYOnImg = event.clientY - imgRect.top;

    if (
      clickXOnImg < 0 ||
      clickYOnImg < 0 ||
      clickXOnImg > imgRect.width ||
      clickYOnImg > imgRect.height
    ) {
      return;
    }

    const displayPos = {
      x: event.clientX - rect.left,
      y: event.clientY - rect.top,
    };
    // Natural coordinates are what backend expects. Display coordinates alone
    // would drift whenever preview size differs from original image size.
    const naturalPos = {
      x: Math.round((clickXOnImg / imgRect.width) * img.naturalWidth),
      y: Math.round((clickYOnImg / imgRect.height) * img.naturalHeight),
    };
    const normalizedPos = {
      x: clickXOnImg / imgRect.width,
      y: clickYOnImg / imgRect.height,
    };

    onImageClick(displayPos, naturalPos, normalizedPos);
  };

  const dotStyle: React.CSSProperties | undefined =
    imageSrc && clickPosition && clickEnabled
      ? {
          left: `${clickPosition.x}px`,
          top: `${clickPosition.y}px`,
        }
      : undefined;

  return (
    <div className="frame upload-frame">
      <input
        ref={setInputRefs}
        type="file"
        accept="image/*"
        className="file-input"
        onChange={handleFileInputChange}
        aria-label="Upload image"
      />

      {imageSrc ? (
        <div
          className={`image-container${clickEnabled ? " is-interactive" : " is-locked"}`}
          onClick={handleContainerClick}
        >
          <img ref={imageRef} src={imageSrc} alt="Uploaded" className="frame-image" />
          {dotStyle ? <div className="click-dot" style={dotStyle} /> : null}
        </div>
      ) : (
        <button
          type="button"
          className="upload-placeholder"
          onClick={handleContainerClick}
          disabled={disabled}
        >
          <span className="upload-icon">+</span>
          <span>Upload image</span>
        </button>
      )}
    </div>
  );
});

UploadFrame.displayName = "UploadFrame";
