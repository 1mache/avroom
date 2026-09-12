import { naturalPointToStage, polygonToStagePoints } from "../../utils/stageGeometry";
import type { Rect, Size } from "../../utils/stageGeometry";
import type { ArmedOverlays } from "../../utils/armedBatch";
import type { ClickPosition } from "../../types/session";
import type { LassoDraft } from "../../hooks/useLassoSelect";

interface Common {
  renderedRect: Rect;
  naturalSize: Size;
}

export interface StageMarkersProps extends Common {
  /** Seeds staged for the next cutout, numbered once there is more than one. */
  pendingSeeds: ClickPosition[];
  /** Seeds belonging to jobs already armed in the batch queue. */
  armedSeeds: ArmedOverlays["seeds"];
  /** The cut tool is armed, which brightens the pending markers. */
  cutArmed: boolean;
}

/**
 * The click markers drawn over the photo.
 *
 * Two lists with the same shape: seeds the user is staging right now, and
 * seeds already parked in the batch queue. They render as one component
 * because the only thing either needs is "put a ring at this natural-image
 * point", and duplicating that positioning maths is how the two drifted
 * apart in the first place.
 */
export const StageMarkers: React.FC<StageMarkersProps> = ({
  renderedRect,
  naturalSize,
  pendingSeeds,
  armedSeeds,
  cutArmed,
}) => {
  if (pendingSeeds.length === 0 && armedSeeds.length === 0) {
    return null;
  }

  const at = (point: ClickPosition) => {
    const { x, y } = naturalPointToStage(point, renderedRect, naturalSize);
    return { left: `${x}px`, top: `${y}px` };
  };

  return (
    <div className="stage-seed-markers" aria-hidden="true">
      {pendingSeeds.map((seed, index) => (
        <span
          key={`pending-${seed.x}-${seed.y}-${index}`}
          className={`stage-pick-marker${cutArmed ? " is-armed" : ""}`}
          style={at(seed)}
        >
          <span className="stage-pick-marker-ring" />
          {pendingSeeds.length > 1 ? (
            <span className="stage-pick-marker-label">{index + 1}</span>
          ) : null}
        </span>
      ))}

      {armedSeeds.map((seed) => (
        <span
          key={seed.id}
          className={`stage-pick-marker is-pending${seed.selected ? " is-selected" : ""}`}
          style={at(seed.value)}
        >
          <span className="stage-pick-marker-ring" />
        </span>
      ))}
    </div>
  );
};

export interface StageLassoLayerProps extends Common {
  /** Lasso regions belonging to jobs already armed in the batch queue. */
  armedLassos: ArmedOverlays["lassos"];
  /** Regions staged for the next erase. */
  pendingEraseRegions: ClickPosition[][];
  /** The loop currently being drawn, still open. */
  draft: LassoDraft | null;
};

/** Every freehand erase region: armed, staged, and the one being drawn. */
export const StageLassoLayer: React.FC<StageLassoLayerProps> = ({
  renderedRect,
  naturalSize,
  armedLassos,
  pendingEraseRegions,
  draft,
}) => {
  if (armedLassos.length === 0 && pendingEraseRegions.length === 0 && !draft) {
    return null;
  }

  const points = (polygon: ClickPosition[]) =>
    polygonToStagePoints(polygon, renderedRect, naturalSize);

  return (
    <svg className="stage-lasso-layer" aria-hidden="true">
      {armedLassos.map((lasso) => (
        <polygon
          key={lasso.id}
          className={`stage-lasso-path is-pending${lasso.selected ? " is-selected" : ""}`}
          points={points(lasso.value)}
        />
      ))}
      {pendingEraseRegions.map((polygon, index) => (
        <polygon
          key={`pending-erase-${index}`}
          className="stage-lasso-path is-pending"
          points={points(polygon)}
        />
      ))}
      {/* Open polyline, not a polygon: the loop is not closed until release. */}
      {draft ? <polyline className="stage-lasso-path" points={points(draft.points)} /> : null}
    </svg>
  );
};
