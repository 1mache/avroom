import React, { useCallback, useEffect, useRef, useState } from "react";

import { sessionPreviewUrl } from "../../api/images";
import { formatEditedAgo } from "../../utils/time";
import { MoreIcon, PhotoIcon, TrashIcon } from "../icons";

export interface SessionCardProps {
  uid: string;
  name: string | null;
  lastChanged: string | null;
  /** Session has a queued/running job (segment, inpaint, or 3D generation). */
  isBusy?: boolean;
  /** Session has a failed/conflict job waiting to be seen. Takes precedence
   * over isBusy in the dot's color when both are somehow true at once. */
  isFailed?: boolean;
  /** True while this card's copy request is in flight. */
  isCopying?: boolean;
  onOpen: (uid: string) => void;
  onRequestDelete: (uid: string) => void;
  onRequestCopy: (uid: string) => void;
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
  isCopying = false,
  onOpen,
  onRequestDelete,
  onRequestCopy,
}) => {
  const [previewFailed, setPreviewFailed] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement | null>(null);
  const editedAgo = formatEditedAgo(lastChanged);
  const label = name ?? "Untitled room";

  const closeMenu = useCallback(() => {
    setMenuOpen(false);
  }, []);

  useEffect(() => {
    if (!menuOpen) {
      return;
    }
    const handlePointerDown = (event: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        closeMenu();
      }
    };
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        closeMenu();
      }
    };
    window.addEventListener("pointerdown", handlePointerDown);
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("pointerdown", handlePointerDown);
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [closeMenu, menuOpen]);

  return (
    <div className="session-card">
      {isFailed || isBusy ? (
        <span
          className={`session-card-dot${isFailed ? " is-failed" : " is-busy"}`}
          aria-label={isFailed ? "A job in this room failed" : "This room has work in progress"}
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

      <div className="session-card-more-wrap" ref={menuRef}>
        <button
          type="button"
          className={`session-card-more${menuOpen ? " is-open" : ""}`}
          onClick={(event) => {
            event.stopPropagation();
            setMenuOpen((open) => !open);
          }}
          aria-label={`Room options for ${label}`}
          aria-expanded={menuOpen}
          aria-haspopup="menu"
          data-tip="Room options"
          disabled={isCopying}
        >
          <MoreIcon size={15} />
        </button>
        {menuOpen ? (
          <div className="session-card-menu" role="menu">
            <button
              type="button"
              className="session-card-menu-item"
              role="menuitem"
              disabled={isCopying}
              onClick={(event) => {
                event.stopPropagation();
                closeMenu();
                onRequestCopy(uid);
              }}
            >
              {isCopying ? "Copying…" : "Copy room"}
            </button>
          </div>
        ) : null}
      </div>

      <button
        type="button"
        className="session-card-delete"
        onClick={() => onRequestDelete(uid)}
        aria-label={`Delete ${label}`}
        data-tip="Delete room"
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
