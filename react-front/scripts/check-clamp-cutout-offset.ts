/**
 * Self-check for clampCutoutOffset (hang-off-photo with a kept sliver).
 * Run: npx --yes tsx react-front/scripts/check-clamp-cutout-offset.ts
 */
import {
  MIN_ON_PHOTO_PX,
  clampCutoutOffset,
} from "../src/utils/stageGeometry";

function assert(cond: boolean, msg: string): void {
  if (!cond) {
    throw new Error(msg);
  }
}

const imageSize = { width: 100, height: 80 };
// Opaque box from (40,20) to (60,50) — 20×30.
const bounds = {
  left: 40,
  top: 20,
  right: 60,
  bottom: 50,
  naturalWidth: 100,
  naturalHeight: 80,
};

// Old flush-inside limits: minX=-40, maxX=40, minY=-20, maxY=30.
assert(MIN_ON_PHOTO_PX === 8, "MIN_ON_PHOTO_PX should be 8");

const flushLeft = clampCutoutOffset({ x: -40, y: 0 }, bounds, imageSize);
assert(flushLeft.x === -40 && flushLeft.y === 0, `flush-inside left still allowed: ${JSON.stringify(flushLeft)}`);

const flushRight = clampCutoutOffset({ x: 40, y: 0 }, bounds, imageSize);
assert(flushRight.x === 40, `flush-inside right still allowed: ${flushRight.x}`);

// 1px past the old left clamp (−41): right edge of cutout at −1 → still more than 8px? 
// At offset −41: right = 60-41 = 19 on photo. Allowed.
// Old max leftward with full-inside was −40. New minX = 8 - 60 = −52.
const pastOldLeft = clampCutoutOffset({ x: -41, y: 0 }, bounds, imageSize);
assert(pastOldLeft.x === -41, `1px past old clamp allowed: got ${pastOldLeft.x}`);

const atSliverLeft = clampCutoutOffset({ x: -52, y: 0 }, bounds, imageSize);
assert(atSliverLeft.x === -52, `sliver-left limit (−52) allowed: got ${atSliverLeft.x}`);

const fullyOffLeft = clampCutoutOffset({ x: -60, y: 0 }, bounds, imageSize);
assert(fullyOffLeft.x === -52, `fully off-photo rejected (clamped to −52): got ${fullyOffLeft.x}`);

const pastOldRight = clampCutoutOffset({ x: 41, y: 0 }, bounds, imageSize);
assert(pastOldRight.x === 41, `1px past old right clamp allowed: got ${pastOldRight.x}`);

// maxX = 100 - 8 - 40 = 52
const fullyOffRight = clampCutoutOffset({ x: 80, y: 0 }, bounds, imageSize);
assert(fullyOffRight.x === 52, `fully off right rejected (clamped to 52): got ${fullyOffRight.x}`);

// Y: minY = 8-50 = −42, maxY = 80-8-20 = 52
const pastOldTop = clampCutoutOffset({ x: 0, y: -21 }, bounds, imageSize);
assert(pastOldTop.y === -21, `1px past old top clamp allowed: got ${pastOldTop.y}`);

const fullyOffTop = clampCutoutOffset({ x: 0, y: -100 }, bounds, imageSize);
assert(fullyOffTop.y === -42, `fully off top rejected: got ${fullyOffTop.y}`);

console.log("check-clamp-cutout-offset: ok");
