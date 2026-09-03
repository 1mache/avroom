import type { BatchRequest } from "../types/api";
import type { ArmedJob, ArmedJobAction, ArmedJobSource } from "../types/armedBatch";
import type { ClickPosition } from "../types/session";
import { rasterizeEraseMask } from "./lassoMask";

export type ArmedBatchApiStep =
  | { kind: "erase"; maskB64: string }
  | { kind: "batch"; payload: BatchRequest };

export interface ArmedBatchPlanStep {
  step: ArmedBatchApiStep;
  jobIds: string[];
}

export function defaultCutAction(autoGenerate3d: boolean): "cutOut" | "cutOutAnd3d" {
  return autoGenerate3d ? "cutOutAnd3d" : "cutOut";
}

export function actionToBatchThen(action: ArmedJobAction): BatchRequest["then"] | null {
  if (action === "cutOut") {
    return ["inpaint"];
  }
  if (action === "cutOutAnd3d") {
    return ["inpaint", "generate_3d"];
  }
  if (action === "generate3d") {
    return ["generate_3d"];
  }
  return null;
}

function polygonBounds(polygon: ClickPosition[]): {
  minX: number;
  minY: number;
  maxX: number;
  maxY: number;
} | null {
  if (polygon.length === 0) {
    return null;
  }
  let minX = polygon[0].x;
  let minY = polygon[0].y;
  let maxX = polygon[0].x;
  let maxY = polygon[0].y;
  for (const point of polygon) {
    minX = Math.min(minX, point.x);
    minY = Math.min(minY, point.y);
    maxX = Math.max(maxX, point.x);
    maxY = Math.max(maxY, point.y);
  }
  return { minX, minY, maxX, maxY };
}

/** Bounding-box center — used when a lasso is promoted to a SAM click. */
export function regionCenter(polygon: ClickPosition[]): ClickPosition | null {
  const bounds = polygonBounds(polygon);
  if (!bounds) {
    return null;
  }
  return {
    x: Math.round((bounds.minX + bounds.maxX) / 2),
    y: Math.round((bounds.minY + bounds.maxY) / 2),
  };
}

function boxToPolygon(box: Extract<ArmedJobSource, { kind: "box" }>): ClickPosition[] {
  return [
    { x: box.x0, y: box.y0 },
    { x: box.x1, y: box.y0 },
    { x: box.x1, y: box.y1 },
    { x: box.x0, y: box.y1 },
  ];
}

function roundedPoints(points: ClickPosition[]): { x: number; y: number }[] {
  return points.map((point) => ({
    x: Math.round(point.x),
    y: Math.round(point.y),
  }));
}

function clicksStep(
  points: ClickPosition[],
  action: ArmedJobAction,
  jobIds: string[],
): ArmedBatchPlanStep | null {
  const then = actionToBatchThen(action);
  if (!then || points.length === 0) {
    return null;
  }
  return {
    jobIds,
    step: {
      kind: "batch",
      payload: {
        source: { kind: "clicks", points: roundedPoints(points) },
        then,
        verify: "auto",
      },
    },
  };
}

function boxStep(
  box: Extract<ArmedJobSource, { kind: "box" }>,
  action: ArmedJobAction,
  jobId: string,
): ArmedBatchPlanStep | null {
  if (action === "erase") {
    return null;
  }
  const then = actionToBatchThen(action);
  if (!then) {
    return null;
  }
  return {
    jobIds: [jobId],
    step: {
      kind: "batch",
      payload: {
        source: {
          kind: "box",
          x0: Math.round(box.x0),
          y0: Math.round(box.y0),
          x1: Math.round(box.x1),
          y1: Math.round(box.y1),
        },
        then,
        verify: "auto",
      },
    },
  };
}

function eraseStep(
  width: number,
  height: number,
  regions: ClickPosition[][],
  jobIds: string[],
): ArmedBatchPlanStep | null {
  const maskB64 = rasterizeEraseMask(width, height, regions);
  if (!maskB64) {
    return null;
  }
  return {
    jobIds,
    step: { kind: "erase", maskB64 },
  };
}

function lassoToClickPoints(regions: ClickPosition[][]): ClickPosition[] {
  const points: ClickPosition[] = [];
  for (const region of regions) {
    const center = regionCenter(region);
    if (center) {
      points.push(center);
    }
  }
  return points;
}

/**
 * Map armed rows to sequential API calls. Each click row is one object
 * (all its seeds go to one /images/segment-style points list).
 */
export function buildArmedBatchPlan(
  jobs: ArmedJob[],
  naturalSize: { width: number; height: number },
): ArmedBatchPlanStep[] {
  const plan: ArmedBatchPlanStep[] = [];

  for (const job of jobs) {
    const { source, action, id } = job;

    if (source.kind === "clicks") {
      const step = clicksStep(source.points, action, [id]);
      if (step) {
        plan.push(step);
      }
      continue;
    }

    if (source.kind === "objects" && action === "generate3d") {
      const then = actionToBatchThen(action);
      if (then) {
        plan.push({
          jobIds: [id],
          step: {
            kind: "batch",
            payload: {
              source: { kind: "objects", uuids: [...source.uuids] },
              then,
              verify: "auto",
            },
          },
        });
      }
      continue;
    }

    if (source.kind === "box") {
      if (action === "erase") {
        const step = eraseStep(naturalSize.width, naturalSize.height, [boxToPolygon(source)], [
          id,
        ]);
        if (step) {
          plan.push(step);
        }
      } else {
        const step = boxStep(source, action, id);
        if (step) {
          plan.push(step);
        }
      }
      continue;
    }

    if (source.kind === "lasso") {
      if (action === "erase") {
        const step = eraseStep(naturalSize.width, naturalSize.height, source.regions, [id]);
        if (step) {
          plan.push(step);
        }
      } else {
        const points = lassoToClickPoints(source.regions);
        const step = clicksStep(points, action, [id]);
        if (step) {
          plan.push(step);
        }
      }
      continue;
    }
  }

  return plan;
}

const ACTION_LABELS: Record<ArmedJobAction, string> = {
  erase: "Erase",
  cutOut: "Cut out",
  cutOutAnd3d: "Cut out + 3D",
  generate3d: "Build 3D",
};

export function armedJobLabel(job: ArmedJob): string {
  const action = ACTION_LABELS[job.action];
  switch (job.source.kind) {
    case "clicks":
      return job.source.points.length === 1
        ? `${action} (1 seed)`
        : `${action} (${job.source.points.length} seeds)`;
    case "box":
      return `${action} (box)`;
    case "lasso":
      return job.source.regions.length === 1
        ? `${action} (lasso)`
        : `${action} (${job.source.regions.length} lassos)`;
    case "objects":
      return `${action} (${job.source.uuids.length} object${job.source.uuids.length === 1 ? "" : "s"})`;
    default:
      return action;
  }
}

export function actionsForSource(
  source: ArmedJobSource,
): ArmedJobAction[] {
  switch (source.kind) {
    case "clicks":
      return ["cutOut", "cutOutAnd3d"];
    case "objects":
      return ["generate3d"];
    default:
      return ["erase", "cutOut", "cutOutAnd3d"];
  }
}

export function moveArmedJob(jobs: ArmedJob[], id: string, direction: "up" | "down"): ArmedJob[] {
  const index = jobs.findIndex((job) => job.id === id);
  if (index < 0) {
    return jobs;
  }
  const target = direction === "up" ? index - 1 : index + 1;
  if (target < 0 || target >= jobs.length) {
    return jobs;
  }
  const next = [...jobs];
  const [row] = next.splice(index, 1);
  next.splice(target, 0, row);
  return next;
}
