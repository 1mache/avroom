import { rectStyle } from "../../utils/stageGeometry";
import type { ResizeHandle } from "../../utils/stageGeometry";

/**
 * The eight resize grips, as data.
 *
 * Corners scale both axes, edges scale one. The two-letter codes are the
 * same ones `useObjectResize` keys its maths off, and the CSS class carries
 * the code verbatim to position the grip.
 */
const HANDLES: { handle: ResizeHandle; kind: "corner" | "edge"; label: string }[] = [
  { handle: "tl", kind: "corner", label: "top left" },
  { handle: "tr", kind: "corner", label: "top right" },
  { handle: "bl", kind: "corner", label: "bottom left" },
  { handle: "br", kind: "corner", label: "bottom right" },
  { handle: "t", kind: "edge", label: "top" },
  { handle: "r", kind: "edge", label: "right" },
  { handle: "b", kind: "edge", label: "bottom" },
  { handle: "l", kind: "edge", label: "left" },
];

export interface SelectionFrameProps {
  /** Selected object's box in clip-local coords (origin = photo top-left). */
  rect: { left: number; top: number; width: number; height: number };
  /** Grips are hidden while another gesture owns the object (drag, rotate, cut). */
  canResize: boolean;
  onResizePointerDown: (handle: ResizeHandle) => React.PointerEventHandler<HTMLElement>;
}

/** Outline around the selected object, with its resize grips when allowed. */
export const SelectionFrame: React.FC<SelectionFrameProps> = ({
  rect,
  canResize,
  onResizePointerDown,
}) => (
  <div className="selection-frame" style={{ ...rectStyle(rect), zIndex: 210 }}>
    {canResize
      ? HANDLES.map(({ handle, kind, label }) => (
          <button
            key={handle}
            type="button"
            className={`selection-handle selection-${kind} ${handle}`}
            aria-label={`Resize ${label}`}
            onPointerDown={onResizePointerDown(handle)}
          />
        ))
      : null}
  </div>
);
