import React from "react";

import type { Css3dPose } from "../../utils/css3dTransform";

export interface RotationSliderBarProps {
  pose: Css3dPose;
  onChange: (next: Css3dPose) => void;
}

const ANGLE_MIN = -180;
const ANGLE_MAX = 180;
const AXIS_DEFAULT = 0;

type AxisKey = "rotateXDeg" | "rotateYDeg" | "rotateZDeg";

const AXES: ReadonlyArray<{ key: AxisKey; label: string }> = [
  { key: "rotateXDeg", label: "rotateX" },
  { key: "rotateYDeg", label: "rotateY" },
  { key: "rotateZDeg", label: "rotateZ" },
];

/**
 * Compact rotateX/Y/Z knobs shown beside the object while Rotate is armed.
 * Each axis has a reset-to-default (0°) control. Perspective stays fixed.
 */
export const RotationSliderBar: React.FC<RotationSliderBarProps> = ({
  pose,
  onChange,
}) => {
  return (
    <div className="rotation-slider-bar" role="group" aria-label="Rotation sliders">
      {AXES.map(({ key, label }) => {
        const value = pose[key];
        const atDefault = value === AXIS_DEFAULT;
        return (
          <div key={key} className="rotation-slider">
            <span className="rotation-slider-label">{label}</span>
            <input
              type="range"
              min={ANGLE_MIN}
              max={ANGLE_MAX}
              step={1}
              value={value}
              aria-label={label}
              onChange={(e) => onChange({ ...pose, [key]: Number(e.target.value) })}
            />
            <span className="rotation-slider-value">{Math.round(value)}°</span>
            <button
              type="button"
              className="rotation-slider-reset"
              data-tip={`Reset ${label} to 0°`}
              aria-label={`Reset ${label} to default`}
              disabled={atDefault}
              onClick={() => onChange({ ...pose, [key]: AXIS_DEFAULT })}
            >
              0°
            </button>
          </div>
        );
      })}
    </div>
  );
};
