import React, { useRef, useState } from "react";

import { PhotoIcon } from "../../icons";
import { getContainedImageRect } from "../../../utils/stageGeometry";

export interface DebugSeed {
  x: number;
  y: number;
}

export interface DebugSourcePanelProps {
  file: File | null;
  previewUrl: string | null;
  seeds: DebugSeed[];
  busy: boolean;
  /** Replaces the current file — parent resets every panel's state. */
  onFileAccepted: (file: File) => void;
  onPreviewClick: React.MouseEventHandler<HTMLImageElement>;
  onClearSeeds: () => void;
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
  seeds,
  busy,
  onFileAccepted,
  onPreviewClick,
  onClearSeeds,
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

  const seedReadout =
    seeds.length === 0
      ? "Click the photo to add seed points (up to 8)"
      : seeds.length === 1
        ? `1 seed at ${seeds[0].x}, ${seeds[0].y} — Esc or Clear resets`
        : `${seeds.length} seeds · Esc or Clear resets`;

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
              {previewImgRef.current
                ? seeds.map((seed, index) => {
                    const img = previewImgRef.current;
                    if (!img) {
                      return null;
                    }
                    const natural = { width: img.naturalWidth, height: img.naturalHeight };
                    const rendered = getContainedImageRect(
                      { width: img.clientWidth, height: img.clientHeight },
                      natural,
                    );
                    if (!rendered || natural.width <= 0 || natural.height <= 0) {
                      return null;
                    }
                    return (
                      <span
                        key={`${seed.x}-${seed.y}-${index}`}
                        className="debug-click-marker"
                        style={{
                          left: rendered.x + (seed.x / natural.width) * rendered.width,
                          top: rendered.y + (seed.y / natural.height) * rendered.height,
                        }}
                      >
                        {seeds.length > 1 ? (
                          <span className="debug-click-marker-label">{index + 1}</span>
                        ) : null}
                      </span>
                    );
                  })
                : null}
            </div>
            <div className="dropzone-file">
              <span className="dropzone-filename">{file.name}</span>
            </div>
            <p className="debug-click-readout">{seedReadout}</p>
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
        <button
          type="button"
          className="btn"
          onClick={onClearSeeds}
          disabled={seeds.length === 0}
        >
          Clear seeds
        </button>
        <button type="button" className="btn is-primary" onClick={onRunAll} disabled={!file || busy}>
          {busy ? <span className="tool-spinner" /> : "Run all"}
        </button>
      </div>
    </div>
  );
};
