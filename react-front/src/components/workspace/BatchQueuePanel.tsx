import React from "react";

import type { ArmedJob, ArmedJobAction } from "../../types/armedBatch";
import { actionsForSource, armedJobLabel } from "../../utils/armedBatch";

export interface BatchQueuePanelProps {
  jobs: ArmedJob[];
  selectedJobId: string | null;
  busy: boolean;
  onSelectJob: (id: string) => void;
  onActionChange: (id: string, action: ArmedJobAction) => void;
  onMoveUp: (id: string) => void;
  onMoveDown: (id: string) => void;
  onRemove: (id: string) => void;
  onApprove: () => void;
  onClear: () => void;
  onClose: () => void;
}

const ACTION_OPTIONS: { value: ArmedJobAction; label: string }[] = [
  { value: "erase", label: "Erase" },
  { value: "cutOut", label: "Cut out" },
  { value: "cutOutAnd3d", label: "Cut out + 3D" },
  { value: "generate3d", label: "Build 3D" },
];

export const BatchQueuePanel: React.FC<BatchQueuePanelProps> = ({
  jobs,
  selectedJobId,
  busy,
  onSelectJob,
  onActionChange,
  onMoveUp,
  onMoveDown,
  onRemove,
  onApprove,
  onClear,
  onClose,
}) => {
  return (
    <aside className="batch-queue-panel" aria-label="Armed batch queue">
      <div className="batch-queue-head">
        <div>
          <h2 className="batch-queue-title">Batch queue</h2>
          <p className="batch-queue-sub">
            {jobs.length === 0 ? "Nothing armed" : `${jobs.length} armed`}
          </p>
        </div>
        <button type="button" className="batch-queue-close" onClick={onClose} aria-label="Close">
          ×
        </button>
      </div>

      <ul className="batch-queue-list">
        {jobs.map((job, index) => {
          const allowed = actionsForSource(job.source);
          const isSelected = job.id === selectedJobId;
          return (
            <li
              key={job.id}
              className={`batch-queue-row${isSelected ? " is-selected" : ""}`}
            >
              <button
                type="button"
                className="batch-queue-row-main"
                onClick={() => onSelectJob(job.id)}
              >
                <span className="batch-queue-index">{String(index + 1).padStart(2, "0")}</span>
                <span className="batch-queue-label">{armedJobLabel(job)}</span>
              </button>
              <select
                className="batch-queue-action"
                value={job.action}
                disabled={busy}
                aria-label={`Action for row ${index + 1}`}
                onChange={(event) =>
                  onActionChange(job.id, event.target.value as ArmedJobAction)
                }
              >
                {ACTION_OPTIONS.filter((option) => allowed.includes(option.value)).map(
                  (option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ),
                )}
              </select>
              <div className="batch-queue-row-actions">
                <button
                  type="button"
                  className="batch-queue-icon-btn"
                  aria-label="Move up"
                  disabled={busy || index === 0}
                  onClick={() => onMoveUp(job.id)}
                >
                  ↑
                </button>
                <button
                  type="button"
                  className="batch-queue-icon-btn"
                  aria-label="Move down"
                  disabled={busy || index === jobs.length - 1}
                  onClick={() => onMoveDown(job.id)}
                >
                  ↓
                </button>
                <button
                  type="button"
                  className="batch-queue-icon-btn is-danger"
                  aria-label="Remove"
                  disabled={busy}
                  onClick={() => onRemove(job.id)}
                >
                  ×
                </button>
              </div>
            </li>
          );
        })}
      </ul>

      <div className="batch-queue-foot">
        <button
          type="button"
          className="batch-queue-approve"
          disabled={busy || jobs.length === 0}
          onClick={onApprove}
        >
          {busy ? <span className="tool-spinner" /> : "Approve"}
        </button>
        <button
          type="button"
          className="batch-queue-clear"
          disabled={busy || jobs.length === 0}
          onClick={onClear}
        >
          Clear
        </button>
      </div>
    </aside>
  );
};
