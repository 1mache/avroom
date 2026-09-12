import { effectiveCutoutSrc } from "../../types/session";
import type { CutoutObject } from "../../types/session";

export interface StageCutoutsProps {
  /** Objects to draw, already filtered to the ones the stage owns. */
  objects: CutoutObject[];
  selectedObjectId: number | null;
  isShowingOriginal: (obj: CutoutObject) => boolean;
  usesPlanarCss3d: (obj: CutoutObject) => boolean;
  cutoutStyle: (
    obj: CutoutObject,
    showOriginal: boolean,
    zIndex: number,
  ) => React.CSSProperties | undefined;
  planarCutoutImgStyle: (
    obj: CutoutObject,
    showOriginal: boolean,
  ) => React.CSSProperties | undefined;
}

/**
 * The object layer: every visible cutout, stacked over the photo.
 *
 * Two render shapes, decided per object by `usesPlanarCss3d`. A tilted object
 * needs a tight wrapper div so the CSS 3D transform has a box the size of the
 * object to rotate; everything else is the full-frame transparent PNG laid
 * straight over the photo. The selected object is lifted above the rest so a
 * drag never slides under a neighbour.
 */
export const StageCutouts: React.FC<StageCutoutsProps> = ({
  objects,
  selectedObjectId,
  isShowingOriginal,
  usesPlanarCss3d,
  cutoutStyle,
  planarCutoutImgStyle,
}) => (
  <>
    {objects.map((obj, index) => {
      const showOriginal = isShowingOriginal(obj);
      const zIndex = obj.objectId === selectedObjectId ? objects.length + 2 : index + 2;
      const src = effectiveCutoutSrc(obj, showOriginal);

      if (usesPlanarCss3d(obj)) {
        return (
          <div
            key={obj.objectId}
            className="stage-cutout-css3d"
            style={cutoutStyle(obj, showOriginal, zIndex)}
          >
            <img src={src} alt="" style={planarCutoutImgStyle(obj, showOriginal)} draggable={false} />
          </div>
        );
      }

      return (
        <img
          key={obj.objectId}
          src={src}
          alt=""
          className="stage-cutout"
          style={cutoutStyle(obj, showOriginal, zIndex)}
          draggable={false}
        />
      );
    })}
  </>
);
