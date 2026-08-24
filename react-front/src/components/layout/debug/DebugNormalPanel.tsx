import React, { useRef } from "react";

import type { DebugImageResult, NormalHubModel } from "../../../types/debug";
import { getContainedImageRect, toNaturalPoint } from "../../../utils/stageGeometry";
import { NORMAL_HUB_MODELS, formatMs, type PanelState } from "./shared";

export type NormalSample = { x: number; y: number; nx: number; ny: number; nz: number };

export interface DebugNormalPanelProps {
  file: File | null;
  normals: PanelState<DebugImageResult>;
  normalSample: NormalSample | null;
  onSample: (sample: NormalSample | null) => void;
  hubModel: NormalHubModel;
  onHubModelChange: (model: NormalHubModel) => void;
  onRun: () => void;
  onOpenLightbox: (src: string, alt: string) => void;
}

export const DebugNormalPanel: React.FC<DebugNormalPanelProps> = ({
  file,
  normals,
  normalSample,
  onSample,
  hubModel,
  onHubModelChange,
  onRun,
  onOpenLightbox,
}) => {
  // Unreferenced outside this panel — the click handler reads its own
  // event.currentTarget, so this ref never needs to leave here.
  const normalImgRef = useRef<HTMLImageElement>(null);

  const handleNormalMapClick: React.MouseEventHandler<HTMLImageElement> = (event) => {
    const img = event.currentTarget;
    if (!img.naturalWidth || !img.naturalHeight) {
      return;
    }
    const natural = { width: img.naturalWidth, height: img.naturalHeight };
    const box = { width: img.clientWidth, height: img.clientHeight };
    const rendered = getContainedImageRect(box, natural);
    if (!rendered) {
      return;
    }
    const point = toNaturalPoint(event.nativeEvent.offsetX, event.nativeEvent.offsetY, rendered, natural);
    if (!point) {
      return;
    }
    const x = Math.max(0, Math.min(img.naturalWidth - 1, Math.round(point.x)));
    const y = Math.max(0, Math.min(img.naturalHeight - 1, Math.round(point.y)));

    const canvas = document.createElement("canvas");
    canvas.width = img.naturalWidth;
    canvas.height = img.naturalHeight;
    const ctx = canvas.getContext("2d");
    if (!ctx) {
      return;
    }
    ctx.drawImage(img, 0, 0);
    const pixel = ctx.getImageData(x, y, 1, 1).data;
    const nx = (pixel[0] / 255) * 2 - 1;
    const ny = (pixel[1] / 255) * 2 - 1;
    const nz = (pixel[2] / 255) * 2 - 1;
    onSample({ x, y, nx, ny, nz });
  };

  return (
    <section className="debug-panel">
      <header className="debug-panel-head">
        <h3 className="debug-panel-title">Normal map</h3>
        <button type="button" className="btn" onClick={onRun} disabled={!file || normals.status === "running"}>
          {normals.status === "running" ? <span className="tool-spinner" /> : "Generate"}
        </button>
      </header>

      <div className="debug-knobs">
        <label className="debug-knob">
          <span>Metric3D hub model</span>
          <select value={hubModel} onChange={(e) => onHubModelChange(e.target.value as NormalHubModel)}>
            {NORMAL_HUB_MODELS.map((m) => (
              <option key={m.value} value={m.value}>
                {m.label}
              </option>
            ))}
          </select>
        </label>
      </div>

      {normals.status === "error" ? <p className="debug-panel-error">{normals.message}</p> : null}

      {normals.status === "done" ? (
        <>
          <div className="debug-image-frame debug-image-frame-sample">
            <img
              ref={normalImgRef}
              src={normals.data.objectUrl}
              alt="Normal map render"
              onClick={handleNormalMapClick}
            />
          </div>
          <p className="debug-panel-hint">
            Click a pixel to read nx, ny, nz (8-bit from the PNG).{" "}
            <button
              type="button"
              className="debug-inline-link"
              onClick={() => onOpenLightbox(normals.data.objectUrl, "Normal map render")}
            >
              Expand
            </button>
          </p>
          {normalSample ? (
            <p className="debug-normal-readout" role="status">
              ({normalSample.x}, {normalSample.y}) → nx={normalSample.nx.toFixed(3)} ny=
              {normalSample.ny.toFixed(3)} nz={normalSample.nz.toFixed(3)}
            </p>
          ) : null}
          <p className="debug-panel-elapsed">{formatMs(normals.data.elapsedMs)}</p>
        </>
      ) : normals.status === "idle" ? (
        <p className="debug-panel-hint">Metric3D surface normals. Generate explicitly — not part of Run all.</p>
      ) : null}
    </section>
  );
};
