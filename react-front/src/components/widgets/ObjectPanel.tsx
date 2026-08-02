import React, { useCallback, useRef, useState } from "react";

import { effectiveCutoutSrc, type ObjectRotation } from "../../types/session";

const EyeOpenIcon: React.FC = () => (
  <svg viewBox="0 0 24 24" width="14" height="14" fill="none" xmlns="http://www.w3.org/2000/svg">
    <path
      d="M2 12C2 12 5.5 5.5 12 5.5C18.5 5.5 22 12 22 12C22 12 18.5 18.5 12 18.5C5.5 18.5 2 12 2 12Z"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
    <circle cx="12" cy="12" r="2.75" stroke="currentColor" strokeWidth="1.5" />
  </svg>
);

const EyeOffIcon: React.FC = () => (
  <svg viewBox="0 0 24 24" width="14" height="14" fill="none" xmlns="http://www.w3.org/2000/svg">
    <path
      d="M2 12C2 12 5.5 5.5 12 5.5C18.5 5.5 22 12 22 12C22 12 18.5 18.5 12 18.5C5.5 18.5 2 12 2 12Z"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
    <circle cx="12" cy="12" r="2.75" stroke="currentColor" strokeWidth="1.5" />
    <line x1="4" y1="4" x2="20" y2="20" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
  </svg>
);

interface ObjectEntry {
  objectId: number;
  uuid: string | null;
  name: string | null;
  cutoutSrc: string;
  rotation: ObjectRotation | null;
  hidden: boolean;
}

interface PendingEntry {
  jobId: string;
}

interface ObjectPanelProps {
  objects: ObjectEntry[];
  pending: PendingEntry[];
  selectedObjectId: number | null;
  isAddingObject: boolean;
  // Narrowed to genuinely blocking states — a concurrent inpaint elsewhere no
  // longer freezes this panel; only 3D generation for the selected object does.
  disabled: boolean;
  // "Show original" is scoped to the selected object only (see MainPage's
  // dashboard toggle); every other object's thumbnail always shows its own
  // rotated result, if it has one.
  showOriginal: boolean;
  onSelectObject: (objectId: number) => void;
  onToggleHidden: (objectId: number) => void;
  onAddObject: () => void;
  onRenameObject: (objectId: number, uuid: string, name: string | null) => void;
  collapsed: boolean;
  onToggleCollapsed: () => void;
}

export const ObjectPanel: React.FC<ObjectPanelProps> = ({
  objects,
  pending,
  selectedObjectId,
  isAddingObject,
  disabled,
  showOriginal,
  onSelectObject,
  onToggleHidden,
  onAddObject,
  onRenameObject,
  collapsed,
  onToggleCollapsed,
}) => {
  const [editingObjectId, setEditingObjectId] = useState<number | null>(null);
  const [draftName, setDraftName] = useState("");

  const handleSelectObject = useCallback(
    (objectId: number) => {
      if (!disabled) {
        onSelectObject(objectId);
      }
    },
    [disabled, onSelectObject],
  );

  const handleToggleHidden = useCallback(
    (event: React.MouseEvent, objectId: number) => {
      // Don't let the eye toggle also trigger selection of the thumbnail
      // underneath it.
      event.stopPropagation();
      if (!disabled) {
        onToggleHidden(objectId);
      }
    },
    [disabled, onToggleHidden],
  );

  const handleAddObject = useCallback(() => {
    if (!disabled) {
      onAddObject();
    }
  }, [disabled, onAddObject]);

  // Escape blurs the input (to drop focus) without saving; the blur handler
  // checks this ref so it knows not to commit the draft in that case.
  const cancelledEditRef = useRef(false);

  const startEditing = useCallback(
    (event: React.MouseEvent, obj: ObjectEntry) => {
      event.stopPropagation();
      if (disabled || !obj.uuid) {
        return;
      }
      cancelledEditRef.current = false;
      setEditingObjectId(obj.objectId);
      setDraftName(obj.name ?? "");
    },
    [disabled],
  );

  const commitEditing = useCallback(
    (obj: ObjectEntry) => {
      setEditingObjectId(null);
      if (cancelledEditRef.current || !obj.uuid) {
        return;
      }
      const trimmed = draftName.trim();
      const nextName = trimmed.length > 0 ? trimmed : null;
      if (nextName !== (obj.name ?? null)) {
        onRenameObject(obj.objectId, obj.uuid, nextName);
      }
    },
    [draftName, onRenameObject],
  );

  const handleLabelKeyDown = useCallback((event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Enter") {
      event.currentTarget.blur();
    } else if (event.key === "Escape") {
      cancelledEditRef.current = true;
      event.currentTarget.blur();
    }
  }, []);

  return (
    <div className="object-panel-container">
      {/* Side column — always visible regardless of collapsed state */}
      <div className="object-panel-side">
        <button
          type="button"
          className="object-panel-toggle"
          onClick={onToggleCollapsed}
          aria-label={collapsed ? "Expand objects panel" : "Collapse objects panel"}
          title={collapsed ? "Expand" : "Collapse"}
        >
          {collapsed ? "▶" : "◀"}
        </button>
      </div>

      {/* Expandable body with scrollable thumbnail list */}
      <div className={`object-panel-body${collapsed ? " is-collapsed" : ""}`}>
        <span className="object-panel-label">Objects</span>

        <button
          type="button"
          className={`object-panel-add-big${isAddingObject ? " is-active" : ""}`}
          onClick={handleAddObject}
          disabled={disabled}
        >
          + Add object
        </button>

        <div className="object-panel-list">
          {objects.map((obj) => (
            <div key={obj.objectId} className="object-thumbnail-row">
              <button
                type="button"
                className={`object-thumbnail-btn${obj.objectId === selectedObjectId ? " is-active" : ""}`}
                onClick={() => handleSelectObject(obj.objectId)}
                disabled={disabled || obj.hidden}
                aria-label={`Select object ${obj.name ?? obj.objectId}`}
                title={obj.hidden ? `${obj.name ?? `Object ${obj.objectId}`} (hidden)` : obj.name ?? `Object ${obj.objectId}`}
              >
                <img
                  src={effectiveCutoutSrc(
                    obj,
                    showOriginal && obj.objectId === selectedObjectId,
                  )}
                  alt={obj.name ?? `Object ${obj.objectId}`}
                  className="object-thumbnail-img"
                />
                {obj.rotation?.status === "pending" ? (
                  <span className="object-thumbnail-rotating-badge" aria-label="Rotating">
                    <span className="object-thumbnail-spinner" />
                  </span>
                ) : null}
              </button>

              {editingObjectId === obj.objectId ? (
                <input
                  type="text"
                  className="object-thumbnail-name-input"
                  autoFocus
                  value={draftName}
                  onChange={(e) => setDraftName(e.target.value)}
                  onBlur={() => commitEditing(obj)}
                  onKeyDown={handleLabelKeyDown}
                  onClick={(e) => e.stopPropagation()}
                  aria-label={`Rename object ${obj.objectId}`}
                />
              ) : (
                <span
                  className={`object-thumbnail-name${obj.uuid ? " is-editable" : ""}`}
                  onDoubleClick={(e) => startEditing(e, obj)}
                  title={obj.uuid ? "Double-click to rename" : undefined}
                >
                  {obj.name ?? `Object ${obj.objectId}`}
                </span>
              )}

              <button
                type="button"
                className="object-visibility-btn"
                onClick={(event) => handleToggleHidden(event, obj.objectId)}
                disabled={disabled}
                aria-label={obj.hidden ? `Show object ${obj.objectId}` : `Hide object ${obj.objectId}`}
                title={obj.hidden ? "Show object" : "Hide object"}
              >
                {obj.hidden ? <EyeOffIcon /> : <EyeOpenIcon />}
              </button>
            </div>
          ))}

          {/* In-flight inpaint jobs render as non-interactive placeholders
              until their response lands and they become real thumbnails
              above (see useSessionJobs.pendingJobs). */}
          {pending.map((job) => (
            <div key={job.jobId} className="object-thumbnail-row is-pending">
              <div className="object-thumbnail-btn object-thumbnail-pending" aria-busy="true">
                <span className="object-thumbnail-spinner" />
              </div>
              <span className="object-thumbnail-name">Removing...</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
