import { describe, expect, it } from "vitest";
import { alignDrafts, appendDraftSource, emptyDrafts, readDraft, readDraftInsertion, readDraftRevision, undoDraftSource, writeDraft } from "./drafts";
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

describe("one guarded source insertion in the existing draft owner", () => {
  const source = { identity: "exact-result:v1", excerpt: "Source text\n第二行", label: "Job result · historical · acceptance not projected" };
  it("preserves the complete original draft and adds the exact unsent excerpt once", () => {
    const before = writeDraft(emptyDrafts(3), context, "My original question.\n");
    const added = appendDraftSource(before, context, 1, source);
    expect(readDraft(added, context)).toBe("My original question.\n\n\n“Source text\n第二行”\nSource: Job result · historical · acceptance not projected");
    expect(readDraftRevision(added, context)).toBe(2);
    expect(appendDraftSource(added, context, 1, source)).toBe(added);
    expect(appendDraftSource(added, context, 2, source)).toBe(added);
    expect(readDraft(before, context)).toBe("My original question.\n");
  });
  it("undoes only its own unchanged insertion and preserves prior text byte for byte", () => {
    const before = writeDraft(emptyDrafts(3), context, "Exact prior text\n ");
    const added = appendDraftSource(before, context, 1, source);
    const undone = undoDraftSource(added, context, 2, source.identity);
    expect(readDraft(undone, context)).toBe(readDraft(before, context));
    expect(readDraftRevision(undone, context)).toBe(3);
    expect(readDraftInsertion(undone, context)).toBeNull();
    expect(undoDraftSource(undone, context, 2, source.identity)).toBe(undone);
  });
  it("never erases intervening typing, including text edited away and back", () => {
    const added = appendDraftSource(emptyDrafts(3), context, 0, source);
    const edited = writeDraft(added, context, "New private typing");
    const sameTextAgain = writeDraft(edited, context, readDraft(added, context));
    expect(undoDraftSource(edited, context, 1, source.identity)).toBe(edited);
    expect(undoDraftSource(sameTextAgain, context, 3, source.identity)).toBe(sameTextAgain);
    expect(appendDraftSource(sameTextAgain, context, 1, { ...source, identity: "next" })).toBe(sameTextAgain);
  });
  it("refuses stale auth, another scope, missing project and an obsolete revision", () => {
    const before = writeDraft(emptyDrafts(3), context, "Keep this");
    const added = appendDraftSource(before, context, 1, source);
    const changed = { ...context, selection: { workRef: "WS:B", rootJobId: "JOB-2" } };
    expect(appendDraftSource(before, context, 0, source)).toBe(before);
    expect(appendDraftSource(before, { ...context, selection: null }, 0, source)).toBe(before);
    expect(undoDraftSource(added, changed, 2, source.identity)).toBe(added);
    const cleared = alignDrafts(added, 4);
    expect(appendDraftSource(cleared, context, 1, source)).toBe(cleared);
    expect(undoDraftSource(cleared, context, 2, source.identity)).toBe(cleared);
    expect(JSON.stringify(cleared)).not.toContain(source.excerpt);
  });
  it("does not deduplicate unrelated user text and keeps only the last bounded insertion", () => {
    const before = writeDraft(emptyDrafts(3), context, source.excerpt);
    const first = appendDraftSource(before, context, 1, source);
    const second = appendDraftSource(first, context, 2, { ...source, identity: "another exact result" });
    expect(readDraftInsertion(second, context)?.before).toBe(readDraft(first, context));
    expect(undoDraftSource(second, context, 3, source.identity)).toBe(second);
  });
});
