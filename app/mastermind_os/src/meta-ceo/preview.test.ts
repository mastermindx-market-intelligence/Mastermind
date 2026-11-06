import { describe, expect, it } from "vitest";
import { projectOffice, type ProjectionContext } from "./projection";
import {
  createDirectionPreview, decideOfficeLaunchHandoff, officeLaunchWorkstreamAgrees, previewIsCurrent,
  type OfficeLaunchOwnerState,
} from "./preview";

const context: ProjectionContext = {
  authGeneration: 4,
  selection: { workRef: "WS:ALPHA", rootJobId: "JOB-1" },
  sessionRef: "session:alpha", bindingGeneration: "generation:4",
  revisions: { mission: null, programs: null, result: null, conversation: null },
};
const projection = () => projectOffice({ mission: null, programs: null, result: null, conversation: null }, context);

describe("direction preview is inert context, never command authority", () => {
  it("freezes the draft and exact target without inventing permission or sending", () => {
    const view = projection();
    const preview = createDirectionPreview(view, "Finish the independent source work.");
    expect(preview.effectExpectation).toBe("NONE");
    expect(preview.draft).toBe("Finish the independent source work.");
    expect(preview.context.selection).toEqual({ workRef: "WS:ALPHA", rootJobId: "JOB-1" });
    expect(preview.commandPermission).toBe("NOT_PROJECTED");
    expect(preview.contentPermission).toBe("NOT_PROJECTED");
    expect(Object.isFrozen(preview)).toBe(true);
    expect(Object.isFrozen(preview.context)).toBe(true);
    expect(Object.isFrozen(preview.context.selection)).toBe(true);
    view.context.selection!.rootJobId = "JOB-2";
    expect(preview.context.selection!.rootJobId).toBe("JOB-1");
  });

  it.each([
    { authGeneration: 5 },
    { selection: { workRef: "WS:BETA", rootJobId: "JOB-1" } },
    { sessionRef: "session:beta" },
    { bindingGeneration: "generation:5" },
    { revisions: { ...context.revisions, mission: "revision:new" } },
  ])("invalidates a frozen preview when observed context changes: %j", (change) => {
    const preview = createDirectionPreview(projection(), "Retain this draft.");
    expect(previewIsCurrent(preview, { ...context, ...change })).toBe(false);
    expect(preview.draft).toBe("Retain this draft.");
  });

  it("does not attach unavailable source refs as current evidence", () => {
    const preview = createDirectionPreview(projection(), "A direction");
    expect(preview.contextRefs).toEqual([]);
    expect(previewIsCurrent(preview, context)).toBe(true);
  });
});

const owner: OfficeLaunchOwnerState = {
  configuredWorkstream: "WS:ALPHA",
  selectedWorkstream: "WS:ALPHA",
  launchAvailable: true,
  retainedGoal: "",
  commandHeld: false,
  handoffAlreadyOpen: false,
};

describe("Office launch handoff decision is inert and refuses rather than replaces", () => {
  it("opens the existing launch owner for a current frozen preview", () => {
    const preview = createDirectionPreview(projection(), "Ship the bounded launch slice.");
    expect(decideOfficeLaunchHandoff(preview, context, owner)).toEqual({ status: "OPENED" });
  });

  it("refuses a stale preview before anything else", () => {
    const preview = createDirectionPreview(projection(), "Ship the bounded launch slice.");
    expect(decideOfficeLaunchHandoff(preview, { ...context, authGeneration: 5 }, owner))
      .toEqual({ status: "REFUSED", reason: "PREVIEW_NOT_CURRENT" });
    expect(decideOfficeLaunchHandoff(preview, context, { ...owner, launchAvailable: false }))
      .toEqual({ status: "REFUSED", reason: "LAUNCH_OWNER_UNAVAILABLE" });
  });

  it("refuses rather than replace an existing unsent launch goal", () => {
    const preview = createDirectionPreview(projection(), "Ship the bounded launch slice.");
    expect(decideOfficeLaunchHandoff(preview, context, { ...owner, retainedGoal: "An existing goal" }))
      .toEqual({ status: "REFUSED", reason: "LAUNCH_GOAL_PRESERVED" });
    expect(decideOfficeLaunchHandoff(preview, context, { ...owner, retainedGoal: "   " }))
      .toEqual({ status: "OPENED" });
  });

  it("refuses while an original launch command is held on its own pointer", () => {
    const preview = createDirectionPreview(projection(), "Ship the bounded launch slice.");
    expect(decideOfficeLaunchHandoff(preview, context, { ...owner, commandHeld: true }))
      .toEqual({ status: "REFUSED", reason: "LAUNCH_COMMAND_HELD" });
  });

  it("revisits an already open handoff without a second owner or a replaced goal", () => {
    const preview = createDirectionPreview(projection(), "Ship the bounded launch slice.");
    expect(decideOfficeLaunchHandoff(preview, context, {
      ...owner, retainedGoal: "Ship the bounded launch slice.", handoffAlreadyOpen: true,
    })).toEqual({ status: "OPENED" });
  });

  it("refuses a selection that names another workstream than the configured launch", () => {
    const preview = createDirectionPreview(projection(), "Ship the bounded launch slice.");
    expect(decideOfficeLaunchHandoff(preview, context, { ...owner, selectedWorkstream: "WS:BETA" }))
      .toEqual({ status: "REFUSED", reason: "WORKSTREAM_MISMATCH" });
    expect(officeLaunchWorkstreamAgrees("WS:BETA", "WS:ALPHA")).toBe(false);
    expect(officeLaunchWorkstreamAgrees("WS:ALPHA", "WS:ALPHA")).toBe(true);
    // An unselected Office cannot borrow the normal launcher default.
    // Missing configuration cannot establish a match.
    expect(officeLaunchWorkstreamAgrees(null, "WS:ALPHA")).toBe(false);
    expect(officeLaunchWorkstreamAgrees("WS:ALPHA", null)).toBe(false);
    expect(officeLaunchWorkstreamAgrees(null, null)).toBe(false);
    expect(decideOfficeLaunchHandoff(preview, context, { ...owner, configuredWorkstream: null }))
      .toEqual({ status: "REFUSED", reason: "LAUNCH_OWNER_UNAVAILABLE" });
  });
});
