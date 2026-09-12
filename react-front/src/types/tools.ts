/**
 * Which picking tool owns the next click on the photo.
 *
 * "select" is the resting state: clicks select, drag, and deselect objects.
 * The rest each claim pointer-down for their own gesture, and only one can
 * ever be armed -- that is the whole point of modelling them as one value
 * rather than as three independent booleans that every reader had to
 * re-exclude by hand.
 *
 * Rotate is deliberately not a member: it lives in useRotationController with
 * its own async 3D-prep lifecycle, and several call sites depend on a picking
 * tool taking precedence over it.
 */
export type PickTool = "select" | "cut" | "area" | "erase";

/** Every tool the toolbar can actually arm (i.e. all but the resting state). */
export type ArmablePickTool = Exclude<PickTool, "select">;
