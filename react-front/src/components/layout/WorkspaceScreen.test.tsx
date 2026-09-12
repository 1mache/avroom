import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

/**
 * Behavioural cover for the workspace's toolbar/tool state.
 *
 * WorkspaceScreen is large and has no other automated cover, so these tests
 * deliberately drive it the way a user does -- click the toolbar, read the
 * hint line -- rather than reaching into its internals. That is what makes
 * them survive a restructuring of the component, which is the whole point of
 * having them: they should still pass after the render tree is split up.
 *
 * Everything that would hit the network is stubbed at the api/images module,
 * which is the single seam every hook in this screen goes through.
 */

const cacheStatus = {
  uid: "sess-1",
  name: "Test room",
  has_background: false,
  has_cutout: false,
  has_3d: false,
  can_undo: false,
  can_redo: false,
};

const getUidCacheStatus = vi.fn(async () => ({ ...cacheStatus }));
const getSessionObjects = vi.fn(async () => ({ objects: [] }));
const warmSessionMaps = vi.fn(async () => ({}));
const syncCheck = vi.fn(async () => ({ needs_refresh: false, last_changed: "0", jobs: [] }));

vi.mock("../../api/images", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api/images")>();
  return {
    ...actual,
    getUidCacheStatus: (...args: unknown[]) => getUidCacheStatus(...(args as [])),
    getSessionObjects: (...args: unknown[]) => getSessionObjects(...(args as [])),
    warmSessionMaps: (...args: unknown[]) => warmSessionMaps(...(args as [])),
    syncCheckSession: (...args: unknown[]) => syncCheck(...(args as [])),
    setSessionName: vi.fn(async () => ({})),
    saveSessionPreview: vi.fn(async () => ({})),
    segmentImage: vi.fn(async () => ({ job_id: "job-1" })),
    deleteJob: vi.fn(async () => undefined),
  };
});

const { WorkspaceScreen } = await import("./WorkspaceScreen");

/** Mount and wait for the session-load effect to settle. */
async function mountWorkspace() {
  const view = render(<WorkspaceScreen uid="sess-1" onExit={() => {}} />);
  await waitFor(() => expect(getUidCacheStatus).toHaveBeenCalled());
  return view;
}

/** The toolbar buttons name themselves through their aria-label. */
const CUT = "Cut out object";
const AREA = "Cut objects in area";
const ERASE = "Erase area";

function tool(label: string) {
  return screen.getByRole("button", { name: label });
}

const hint = () => document.querySelector(".stage-hint")?.textContent ?? null;

beforeEach(() => {
  getUidCacheStatus.mockClear();
  getSessionObjects.mockClear();
  warmSessionMaps.mockClear();
});

describe("WorkspaceScreen tool arming", () => {
  it("loads the session name from the cache status", async () => {
    await mountWorkspace();
    expect(await screen.findByDisplayValue("Test room")).toBeInTheDocument();
  });

  it("shows no hint until a tool is armed", async () => {
    await mountWorkspace();
    expect(hint()).toBeNull();
  });

  it("arms the cut tool and shows its hint", async () => {
    const user = userEvent.setup();
    await mountWorkspace();

    await user.click(tool(CUT));

    expect(hint()).toMatch(/click the object/i);
  });

  it("disarms the cut tool when it is clicked a second time", async () => {
    const user = userEvent.setup();
    await mountWorkspace();

    await user.click(tool(CUT));
    await user.click(tool(CUT));

    expect(hint()).toBeNull();
  });

  it("arming the eraser replaces the cut tool rather than stacking with it", async () => {
    // The exclusion these assert used to be hand-maintained across three
    // booleans; it is now structural, and this is what proves it stayed true.
    const user = userEvent.setup();
    await mountWorkspace();

    await user.click(tool(CUT));
    await user.click(tool(ERASE));

    expect(hint()).toMatch(/loop/i);
    expect(hint()).not.toMatch(/click the object/i);
  });

  it("arming the area tool replaces the eraser", async () => {
    const user = userEvent.setup();
    await mountWorkspace();

    await user.click(tool(ERASE));
    await user.click(tool(AREA));

    expect(hint()).toMatch(/box/i);
  });

  it("Escape returns to the resting tool", async () => {
    const user = userEvent.setup();
    await mountWorkspace();

    await user.click(tool(CUT));
    expect(hint()).not.toBeNull();

    await user.keyboard("{Escape}");

    expect(hint()).toBeNull();
  });

  it("marks the stage as picking only while a tool is armed", async () => {
    const user = userEvent.setup();
    await mountWorkspace();
    const stage = document.querySelector(".stage");

    expect(stage).not.toHaveClass("is-picking");

    await user.click(tool(CUT));
    expect(stage).toHaveClass("is-picking");

    await user.keyboard("{Escape}");
    expect(stage).not.toHaveClass("is-picking");
  });
});
