import React from "react";

import type { DebugAutoMaskPickResponse } from "../../../types/debug";
import { formatMs, pngSrc, type PanelState } from "./shared";

export interface DebugMaskPickPanelProps {
  file: File | null;
  clickPos: { x: number; y: number } | null;
  maskPick: PanelState<DebugAutoMaskPickResponse>;
  selectedMaskIndex: number | null;
  onSelectMaskIndex: (index: number) => void;
  onRun: () => void;
  onOpenLightbox: (src: string, alt: string) => void;
}

export const DebugMaskPickPanel: React.FC<DebugMaskPickPanelProps> = ({
  file,
  clickPos,
  maskPick,
  selectedMaskIndex,
  onSelectMaskIndex,
  onRun,
  onOpenLightbox,
}) => (
  <section className="debug-panel">
    <header className="debug-panel-head">
      <h3 className="debug-panel-title">Auto mask pick</h3>
      {maskPick.status === "done" ? (
        <span className={`debug-verdict${maskPick.data.winner_index !== null ? " is-pass" : " is-fail"}`}>
          {maskPick.data.winner_index !== null ? `WINNER ${maskPick.data.winner_index}` : "NO WINNER"}
        </span>
      ) : null}
      <button
        type="button"
        className="btn"
        onClick={onRun}
        disabled={!file || !clickPos || maskPick.status === "running"}
      >
        {maskPick.status === "running" ? <span className="tool-spinner" /> : "Re-run"}
      </button>
    </header>
    {maskPick.status === "error" ? <p className="debug-panel-error">{maskPick.message}</p> : null}
    {maskPick.status === "done" ? (
      <>
        <p className="debug-panel-hint">
          Threshold {maskPick.data.threshold.toFixed(2)}. Click a card to send that mask to inpaint verify.
        </p>
        {maskPick.data.finalist_indices.length > 1 ? (
          <p className="debug-panel-hint">
            Tiebreak: {maskPick.data.tiebreak_method}
            {maskPick.data.tiebreak_reason ? ` — ${maskPick.data.tiebreak_reason}` : ""}{" "}
            (finalists {maskPick.data.finalist_indices.join(", ")})
          </p>
        ) : null}
        <div className="debug-candidate-grid">
          {maskPick.data.candidates.map((candidate) => {
            const isWinner = candidate.index === maskPick.data.winner_index;
            const isSelected = candidate.index === selectedMaskIndex;
            return (
              <button
                key={candidate.index}
                type="button"
                className={`debug-candidate-card${isWinner ? " is-winner" : ""}${isSelected ? " is-selected" : ""}`}
                onClick={() => onSelectMaskIndex(candidate.index)}
              >
                <img
                  src={pngSrc(candidate.preview_b64)}
                  alt={`Candidate ${candidate.index}`}
                  onClick={(event) => {
                    event.stopPropagation();
                    onOpenLightbox(pngSrc(candidate.preview_b64), `Candidate ${candidate.index}`);
                  }}
                />
                <div className="debug-candidate-meta">
                  <span>#{candidate.index}</span>
                  <span>{candidate.score.toFixed(3)}</span>
                </div>
                <span className="debug-check-message">{candidate.reason}</span>
                {candidate.clip_crop_b64 ? (
                  <img
                    src={pngSrc(candidate.clip_crop_b64)}
                    alt={`CLIP crop ${candidate.index}`}
                    onClick={(event) => {
                      event.stopPropagation();
                      onOpenLightbox(pngSrc(candidate.clip_crop_b64 as string), `CLIP crop ${candidate.index}`);
                    }}
                  />
                ) : (
                  <span className="debug-panel-hint">Not scored</span>
                )}
              </button>
            );
          })}
        </div>
        <p className="debug-panel-elapsed">{formatMs(maskPick.data.elapsed_ms)}</p>
      </>
    ) : (
      <p className="debug-panel-hint">Click the photo, then run. Shows every SAM mask, CLIP score, and the winner.</p>
    )}
  </section>
);
