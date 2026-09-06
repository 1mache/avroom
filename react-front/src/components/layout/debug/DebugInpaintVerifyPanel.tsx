import React from "react";

import type { DebugInpaintVerifyResponse } from "../../../types/debug";
import { formatMs, pngSrc, type PanelState } from "./shared";

export interface DebugInpaintVerifyPanelProps {
  file: File | null;
  seedCount: number;
  inpaintVerify: PanelState<DebugInpaintVerifyResponse>;
  onRun: () => void;
  onOpenLightbox: (src: string, alt: string) => void;
}

export const DebugInpaintVerifyPanel: React.FC<DebugInpaintVerifyPanelProps> = ({
  file,
  seedCount,
  inpaintVerify,
  onRun,
  onOpenLightbox,
}) => (
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
        onClick={onRun}
        disabled={!file || seedCount < 1 || inpaintVerify.status === "running"}
      >
        {inpaintVerify.status === "running" ? <span className="tool-spinner" /> : "Re-run"}
      </button>
    </header>
    {inpaintVerify.status === "error" ? <p className="debug-panel-error">{inpaintVerify.message}</p> : null}
    {inpaintVerify.status === "done" ? (
      <>
        <p className="debug-panel-hint">
          Mask {inpaintVerify.data.mask_index}. LaMa once, then each verify retry with SD params in and verifier
          JSON out.
        </p>
        <p className="debug-panel-hint">Chosen mask #{inpaintVerify.data.mask_index}</p>
        <div className="debug-attempt-images">
          <img
            src={pngSrc(inpaintVerify.data.preview_b64)}
            alt={`Chosen mask preview ${inpaintVerify.data.mask_index}`}
            title="Preview with click marker"
            onClick={() =>
              onOpenLightbox(
                pngSrc(inpaintVerify.data.preview_b64),
                `Chosen mask preview ${inpaintVerify.data.mask_index}`,
              )
            }
          />
          <img
            src={pngSrc(inpaintVerify.data.cutout_b64)}
            alt={`Chosen cutout ${inpaintVerify.data.mask_index}`}
            title="Cutout alpha"
            onClick={() =>
              onOpenLightbox(pngSrc(inpaintVerify.data.cutout_b64), `Chosen cutout ${inpaintVerify.data.mask_index}`)
            }
          />
        </div>
        {inpaintVerify.data.lama_b64 ? (
          <img
            className="debug-trace-image"
            src={pngSrc(inpaintVerify.data.lama_b64)}
            alt="LaMa output"
            onClick={() => onOpenLightbox(pngSrc(inpaintVerify.data.lama_b64 as string), "LaMa output")}
          />
        ) : null}
        {inpaintVerify.data.attempts.map((attempt) => (
          <div key={attempt.attempt_index} className="debug-attempt">
            <div className="debug-candidate-meta">
              <span>Attempt {attempt.attempt_index}</span>
              <span>
                {attempt.ok ? "ok" : "fail"}
                {attempt.sd_skipped ? " · SD skipped" : ""}
              </span>
            </div>
            <div className="debug-attempt-images">
              <img
                src={pngSrc(attempt.candidate_b64)}
                alt={`Candidate attempt ${attempt.attempt_index}`}
                onClick={() =>
                  onOpenLightbox(pngSrc(attempt.candidate_b64), `Candidate attempt ${attempt.attempt_index}`)
                }
              />
              {attempt.verify_original_crop_b64 ? (
                <img
                  src={pngSrc(attempt.verify_original_crop_b64)}
                  alt={`Original crop attempt ${attempt.attempt_index}`}
                  title="Gemini in: original"
                  onClick={() =>
                    onOpenLightbox(
                      pngSrc(attempt.verify_original_crop_b64 as string),
                      `Original crop attempt ${attempt.attempt_index}`,
                    )
                  }
                />
              ) : null}
              <img
                src={pngSrc(attempt.clip_crop_b64)}
                alt={`Outlined candidate crop attempt ${attempt.attempt_index}`}
                title="Gemini in: outlined candidate"
                onClick={() =>
                  onOpenLightbox(
                    pngSrc(attempt.clip_crop_b64),
                    `Outlined candidate crop attempt ${attempt.attempt_index}`,
                  )
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
              SD in: strength={attempt.params.strength} steps={attempt.params.num_inference_steps} guidance=
              {attempt.params.guidance_scale}
              {"\n"}prompt: {attempt.params.prompt}
              {"\n"}negative: {attempt.params.negative_prompt}
              {attempt.mask_pixel_count != null ? `\nmask pixels: ${attempt.mask_pixel_count}` : ""}
            </p>
            {!attempt.ok && attempt.next_params ? (
              <p className="debug-kv">
                Next retry: strength={attempt.next_params.strength} steps=
                {attempt.next_params.num_inference_steps} guidance={attempt.next_params.guidance_scale}
                {"\n"}mask dilate: {attempt.next_params.mask_dilate_pixels ?? 0} compose dilate:{" "}
                {attempt.next_params.compose_dilate_pixels ?? 0}
                {"\n"}prompt: {attempt.next_params.prompt}
                {"\n"}negative: {attempt.next_params.negative_prompt}
              </p>
            ) : null}
            <p className="debug-kv">verifier JSON: {attempt.param_fixes_json}</p>
          </div>
        ))}
        <img
          className="debug-trace-image"
          src={pngSrc(inpaintVerify.data.final_b64)}
          alt="Final inpaint"
          onClick={() => onOpenLightbox(pngSrc(inpaintVerify.data.final_b64), "Final inpaint")}
        />
        <p className="debug-panel-elapsed">{formatMs(inpaintVerify.data.elapsed_ms)}</p>
      </>
    ) : (
      <p className="debug-panel-hint">
        Uses the selected mask (winner after auto pick, or an explicit card). Minutes on a cold GPU.
      </p>
    )}
  </section>
);
