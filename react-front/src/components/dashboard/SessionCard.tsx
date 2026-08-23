import React, { useState } from "react";

import { sessionPreviewUrl } from "../../api/images";
import { formatEditedAgo } from "../../utils/time";
import { PhotoIcon, TrashIcon } from "../icons";

export interface SessionCardProps {
  uid: string;
  name: string | null;
  lastChanged: string | null;
  /** Session has a queued/running job (segment, inpaint, or 3D generation). */
  isBusy?: boolean;
  /** Session has a failed/conflict job waiting to be seen. Takes precedence
   * over isBusy in the dot's color when both are somehow true at once. */
  isFailed?: boolean;
  onOpen: (uid: string) => void;
  onRequestDelete: (uid: string) => void;
}

/**
 * One session, shown as the room the user left behind. The preview endpoint
 * doesn't exist yet, so a failed load quietly becomes the placeholder tile
 * rather than a broken image.
 */
export const SessionCard: React.FC<SessionCardProps> = ({
  uid,
  name,
  lastChanged,
  isBusy = false,
  isFailed = false,
  onOpen,
  onRequestDelete,
}) => {
  const [previewFailed, setPreviewFailed] = useState(false);
  const editedAgo = formatEditedAgo(lastChanged);
  const label = name ?? "Untitled session";

  return (
    <div className="session-card">
      {isFailed || isBusy ? (
        <span
          className={`session-card-dot${isFailed ? " is-failed" : " is-busy"}`}
          aria-label={isFailed ? "A job in this session failed" : "This session has work in progress"}
          data-tip={isFailed ? "A job failed" : "Working…"}
        />
      ) : null}

      <button
        type="button"
        className="session-card-frame"
        onClick={() => onOpen(uid)}
        aria-label={`Open ${label}`}
      >
        {previewFailed ? (
          <span className="session-card-placeholder">
            <PhotoIcon size={22} />
            <span className="session-card-placeholder-text">No preview yet</span>
          </span>
        ) : (
          <img
            src={sessionPreviewUrl(uid, lastChanged)}
            alt=""
            className="session-card-preview"
            onError={() => setPreviewFailed(true)}
            draggable={false}
          />
        )}
      </button>

      <button
        type="button"
        className="session-card-delete"
        onClick={() => onRequestDelete(uid)}
        aria-label={`Delete ${label}`}
        data-tip="Delete session"
      >
        <TrashIcon size={15} />
      </button>

      <div className="session-card-caption">
        <span className="session-card-name" title={label}>
          {label}
        </span>
        <span className="session-card-edited">{editedAgo ?? "never edited"}</span>
      </div>
    </div>
  );
};
