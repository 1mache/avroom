import React from "react";

import type { VerifyMode } from "../../types/api";
import {
  AreaIcon,
  BackIcon,
  BacktrackIcon,
  CheckIcon,
  CopyIcon,
  DownloadIcon,
  EraserIcon,
  ForwardIcon,
  MultiPointIcon,
  RevertIcon,
  RotateIcon,
  ScissorsIcon,
  SmartPasteIcon,
  TrashIcon,
} from "../icons";

export interface ToolbarProps {
  sessionName: string;
  onSessionNameChange: (name: string) => void;
  onSessionNameKeyDown: React.KeyboardEventHandler<HTMLInputElement>;
  onBack: () => void;
  hasSelection: boolean;
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
  batchBusy: boolean;
  /** A box batch or multi-point seeds are staged and waiting for submit. */
  hasPendingBatch: boolean;
  onSubmitBatch: () => void;
  /** CLIP vs picker for the next cutout. */
  verifyMode: VerifyMode;
  onVerifyModeChange: (mode: VerifyMode) => void;
  /** The 3D angle picker is open; pressing rotate again applies the angle. */
  rotateMode: boolean;
  isPreparing3D: boolean;
  onRotate: () => void;
  isDuplicating: boolean;
  onCopy: () => void;
  smartPaste: boolean;
  onToggleSmartPaste: () => void;
  isDeleting: boolean;
  onDeleteObject: () => void;
  canUndo: boolean;
  canRedo: boolean;
  historyBusy: boolean;
  onBacktrack: () => void;
  onForward: () => void;
  hasSnapshot: boolean;
  isSavingSnapshot: boolean;
  onDownloadSnapshot: () => void;
  /** Short readout of in-flight work, e.g. "removing 2". Null when idle. */
  status: string | null;
}

/**
 * The workspace's only permanent chrome. Every control is icon-only and names
 * itself on hover (`data-tip`); the object-scoped tools grey out until an
 * object is selected rather than disappearing, so the row never reflows.
 */
export const Toolbar: React.FC<ToolbarProps> = ({
  sessionName,
  onSessionNameChange,
  onSessionNameKeyDown,
  onBack,
  hasSelection,
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
  batchBusy,
  hasPendingBatch,
  onSubmitBatch,
  verifyMode,
  onVerifyModeChange,
  rotateMode,
  isPreparing3D,
  onRotate,
  isDuplicating,
  onCopy,
  smartPaste,
  onToggleSmartPaste,
  isDeleting,
  onDeleteObject,
  canUndo,
  canRedo,
  historyBusy,
  onBacktrack,
  onForward,
  hasSnapshot,
  isSavingSnapshot,
  onDownloadSnapshot,
  status,
}) => {
  const objectToolsDisabled = !hasSelection;
  const historyDisabled = historyBusy || Boolean(status);

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
        placeholder="Untitled session"
        aria-label="Session name"
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
        className={`tool-btn${hasPendingBatch ? " is-armed" : ""}`}
        data-tip={
          hasPendingEraseRegions
            ? "Run staged erase regions"
            : hasPendingSegmentSeeds
              ? "Run multi-point cut"
              : hasPendingBatch
                ? "Run batch cut in the box"
                : "Stage seeds, a box, or erase regions first"
        }
        aria-label="Submit pending work"
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

      <div
        className="tool-radios"
        role="radiogroup"
        aria-label="Cutout verification"
        data-tip={verifyMode === "auto" ? "CLIP picks the mask" : "Pick a mask"}
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
