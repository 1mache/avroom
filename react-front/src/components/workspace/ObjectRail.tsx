import React, { useCallback, useEffect, useRef, useState } from "react";

import { effectiveCutoutSrc, type ObjectRotation } from "../../types/session";
import { EyeIcon, EyeOffIcon, RevertIcon } from "../icons";

// Grace period before the rail retracts, so clipping the edge of the panel on
// the way somewhere else doesn't snap it shut mid-reach.
const CLOSE_DELAY_MS = 220;

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

export interface ObjectRailProps {
  objects: ObjectEntry[];
  pending: PendingEntry[];
  selectedObjectId: number | null;
  /** Objects currently showing their pre-rotation cutout instead of the result. */
  showOriginalIds: ReadonlySet<number>;
  disabled: boolean;
  onSelectObject: (objectId: number) => void;
  batchUuids: ReadonlySet<string>;
  onToggleBatchUuid: (uuid: string, on: boolean) => void;
  onGenerate3D: () => void;
  generate3DDisabled: boolean;
  onToggleHidden: (objectId: number) => void;
  onToggleShowOriginal: (objectId: number) => void;
  onRenameObject: (objectId: number, uuid: string, name: string | null) => void;
}

/**
 * The session's objects, parked in the right edge of the screen.
 *
 * Retracted, the rail still reports itself: one notch per object, bright for
 * the selected one and dimmed for hidden ones, so the stack is countable
 * without opening anything. Hovering the edge slides the full list out.
 */
export const ObjectRail: React.FC<ObjectRailProps> = ({
  objects,
  pending,
  selectedObjectId,
  showOriginalIds,
  disabled,
  onSelectObject,
  batchUuids,
  onToggleBatchUuid,
  onGenerate3D,
  generate3DDisabled,
  onToggleHidden,
  onToggleShowOriginal,
  onRenameObject,
}) => {
  const [open, setOpen] = useState(false);
  const [editingObjectId, setEditingObjectId] = useState<number | null>(null);
  const [draftName, setDraftName] = useState("");
  const closeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const cancelClose = useCallback(() => {
    if (closeTimerRef.current) {
      clearTimeout(closeTimerRef.current);
      closeTimerRef.current = null;
    }
  }, []);

  const scheduleClose = useCallback(() => {
    cancelClose();
    closeTimerRef.current = setTimeout(() => setOpen(false), CLOSE_DELAY_MS);
  }, [cancelClose]);

  useEffect(() => cancelClose, [cancelClose]);

  // A rename in progress owns the keyboard; retracting the rail out from under
  // the input would blur it and commit a half-typed name.
  const handlePointerLeave = useCallback(() => {
    if (editingObjectId === null) {
      scheduleClose();
    }
  }, [editingObjectId, scheduleClose]);

  const handleOpen = useCallback(() => {
    cancelClose();
    setOpen(true);
  }, [cancelClose]);

  const handleSelect = useCallback(
    (objectId: number) => {
      if (!disabled) {
        onSelectObject(objectId);
      }
    },
    [disabled, onSelectObject],
  );

  // Escape blurs the input without saving; the blur handler reads this to know
  // it must not commit the draft.
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

  const handleNameKeyDown = useCallback((event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Enter") {
      event.currentTarget.blur();
    } else if (event.key === "Escape") {
      cancelledEditRef.current = true;
      event.currentTarget.blur();
    }
  }, []);

  const total = objects.length + pending.length;

  return (
    <div
      className="rail"
      data-open={open}
      onPointerEnter={handleOpen}
      onPointerLeave={handlePointerLeave}
    >
      <div className="rail-spine" aria-hidden="true">
        {objects.map((obj) => (
          <span
            key={obj.objectId}
            className={[
              "rail-notch",
              obj.objectId === selectedObjectId ? "is-selected" : "",
              obj.hidden ? "is-hidden" : "",
              obj.rotation?.status === "pending" ? "is-working" : "",
            ]
              .filter(Boolean)
              .join(" ")}
          />
        ))}
        {pending.map((job) => (
          <span key={job.jobId} className="rail-notch is-working" />
        ))}
      </div>

      <aside className="rail-panel" aria-label="Objects">
        <div className="rail-head">
          <span className="rail-title">Objects</span>
          <span className="rail-count">{String(total).padStart(2, "0")}</span>
          <button
            type="button"
            className="rail-3d"
            onClick={onGenerate3D}
            disabled={generate3DDisabled || objects.every((o) => !o.uuid)}
          >
            3D
          </button>
        </div>

        <div className="rail-list">
          {objects.map((obj) => {
            const isSelected = obj.objectId === selectedObjectId;
            const showsOriginal = showOriginalIds.has(obj.objectId);
            const canRevert = obj.rotation?.status === "ready";

            return (
              <div
                key={obj.objectId}
                className={`rail-row${isSelected ? " is-selected" : ""}${obj.hidden ? " is-hidden" : ""}${obj.uuid && batchUuids.has(obj.uuid) ? " is-batch" : ""}`}
              >
                <button
                  type="button"
                  className="rail-thumb"
                  onClick={(event) => {
                    if (event.ctrlKey || event.metaKey) {
                      if (obj.uuid) {
                        onToggleBatchUuid(obj.uuid, !(obj.uuid && batchUuids.has(obj.uuid)));
                      }
                      return;
                    }
                    handleSelect(obj.objectId);
                  }}
                  disabled={disabled || obj.hidden}
                  aria-label={`Select ${obj.name ?? `object ${obj.objectId}`}`}
                >
                  <img
                    src={effectiveCutoutSrc(obj, showsOriginal)}
                    alt=""
                    className="rail-thumb-img"
                    draggable={false}
                  />
                  {obj.rotation?.status === "pending" ? (
                    <span className="rail-thumb-badge">
                      <span className="tool-spinner" />
                    </span>
                  ) : null}
                </button>

                <div className="rail-row-body">
                  {editingObjectId === obj.objectId ? (
                    <input
                      type="text"
                      className="rail-name-input"
                      autoFocus
                      value={draftName}
                      onChange={(event) => setDraftName(event.target.value)}
                      onBlur={() => commitEditing(obj)}
                      onKeyDown={handleNameKeyDown}
                      aria-label={`Rename object ${obj.objectId}`}
                    />
                  ) : (
                    <span
                      className={`rail-name${obj.uuid ? " is-editable" : ""}`}
                      onDoubleClick={(event) => startEditing(event, obj)}
                      title={obj.uuid ? "Double-click to rename" : undefined}
                    >
                      {obj.name ?? `Object ${obj.objectId}`}
                    </span>
                  )}

                  <div className="rail-row-actions">
                    <button
                      type="button"
                      className="rail-action"
                      data-tip={obj.hidden ? "Show" : "Hide"}
                      aria-label={obj.hidden ? "Show object" : "Hide object"}
                      onClick={() => !disabled && onToggleHidden(obj.objectId)}
                      disabled={disabled}
                    >
                      {obj.hidden ? <EyeOffIcon size={15} /> : <EyeIcon size={15} />}
                    </button>

                    {canRevert ? (
                      <button
                        type="button"
                        className={`rail-action${showsOriginal ? " is-on" : ""}`}
                        data-tip={showsOriginal ? "Show rotated" : "Show original"}
                        aria-label={showsOriginal ? "Show rotated object" : "Show original object"}
                        aria-pressed={showsOriginal}
                        onClick={() => !disabled && onToggleShowOriginal(obj.objectId)}
                        disabled={disabled}
                      >
                        <RevertIcon size={15} />
                      </button>
                    ) : null}
                  </div>
                </div>
              </div>
            );
          })}

          {/* In-flight removals stand in for objects that don't exist yet. */}
          {pending.map((job) => (
            <div key={job.jobId} className="rail-row is-pending">
              <div className="rail-thumb rail-thumb-empty" aria-busy="true">
                <span className="tool-spinner" />
              </div>
              <div className="rail-row-body">
                <span className="rail-name">Removing</span>
              </div>
            </div>
          ))}

          {total === 0 ? (
            <p className="rail-empty">Cut an object out of the photo and it lands here.</p>
          ) : null}
        </div>
      </aside>
    </div>
  );
};
