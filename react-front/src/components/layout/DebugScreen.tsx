import React, { useCallback, useEffect, useRef, useState } from "react";

import { debugAutoMaskPick, debugDepthMap, debugInpaintVerify, debugSamEverything, validateImageDebug } from "../../api/debug";
import { ApiError } from "../../api/images";
import { BackIcon, PhotoIcon } from "../icons";
import {
  CAMERA_FOV,
  KEY_LIGHT_INTENSITY,
  MATERIAL_ROUGHNESS,
  MAX_MATERIAL_METALNESS,
  Model3DFrame,
  type Model3DFrameHandle,
} from "../widgets/Model3DFrame";
import type {
  DebugAutoMaskPickResponse,
  DebugImageResult,
  DebugInpaintVerifyResponse,
  DebugValidationResponse,
  DepthColormap,
  DepthStrategy,
  SamSource,
} from "../../types/debug";
import { getContainedImageRect, toNaturalPoint } from "../../utils/stageGeometry";

// Bundled fallback model for the 3D panel — copied from the same file the
// backend's own /3d/test-3d debug shortcut points at (fastApi-app/api/model_3d.py),
// just as an .obj instead of a .glb so both loader paths get exercised.
const DEFAULT_MODEL_URL = "/debug-models/debug_toilet.obj";
const DEFAULT_MODEL_FORMAT: ModelFormat = "obj";

type ModelFormat = "glb" | "obj";

type Render3DState =
  | { status: "idle" }
  | { status: "done"; dataUrl: string }
  | { status: "error"; message: string };

export interface DebugScreenProps {
  onExit: () => void;
}

// One HF checkpoint dropdown shared by the depth panel and the SAM panel's
// "source=depth" knobs. Values match the strategies actually wired up in
// TestModules/src/ai_engines/depth/strategies — see DebugScreen's model
// picker for how free text stays available alongside these.
const KNOWN_DEPTH_MODELS = [
  "LiheYoung/depth-anything-small-hf",
  "LiheYoung/depth-anything-base-hf",
  "LiheYoung/depth-anything-large-hf",
  "depth-anything/Depth-Anything-V2-Small-hf",
  "depth-anything/Depth-Anything-V2-Base-hf",
];

const DEPTH_STRATEGIES: { value: DepthStrategy; label: string }[] = [
  { value: "anything", label: "anything (single checkpoint)" },
  { value: "blended", label: "blended (near+far, production default input)" },
  { value: "enhanced_edge", label: "enhanced_edge (blended + CLAHE, true production default)" },
];

const COLORMAPS: DepthColormap[] = ["none", "inferno", "magma", "turbo", "jet"];

type PanelState<T> =
  | { status: "idle" }
  | { status: "running" }
  | { status: "done"; data: T }
  | { status: "error"; message: string };

function errorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 404) {
      return "Debug endpoints are disabled on the server (DEBUG_ENDPOINTS=false).";
    }
    return err.detail || err.message;
  }
  return err instanceof Error ? err.message : "Request failed.";
}

const formatMs = (ms: number | null): string => (ms === null ? "—" : `${ms.toFixed(0)} ms`);

const pngSrc = (b64: string): string => `data:image/png;base64,${b64}`;

/** One row of a validation check group: dot, name, score, message. */
const CheckRow: React.FC<{ name: string; passed: boolean; score: number | null; message: string }> = ({
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
const DebugLightbox: React.FC<{ src: string; alt: string; onClose: () => void }> = ({
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

/**
 * Reachable from the dashboard header. Upload a photo, watch the full
 * validation scoreboard plus the depth-map and SAM segment-everything debug
 * endpoints run on it — regardless of whether validation passed — with every
 * knob exposed for comparing configurations. Nothing here creates a session
 * or writes to disk.
 */
export const DebugScreen: React.FC<DebugScreenProps> = ({ onExit }) => {
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [isDragOver, setIsDragOver] = useState(false);
  const [lightboxSrc, setLightboxSrc] = useState<{ src: string; alt: string } | null>(null);

  const [validation, setValidation] = useState<PanelState<DebugValidationResponse>>({
    status: "idle",
  });
  const [depth, setDepth] = useState<PanelState<DebugImageResult>>({ status: "idle" });
  const [sam, setSam] = useState<PanelState<DebugImageResult>>({ status: "idle" });
  const [maskPick, setMaskPick] = useState<PanelState<DebugAutoMaskPickResponse>>({ status: "idle" });
  const [inpaintVerify, setInpaintVerify] = useState<PanelState<DebugInpaintVerifyResponse>>({
    status: "idle",
  });
  const [clickPos, setClickPos] = useState<{ x: number; y: number } | null>(null);
  const [selectedMaskIndex, setSelectedMaskIndex] = useState<number | null>(null);
  const previewImgRef = useRef<HTMLImageElement>(null);

  const [depthStrategy, setDepthStrategy] = useState<DepthStrategy>("anything");
  const [depthModel, setDepthModel] = useState(KNOWN_DEPTH_MODELS[0]);
  const [colormap, setColormap] = useState<DepthColormap>("none");

  const [samSource, setSamSource] = useState<SamSource>("depth");
  const [samDepthStrategy, setSamDepthStrategy] = useState<DepthStrategy>("anything");
  const [samDepthModel, setSamDepthModel] = useState(KNOWN_DEPTH_MODELS[0]);
  const [pointsPerSide, setPointsPerSide] = useState(16);
  const [predIouThresh, setPredIouThresh] = useState(0.88);
  const [stabilityScoreThresh, setStabilityScoreThresh] = useState(0.95);
  const [minMaskRegionArea, setMinMaskRegionArea] = useState(0);
  const [alpha, setAlpha] = useState(0.45);

  // ── 3D panel — independent of the photo dropzone/Run all above; has its
  // own model (default or uploaded) and its own live viewer. ──────────────
  const model3DFrameRef = useRef<Model3DFrameHandle>(null);
  const model3DInputRef = useRef<HTMLInputElement>(null);
  const [modelBuffer, setModelBuffer] = useState<ArrayBuffer | null>(null);
  const [modelFormat, setModelFormat] = useState<ModelFormat>(DEFAULT_MODEL_FORMAT);
  const [modelName, setModelName] = useState("debug_toilet.obj (default)");
  const [modelLoadError, setModelLoadError] = useState<string | null>(null);
  // Defaults mirror Model3DFrame's own defaults exactly (imported, not
  // re-typed) so the panel's first render matches what actually loads.
  const [roughness3D, setRoughness3D] = useState(MATERIAL_ROUGHNESS);
  const [metalness3D, setMetalness3D] = useState(MAX_MATERIAL_METALNESS);
  const [keyLightIntensity3D, setKeyLightIntensity3D] = useState(KEY_LIGHT_INTENSITY);
  const [cameraFov3D, setCameraFov3D] = useState(CAMERA_FOV);
  const [render3D, setRender3D] = useState<Render3DState>({ status: "idle" });

  const loadDefaultModel = useCallback(() => {
    setModelLoadError(null);
    fetch(DEFAULT_MODEL_URL)
      .then((response) => {
        if (!response.ok) {
          throw new Error(`Failed to fetch default model (${response.status}).`);
        }
        return response.arrayBuffer();
      })
      .then((buffer) => {
        setModelBuffer(buffer);
        setModelFormat(DEFAULT_MODEL_FORMAT);
        setModelName("debug_toilet.obj (default)");
      })
      .catch((err: unknown) => {
        setModelLoadError(err instanceof Error ? err.message : "Failed to load default model.");
      });
  }, []);

  useEffect(() => {
    loadDefaultModel();
    // Only on mount — re-loading the default is an explicit "Reset" click.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleModelFileChange: React.ChangeEventHandler<HTMLInputElement> = useCallback((event) => {
    const picked = event.target.files?.[0];
    event.target.value = "";
    if (!picked) {
      return;
    }
    const lowerName = picked.name.toLowerCase();
    const format: ModelFormat = lowerName.endsWith(".obj") ? "obj" : "glb";
    setModelLoadError(null);
    const reader = new FileReader();
    reader.onload = () => {
      if (reader.result instanceof ArrayBuffer) {
        setModelBuffer(reader.result);
        setModelFormat(format);
        setModelName(picked.name);
      }
    };
    reader.onerror = () => setModelLoadError("Failed to read the chosen file.");
    reader.readAsArrayBuffer(picked);
  }, []);

  const renderModel3D = useCallback(() => {
    const capture = model3DFrameRef.current?.capture();
    if (!capture) {
      setRender3D({ status: "error", message: "Nothing to render yet — the model hasn't loaded." });
      return;
    }
    setRender3D({ status: "done", dataUrl: capture.snapshotDataUrl });
  }, []);

  // Bumped on every new file pick; each async run checks its own captured
  // token before committing state, so a slow response for a discarded photo
  // can never overwrite a fresher run's result.
  const runTokenRef = useRef(0);
  // Every blob object URL this screen has ever handed out, so unmount can
  // revoke them all regardless of which panel produced them. Mirrors
  // previewUrl too (via a ref, since the unmount effect's closure would
  // otherwise only ever see the value from the initial render).
  const heldUrlsRef = useRef<Set<string>>(new Set());
  const previewUrlRef = useRef<string | null>(null);
  previewUrlRef.current = previewUrl;

  useEffect(() => {
    const heldUrls = heldUrlsRef.current;
    return () => {
      if (previewUrlRef.current) {
        URL.revokeObjectURL(previewUrlRef.current);
      }
      heldUrls.forEach((url) => URL.revokeObjectURL(url));
    };
  }, []);

  const acceptFile = useCallback((next: File) => {
    runTokenRef.current += 1;
    setFile(next);
    setPreviewUrl((prev) => {
      if (prev) {
        URL.revokeObjectURL(prev);
      }
      return URL.createObjectURL(next);
    });
    setValidation({ status: "idle" });
    setDepth({ status: "idle" });
    setSam({ status: "idle" });
    setMaskPick({ status: "idle" });
    setInpaintVerify({ status: "idle" });
    setClickPos(null);
    setSelectedMaskIndex(null);
  }, []);

  const handleInputChange: React.ChangeEventHandler<HTMLInputElement> = useCallback(
    (event) => {
      const picked = event.target.files?.[0];
      if (picked) {
        acceptFile(picked);
      }
      event.target.value = "";
    },
    [acceptFile],
  );

  const handleDrop: React.DragEventHandler<HTMLDivElement> = useCallback(
    (event) => {
      event.preventDefault();
      setIsDragOver(false);
      const dropped = event.dataTransfer.files?.[0];
      if (dropped) {
        acceptFile(dropped);
      }
    },
    [acceptFile],
  );

  const runValidation = useCallback(async () => {
    if (!file) return;
    const token = runTokenRef.current;
    setValidation({ status: "running" });
    try {
      const data = await validateImageDebug(file);
      if (runTokenRef.current === token) setValidation({ status: "done", data });
    } catch (err) {
      if (runTokenRef.current === token) setValidation({ status: "error", message: errorMessage(err) });
    }
  }, [file]);

  const runDepth = useCallback(async () => {
    if (!file) return;
    const token = runTokenRef.current;
    setDepth({ status: "running" });
    try {
      const data = await debugDepthMap(file, { strategy: depthStrategy, model: depthModel, colormap });
      if (runTokenRef.current !== token) {
        URL.revokeObjectURL(data.objectUrl);
        return;
      }
      heldUrlsRef.current.add(data.objectUrl);
      setDepth((prev) => {
        if (prev.status === "done") {
          URL.revokeObjectURL(prev.data.objectUrl);
          heldUrlsRef.current.delete(prev.data.objectUrl);
        }
        return { status: "done", data };
      });
    } catch (err) {
      if (runTokenRef.current === token) setDepth({ status: "error", message: errorMessage(err) });
    }
  }, [file, depthStrategy, depthModel, colormap]);

  const runSam = useCallback(async () => {
    if (!file) return;
    const token = runTokenRef.current;
    setSam({ status: "running" });
    try {
      const data = await debugSamEverything(file, {
        source: samSource,
        depthStrategy: samDepthStrategy,
        depthModel: samDepthModel,
        pointsPerSide,
        predIouThresh,
        stabilityScoreThresh,
        minMaskRegionArea,
        alpha,
      });
      if (runTokenRef.current !== token) {
        URL.revokeObjectURL(data.objectUrl);
        return;
      }
      heldUrlsRef.current.add(data.objectUrl);
      setSam((prev) => {
        if (prev.status === "done") {
          URL.revokeObjectURL(prev.data.objectUrl);
          heldUrlsRef.current.delete(prev.data.objectUrl);
        }
        return { status: "done", data };
      });
    } catch (err) {
      if (runTokenRef.current === token) setSam({ status: "error", message: errorMessage(err) });
    }
  }, [
    file,
    samSource,
    samDepthStrategy,
    samDepthModel,
    pointsPerSide,
    predIouThresh,
    stabilityScoreThresh,
    minMaskRegionArea,
    alpha,
  ]);

  const handlePreviewClick: React.MouseEventHandler<HTMLImageElement> = useCallback((event) => {
    const img = event.currentTarget;
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
    setClickPos({ x: Math.round(point.x), y: Math.round(point.y) });
  }, []);

  const runMaskPick = useCallback(async () => {
    if (!file || !clickPos) return;
    const token = runTokenRef.current;
    setMaskPick({ status: "running" });
    try {
      const data = await debugAutoMaskPick(file, clickPos.x, clickPos.y);
      if (runTokenRef.current !== token) return;
      setMaskPick({ status: "done", data });
      setSelectedMaskIndex(data.winner_index);
    } catch (err) {
      if (runTokenRef.current === token) setMaskPick({ status: "error", message: errorMessage(err) });
    }
  }, [file, clickPos]);

  const runInpaintVerify = useCallback(async () => {
    if (!file || !clickPos) return;
    const token = runTokenRef.current;
    setInpaintVerify({ status: "running" });
    try {
      const data = await debugInpaintVerify(file, clickPos.x, clickPos.y, selectedMaskIndex);
      if (runTokenRef.current !== token) return;
      setInpaintVerify({ status: "done", data });
    } catch (err) {
      if (runTokenRef.current === token) {
        setInpaintVerify({ status: "error", message: errorMessage(err) });
      }
    }
  }, [file, clickPos, selectedMaskIndex]);

  // Sequential on purpose: SAM shares the process-wide GPU lock with
  // everything else in inline mode, so firing all three at once would just
  // queue behind each other anyway. Each stage runs regardless of whether
  // the previous one failed — that's the whole point of the screen.
  const runAll = useCallback(async () => {
    await runValidation();
    await runDepth();
    await runSam();
  }, [runValidation, runDepth, runSam]);

  const busy =
    validation.status === "running" ||
    depth.status === "running" ||
    sam.status === "running" ||
    maskPick.status === "running" ||
    inpaintVerify.status === "running";

  return (
    <div className="dashboard">
      <header className="dash-header">
        <button
          type="button"
          className="tool-btn"
          onClick={onExit}
          aria-label="Back to dashboard"
          data-tip="Back to dashboard"
        >
          <BackIcon />
        </button>
        <span className="dash-wordmark">Pipeline debug</span>
      </header>

      <main className="dash-main">
        <div className="session-scroll debug-scroll">
          <div className="debug-source">
            <input
              ref={inputRef}
              type="file"
              accept="image/jpeg,image/png,image/webp"
              className="file-input"
              onChange={handleInputChange}
              aria-label="Choose an image"
            />
            <div
              className={`dropzone debug-dropzone${isDragOver ? " is-over" : ""}${file ? " has-file" : ""}`}
              onDragOver={(event) => {
                event.preventDefault();
                setIsDragOver(true);
              }}
              onDragLeave={() => setIsDragOver(false)}
              onDrop={handleDrop}
            >
              {previewUrl && file ? (
                <>
                  <div className="debug-click-frame">
                    <img
                      ref={previewImgRef}
                      src={previewUrl}
                      alt=""
                      className="dropzone-preview"
                      onClick={handlePreviewClick}
                    />
                    {clickPos && previewImgRef.current ? (
                      <span
                        className="debug-click-marker"
                        style={(() => {
                          const img = previewImgRef.current;
                          const natural = { width: img.naturalWidth, height: img.naturalHeight };
                          const rendered = getContainedImageRect(
                            { width: img.clientWidth, height: img.clientHeight },
                            natural,
                          );
                          if (!rendered || natural.width <= 0 || natural.height <= 0) {
                            return undefined;
                          }
                          return {
                            left: rendered.x + (clickPos.x / natural.width) * rendered.width,
                            top: rendered.y + (clickPos.y / natural.height) * rendered.height,
                          };
                        })()}
                      />
                    ) : null}
                  </div>
                  <div className="dropzone-file">
                    <span className="dropzone-filename">{file.name}</span>
                  </div>
                  <p className="debug-click-readout">
                    {clickPos
                      ? `Click ${clickPos.x}, ${clickPos.y} — used by auto mask pick and inpaint verify`
                      : "Click the photo to set a seed point"}
                  </p>
                </>
              ) : (
                <button
                  type="button"
                  className="dropzone-invite"
                  onClick={() => inputRef.current?.click()}
                >
                  <PhotoIcon size={28} />
                  <span className="dropzone-invite-line">Drop any image here</span>
                  <span className="dropzone-invite-hint">
                    or choose a file — no client-side checks, the point is watching the server decide
                  </span>
                </button>
              )}
            </div>

            <div className="debug-source-actions">
              <button type="button" className="btn" onClick={() => inputRef.current?.click()}>
                {file ? "Choose another" : "Choose a file"}
              </button>
              <button
                type="button"
                className="btn is-primary"
                onClick={() => void runAll()}
                disabled={!file || busy}
              >
                {busy ? <span className="tool-spinner" /> : "Run all"}
              </button>
            </div>
          </div>

          {/* ── Validation panel ─────────────────────────────────────────── */}
          <section className="debug-panel">
            <header className="debug-panel-head">
              <h3 className="debug-panel-title">Validation</h3>
              {validation.status === "done" ? (
                <span className={`debug-verdict${validation.data.ok ? " is-pass" : " is-fail"}`}>
                  {validation.data.ok ? "PASS" : "FAIL"}
                </span>
              ) : null}
              <button
                type="button"
                className="btn"
                onClick={() => void runValidation()}
                disabled={!file || validation.status === "running"}
              >
                {validation.status === "running" ? <span className="tool-spinner" /> : "Re-run"}
              </button>
            </header>

            {validation.status === "error" ? (
              <p className="debug-panel-error">{validation.message}</p>
            ) : null}

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

          {/* ── Depth map panel ──────────────────────────────────────────── */}
          <section className="debug-panel">
            <header className="debug-panel-head">
              <h3 className="debug-panel-title">Depth map</h3>
              <button
                type="button"
                className="btn"
                onClick={() => void runDepth()}
                disabled={!file || depth.status === "running"}
              >
                {depth.status === "running" ? <span className="tool-spinner" /> : "Re-run"}
              </button>
            </header>

            <div className="debug-knobs">
              <label className="debug-knob">
                <span>Strategy</span>
                <select
                  value={depthStrategy}
                  onChange={(e) => setDepthStrategy(e.target.value as DepthStrategy)}
                >
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
                  value={depthModel}
                  onChange={(e) => setDepthModel(e.target.value)}
                  disabled={depthStrategy !== "anything"}
                />
              </label>
              <label className="debug-knob">
                <span>Colormap</span>
                <select value={colormap} onChange={(e) => setColormap(e.target.value as DepthColormap)}>
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
                  onClick={() =>
                    setLightboxSrc({ src: depth.data.objectUrl, alt: "Depth map render" })
                  }
                >
                  <img src={depth.data.objectUrl} alt="Depth map render" />
                </button>
                <p className="debug-panel-elapsed">{formatMs(depth.data.elapsedMs)}</p>
              </>
            ) : depth.status === "idle" ? (
              <p className="debug-panel-hint">Renders whatever Depth-Anything sees, as an image.</p>
            ) : null}
          </section>

          {/* ── SAM segment-everything panel ─────────────────────────────── */}
          <section className="debug-panel">
            <header className="debug-panel-head">
              <h3 className="debug-panel-title">SAM segment-everything</h3>
              <button
                type="button"
                className="btn"
                onClick={() => void runSam()}
                disabled={!file || sam.status === "running"}
              >
                {sam.status === "running" ? <span className="tool-spinner" /> : "Re-run"}
              </button>
            </header>

            <div className="debug-knobs">
              <label className="debug-knob">
                <span>Source</span>
                <select value={samSource} onChange={(e) => setSamSource(e.target.value as SamSource)}>
                  <option value="depth">depth (production rule)</option>
                  <option value="rgb">rgb (raw photo)</option>
                </select>
              </label>
              <label className="debug-knob">
                <span>Depth strategy (source=depth only)</span>
                <select
                  value={samDepthStrategy}
                  onChange={(e) => setSamDepthStrategy(e.target.value as DepthStrategy)}
                  disabled={samSource !== "depth"}
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
                  value={samDepthModel}
                  onChange={(e) => setSamDepthModel(e.target.value)}
                  disabled={samSource !== "depth" || samDepthStrategy !== "anything"}
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
                  onChange={(e) => setPointsPerSide(Number(e.target.value))}
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
                  onChange={(e) => setPredIouThresh(Number(e.target.value))}
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
                  onChange={(e) => setStabilityScoreThresh(Number(e.target.value))}
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
                  onChange={(e) => setMinMaskRegionArea(Number(e.target.value))}
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
                  onChange={(e) => setAlpha(Number(e.target.value))}
                />
              </label>
            </div>

            {sam.status === "error" ? <p className="debug-panel-error">{sam.message}</p> : null}

            {sam.status === "done" ? (
              <>
                <button
                  type="button"
                  className="debug-image-frame"
                  onClick={() =>
                    setLightboxSrc({ src: sam.data.objectUrl, alt: "SAM segment-everything render" })
                  }
                >
                  <img src={sam.data.objectUrl} alt="SAM segment-everything render" />
                </button>
                <p className="debug-panel-elapsed">
                  {sam.data.maskCount === null ? "" : `${sam.data.maskCount} masks · `}
                  {formatMs(sam.data.elapsedMs)}
                </p>
              </>
            ) : sam.status === "idle" ? (
              <p className="debug-panel-hint">
                Can take seconds to minutes — points_per_side² SAM forward passes.
              </p>
            ) : null}
          </section>

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
                onClick={() => void runMaskPick()}
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
                <div className="debug-candidate-grid">
                  {maskPick.data.candidates.map((candidate) => {
                    const isWinner = candidate.index === maskPick.data.winner_index;
                    const isSelected = candidate.index === selectedMaskIndex;
                    return (
                      <button
                        key={candidate.index}
                        type="button"
                        className={`debug-candidate-card${isWinner ? " is-winner" : ""}${isSelected ? " is-selected" : ""}`}
                        onClick={() => setSelectedMaskIndex(candidate.index)}
                      >
                        <img
                          src={pngSrc(candidate.preview_b64)}
                          alt={`Candidate ${candidate.index}`}
                          onClick={(event) => {
                            event.stopPropagation();
                            setLightboxSrc({
                              src: pngSrc(candidate.preview_b64),
                              alt: `Candidate ${candidate.index}`,
                            });
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
                              setLightboxSrc({
                                src: pngSrc(candidate.clip_crop_b64 as string),
                                alt: `CLIP crop ${candidate.index}`,
                              });
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

          <section className="debug-panel">
            <header className="debug-panel-head">
              <h3 className="debug-panel-title">Inpaint verification</h3>
              {inpaintVerify.status === "done" ? (
                <span className={`debug-verdict${inpaintVerify.data.passed ? " is-pass" : " is-fail"}`}>
                  {inpaintVerify.data.passed ? "PASS" : "RETRIES EXHAUSTED"}
                </span>
              ) : null}
              <button
                type="button"
                className="btn"
                onClick={() => void runInpaintVerify()}
                disabled={!file || !clickPos || inpaintVerify.status === "running"}
              >
                {inpaintVerify.status === "running" ? <span className="tool-spinner" /> : "Re-run"}
              </button>
            </header>
            {inpaintVerify.status === "error" ? (
              <p className="debug-panel-error">{inpaintVerify.message}</p>
            ) : null}
            {inpaintVerify.status === "done" ? (
              <>
                <p className="debug-panel-hint">
                  Mask {inpaintVerify.data.mask_index}. LaMa once, then each CLIP retry with SD params in and verifier JSON out.
                </p>
                {inpaintVerify.data.lama_b64 ? (
                  <img
                    className="debug-trace-image"
                    src={pngSrc(inpaintVerify.data.lama_b64)}
                    alt="LaMa output"
                    onClick={() =>
                      setLightboxSrc({ src: pngSrc(inpaintVerify.data.lama_b64 as string), alt: "LaMa output" })
                    }
                  />
                ) : null}
                {inpaintVerify.data.attempts.map((attempt) => (
                  <div key={attempt.attempt_index} className="debug-attempt">
                    <div className="debug-candidate-meta">
                      <span>Attempt {attempt.attempt_index}</span>
                      <span>{attempt.ok ? "ok" : "fail"}{attempt.sd_skipped ? " · SD skipped" : ""}</span>
                    </div>
                    <div className="debug-attempt-images">
                      <img
                        src={pngSrc(attempt.candidate_b64)}
                        alt={`Candidate attempt ${attempt.attempt_index}`}
                        onClick={() =>
                          setLightboxSrc({
                            src: pngSrc(attempt.candidate_b64),
                            alt: `Candidate attempt ${attempt.attempt_index}`,
                          })
                        }
                      />
                      <img
                        src={pngSrc(attempt.clip_crop_b64)}
                        alt={`CLIP crop attempt ${attempt.attempt_index}`}
                        onClick={() =>
                          setLightboxSrc({
                            src: pngSrc(attempt.clip_crop_b64),
                            alt: `CLIP crop attempt ${attempt.attempt_index}`,
                          })
                        }
                      />
                    </div>
                    <p className="debug-kv">
                      winner {attempt.winner_label || "—"}
                      {"\n"}
                      {Object.entries(attempt.scores)
                        .map(([label, score]) => `${label}: ${score.toFixed(3)}`)
                        .join("\n") || "(no CLIP scores)"}
                    </p>
                    <p className="debug-kv">
                      SD in: strength={attempt.params.strength} steps={attempt.params.num_inference_steps}{" "}
                      guidance={attempt.params.guidance_scale}
                      {"\n"}prompt: {attempt.params.prompt}
                      {"\n"}negative: {attempt.params.negative_prompt}
                    </p>
                    <p className="debug-kv">verifier JSON: {attempt.param_fixes_json}</p>
                  </div>
                ))}
                <img
                  className="debug-trace-image"
                  src={pngSrc(inpaintVerify.data.final_b64)}
                  alt="Final inpaint"
                  onClick={() =>
                    setLightboxSrc({ src: pngSrc(inpaintVerify.data.final_b64), alt: "Final inpaint" })
                  }
                />
                <p className="debug-panel-elapsed">{formatMs(inpaintVerify.data.elapsed_ms)}</p>
              </>
            ) : (
              <p className="debug-panel-hint">
                Uses the selected mask (winner after auto pick, or an explicit card). Minutes on a cold GPU.
              </p>
            )}
          </section>

          {/* ── 3D viewer panel ───────────────────────────────────────────── */}
          <section className="debug-panel">
            <header className="debug-panel-head">
              <h3 className="debug-panel-title">3D viewer</h3>
              <button type="button" className="btn" onClick={loadDefaultModel}>
                Reset to default
              </button>
              <button type="button" className="btn is-primary" onClick={renderModel3D} disabled={!modelBuffer}>
                Render image
              </button>
            </header>

            <input
              ref={model3DInputRef}
              type="file"
              accept=".obj,.glb,.gltf"
              className="file-input"
              onChange={handleModelFileChange}
              aria-label="Choose a 3D model file"
            />

            <div className="debug-knobs">
              <label className="debug-knob">
                <span>Model</span>
                <button type="button" className="btn" onClick={() => model3DInputRef.current?.click()}>
                  {modelName}
                </button>
              </label>
              <label className="debug-knob">
                <span>Roughness ({roughness3D.toFixed(2)})</span>
                <input
                  type="range"
                  min={0}
                  max={1}
                  step={0.01}
                  value={roughness3D}
                  onChange={(e) => setRoughness3D(Number(e.target.value))}
                />
              </label>
              <label className="debug-knob">
                <span>Metalness ({metalness3D.toFixed(2)})</span>
                <input
                  type="range"
                  min={0}
                  max={1}
                  step={0.01}
                  value={metalness3D}
                  onChange={(e) => setMetalness3D(Number(e.target.value))}
                />
              </label>
              <label className="debug-knob">
                <span>Key light intensity ({keyLightIntensity3D.toFixed(1)})</span>
                <input
                  type="range"
                  min={0}
                  max={6}
                  step={0.1}
                  value={keyLightIntensity3D}
                  onChange={(e) => setKeyLightIntensity3D(Number(e.target.value))}
                />
              </label>
              <label className="debug-knob">
                <span>Camera FOV ({cameraFov3D}°)</span>
                <input
                  type="range"
                  min={15}
                  max={90}
                  step={1}
                  value={cameraFov3D}
                  onChange={(e) => setCameraFov3D(Number(e.target.value))}
                />
              </label>
            </div>

            {modelLoadError ? <p className="debug-panel-error">{modelLoadError}</p> : null}

            <div className="debug-model-viewport">
              {modelBuffer ? (
                <Model3DFrame
                  ref={model3DFrameRef}
                  glbData={modelBuffer}
                  format={modelFormat}
                  roughness={roughness3D}
                  metalness={metalness3D}
                  keyLightIntensity={keyLightIntensity3D}
                  cameraFov={cameraFov3D}
                />
              ) : (
                <p className="debug-panel-hint">Loading model…</p>
              )}
            </div>

            {render3D.status === "error" ? (
              <p className="debug-panel-error">{render3D.message}</p>
            ) : null}

            {render3D.status === "done" ? (
              <button
                type="button"
                className="debug-image-frame"
                onClick={() => setLightboxSrc({ src: render3D.dataUrl, alt: "3D viewer render" })}
              >
                <img src={render3D.dataUrl} alt="3D viewer render" />
              </button>
            ) : (
              <p className="debug-panel-hint">
                Orbit with the mouse, then Render image to capture exactly what's on screen — the same
                canvas snapshot the production rotation flow captures before synthesis.
              </p>
            )}
          </section>
        </div>
      </main>

      <datalist id="debug-depth-models">
        {KNOWN_DEPTH_MODELS.map((m) => (
          <option key={m} value={m} />
        ))}
      </datalist>

      {lightboxSrc ? (
        <DebugLightbox
          src={lightboxSrc.src}
          alt={lightboxSrc.alt}
          onClose={() => setLightboxSrc(null)}
        />
      ) : null}
    </div>
  );
};
