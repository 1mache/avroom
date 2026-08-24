import React from "react";

import type { DebugValidationResponse } from "../../../types/debug";
import { CheckRow, formatMs, type PanelState } from "./shared";

export interface DebugValidationPanelProps {
  file: File | null;
  validation: PanelState<DebugValidationResponse>;
  onRun: () => void;
}

export const DebugValidationPanel: React.FC<DebugValidationPanelProps> = ({ file, validation, onRun }) => (
  <section className="debug-panel">
    <header className="debug-panel-head">
      <h3 className="debug-panel-title">Validation</h3>
      {validation.status === "done" ? (
        <span className={`debug-verdict${validation.data.ok ? " is-pass" : " is-fail"}`}>
          {validation.data.ok ? "PASS" : "FAIL"}
        </span>
      ) : null}
      <button type="button" className="btn" onClick={onRun} disabled={!file || validation.status === "running"}>
        {validation.status === "running" ? <span className="tool-spinner" /> : "Re-run"}
      </button>
    </header>

    {validation.status === "error" ? <p className="debug-panel-error">{validation.message}</p> : null}

    {validation.status === "done" ? (
      <div className="debug-check-groups">
        <div className="debug-check-group">
          <span className="debug-check-group-title">
            Technical{validation.data.technical_ok ? "" : " — failed"}
          </span>
          {validation.data.technical.map((check) => (
            <CheckRow key={check.name} {...check} />
          ))}
        </div>
        <div className="debug-check-group">
          <span className="debug-check-group-title">
            Content{" "}
            {validation.data.content_skipped_reason
              ? `— skipped (${validation.data.content_skipped_reason})`
              : validation.data.content_ok
                ? ""
                : "— failed"}
          </span>
          {validation.data.content.map((check) => (
            <CheckRow key={check.name} {...check} />
          ))}
        </div>
        <p className="debug-panel-elapsed">{formatMs(validation.data.elapsed_ms)}</p>
      </div>
    ) : validation.status === "idle" ? (
      <p className="debug-panel-hint">Pick a photo, then run to see the scoreboard.</p>
    ) : null}
  </section>
);
