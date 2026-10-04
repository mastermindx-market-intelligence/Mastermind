import { describe, expect, it } from "vitest";
import { alignDrafts, emptyDrafts, readDraft, writeDraft } from "./drafts";
import type { ProjectionContext } from "../meta-ceo/projection";

const context: ProjectionContext = { authGeneration: 3, selection: { workRef: "WS:A", rootJobId: "JOB-1" },
  sessionRef: null, bindingGeneration: null, revisions: { mission: null, programs: null, conversation: null, result: null } };

describe("ephemeral scoped unsent drafts", () => {
  it("survives a route detour and source revision change without addressing or sending", () => {
    const state = writeDraft(emptyDrafts(3), context, "Keep the exact draft.\n第二行");
    const other = { ...context, selection: { workRef: "WS:B", rootJobId: "JOB-2" } };
    expect(readDraft(state, other)).toBe("");
    expect(readDraft(state, { ...context, revisions: { ...context.revisions, mission: "new" } })).toBe("Keep the exact draft.\n第二行");
    expect(Object.keys(state)).toEqual(["authGeneration", "entries"]);
  });
  it.each([
    { selection: { workRef: "WS:B", rootJobId: "JOB-1" } },
    { selection: { workRef: "WS:A", rootJobId: "JOB-2" } },
    { sessionRef: "owner-session" }, { bindingGeneration: "next" },
  ])("never transfers a draft to another target: %j", change => {
    const state = writeDraft(emptyDrafts(3), context, "Private draft");
    expect(readDraft(state, { ...context, ...change })).toBe("");
    expect(readDraft(state, context)).toBe("Private draft");
  });
  it("clears all drafts at an auth boundary and rejects a late old-auth write", () => {
    const state = alignDrafts(writeDraft(emptyDrafts(3), context, "Private draft"), 4);
    expect(JSON.stringify(state)).not.toContain("Private draft");
    const late = writeDraft(state, context, "Late private value");
    expect(late).toBe(state);
    expect(readDraft(late, context)).toBe("");
    expect(readDraft(late, { ...context, authGeneration: 4 })).toBe("");
  });
  it("does not mutate a previous React state snapshot", () => {
    const before = emptyDrafts(3), after = writeDraft(before, context, "New draft");
    expect(readDraft(before, context)).toBe("");
    expect(readDraft(after, context)).toBe("New draft");
  });
});
