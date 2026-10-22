import { describe, expect, it } from "vitest";
import { projectOffice, type ProjectionContext } from "./projection";
import { createDirectionPreview, previewIsCurrent } from "./preview";

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
