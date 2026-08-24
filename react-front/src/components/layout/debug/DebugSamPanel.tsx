import React from "react";

import type { DebugImageResult, DepthStrategy, SamSource } from "../../../types/debug";
import { DEPTH_STRATEGIES, formatMs, type PanelState } from "./shared";

export interface DebugSamPanelProps {
  file: File | null;
  sam: PanelState<DebugImageResult>;
  source: SamSource;
  onSourceChange: (source: SamSource) => void;
  depthStrategy: DepthStrategy;
  onDepthStrategyChange: (strategy: DepthStrategy) => void;
  depthModel: string;
  onDepthModelChange: (model: string) => void;
  pointsPerSide: number;
  onPointsPerSideChange: (value: number) => void;
  predIouThresh: number;
  onPredIouThreshChange: (value: number) => void;
  stabilityScoreThresh: number;
  onStabilityScoreThreshChange: (value: number) => void;
  minMaskRegionArea: number;
  onMinMaskRegionAreaChange: (value: number) => void;
  alpha: number;
  onAlphaChange: (value: number) => void;
  onRun: () => void;
  onOpenLightbox: (src: string, alt: string) => void;
}

export const DebugSamPanel: React.FC<DebugSamPanelProps> = ({
  file,
  sam,
  source,
  onSourceChange,
  depthStrategy,
  onDepthStrategyChange,
  depthModel,
  onDepthModelChange,
  pointsPerSide,
  onPointsPerSideChange,
  predIouThresh,
  onPredIouThreshChange,
  stabilityScoreThresh,
  onStabilityScoreThreshChange,
  minMaskRegionArea,
  onMinMaskRegionAreaChange,
  alpha,
  onAlphaChange,
  onRun,
  onOpenLightbox,
}) => (
  <section className="debug-panel">
    <header className="debug-panel-head">
      <h3 className="debug-panel-title">SAM segment-everything</h3>
      <button type="button" className="btn" onClick={onRun} disabled={!file || sam.status === "running"}>
        {sam.status === "running" ? <span className="tool-spinner" /> : "Re-run"}
      </button>
    </header>

    <div className="debug-knobs">
      <label className="debug-knob">
        <span>Source</span>
        <select value={source} onChange={(e) => onSourceChange(e.target.value as SamSource)}>
          <option value="depth">depth (production rule)</option>
          <option value="rgb">rgb (raw photo)</option>
        </select>
      </label>
      <label className="debug-knob">
        <span>Depth strategy (source=depth only)</span>
        <select
          value={depthStrategy}
          onChange={(e) => onDepthStrategyChange(e.target.value as DepthStrategy)}
          disabled={source !== "depth"}
        >
          {DEPTH_STRATEGIES.map((s) => (
            <option key={s.value} value={s.value}>
              {s.label}
            </option>
          ))}
        </select>
      </label>
      <label className="debug-knob">
        <span>Depth model</span>
        <input
          list="debug-depth-models"
          value={depthModel}
          onChange={(e) => onDepthModelChange(e.target.value)}
          disabled={source !== "depth" || depthStrategy !== "anything"}
        />
      </label>
      <label className="debug-knob">
        <span>Points per side ({pointsPerSide})</span>
        <input
          type="range"
          min={4}
          max={64}
          step={1}
          value={pointsPerSide}
          onChange={(e) => onPointsPerSideChange(Number(e.target.value))}
        />
      </label>
      <label className="debug-knob">
        <span>Pred IoU thresh ({predIouThresh.toFixed(2)})</span>
        <input
          type="range"
          min={0}
          max={1}
          step={0.01}
          value={predIouThresh}
          onChange={(e) => onPredIouThreshChange(Number(e.target.value))}
        />
      </label>
      <label className="debug-knob">
        <span>Stability score thresh ({stabilityScoreThresh.toFixed(2)})</span>
        <input
          type="range"
          min={0}
          max={1}
          step={0.01}
          value={stabilityScoreThresh}
          onChange={(e) => onStabilityScoreThreshChange(Number(e.target.value))}
        />
      </label>
      <label className="debug-knob">
        <span>Min mask region area ({minMaskRegionArea}px)</span>
        <input
          type="range"
          min={0}
          max={5000}
          step={50}
          value={minMaskRegionArea}
          onChange={(e) => onMinMaskRegionAreaChange(Number(e.target.value))}
        />
      </label>
      <label className="debug-knob">
        <span>Overlay alpha ({alpha.toFixed(2)})</span>
        <input
          type="range"
          min={0}
          max={1}
          step={0.05}
          value={alpha}
          onChange={(e) => onAlphaChange(Number(e.target.value))}
        />
      </label>
    </div>

    {sam.status === "error" ? <p className="debug-panel-error">{sam.message}</p> : null}

    {sam.status === "done" ? (
      <>
        <button
          type="button"
          className="debug-image-frame"
          onClick={() => onOpenLightbox(sam.data.objectUrl, "SAM segment-everything render")}
        >
          <img src={sam.data.objectUrl} alt="SAM segment-everything render" />
        </button>
        <p className="debug-panel-elapsed">
          {sam.data.maskCount === null ? "" : `${sam.data.maskCount} masks · `}
          {formatMs(sam.data.elapsedMs)}
        </p>
      </>
    ) : sam.status === "idle" ? (
      <p className="debug-panel-hint">Can take seconds to minutes — points_per_side² SAM forward passes.</p>
    ) : null}
  </section>
);
