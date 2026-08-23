import React, { useRef, useState } from "react";

import { PhotoIcon } from "../../icons";
import { getContainedImageRect } from "../../../utils/stageGeometry";

export interface DebugSourcePanelProps {
  file: File | null;
  previewUrl: string | null;
  clickPos: { x: number; y: number } | null;
  busy: boolean;
  /** Replaces the current file — parent resets every panel's state. */
  onFileAccepted: (file: File) => void;
  onPreviewClick: React.MouseEventHandler<HTMLImageElement>;
  onRunAll: () => void;
}

/**
 * The dropzone/file-picker plus the click-to-seed photo and "Run all"
 * button. isDragOver and the file/model input refs are pure UI state no
 * other panel observes, so they live here instead of in DebugScreen.
 */
export const DebugSourcePanel: React.FC<DebugSourcePanelProps> = ({
  file,
  previewUrl,
  clickPos,
  busy,
  onFileAccepted,
  onPreviewClick,
  onRunAll,
}) => {
  const inputRef = useRef<HTMLInputElement>(null);
  const previewImgRef = useRef<HTMLImageElement>(null);
  const [isDragOver, setIsDragOver] = useState(false);

  const handleInputChange: React.ChangeEventHandler<HTMLInputElement> = (event) => {
    const picked = event.target.files?.[0];
    if (picked) {
      onFileAccepted(picked);
    }
    event.target.value = "";
  };

  const handleDrop: React.DragEventHandler<HTMLDivElement> = (event) => {
    event.preventDefault();
    setIsDragOver(false);
    const dropped = event.dataTransfer.files?.[0];
    if (dropped) {
      onFileAccepted(dropped);
    }
  };

  return (
    <div className="debug-source">
      <input
        ref={inputRef}
        type="file"
        accept="image/jpeg,image/png,image/webp"
        className="file-input"
        onChange={handleInputChange}
        aria-label="Choose an image"
      />
      <div
        className={`dropzone debug-dropzone${isDragOver ? " is-over" : ""}${file ? " has-file" : ""}`}
        onDragOver={(event) => {
          event.preventDefault();
          setIsDragOver(true);
        }}
        onDragLeave={() => setIsDragOver(false)}
        onDrop={handleDrop}
      >
        {previewUrl && file ? (
          <>
            <div className="debug-click-frame">
              <img
                ref={previewImgRef}
                src={previewUrl}
                alt=""
                className="dropzone-preview"
                onClick={onPreviewClick}
              />
              {clickPos && previewImgRef.current ? (
                <span
                  className="debug-click-marker"
                  style={(() => {
                    const img = previewImgRef.current;
                    const natural = { width: img.naturalWidth, height: img.naturalHeight };
                    const rendered = getContainedImageRect(
                      { width: img.clientWidth, height: img.clientHeight },
                      natural,
                    );
                    if (!rendered || natural.width <= 0 || natural.height <= 0) {
                      return undefined;
                    }
                    return {
                      left: rendered.x + (clickPos.x / natural.width) * rendered.width,
                      top: rendered.y + (clickPos.y / natural.height) * rendered.height,
                    };
                  })()}
                />
              ) : null}
            </div>
            <div className="dropzone-file">
              <span className="dropzone-filename">{file.name}</span>
            </div>
            <p className="debug-click-readout">
              {clickPos
                ? `Click ${clickPos.x}, ${clickPos.y} — used by auto mask pick and inpaint verify`
                : "Click the photo to set a seed point"}
            </p>
          </>
        ) : (
          <button type="button" className="dropzone-invite" onClick={() => inputRef.current?.click()}>
            <PhotoIcon size={28} />
            <span className="dropzone-invite-line">Drop any image here</span>
            <span className="dropzone-invite-hint">
              or choose a file — no client-side checks, the point is watching the server decide
            </span>
          </button>
        )}
      </div>

      <div className="debug-source-actions">
        <button type="button" className="btn" onClick={() => inputRef.current?.click()}>
          {file ? "Choose another" : "Choose a file"}
        </button>
        <button type="button" className="btn is-primary" onClick={onRunAll} disabled={!file || busy}>
          {busy ? <span className="tool-spinner" /> : "Run all"}
        </button>
      </div>
    </div>
  );
};
