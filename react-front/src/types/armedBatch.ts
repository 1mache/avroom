import type { ClickPosition } from "./session";

/** What happens when an armed row is approved. */
export type ArmedJobAction = "erase" | "cutOut" | "cutOutAnd3d" | "generate3d";

export type ArmedJobSource =
  | { kind: "clicks"; points: ClickPosition[] }
  | { kind: "box"; x0: number; y0: number; x1: number; y1: number }
  | { kind: "lasso"; regions: ClickPosition[][] }
  | { kind: "objects"; uuids: string[] };

/** One locally armed job — not a server Job until approved. */
export interface ArmedJob {
  id: string;
  source: ArmedJobSource;
  action: ArmedJobAction;
}
