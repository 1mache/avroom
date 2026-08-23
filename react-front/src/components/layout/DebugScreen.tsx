import React, { useCallback, useEffect, useRef, useState } from "react";

import { debugAutoMaskPick, debugDepthMap, debugInpaintVerify, debugNormalMap, debugSamEverything, validateImageDebug } from "../../api/debug";
import { BackIcon } from "../icons";
import type {
  DebugAutoMaskPickResponse,
  DebugImageResult,
  DebugInpaintVerifyResponse,
  DebugValidationResponse,
  DepthColormap,
  DepthStrategy,
  NormalHubModel,
  SamSource,
} from "../../types/debug";
import { getContainedImageRect, toNaturalPoint } from "../../utils/stageGeometry";
import { Debug3DPanel } from "./debug/Debug3DPanel";
import { DebugDepthPanel } from "./debug/DebugDepthPanel";
import { DebugInpaintVerifyPanel } from "./debug/DebugInpaintVerifyPanel";
import { DebugLightbox, KNOWN_DEPTH_MODELS, errorMessage, type PanelState } from "./debug/shared";
import { DebugMaskPickPanel } from "./debug/DebugMaskPickPanel";
import { DebugNormalPanel, type NormalSample } from "./debug/DebugNormalPanel";
import { DebugSamPanel } from "./debug/DebugSamPanel";
import { DebugSourcePanel } from "./debug/DebugSourcePanel";
import { DebugValidationPanel } from "./debug/DebugValidationPanel";

export interface DebugScreenProps {
  onExit: () => void;
}

/**
 * Reachable from the dashboard header. Upload a photo, watch the full
 * validation scoreboard plus the depth-map and SAM segment-everything debug
 * endpoints run on it — regardless of whether validation passed — with every
 * knob exposed for comparing configurations. Nothing here creates a session
 * or writes to disk.
 *
 * Each section below is its own panel component (components/layout/debug/) —
 * this screen just owns the shared photo/click state, the per-panel result
 * state, and the run/orchestration callbacks (runAll chains three of them).
 */
export const DebugScreen: React.FC<DebugScreenProps> = ({ onExit }) => {
  const [file, setFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [lightboxSrc, setLightboxSrc] = useState<{ src: string; alt: string } | null>(null);
  const openLightbox = useCallback((src: string, alt: string) => setLightboxSrc({ src, alt }), []);

  const [validation, setValidation] = useState<PanelState<DebugValidationResponse>>({
    status: "idle",
  });
  const [depth, setDepth] = useState<PanelState<DebugImageResult>>({ status: "idle" });
  const [normals, setNormals] = useState<PanelState<DebugImageResult>>({ status: "idle" });
  const [sam, setSam] = useState<PanelState<DebugImageResult>>({ status: "idle" });
  const [maskPick, setMaskPick] = useState<PanelState<DebugAutoMaskPickResponse>>({ status: "idle" });
  const [inpaintVerify, setInpaintVerify] = useState<PanelState<DebugInpaintVerifyResponse>>({
    status: "idle",
  });
  const [clickPos, setClickPos] = useState<{ x: number; y: number } | null>(null);
  const [selectedMaskIndex, setSelectedMaskIndex] = useState<number | null>(null);
  const [normalSample, setNormalSample] = useState<NormalSample | null>(null);

  const [depthStrategy, setDepthStrategy] = useState<DepthStrategy>("anything");
  const [depthModel, setDepthModel] = useState(KNOWN_DEPTH_MODELS[0]);
  const [colormap, setColormap] = useState<DepthColormap>("none");
  const [normalHubModel, setNormalHubModel] = useState<NormalHubModel>("metric3d_vit_small");

  const [samSource, setSamSource] = useState<SamSource>("depth");
  const [samDepthStrategy, setSamDepthStrategy] = useState<DepthStrategy>("anything");
  const [samDepthModel, setSamDepthModel] = useState(KNOWN_DEPTH_MODELS[0]);
  const [pointsPerSide, setPointsPerSide] = useState(16);
  const [predIouThresh, setPredIouThresh] = useState(0.88);
  const [stabilityScoreThresh, setStabilityScoreThresh] = useState(0.95);
  const [minMaskRegionArea, setMinMaskRegionArea] = useState(0);
  const [alpha, setAlpha] = useState(0.45);

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
    setNormals({ status: "idle" });
    setNormalSample(null);
    setSam({ status: "idle" });
    setMaskPick({ status: "idle" });
    setInpaintVerify({ status: "idle" });
    setClickPos(null);
    setSelectedMaskIndex(null);
  }, []);

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

  const runNormals = useCallback(async () => {
    if (!file) return;
    const token = runTokenRef.current;
    setNormals({ status: "running" });
    setNormalSample(null);
    try {
      const data = await debugNormalMap(file, { hubModel: normalHubModel });
      if (runTokenRef.current !== token) {
        URL.revokeObjectURL(data.objectUrl);
        return;
      }
      heldUrlsRef.current.add(data.objectUrl);
      setNormals((prev) => {
        if (prev.status === "done") {
          URL.revokeObjectURL(prev.data.objectUrl);
          heldUrlsRef.current.delete(prev.data.objectUrl);
        }
        return { status: "done", data };
      });
    } catch (err) {
      if (runTokenRef.current === token) setNormals({ status: "error", message: errorMessage(err) });
    }
  }, [file, normalHubModel]);

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
          <DebugSourcePanel
            file={file}
            previewUrl={previewUrl}
            clickPos={clickPos}
            busy={busy}
            onFileAccepted={acceptFile}
            onPreviewClick={handlePreviewClick}
            onRunAll={() => void runAll()}
          />

          <DebugValidationPanel file={file} validation={validation} onRun={() => void runValidation()} />

          <DebugDepthPanel
            file={file}
            depth={depth}
            strategy={depthStrategy}
            onStrategyChange={setDepthStrategy}
            model={depthModel}
            onModelChange={setDepthModel}
            colormap={colormap}
            onColormapChange={setColormap}
            onRun={() => void runDepth()}
            onOpenLightbox={openLightbox}
          />

          <DebugNormalPanel
            file={file}
            normals={normals}
            normalSample={normalSample}
            onSample={setNormalSample}
            hubModel={normalHubModel}
            onHubModelChange={setNormalHubModel}
            onRun={() => void runNormals()}
            onOpenLightbox={openLightbox}
          />

          <DebugSamPanel
            file={file}
            sam={sam}
            source={samSource}
            onSourceChange={setSamSource}
            depthStrategy={samDepthStrategy}
            onDepthStrategyChange={setSamDepthStrategy}
            depthModel={samDepthModel}
            onDepthModelChange={setSamDepthModel}
            pointsPerSide={pointsPerSide}
            onPointsPerSideChange={setPointsPerSide}
            predIouThresh={predIouThresh}
            onPredIouThreshChange={setPredIouThresh}
            stabilityScoreThresh={stabilityScoreThresh}
            onStabilityScoreThreshChange={setStabilityScoreThresh}
            minMaskRegionArea={minMaskRegionArea}
            onMinMaskRegionAreaChange={setMinMaskRegionArea}
            alpha={alpha}
            onAlphaChange={setAlpha}
            onRun={() => void runSam()}
            onOpenLightbox={openLightbox}
          />

          <DebugMaskPickPanel
            file={file}
            clickPos={clickPos}
            maskPick={maskPick}
            selectedMaskIndex={selectedMaskIndex}
            onSelectMaskIndex={setSelectedMaskIndex}
            onRun={() => void runMaskPick()}
            onOpenLightbox={openLightbox}
          />

          <DebugInpaintVerifyPanel
            file={file}
            clickPos={clickPos}
            inpaintVerify={inpaintVerify}
            onRun={() => void runInpaintVerify()}
            onOpenLightbox={openLightbox}
          />

          <Debug3DPanel onOpenLightbox={openLightbox} />
        </div>
      </main>

      {lightboxSrc ? (
        <DebugLightbox src={lightboxSrc.src} alt={lightboxSrc.alt} onClose={() => setLightboxSrc(null)} />
      ) : null}
    </div>
  );
};
