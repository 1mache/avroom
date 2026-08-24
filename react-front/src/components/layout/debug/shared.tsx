import React, { useEffect } from "react";

import { ApiError } from "../../../api/images";
import type { DepthColormap, DepthStrategy, NormalHubModel } from "../../../types/debug";

/** Shared across every debug panel: idle until run, then done or error. */
export type PanelState<T> =
  | { status: "idle" }
  | { status: "running" }
  | { status: "done"; data: T }
  | { status: "error"; message: string };

export function errorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 404) {
      return "Debug endpoints are disabled on the server (DEBUG_ENDPOINTS=false).";
    }
    return err.detail || err.message;
  }
  return err instanceof Error ? err.message : "Request failed.";
}

export const formatMs = (ms: number | null): string => (ms === null ? "—" : `${ms.toFixed(0)} ms`);

export const pngSrc = (b64: string): string => `data:image/png;base64,${b64}`;

// One HF checkpoint dropdown shared by the depth panel and the SAM panel's
// "source=depth" knobs. Values match the strategies actually wired up in
// TestModules/src/ai_engines/depth/strategies — see DebugScreen's model
// picker for how free text stays available alongside these.
export const KNOWN_DEPTH_MODELS = [
  "LiheYoung/depth-anything-small-hf",
  "LiheYoung/depth-anything-base-hf",
  "LiheYoung/depth-anything-large-hf",
  "depth-anything/Depth-Anything-V2-Small-hf",
  "depth-anything/Depth-Anything-V2-Base-hf",
];

export const DEPTH_STRATEGIES: { value: DepthStrategy; label: string }[] = [
  { value: "anything", label: "anything (single checkpoint)" },
  { value: "blended", label: "blended (near+far, production default input)" },
  { value: "enhanced_edge", label: "enhanced_edge (blended + CLAHE, true production default)" },
];

export const COLORMAPS: DepthColormap[] = ["none", "inferno", "magma", "turbo", "jet"];

export const NORMAL_HUB_MODELS: { value: NormalHubModel; label: string }[] = [
  { value: "metric3d_vit_small", label: "metric3d_vit_small (default)" },
  { value: "metric3d_vit_large", label: "metric3d_vit_large" },
  { value: "metric3d_vit_giant2", label: "metric3d_vit_giant2" },
];

/** One row of a validation check group: dot, name, score, message. */
export const CheckRow: React.FC<{ name: string; passed: boolean; score: number | null; message: string }> = ({
  name,
  passed,
  score,
  message,
}) => (
  <div className={`debug-check-row${passed ? "" : " is-failed"}`}>
    <span className="debug-check-dot" aria-hidden="true" />
    <span className="debug-check-name">{name}</span>
    <span className="debug-check-score">{score === null ? "—" : score.toFixed(3)}</span>
    <span className="debug-check-message">{message}</span>
  </div>
);

/** Fixed-position full-screen image viewer for a rendered debug PNG. */
export const DebugLightbox: React.FC<{ src: string; alt: string; onClose: () => void }> = ({
  src,
  alt,
  onClose,
}) => {
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  return (
    <div className="modal-backdrop debug-lightbox-backdrop" role="presentation" onClick={onClose}>
      <img src={src} alt={alt} className="debug-lightbox-img" onClick={(e) => e.stopPropagation()} />
      <button type="button" className="modal-close debug-lightbox-close" onClick={onClose}>
        Close
      </button>
    </div>
  );
};
