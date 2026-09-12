import React, { useCallback, useEffect, useRef, useState } from "react";

import type { SmartPasteSettings } from "../../hooks/useSmartPasteSettings";
import type { VerifyMode } from "../../types/api";
import {
  AreaIcon,
  BackIcon,
  BacktrackIcon,
  BatchIcon,
  CheckIcon,
  CopyIcon,
  DownloadIcon,
  EraserIcon,
  ForwardIcon,
  MultiPointIcon,
  QueueIcon,
  RevertIcon,
  RotateIcon,
  ScissorsIcon,
  SettingsIcon,
  SmartPasteIcon,
  TrashIcon,
} from "../icons";

/** Room identity and whole-room actions: the left end of the bar, plus status. */
export interface ToolbarSession {
  name: string;
  onNameChange: (name: string) => void;
  onNameKeyDown: React.KeyboardEventHandler<HTMLInputElement>;
  onBack: () => void;
  isCopyingRoom: boolean;
  onCopyRoom: () => void;
  hasSnapshot: boolean;
  isSavingSnapshot: boolean;
  onDownloadSnapshot: () => void;
  /** Short readout of in-flight work, e.g. "removing 2". Null when idle. */
  status: string | null;
}

/** The tools that arm a gesture on the photo. Only one is ever armed. */
export interface ToolbarPicking {
  /** Scissors is armed: the next click on the photo starts a cutout. */
  cutMode: boolean;
  onCut: () => void;
  multiPoint: boolean;
  onToggleMultiPoint: () => void;
  hasPendingSegmentSeeds: boolean;
  onUndoLastSeed: () => void;
  areaMode: boolean;
  onArea: () => void;
  eraserMode: boolean;
  onEraser: () => void;
  hasPendingEraseRegions: boolean;
}

/** Arming several operations before approving them in one go. */
export interface ToolbarBatch {
  batchMode: boolean;
  onToggleBatchMode: () => void;
  armedQueueCount: number;
  queuePanelOpen: boolean;
  onToggleQueuePanel: () => void;
  busy: boolean;
  /** A box batch or multi-point seeds are staged and waiting for submit. */
  hasPending: boolean;
  onSubmit: () => void;
  /** CLIP vs picker for the next cutout. */
  verifyMode: VerifyMode;
  onVerifyModeChange: (mode: VerifyMode) => void;
}

/** Actions scoped to whichever object is selected. */
export interface ToolbarObject {
  hasSelection: boolean;
  /** The 3D angle picker is open; pressing rotate again applies the angle. */
  rotateMode: boolean;
  isPreparing3D: boolean;
  onRotate: () => void;
  isDuplicating: boolean;
  onCopy: () => void;
  isDeleting: boolean;
  onDelete: () => void;
}

/** Backtrack / forward through the room's background history. */
export interface ToolbarHistory {
  canUndo: boolean;
  canRedo: boolean;
  busy: boolean;
  backtrack: () => void;
  forward: () => void;
}

/**
 * Six groups rather than the 53 flat props this used to take.
 *
 * The grouping is not cosmetic: each one matches a visible section of the
 * bar, and `history` and `smartPaste` are exactly the shapes
 * `useSessionHistory` and `useSmartPasteSettings` already return, so the
 * call site passes them straight through instead of unpacking and
 * re-packing every field.
 */
export interface ToolbarProps {
  session: ToolbarSession;
  picking: ToolbarPicking;
  batch: ToolbarBatch;
  object: ToolbarObject;
  smartPaste: SmartPasteSettings;
  history: ToolbarHistory;
}

/**
 * The workspace's only permanent chrome. Every control is icon-only and names
 * itself on hover (`data-tip`); the object-scoped tools grey out until an
 * object is selected rather than disappearing, so the row never reflows.
 */
export const Toolbar: React.FC<ToolbarProps> = ({
  session,
  picking,
  batch,
  object,
  smartPaste: paste,
  history,
}) => {
  // Unpacked so the markup below reads exactly as it did when these arrived
  // as 53 separate props; the grouping is for the call site's benefit.
  const {
    name: sessionName,
    onNameChange: onSessionNameChange,
    onNameKeyDown: onSessionNameKeyDown,
    onBack,
    isCopyingRoom,
    onCopyRoom,
    hasSnapshot,
    isSavingSnapshot,
    onDownloadSnapshot,
    status,
  } = session;
  const {
    cutMode,
    onCut,
    multiPoint,
    onToggleMultiPoint,
    hasPendingSegmentSeeds,
    onUndoLastSeed,
    areaMode,
    onArea,
    eraserMode,
    onEraser,
    hasPendingEraseRegions,
  } = picking;
  const {
    batchMode,
    onToggleBatchMode,
    armedQueueCount,
    queuePanelOpen,
    onToggleQueuePanel,
    busy: batchBusy,
    hasPending: hasPendingBatch,
    onSubmit: onSubmitBatch,
    verifyMode,
    onVerifyModeChange,
  } = batch;
  const {
    hasSelection,
    rotateMode,
    isPreparing3D,
    onRotate,
    isDuplicating,
    onCopy,
    isDeleting,
    onDelete: onDeleteObject,
  } = object;
  const {
    enabled: smartPaste,
    scaleByPov,
    smartRotate,
    autoGenerate3d,
    toggleEnabled: onToggleSmartPaste,
    toggleScaleByPov: onToggleScaleByPov,
    toggleSmartRotate: onToggleSmartRotate,
    toggleAutoGenerate3d: onToggleAutoGenerate3d,
  } = paste;
  const { canUndo, canRedo, busy: historyBusy, backtrack: onBacktrack, forward: onForward } = history;
  const objectToolsDisabled = !hasSelection;
  const historyDisabled = historyBusy || Boolean(status);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const settingsWrapRef = useRef<HTMLDivElement | null>(null);

  const closeSettings = useCallback(() => {
    setSettingsOpen(false);
  }, []);

  useEffect(() => {
    if (!settingsOpen) {
      return;
    }

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        closeSettings();
      }
    };

    const handlePointerDown = (event: PointerEvent) => {
      const root = settingsWrapRef.current;
      if (root && !root.contains(event.target as Node)) {
        closeSettings();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    window.addEventListener("pointerdown", handlePointerDown);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
      window.removeEventListener("pointerdown", handlePointerDown);
    };
  }, [closeSettings, settingsOpen]);

  return (
    <header className="toolbar">
      <button
        type="button"
        className="tool-btn"
        data-tip="Back to dashboard"
        aria-label="Back to dashboard"
        onClick={onBack}
      >
        <BackIcon />
      </button>

      <span className="toolbar-rule" />

      <input
        type="text"
        className="session-name"
        value={sessionName}
        onChange={(event) => onSessionNameChange(event.target.value)}
        onKeyDown={onSessionNameKeyDown}
        placeholder="Untitled room"
        aria-label="Room name"
        spellCheck={false}
      />

      <span className="toolbar-rule" />

      <button
        type="button"
        className={`tool-btn${cutMode ? " is-armed" : ""}`}
        data-tip={cutMode ? "Click the photo to cut" : "Cut out object"}
        aria-label="Cut out object"
        aria-pressed={cutMode}
        onClick={onCut}
      >
        <ScissorsIcon />
      </button>

      <button
        type="button"
        role="switch"
        aria-checked={multiPoint}
        className={`tool-switch${multiPoint ? " is-on" : ""}`}
        data-tip="Multi-point cutout"
        aria-label="Multi-point cutout"
        onClick={onToggleMultiPoint}
      >
        <MultiPointIcon />
        <span className="tool-switch-track">
          <span className="tool-switch-nub" />
        </span>
      </button>

      {multiPoint ? (
        <button
          type="button"
          className="tool-btn"
          data-tip="Remove last seed"
          aria-label="Remove last seed"
          disabled={!hasPendingSegmentSeeds}
          onClick={onUndoLastSeed}
        >
          <RevertIcon size={15} />
        </button>
      ) : null}

      <button
        type="button"
        className={`tool-btn${areaMode ? " is-armed" : ""}`}
        data-tip={areaMode ? "Drag a box on the photo" : "Cut everything in a box"}
        aria-label="Cut objects in area"
        aria-pressed={areaMode}
        disabled={batchBusy}
        onClick={onArea}
      >
        <AreaIcon />
      </button>

      <button
        type="button"
        className={`tool-btn${batchMode ? " is-armed" : ""}`}
        data-tip={batchMode ? "Batch on — jobs arm until approved" : "Batch mode"}
        aria-label="Batch mode"
        aria-pressed={batchMode}
        disabled={batchBusy}
        onClick={onToggleBatchMode}
      >
        <BatchIcon />
      </button>

      <button
        type="button"
        className={`tool-btn has-badge${queuePanelOpen ? " is-armed" : ""}`}
        data-tip="Armed batch queue"
        aria-label="Armed batch queue"
        aria-pressed={queuePanelOpen}
        disabled={armedQueueCount === 0 && !batchMode}
        onClick={onToggleQueuePanel}
      >
        <QueueIcon />
        {armedQueueCount > 0 ? (
          <span className="tool-btn-badge">{armedQueueCount > 9 ? "9+" : armedQueueCount}</span>
        ) : null}
      </button>

      <button
        type="button"
        className={`tool-btn${hasPendingBatch ? " is-armed" : ""}`}
        data-tip={
          batchMode
            ? hasPendingSegmentSeeds
              ? "Approve batch (flush seeds first)"
              : hasPendingBatch
                ? "Approve batch queue"
                : "Arm jobs first"
            : hasPendingEraseRegions
              ? "Run staged erase regions"
              : hasPendingSegmentSeeds
                ? "Run multi-point cut"
                : hasPendingBatch
                  ? "Run batch cut in the box"
                  : "Stage seeds, a box, or erase regions first"
        }
        aria-label={batchMode ? "Approve batch" : "Submit pending work"}
        disabled={!hasPendingBatch || batchBusy}
        onClick={onSubmitBatch}
      >
        {batchBusy ? <span className="tool-spinner" /> : <CheckIcon />}
      </button>

      <button
        type="button"
        className={`tool-btn${eraserMode ? " is-armed" : ""}`}
        data-tip={eraserMode ? "Drag a loop on the photo" : "Erase area"}
        aria-label="Erase area"
        aria-pressed={eraserMode}
        onClick={onEraser}
      >
        <EraserIcon />
      </button>

      <button
        type="button"
        className="tool-btn"
        data-tip="Backtrack room"
        aria-label="Backtrack room"
        disabled={!canUndo || historyDisabled}
        onClick={onBacktrack}
      >
        {historyBusy ? <span className="tool-spinner" /> : <BacktrackIcon />}
      </button>

      <button
        type="button"
        className="tool-btn"
        data-tip="Forward room"
        aria-label="Forward room"
        disabled={!canRedo || historyDisabled}
        onClick={onForward}
      >
        <ForwardIcon />
      </button>

      <button
        type="button"
        className="tool-btn"
        data-tip="Save room snapshot"
        aria-label="Save room snapshot"
        disabled={!hasSnapshot || isSavingSnapshot || historyDisabled}
        onClick={onDownloadSnapshot}
      >
        {isSavingSnapshot ? <span className="tool-spinner" /> : <DownloadIcon />}
      </button>

      <button
        type="button"
        className={`tool-btn${rotateMode ? " is-armed" : ""}`}
        data-tip={
          isPreparing3D ? "Building 3D model" : rotateMode ? "Apply rotation" : "Rotate object"
        }
        aria-label={rotateMode ? "Apply rotation" : "Rotate object"}
        aria-pressed={rotateMode}
        onClick={onRotate}
        disabled={objectToolsDisabled || isPreparing3D}
      >
        {isPreparing3D ? (
          <span className="tool-spinner" />
        ) : rotateMode ? (
          <CheckIcon />
        ) : (
          <RotateIcon />
        )}
      </button>

      <button
        type="button"
        className="tool-btn"
        data-tip="Duplicate object"
        aria-label="Duplicate object"
        onClick={onCopy}
        disabled={objectToolsDisabled || isDuplicating || rotateMode}
      >
        {isDuplicating ? <span className="tool-spinner" /> : <CopyIcon />}
      </button>

      <span className="toolbar-rule" />

      <button
        type="button"
        role="switch"
        aria-checked={smartPaste}
        className={`tool-switch${smartPaste ? " is-on" : ""}`}
        data-tip="Smart paste"
        aria-label="Smart paste"
        onClick={onToggleSmartPaste}
        disabled={objectToolsDisabled}
      >
        <SmartPasteIcon />
        <span className="tool-switch-track">
          <span className="tool-switch-nub" />
        </span>
      </button>

      <div className="toolbar-settings-wrap" ref={settingsWrapRef}>
        <button
          type="button"
          className={`tool-btn${settingsOpen ? " is-armed" : ""}`}
          data-tip="Options"
          aria-label="Options"
          aria-expanded={settingsOpen}
          aria-haspopup="dialog"
          onClick={() => setSettingsOpen((open) => !open)}
        >
          <SettingsIcon />
        </button>

        {settingsOpen ? (
          <div
            className="toolbar-settings-popover"
            role="dialog"
            aria-label="Options"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="toolbar-settings-section">
              <p className="toolbar-settings-title">Room</p>
              <button
                type="button"
                className="toolbar-settings-row toolbar-settings-action"
                onClick={() => {
                  closeSettings();
                  onCopyRoom();
                }}
                disabled={isCopyingRoom}
              >
                <span className="toolbar-settings-label">
                  {isCopyingRoom ? "Copying room…" : "Copy room"}
                </span>
              </button>
            </div>
            <div className="toolbar-settings-section">
              <p className="toolbar-settings-title">Mask picker</p>
              <div
                className="tool-radios toolbar-settings-radios"
                role="radiogroup"
                aria-label="Cutout verification"
              >
                <button
                  type="button"
                  role="radio"
                  className="tool-radio"
                  aria-checked={verifyMode === "manual"}
                  onClick={() => onVerifyModeChange("manual")}
                >
                  Manual
                </button>
                <button
                  type="button"
                  role="radio"
                  className="tool-radio"
                  aria-checked={verifyMode === "auto"}
                  onClick={() => onVerifyModeChange("auto")}
                >
                  Auto
                </button>
              </div>
              <p className="toolbar-settings-hint">
                {verifyMode === "auto" ? "CLIP picks the mask" : "Pick a mask"}
              </p>
            </div>
            <div className="toolbar-settings-section">
              <p className="toolbar-settings-title">Object removal</p>
              <button
                type="button"
                role="switch"
                aria-checked={autoGenerate3d}
                className={`toolbar-settings-row tool-switch${autoGenerate3d ? " is-on" : ""}`}
                onClick={onToggleAutoGenerate3d}
              >
                <span className="toolbar-settings-label">Auto 3D</span>
                <span className="tool-switch-track">
                  <span className="tool-switch-nub" />
                </span>
              </button>
            </div>
            <div className="toolbar-settings-section">
              <p className="toolbar-settings-title">Smart paste</p>
              <button
                type="button"
                role="switch"
                aria-checked={scaleByPov}
                className={`toolbar-settings-row tool-switch${scaleByPov ? " is-on" : ""}`}
                onClick={onToggleScaleByPov}
              >
                <span className="toolbar-settings-label">Scale by POV</span>
                <span className="tool-switch-track">
                  <span className="tool-switch-nub" />
                </span>
              </button>
              <button
                type="button"
                role="switch"
                aria-checked={smartRotate}
                className={`toolbar-settings-row tool-switch${smartRotate ? " is-on" : ""}`}
                onClick={onToggleSmartRotate}
              >
                <span className="toolbar-settings-label">Smart rotate</span>
                <span className="tool-switch-track">
                  <span className="tool-switch-nub" />
                </span>
              </button>
            </div>
          </div>
        ) : null}
      </div>

      <span className="toolbar-spacer" />

      {status ? (
        <span className="toolbar-status">
          {status === "preparing maps" ? (
            <span className="tool-spinner" aria-hidden="true" />
          ) : null}
          {status}
        </span>
      ) : null}

      <button
        type="button"
        className="tool-btn is-danger"
        data-tip="Delete object"
        aria-label="Delete object"
        onClick={onDeleteObject}
        disabled={objectToolsDisabled || isDeleting || rotateMode}
      >
        {isDeleting ? <span className="tool-spinner" /> : <TrashIcon />}
      </button>
    </header>
  );
};
