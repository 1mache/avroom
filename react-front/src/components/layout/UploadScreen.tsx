import React, { useCallback, useEffect, useRef, useState } from "react";

import { ApiError, uploadImage } from "../../api/images";
import { useAuth } from "../../context/AuthContext";
import { BackIcon, PhotoIcon } from "../icons";

// Mirrors the backend's own gate (fastApi-app/settings.py: UPLOAD_ALLOWED_MIME_TYPES,
// UPLOAD_MAX_BYTES). Checking here too turns the two most obvious rejections
// into instant feedback instead of a round trip.
const ACCEPTED_TYPES = ["image/jpeg", "image/png", "image/webp"];
const MAX_BYTES = 25 * 1024 * 1024;

export interface UploadScreenProps {
  onCancel: () => void;
  onUploaded: (uid: string) => void;
}

type Phase = "choosing" | "checking" | "rejected";

const formatSize = (bytes: number): string =>
  bytes >= 1024 * 1024 ? `${(bytes / (1024 * 1024)).toFixed(1)} MB` : `${Math.round(bytes / 1024)} KB`;

/**
 * Starts a session from a room photo. The backend validates format, size,
 * sharpness, exposure and content before it stores anything, so a rejection
 * here is a normal outcome and gets explained in place rather than thrown into
 * an error dialog.
 */
export const UploadScreen: React.FC<UploadScreenProps> = ({ onCancel, onUploaded }) => {
  const { user } = useAuth();
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [phase, setPhase] = useState<Phase>("choosing");
  const [rejection, setRejection] = useState<string | null>(null);
  const [isDragOver, setIsDragOver] = useState(false);
  const [skipValidation, setSkipValidation] = useState(false);

  useEffect(() => {
    return () => {
      if (previewUrl) {
        URL.revokeObjectURL(previewUrl);
      }
    };
  }, [previewUrl]);

  const acceptFile = useCallback((next: File) => {
    setPhase("choosing");

    if (!ACCEPTED_TYPES.includes(next.type)) {
      setFile(null);
      setRejection("That file isn't a JPG, PNG or WebP image. Choose a photo instead.");
      setPhase("rejected");
      return;
    }

    if (next.size > MAX_BYTES) {
      setFile(null);
      setRejection(`That photo is ${formatSize(next.size)}. The limit is 25 MB.`);
      setPhase("rejected");
      return;
    }

    setRejection(null);
    setFile(next);
    setPreviewUrl((previous) => {
      if (previous) {
        URL.revokeObjectURL(previous);
      }
      return URL.createObjectURL(next);
    });
  }, []);

  const handleInputChange: React.ChangeEventHandler<HTMLInputElement> = useCallback(
    (event) => {
      const picked = event.target.files?.[0];
      if (picked) {
        acceptFile(picked);
      }
      event.target.value = "";
    },
    [acceptFile],
  );

  const handleDrop: React.DragEventHandler<HTMLDivElement> = useCallback(
    (event) => {
      event.preventDefault();
      setIsDragOver(false);
      const dropped = event.dataTransfer.files?.[0];
      if (dropped) {
        acceptFile(dropped);
      }
    },
    [acceptFile],
  );

  const handleStart = useCallback(async () => {
    if (!file) {
      return;
    }

    setPhase("checking");
    setRejection(null);

    try {
      const response = await uploadImage(file, skipValidation);
      onUploaded(response.image_id);
    } catch (uploadError) {
      // 422 is the validation gate turning the photo down — a normal answer,
      // with a reason worth reading. Anything else is a genuine failure.
      if (uploadError instanceof ApiError && uploadError.status === 422) {
        setRejection(uploadError.detail || "This photo didn't pass the quality checks.");
      } else {
        setRejection(
          uploadError instanceof Error ? uploadError.message : "The upload didn't go through.",
        );
      }
      setPhase("rejected");
    }
  }, [file, onUploaded, skipValidation]);

  const busy = phase === "checking";

  return (
    <div className="dashboard">
      <header className="dash-header">
        <button
          type="button"
          className="tool-btn"
          onClick={onCancel}
          aria-label="Back to dashboard"
          data-tip="Back to dashboard"
          disabled={busy}
        >
          <BackIcon />
        </button>
        <span className="dash-wordmark">New session</span>
      </header>

      <main className="dash-main is-narrow">
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPTED_TYPES.join(",")}
          className="file-input"
          onChange={handleInputChange}
          aria-label="Choose a room photo"
        />

        <div
          className={`dropzone${isDragOver ? " is-over" : ""}${file ? " has-file" : ""}`}
          onDragOver={(event) => {
            event.preventDefault();
            setIsDragOver(true);
          }}
          onDragLeave={() => setIsDragOver(false)}
          onDrop={handleDrop}
        >
          {previewUrl && file ? (
            <>
              <img src={previewUrl} alt="" className="dropzone-preview" />
              <div className="dropzone-file">
                <span className="dropzone-filename">{file.name}</span>
                <span className="dropzone-filesize">{formatSize(file.size)}</span>
              </div>
            </>
          ) : (
            <button
              type="button"
              className="dropzone-invite"
              onClick={() => inputRef.current?.click()}
              disabled={busy}
            >
              <PhotoIcon size={28} />
              <span className="dropzone-invite-line">Drop a room photo here</span>
              <span className="dropzone-invite-hint">or choose a file</span>
            </button>
          )}
        </div>

        {phase === "checking" ? (
          <p className="upload-status">
            <span className="tool-spinner" />
            <span>
              Checking the photo — format, sharpness and what&rsquo;s in the frame.
            </span>
          </p>
        ) : null}

        {rejection ? <p className="upload-rejection">{rejection}</p> : null}

        {user?.is_admin && (
          <button
            type="button"
            role="switch"
            aria-checked={skipValidation}
            className={`tool-switch${skipValidation ? " is-on" : ""}`}
            data-tip="Skip upload validation (admin only)"
            aria-label="Skip upload validation"
            onClick={() => setSkipValidation((prev) => !prev)}
            disabled={busy}
          >
            <span>Skip validation</span>
            <span className="tool-switch-track">
              <span className="tool-switch-nub" />
            </span>
          </button>
        )}

        <div className="upload-actions">
          <button
            type="button"
            className="btn"
            onClick={() => inputRef.current?.click()}
            disabled={busy}
          >
            {file ? "Choose another" : "Choose a file"}
          </button>
          <button
            type="button"
            className="btn is-primary"
            onClick={() => void handleStart()}
            disabled={!file || busy}
          >
            {busy ? "Checking…" : "Start session"}
          </button>
        </div>

        <p className="upload-rules">
          JPG, PNG or WebP · at least 640×480 · up to 25 MB · a clear, well-lit room
        </p>
      </main>
    </div>
  );
};
