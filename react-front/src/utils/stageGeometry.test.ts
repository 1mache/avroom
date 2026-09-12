import { describe, expect, it } from "vitest";

import { findObjectAtPoint, ALPHA_HIT_THRESHOLD } from "./stageGeometry";
import type { CutoutObject } from "../types/session";

/**
 * Hit testing is the one piece of stage geometry a user notices instantly when
 * it breaks: clicks either select the wrong object or nothing at all. It is
 * also the piece with no DOM involvement, so it can be pinned down exactly.
 */

function obj(overrides: Partial<CutoutObject> & { objectId: number }): CutoutObject {
  return {
    uuid: `uuid-${overrides.objectId}`,
    name: null,
    cutoutSrc: "",
    cutoutAlphaBounds: null,
    normalizedClickPos: null,
    glbData: null,
    rotation: null,
    hidden: false,
    beyondStage: false,
    revealed: false,
    offset: { x: 0, y: 0 },
    sourceElevationDeg: 15,
    displayScale: 1,
    has3d: false,
    is3d: null,
    cloneRootUuid: null,
    cssRotateXDeg: 0,
    cssRotateYDeg: 0,
    cssRotateZDeg: 0,
    cssPerspectivePx: 800,
    ...overrides,
  } as CutoutObject;
}

const opaque = () => 255;
const transparent = () => 0;
const showOriginalNever = () => false;

describe("findObjectAtPoint", () => {
  it("returns null when every object is transparent under the pointer", () => {
    const hit = findObjectAtPoint({
      objects: [obj({ objectId: 1 })],
      selectedObjectId: null,
      point: { x: 10, y: 10 },
      isShowingOriginal: showOriginalNever,
      sampleAlpha: transparent,
    });

    expect(hit).toBeNull();
  });

  it("returns the object whose cutout is opaque under the pointer", () => {
    const hit = findObjectAtPoint({
      objects: [obj({ objectId: 7 })],
      selectedObjectId: null,
      point: { x: 10, y: 10 },
      isShowingOriginal: showOriginalNever,
      sampleAlpha: opaque,
    });

    expect(hit?.objectId).toBe(7);
  });

  it("prefers the selected object when two objects overlap", () => {
    const hit = findObjectAtPoint({
      objects: [obj({ objectId: 1 }), obj({ objectId: 2 })],
      selectedObjectId: 2,
      point: { x: 10, y: 10 },
      isShowingOriginal: showOriginalNever,
      sampleAlpha: opaque,
    });

    expect(hit?.objectId).toBe(2);
  });

  it("skips the object named by skipObjectId", () => {
    // This is how a volumetric object being shown as a 3D mesh bows out: its
    // 2D cutout is hidden, so that region belongs to the 3D frame instead.
    const hit = findObjectAtPoint({
      objects: [obj({ objectId: 1 }), obj({ objectId: 2 })],
      selectedObjectId: 2,
      point: { x: 10, y: 10 },
      skipObjectId: 2,
      isShowingOriginal: showOriginalNever,
      sampleAlpha: opaque,
    });

    expect(hit?.objectId).toBe(1);
  });

  it("treats alpha exactly at the threshold as a miss", () => {
    const hit = findObjectAtPoint({
      objects: [obj({ objectId: 1 })],
      selectedObjectId: null,
      point: { x: 10, y: 10 },
      isShowingOriginal: showOriginalNever,
      sampleAlpha: () => ALPHA_HIT_THRESHOLD,
    });

    expect(hit).toBeNull();
  });

  it("samples in the object's own local space, not stage space", () => {
    const sampled: { x: number; y: number }[] = [];
    findObjectAtPoint({
      objects: [obj({ objectId: 1, offset: { x: 100, y: 40 } })],
      selectedObjectId: null,
      point: { x: 130, y: 55 },
      isShowingOriginal: showOriginalNever,
      sampleAlpha: (_id, x, y) => {
        sampled.push({ x, y });
        return 255;
      },
    });

    expect(sampled).toEqual([{ x: 30, y: 15 }]);
  });
});
