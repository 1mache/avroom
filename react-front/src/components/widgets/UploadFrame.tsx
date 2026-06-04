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
    const elementRect = img.getBoundingClientRect();

    // The <img> uses `object-fit: contain`, so the painted image is letterboxed
    // and centered inside the element box. getBoundingClientRect() returns the
    // element box, not the painted image — mapping clicks against it would treat
    // the letterbox bars as image content and skew coordinates toward center.
    // Reconstruct the painted-image rect from the natural aspect ratio.
    const naturalRatio = img.naturalWidth / img.naturalHeight;
    const elementRatio = elementRect.width / elementRect.height;
    let contentWidth = elementRect.width;
    let contentHeight = elementRect.height;
    if (elementRatio > naturalRatio) {
      // Element wider than image → bars on left/right.
      contentWidth = elementRect.height * naturalRatio;
    } else {
      // Element taller than image → bars on top/bottom.
      contentHeight = elementRect.width / naturalRatio;
    }
    const offsetX = (elementRect.width - contentWidth) / 2;
    const offsetY = (elementRect.height - contentHeight) / 2;

    const clickXOnImg = event.clientX - elementRect.left - offsetX;
    const clickYOnImg = event.clientY - elementRect.top - offsetY;

    if (
      clickXOnImg < 0 ||
      clickYOnImg < 0 ||
      clickXOnImg > contentWidth ||
      clickYOnImg > contentHeight
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
      x: Math.round((clickXOnImg / contentWidth) * img.naturalWidth),
      y: Math.round((clickYOnImg / contentHeight) * img.naturalHeight),
    };
    const normalizedPos = {
      x: clickXOnImg / contentWidth,
      y: clickYOnImg / contentHeight,
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
