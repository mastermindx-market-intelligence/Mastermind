import { describe, expect, it } from "vitest";
import { captureObservedConversation, completeObservedConversation } from "./observation-adapter";
import { decodeMissionv3 } from "../mission";
import { decodeWindow } from "../workspace-contract";
import { projectOffice, type ProjectionContext } from "../meta-ceo/projection";
import fixture from "../fixtures/window-mission-association-producer.json";

const context: ProjectionContext = { authGeneration: 4, selection: { workRef: fixture.selection.work_ref, rootJobId: fixture.selection.root_job_id },
  sessionRef: null, bindingGeneration: null, revisions: { mission: null, programs: null, result: null, conversation: null } };
async function observed(current = context, change?: (window: NonNullable<Awaited<ReturnType<typeof decodeWindow>>>) => void) {
  const mission = decodeMissionv3(structuredClone(fixture.mission), context.selection!)!;
  const window = (await decodeWindow(structuredClone(fixture.window)))!; change?.(window);
  return completeObservedConversation(captureObservedConversation(context), current, mission, window, "2026-10-04T10:00:00Z");
}
describe("paired observed Conversation presentation", () => {
  it("retains the owner clock and publication metadata without manufacturing a session", async () => {
    const result = await observed(); if (result.kind !== "observed") throw new Error("Expected observation");
    const p = projectOffice(result.input, result.context);
    expect(p.conversation.source.state).toBe("CURRENT");
    expect(p.conversation.source.observed_at).toBe(fixture.window.view.observed_at);
    expect(p.conversation.source.revision).toContain(fixture.window.view.epoch);
    expect(p.conversation.source.revision).not.toContain("2026-10-04T10:00:00Z");
    expect(p.context.sessionRef).toBeNull(); expect(p.context.bindingGeneration).toBeNull();
    expect(p.conversation.value!.view.items[0].text).toBe(fixture.window.view.items[0].text);
  });
  it.each([
    { authGeneration: 5 }, { selection: { ...context.selection!, rootJobId: "JOB-OTHER" } },
    { sessionRef: "unrelated" }, { bindingGeneration: 1 },
    { revisions: { ...context.revisions, conversation: "newer" } },
  ])("discards changed context %j", async change => {
    expect((await observed({ ...context, ...change })).kind).toBe("discarded");
  });
  it("changes its derived observation identity when owner publication metadata changes", async () => {
    const a = await observed(), b = await observed(context, w => { w.view.items[0].publication_sequence++; });
    if (a.kind !== "observed" || b.kind !== "observed") throw new Error("Expected observations");
    expect(a.context.revisions.conversation).not.toBe(b.context.revisions.conversation);
  });
  it.each(["other-attempt", "terminal", "gap"])("withholds unassociated content for %s", async kind => {
    const result = await observed(context, w => {
      if (kind === "other-attempt" && w.schema === "mastermind.workspace.window_read_candidate.v2") w.observation_binding.attempt_id = "ATT-" + "a".repeat(32);
      if (kind === "terminal") w.view.terminal = true;
      if (kind === "gap") w.view.coverage = "GAP_PRESENT";
    });
    if (result.kind !== "observed") throw new Error("Expected reduced observation");
    const p = projectOffice(result.input, result.context);
    expect(p.conversation.source.state).toBe("UNASSOCIATED");
    expect(p.conversation.value).toBeNull(); expect(p.conversation.source.ref).toBeNull();
  });
  it("keeps a refused Window unavailable even with a qualified Mission", () => {
    const result = completeObservedConversation(captureObservedConversation(context), context,
      decodeMissionv3(structuredClone(fixture.mission), context.selection!), null, "2026-10-04T10:00:00Z");
    if (result.kind !== "observed") throw new Error("Expected reduced observation");
    expect(projectOffice(result.input, result.context).conversation.source.state).toBe("UNAVAILABLE");
  });
});
