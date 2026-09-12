import type { PickTool } from "../../types/tools";

const ZOOM_TAIL = " · hold Ctrl to zoom · scroll to adjust";

export interface StageHintProps {
  rotateMode: boolean;
  /** True while the rotating object is volumetric (mesh), not planar. */
  volumetric: boolean;
  tool: PickTool;
  batchMode: boolean;
  armedJobCount: number;
  pendingEraseRegionCount: number;
  pendingSeedCount: number;
  hasPendingBatchSource: boolean;
  multiPoint: boolean;
}

const plural = (count: number, noun: string) =>
  `${count} ${noun}${count === 1 ? "" : "s"}`;

/**
 * The one line of instructions under the photo.
 *
 * Written as ordered early returns rather than the nested ternary chain this
 * replaces: the order *is* the precedence (rotate beats erase beats area
 * beats a staged box beats staged seeds beats cut), and each branch reads as
 * a sentence instead of as the third arm of someone else's conditional.
 */
function stageHintText(props: StageHintProps): string | null {
  const {
    rotateMode,
    volumetric,
    tool,
    batchMode,
    armedJobCount,
    pendingEraseRegionCount,
    pendingSeedCount,
    hasPendingBatchSource,
    multiPoint,
  } = props;

  if (rotateMode) {
    return volumetric
      ? "Drag mesh or use sliders · Enter applies · Esc cancels"
      : "Sliders tilt · Enter applies · Esc cancels";
  }

  if (tool === "erase") {
    if (batchMode) {
      return "Drag a loop to arm erase · Esc cancels";
    }
    if (pendingEraseRegionCount > 0) {
      return `${plural(pendingEraseRegionCount, "region")} · Shift-drag adds · Enter or checkmark runs · Esc cancels`;
    }
    return "Drag a loop to erase · Shift-drag stages · Esc cancels";
  }

  if (tool === "area") {
    return batchMode
      ? "Drag a box to arm cut · Esc cancels"
      : "Drag a box around the furniture · Esc cancels";
  }

  if (hasPendingBatchSource) {
    return "Submit batch cut (checkmark) · Esc clears box";
  }

  if (pendingSeedCount > 0) {
    const seeds = plural(pendingSeedCount, "seed");
    return batchMode
      ? `${seeds} · Enter or checkmark arms · Esc clears${ZOOM_TAIL}`
      : `${seeds} placed · Shift+click adds · Enter or checkmark runs · Esc clears${ZOOM_TAIL}`;
  }

  if (tool === "cut") {
    if (batchMode) {
      return multiPoint
        ? `Click to add seeds · Enter or checkmark arms · Esc cancels${ZOOM_TAIL}`
        : `Click to arm cutout · Shift+click adds seeds · Esc cancels${ZOOM_TAIL}`;
    }
    return multiPoint
      ? `Click to add seeds · Enter or checkmark runs · Esc cancels${ZOOM_TAIL}`
      : `Click the object · Shift+click adds seeds · Esc cancels${ZOOM_TAIL}`;
  }

  if (batchMode && armedJobCount > 0) {
    return `${armedJobCount} armed · checkmark approves · queue button to edit`;
  }

  return null;
}

export const StageHint: React.FC<StageHintProps> = (props) => {
  const text = stageHintText(props);
  return text === null ? null : <p className="stage-hint">{text}</p>;
};
