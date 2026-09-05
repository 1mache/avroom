/** Build a CSS 3D transform string matching 3dtransformer.com's slider model. */

export const DEFAULT_CSS_PERSPECTIVE_PX = 800;

export interface Css3dPose {
  rotateXDeg: number;
  rotateYDeg: number;
  rotateZDeg: number;
  perspectivePx: number;
}

export const IDENTITY_CSS_POSE: Css3dPose = {
  rotateXDeg: 0,
  rotateYDeg: 0,
  rotateZDeg: 0,
  perspectivePx: DEFAULT_CSS_PERSPECTIVE_PX,
};

/** True when any angle is non-zero (perspective alone is not a "pose"). */
export function hasCss3dPose(pose: Css3dPose): boolean {
  return pose.rotateXDeg !== 0 || pose.rotateYDeg !== 0 || pose.rotateZDeg !== 0;
}

/**
 * Compose perspective + rotateX/Y/Z + optional uniform scale.
 * Order matches 3dtransformer: perspective first, then axis rotates, then scale.
 */
export function css3dTransform(pose: Css3dPose, scale = 1): string {
  const parts = [
    `perspective(${pose.perspectivePx}px)`,
    `rotateX(${pose.rotateXDeg}deg)`,
    `rotateY(${pose.rotateYDeg}deg)`,
    `rotateZ(${pose.rotateZDeg}deg)`,
  ];
  if (scale !== 1) {
    parts.push(`scale(${scale})`);
  }
  return parts.join(" ");
}

/** Whether an object should use the mesh/novel-view rotate path. Null → volumetric. */
export function isVolumetricObject(is3d: boolean | null): boolean {
  return is3d !== false;
}

/** Invert a CSS 3D pose around *center* and return the un-tilted natural point. */
export function mapPointThroughInverseCss3d(
  point: { x: number; y: number },
  center: { x: number; y: number },
  pose: Css3dPose,
  scale = 1,
): { x: number; y: number } {
  if (typeof DOMMatrix === "undefined") {
    return point;
  }
  const matrix = new DOMMatrix(css3dTransform(pose, scale));
  let inverse: DOMMatrix;
  try {
    inverse = matrix.inverse();
  } catch {
    return point;
  }
  const local = inverse.transformPoint({
    x: point.x - center.x,
    y: point.y - center.y,
    z: 0,
  });
  return { x: local.x + center.x, y: local.y + center.y };
}

/** Project a natural-image point through a CSS 3D pose around *center*. */
export function mapPointThroughCss3d(
  point: { x: number; y: number },
  center: { x: number; y: number },
  pose: Css3dPose,
  scale = 1,
): { x: number; y: number } {
  if (typeof DOMMatrix === "undefined") {
    return point;
  }
  const matrix = new DOMMatrix(css3dTransform(pose, scale));
  const local = matrix.transformPoint({
    x: point.x - center.x,
    y: point.y - center.y,
    z: 0,
  });
  return { x: local.x + center.x, y: local.y + center.y };
}
