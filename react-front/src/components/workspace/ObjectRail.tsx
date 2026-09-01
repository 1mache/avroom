import React, { useCallback, useEffect, useRef, useState } from "react";

import type { JobInfo } from "../../types/api";
import { effectiveCutoutSrc, hasUndoableObjectChanges, type ObjectRotation } from "../../types/session";
import { CheckIcon, EyeIcon, EyeOffIcon, MoreIcon, PlusIcon, RevertIcon, TrashIcon } from "../icons";

const JOB_KIND_LABEL: Record<JobInfo["kind"], string> = {
  segment: "Segmenting",
  inpaint: "Removing",
  erase: "Erasing",
  generate_3d: "Building 3D",
};

const CLOSE_DELAY_MS = 220;

interface ObjectEntry {
  objectId: number;
  uuid: string | null;
  name: string | null;
  cutoutSrc: string;
  rotation: ObjectRotation | null;
  hidden: boolean;
  has3d: boolean;
  cloneRootUuid: string | null;
  offset: { x: number; y: number };
  displayScale: number;
}

export interface ObjectRailProps {
  objects: ObjectEntry[];
  jobs: JobInfo[];
  selectedObjectId: number | null;
  showOriginalIds: ReadonlySet<number>;
  disabled: boolean;
  isDuplicating: boolean;
  isDeleting: boolean;
  onSelectObject: (objectId: number) => void;
  batchUuids: ReadonlySet<string>;
  onToggleBatchUuid: (uuid: string, on: boolean) => void;
  onGenerate3D: () => void;
  generate3DDisabled: boolean;
  onToggleHidden: (objectId: number) => void;
  onToggleShowOriginal: (objectId: number) => void;
  onRenameObject: (objectId: number, uuid: string, name: string | null) => void;
  onDuplicateObject: (objectId: number) => void;
  onDeleteObject: (objectId: number) => void;
  onClearObject3d: (objectId: number) => void;
  onResetObjectChanges: (objectId: number) => void;
  onImportObject: (file: File) => void;
  importDisabled: boolean;
  onDismissJob: (jobId: string) => void;
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
  jobs,
  selectedObjectId,
  showOriginalIds,
  disabled,
  isDuplicating,
  isDeleting,
  onSelectObject,
  batchUuids,
  onToggleBatchUuid,
  onGenerate3D,
  generate3DDisabled,
  onToggleHidden,
  onToggleShowOriginal,
  onRenameObject,
  onDuplicateObject,
  onDeleteObject,
  onClearObject3d,
  onResetObjectChanges,
  onImportObject,
  importDisabled,
  onDismissJob,
}) => {
  const pending = jobs.filter((job) => job.status === "queued" || job.status === "running");
  const failed = jobs.filter((job) => job.status === "failed");

  const [open, setOpen] = useState(false);
  const [editingObjectId, setEditingObjectId] = useState<number | null>(null);
  const [menuObjectId, setMenuObjectId] = useState<number | null>(null);
  const [hoveredObjectId, setHoveredObjectId] = useState<number | null>(null);
  const [draftName, setDraftName] = useState("");
  const closeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const menuRef = useRef<HTMLDivElement | null>(null);
  const importInputRef = useRef<HTMLInputElement | null>(null);

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

  const railPinned = editingObjectId !== null || menuObjectId !== null;

  const handlePointerLeave = useCallback(() => {
    if (!railPinned) {
      scheduleClose();
    }
  }, [railPinned, scheduleClose]);

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

  const closeMenu = useCallback(() => {
    setMenuObjectId(null);
  }, []);

  useEffect(() => {
    if (menuObjectId === null) {
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
  }, [closeMenu, menuObjectId]);

  const cancelledEditRef = useRef(false);

  const startEditing = useCallback((obj: ObjectEntry) => {
    if (disabled || !obj.uuid) {
      return;
    }
    closeMenu();
    cancelledEditRef.current = false;
    setEditingObjectId(obj.objectId);
    setDraftName(obj.name ?? "");
  }, [closeMenu, disabled]);

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

  const handleNameKeyDown = useCallback(
    (event: React.KeyboardEvent<HTMLInputElement>, obj: ObjectEntry) => {
      if (event.key === "Enter") {
        event.preventDefault();
        commitEditing(obj);
      } else if (event.key === "Escape") {
        cancelledEditRef.current = true;
        setEditingObjectId(null);
      }
    },
    [commitEditing],
  );

  const handleImportInputChange = useCallback(
    (event: React.ChangeEvent<HTMLInputElement>) => {
      const picked = event.target.files?.[0];
      event.target.value = "";
      if (picked) {
        onImportObject(picked);
      }
    },
    [onImportObject],
  );

  const total = objects.length + pending.length + failed.length;

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
          <span key={job.job_id} className="rail-notch is-working" />
        ))}
        {failed.map((job) => (
          <span key={job.job_id} className="rail-notch is-failed" />
        ))}
      </div>

      <aside className="rail-panel" aria-label="Objects">
        <div className="rail-head">
          <span className="rail-title">Objects</span>
          <span className="rail-count">{String(total).padStart(2, "0")}</span>
          <div className="rail-head-actions">
            <input
              ref={importInputRef}
              type="file"
              accept="image/png"
              className="rail-import-input"
              onChange={handleImportInputChange}
              aria-hidden="true"
              tabIndex={-1}
            />
            <button
              type="button"
              className="rail-add"
              data-tip="Add object from PNG"
              aria-label="Add object from PNG"
              disabled={importDisabled || disabled}
              onClick={() => importInputRef.current?.click()}
            >
              <PlusIcon size={12} />
            </button>
            <button
              type="button"
              className="rail-3d"
              onClick={onGenerate3D}
              disabled={generate3DDisabled || objects.every((o) => !o.uuid)}
            >
              3D
            </button>
          </div>
        </div>

        <div className="rail-list">
          {objects.map((obj) => {
            const isSelected = obj.objectId === selectedObjectId;
            const showsOriginal = showOriginalIds.has(obj.objectId);
            const canRevert = obj.rotation?.status === "ready";
            const showThumbChrome =
              hoveredObjectId === obj.objectId || menuObjectId === obj.objectId;
            const menuOpen = menuObjectId === obj.objectId;
            const showRemove3d = obj.has3d;
            const showUndoChanges =
              hasUndoableObjectChanges(obj) && obj.rotation?.status !== "pending";
            const rowBusy = isDuplicating || isDeleting;

            return (
              <div
                key={obj.objectId}
                className={[
                  "rail-row",
                  isSelected ? "is-selected" : "",
                  obj.hidden ? "is-hidden" : "",
                  obj.uuid && batchUuids.has(obj.uuid) ? "is-batch" : "",
                  menuOpen ? "is-menu-open" : "",
                ]
                  .filter(Boolean)
                  .join(" ")}
                ref={menuOpen ? menuRef : undefined}
              >
                <div
                  className="rail-thumb-wrap"
                  onPointerEnter={() => setHoveredObjectId(obj.objectId)}
                  onPointerLeave={() =>
                    setHoveredObjectId((current) => (current === obj.objectId ? null : current))
                  }
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

                  {showThumbChrome && obj.uuid ? (
                    <div className="rail-thumb-overlay" aria-hidden={false}>
                      <div className="rail-thumb-overlay-actions">
                        <button
                          type="button"
                          className="rail-thumb-action"
                          data-tip="More actions"
                          aria-label={`More actions for ${obj.name ?? `object ${obj.objectId}`}`}
                          aria-expanded={menuOpen}
                          disabled={rowBusy}
                          onClick={(event) => {
                            event.stopPropagation();
                            setMenuObjectId(menuOpen ? null : obj.objectId);
                          }}
                        >
                          <MoreIcon size={15} />
                        </button>
                        <button
                          type="button"
                          className="rail-thumb-action is-danger"
                          data-tip="Delete object"
                          aria-label={`Delete ${obj.name ?? `object ${obj.objectId}`}`}
                          disabled={rowBusy}
                          onClick={(event) => {
                            event.stopPropagation();
                            closeMenu();
                            onDeleteObject(obj.objectId);
                          }}
                        >
                          <TrashIcon size={15} />
                        </button>
                      </div>
                    </div>
                  ) : null}
                </div>

                <div className="rail-row-body">
                  {editingObjectId === obj.objectId ? (
                    <div className="rail-rename-row">
                      <input
                        type="text"
                        className="rail-name-input"
                        autoFocus
                        value={draftName}
                        onChange={(event) => setDraftName(event.target.value)}
                        onKeyDown={(event) => handleNameKeyDown(event, obj)}
                        aria-label={`Rename object ${obj.objectId}`}
                      />
                      <button
                        type="button"
                        className="rail-rename-submit"
                        aria-label="Save name"
                        onClick={() => commitEditing(obj)}
                      >
                        <CheckIcon size={14} />
                      </button>
                    </div>
                  ) : (
                    <span
                      className={`rail-name${obj.uuid ? " is-editable" : ""}`}
                      onDoubleClick={() => startEditing(obj)}
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

                {menuOpen ? (
                  <div className="rail-menu" role="menu">
                    <button
                      type="button"
                      className="rail-menu-item"
                      role="menuitem"
                      disabled={rowBusy}
                      onClick={() => startEditing(obj)}
                    >
                      Rename
                    </button>
                    <button
                      type="button"
                      className="rail-menu-item"
                      role="menuitem"
                      disabled={rowBusy || isDuplicating}
                      onClick={() => {
                        closeMenu();
                        onDuplicateObject(obj.objectId);
                      }}
                    >
                      Duplicate
                    </button>
                    {showUndoChanges ? (
                      <button
                        type="button"
                        className="rail-menu-item"
                        role="menuitem"
                        disabled={rowBusy}
                        onClick={() => {
                          closeMenu();
                          onResetObjectChanges(obj.objectId);
                        }}
                      >
                        Undo all changes
                      </button>
                    ) : null}
                    {showRemove3d ? (
                      <button
                        type="button"
                        className="rail-menu-item"
                        role="menuitem"
                        disabled={rowBusy}
                        onClick={() => {
                          closeMenu();
                          onClearObject3d(obj.objectId);
                        }}
                      >
                        Remove 3D render
                      </button>
                    ) : null}
                    <button
                      type="button"
                      className="rail-menu-item is-danger"
                      role="menuitem"
                      disabled={rowBusy || isDeleting}
                      onClick={() => {
                        closeMenu();
                        onDeleteObject(obj.objectId);
                      }}
                    >
                      Delete
                    </button>
                  </div>
                ) : null}
              </div>
            );
          })}

          {pending.map((job) => (
            <div key={job.job_id} className="rail-row is-pending">
              <div className="rail-thumb rail-thumb-empty" aria-busy="true">
                <span className="tool-spinner" />
              </div>
              <div className="rail-row-body">
                <span className="rail-name">
                  {JOB_KIND_LABEL[job.kind]}
                  {job.status === "queued" ? " (queued)" : ""}
                </span>
              </div>
            </div>
          ))}

          {failed.map((job) => (
            <div key={job.job_id} className="rail-row is-failed">
              <div className="rail-thumb rail-thumb-empty" aria-hidden="true" />
              <div className="rail-row-body">
                <span className="rail-name" title={job.error ?? undefined}>
                  {JOB_KIND_LABEL[job.kind]} failed
                </span>
              </div>
              <button
                type="button"
                className="rail-action"
                data-tip="Dismiss"
                aria-label={`Dismiss failed ${JOB_KIND_LABEL[job.kind].toLowerCase()} job`}
                onClick={() => onDismissJob(job.job_id)}
              >
                ×
              </button>
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
