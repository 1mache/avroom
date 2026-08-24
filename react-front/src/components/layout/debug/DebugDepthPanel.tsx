import React from "react";

import type { DebugImageResult, DepthColormap, DepthStrategy } from "../../../types/debug";
import { COLORMAPS, DEPTH_STRATEGIES, KNOWN_DEPTH_MODELS, formatMs, type PanelState } from "./shared";

export interface DebugDepthPanelProps {
  file: File | null;
  depth: PanelState<DebugImageResult>;
  strategy: DepthStrategy;
  onStrategyChange: (strategy: DepthStrategy) => void;
  model: string;
  onModelChange: (model: string) => void;
  colormap: DepthColormap;
  onColormapChange: (colormap: DepthColormap) => void;
  onRun: () => void;
  onOpenLightbox: (src: string, alt: string) => void;
}

export const DebugDepthPanel: React.FC<DebugDepthPanelProps> = ({
  file,
  depth,
  strategy,
  onStrategyChange,
  model,
  onModelChange,
  colormap,
  onColormapChange,
  onRun,
  onOpenLightbox,
}) => (
  <section className="debug-panel">
    <header className="debug-panel-head">
      <h3 className="debug-panel-title">Depth map</h3>
      <button type="button" className="btn" onClick={onRun} disabled={!file || depth.status === "running"}>
        {depth.status === "running" ? <span className="tool-spinner" /> : "Re-run"}
      </button>
    </header>

    <div className="debug-knobs">
      <label className="debug-knob">
        <span>Strategy</span>
        <select value={strategy} onChange={(e) => onStrategyChange(e.target.value as DepthStrategy)}>
          {DEPTH_STRATEGIES.map((s) => (
            <option key={s.value} value={s.value}>
              {s.label}
            </option>
          ))}
        </select>
      </label>
      <label className="debug-knob">
        <span>Model (strategy=anything only)</span>
        <input
          list="debug-depth-models"
          value={model}
          onChange={(e) => onModelChange(e.target.value)}
          disabled={strategy !== "anything"}
        />
      </label>
      <label className="debug-knob">
        <span>Colormap</span>
        <select value={colormap} onChange={(e) => onColormapChange(e.target.value as DepthColormap)}>
          {COLORMAPS.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
      </label>
    </div>

    {depth.status === "error" ? <p className="debug-panel-error">{depth.message}</p> : null}

    {depth.status === "done" ? (
      <>
        <button
          type="button"
          className="debug-image-frame"
          onClick={() => onOpenLightbox(depth.data.objectUrl, "Depth map render")}
        >
          <img src={depth.data.objectUrl} alt="Depth map render" />
        </button>
        <p className="debug-panel-elapsed">{formatMs(depth.data.elapsedMs)}</p>
      </>
    ) : depth.status === "idle" ? (
      <p className="debug-panel-hint">Renders whatever Depth-Anything sees, as an image.</p>
    ) : null}

    <datalist id="debug-depth-models">
      {KNOWN_DEPTH_MODELS.map((m) => (
        <option key={m} value={m} />
      ))}
    </datalist>
  </section>
);
