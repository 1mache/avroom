import React from "react";

import type { VerifyMode } from "../../types/api";
import {
  BackIcon,
  CheckIcon,
  CopyIcon,
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
  status,
}) => {
  const objectToolsDisabled = !hasSelection;

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

      {status ? <span className="toolbar-status">{status}</span> : null}

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
