import React, { useCallback, useEffect, useRef, useState } from "react";

import {
  CAMERA_FOV,
  KEY_LIGHT_INTENSITY,
  MATERIAL_ROUGHNESS,
  MAX_MATERIAL_METALNESS,
  Model3DFrame,
  type Model3DFrameHandle,
} from "../../widgets/Model3DFrame";

// Bundled fallback model for the 3D panel — copied from the same file the
// backend's own /3d/test-3d debug shortcut points at (fastApi-app/api/model_3d.py),
// just as an .obj instead of a .glb so both loader paths get exercised.
const DEFAULT_MODEL_URL = "/debug-models/debug_toilet.obj";
const DEFAULT_MODEL_FORMAT: ModelFormat = "obj";

type ModelFormat = "glb" | "obj";

type Render3DState = { status: "idle" } | { status: "done"; dataUrl: string } | { status: "error"; message: string };

export interface Debug3DPanelProps {
  onOpenLightbox: (src: string, alt: string) => void;
}

/**
 * Independent of the photo dropzone/Run all above — its own model (default
 * or uploaded) and its own live viewer. Nothing outside this panel observes
 * its state, so it owns all of it.
 */
export const Debug3DPanel: React.FC<Debug3DPanelProps> = ({ onOpenLightbox }) => {
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

  return (
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

      {render3D.status === "error" ? <p className="debug-panel-error">{render3D.message}</p> : null}

      {render3D.status === "done" ? (
        <button
          type="button"
          className="debug-image-frame"
          onClick={() => onOpenLightbox(render3D.dataUrl, "3D viewer render")}
        >
          <img src={render3D.dataUrl} alt="3D viewer render" />
        </button>
      ) : (
        <p className="debug-panel-hint">
          Orbit with the mouse, then Render image to capture exactly what's on screen — the same canvas snapshot the
          production rotation flow captures before synthesis.
        </p>
      )}
    </section>
  );
};
