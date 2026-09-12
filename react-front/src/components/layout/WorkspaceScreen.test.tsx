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
const undoSessionBackground = vi.fn(async () => undefined);
const redoSessionBackground = vi.fn(async () => undefined);
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
    undoSessionBackground: (...args: unknown[]) => undoSessionBackground(...(args as [])),
    redoSessionBackground: (...args: unknown[]) => redoSessionBackground(...(args as [])),
  };
});

const { WorkspaceScreen } = await import("./WorkspaceScreen");

/**
 * Mount and wait for the session-load effect to settle.
 *
 * `uid` is overridable because the component keeps a module-level set of
 * already-warmed session ids, which survives unmount by design — a test that
 * needs to observe the warming overlay has to use a session id no earlier
 * test has warmed.
 */
async function mountWorkspace(uid = "sess-1") {
  const view = render(<WorkspaceScreen uid={uid} onExit={() => {}} />);
  await waitFor(() => expect(getUidCacheStatus).toHaveBeenCalled());
  return view;
}

/** The toolbar buttons name themselves through their aria-label. */
const CUT = "Cut out object";
const AREA = "Cut objects in area";
const ERASE = "Erase area";
const UNDO = "Backtrack room";
const REDO = "Forward room";

function tool(label: string) {
  return screen.getByRole("button", { name: label });
}

const hint = () => document.querySelector(".stage-hint")?.textContent ?? null;

beforeEach(() => {
  getUidCacheStatus.mockClear();
  getSessionObjects.mockClear();
  warmSessionMaps.mockClear();
  undoSessionBackground.mockClear();
  redoSessionBackground.mockClear();
  getUidCacheStatus.mockImplementation(async () => ({ ...cacheStatus }));
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

describe("WorkspaceScreen room history", () => {
  /** The cache status is what tells the workspace whether history has anywhere to go. */
  function withHistory(flags: { can_undo: boolean; can_redo: boolean }) {
    getUidCacheStatus.mockImplementation(async () => ({ ...cacheStatus, ...flags }));
  }

  it("disables both history buttons when the room has no history", async () => {
    await mountWorkspace();

    await waitFor(() => expect(tool(UNDO)).toBeDisabled());
    expect(tool(REDO)).toBeDisabled();
  });

  it("enables undo once the server reports it is available", async () => {
    withHistory({ can_undo: true, can_redo: false });
    await mountWorkspace();

    await waitFor(() => expect(tool(UNDO)).toBeEnabled());
    expect(tool(REDO)).toBeDisabled();
  });

  it("steps back when the undo button is pressed", async () => {
    const user = userEvent.setup();
    withHistory({ can_undo: true, can_redo: false });
    await mountWorkspace();
    await waitFor(() => expect(tool(UNDO)).toBeEnabled());

    await user.click(tool(UNDO));

    await waitFor(() => expect(undoSessionBackground).toHaveBeenCalledWith("sess-1"));
    expect(redoSessionBackground).not.toHaveBeenCalled();
  });

  it("steps forward when the redo button is pressed", async () => {
    const user = userEvent.setup();
    withHistory({ can_undo: false, can_redo: true });
    await mountWorkspace();
    await waitFor(() => expect(tool(REDO)).toBeEnabled());

    await user.click(tool(REDO));

    await waitFor(() => expect(redoSessionBackground).toHaveBeenCalledWith("sess-1"));
  });

  it("Ctrl+Z steps back", async () => {
    const user = userEvent.setup();
    withHistory({ can_undo: true, can_redo: false });
    await mountWorkspace();
    await waitFor(() => expect(tool(UNDO)).toBeEnabled());

    await user.keyboard("{Control>}z{/Control}");

    await waitFor(() => expect(undoSessionBackground).toHaveBeenCalledWith("sess-1"));
  });

  it("Ctrl+Shift+Z and Ctrl+Y both step forward", async () => {
    const user = userEvent.setup();
    withHistory({ can_undo: false, can_redo: true });
    await mountWorkspace();
    await waitFor(() => expect(tool(REDO)).toBeEnabled());

    await user.keyboard("{Control>}{Shift>}Z{/Shift}{/Control}");
    await waitFor(() => expect(redoSessionBackground).toHaveBeenCalledTimes(1));

    await user.keyboard("{Control>}y{/Control}");
    await waitFor(() => expect(redoSessionBackground).toHaveBeenCalledTimes(2));
  });

  it("ignores Ctrl+Z when the room has nothing to undo", async () => {
    const user = userEvent.setup();
    withHistory({ can_undo: false, can_redo: false });
    await mountWorkspace();

    await user.keyboard("{Control>}z{/Control}");

    expect(undoSessionBackground).not.toHaveBeenCalled();
  });

  it("ignores history shortcuts while a text field has focus", async () => {
    const user = userEvent.setup();
    withHistory({ can_undo: true, can_redo: false });
    await mountWorkspace();
    await waitFor(() => expect(tool(UNDO)).toBeEnabled());

    await user.click(screen.getByRole("textbox", { name: "Room name" }));
    await user.keyboard("{Control>}z{/Control}");

    expect(undoSessionBackground).not.toHaveBeenCalled();
  });
});

describe("WorkspaceScreen chrome", () => {
  it("renders the stage with the room photo", async () => {
    await mountWorkspace();

    const photo = document.querySelector(".stage-photo");
    expect(photo).toBeInTheDocument();
    expect(photo).toHaveAttribute("src", expect.stringContaining("/images/sess-1/original"));
  });

  it("covers the stage while depth maps warm, and uncovers when they finish", async () => {
    let finishWarm: () => void = () => {};
    warmSessionMaps.mockImplementation(
      () => new Promise<Record<string, never>>((resolve) => {
        finishWarm = () => resolve({});
      }),
    );

    await mountWorkspace("sess-never-warmed");
    expect(document.querySelector(".stage-warm-overlay")).toBeInTheDocument();

    finishWarm();

    await waitFor(() =>
      expect(document.querySelector(".stage-warm-overlay")).not.toBeInTheDocument(),
    );
  });

  it("shows the object rail", async () => {
    await mountWorkspace();
    expect(document.querySelector(".rail")).toBeInTheDocument();
  });

  it("surfaces a failed history step in the error modal, and closes it", async () => {
    const user = userEvent.setup();
    undoSessionBackground.mockRejectedValueOnce(new Error("Backend exploded"));
    getUidCacheStatus.mockImplementation(async () => ({ ...cacheStatus, can_undo: true }));
    await mountWorkspace();
    await waitFor(() => expect(tool(UNDO)).toBeEnabled());

    await user.click(tool(UNDO));

    const dialog = await screen.findByRole("alertdialog");
    expect(dialog).toHaveTextContent(/Backend exploded/);

    await user.click(screen.getByRole("button", { name: "Close" }));

    await waitFor(() => expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument());
  });

  it("shows no modal and no notices on a clean load", async () => {
    await mountWorkspace();

    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    expect(document.querySelector(".notice-stack")).not.toBeInTheDocument();
  });
});
