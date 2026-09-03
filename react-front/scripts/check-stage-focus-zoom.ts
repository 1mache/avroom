/**
 * Self-check for hold-Control stage zoom mapping.
 * Run: npx --yes tsx react-front/scripts/check-stage-focus-zoom.ts
 */
import {
  STAGE_FOCUS_ZOOM,
  STAGE_FOCUS_ZOOM_MAX,
  STAGE_FOCUS_ZOOM_MIN,
  clampStageFocusZoom,
  unzoomStagePoint,
  toNaturalPoint,
} from "../src/utils/stageGeometry";

function assert(cond: boolean, msg: string): void {
  if (!cond) {
    throw new Error(msg);
  }
}

const origin = { x: 100, y: 200 };
const scale = STAGE_FOCUS_ZOOM;

assert(STAGE_FOCUS_ZOOM === 2.5, "STAGE_FOCUS_ZOOM should be 2.5");
assert(clampStageFocusZoom(0.5) === STAGE_FOCUS_ZOOM_MIN, "clamp floor");
assert(clampStageFocusZoom(99) === STAGE_FOCUS_ZOOM_MAX, "clamp ceiling");
assert(clampStageFocusZoom(3) === 3, "clamp passthrough");

const identity = unzoomStagePoint({ x: 150, y: 250 }, origin, 1);
assert(identity.x === 150 && identity.y === 250, "scale 1 is identity");

const atOrigin = unzoomStagePoint(origin, origin, scale);
assert(atOrigin.x === 100 && atOrigin.y === 200, "origin maps to itself");

const screen = { x: origin.x + 40 * scale, y: origin.y };
const content = unzoomStagePoint(screen, origin, scale);
assert(Math.abs(content.x - (origin.x + 40)) < 1e-9, `expected content x ${origin.x + 40}, got ${content.x}`);
assert(Math.abs(content.y - origin.y) < 1e-9, `expected content y ${origin.y}, got ${content.y}`);

const renderedRect = { x: 50, y: 10, width: 400, height: 300 };
const naturalSize = { width: 800, height: 600 };
const natural = toNaturalPoint(content.x, content.y, renderedRect, naturalSize);
assert(natural !== null, "content point should be on the photo");

console.log("check-stage-focus-zoom: ok");
