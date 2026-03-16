import type React from "react";
import { useRef } from "react";

export interface UploadFrameProps {
  imageSrc?: string | null;
  clickPosition?: { x: number; y: number } | null;
  onFileSelected: (file: File) => void;
  onImageClick: (displayPos: { x: number; y: number }, naturalPos: { x: number; y: number }) => void;
  disabled?: boolean;
}

export const UploadFrame: React.FC<UploadFrameProps> = ({
  imageSrc,
  clickPosition,
  onFileSelected,
  onImageClick,
  disabled,
}) => {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const imageRef = useRef<HTMLImageElement | null>(null);

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
      // No image yet: clicking should open the file picker.
      inputRef.current?.click();
      return;
    }

    // Image is present: clicking records the click position for segmentation.
    const rect = event.currentTarget.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const y = event.clientY - rect.top;
    
    const img = imageRef.current;
    if (img) {
      const imgRect = img.getBoundingClientRect();
      const clickXOnImg = event.clientX - imgRect.left;
      const clickYOnImg = event.clientY - imgRect.top;
      
      const naturalPos = {
        x: Math.round((clickXOnImg / imgRect.width) * img.naturalWidth),
        y: Math.round((clickYOnImg / imgRect.height) * img.naturalHeight),
      };
      
      onImageClick({ x, y }, naturalPos);
    } else {
      onImageClick({ x, y }, { x, y });
    }
  };

  const dotStyle: React.CSSProperties | undefined =
    imageSrc && clickPosition
      ? {
          left: `${clickPosition.x}px`,
          top: `${clickPosition.y}px`,
        }
      : undefined;

  return (
    <div className="frame upload-frame">
      <input
        ref={inputRef}
        type="file"
        accept="image/*"
        className="file-input"
        onChange={handleFileInputChange}
        aria-label="Upload image"
      />

      {imageSrc ? (
        <div className="image-container" onClick={handleContainerClick}>
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
          <span className="upload-icon">↑</span>
          <span>Upload image</span>
        </button>
      )}
    </div>
  );
};

