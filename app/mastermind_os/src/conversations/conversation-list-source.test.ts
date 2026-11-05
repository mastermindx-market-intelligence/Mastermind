// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { bindMissionHost, createNativeClient } from "../host";
import { decodeMissionv3 } from "../mission";
import { projectOffice, type ProjectionContext } from "../meta-ceo/projection";
import { captureProgramsOfficeRead, completeProgramsOfficeRead } from "../meta-ceo/programs-adapter";
import { captureObservedConversation, completeObservedConversation } from "./observation-adapter";
import { composeConversationsList, isListedConversationProject, isListedCurrentConversation } from "./conversation-list-source";
import programs from "../fixtures/programs-available-workspace-service.json";
import paired from "../fixtures/window-mission-association-producer.json";
import { controlRoomFixture } from "../test-fixtures";

beforeEach(async () => {
  const { webcrypto } = await vi.importActual<{ webcrypto: Crypto }>("node:crypto");
  vi.stubGlobal("crypto", webcrypto);
});
afterEach(() => vi.unstubAllGlobals());

async function fixture() {
  const selection = { workRef: paired.selection.work_ref, rootJobId: paired.selection.root_job_id };
  const context: ProjectionContext = { authGeneration: 4, selection, sessionRef: null,
    bindingGeneration: null, revisions: { mission: null, programs: null, result: null, conversation: null } };
  const invoke = vi.fn(async (name: string) => {
    if (name === "auth_status") return { status: "signed_in", reason: null, acquisition: true, content: true };
    if (name === "executive_auth_status") return { generation: 0, available: false };
    // The retained service envelope is deliberately minimal. Reuse the same
    // strict full consumer fixture as the accepted Programs adapter tests.
    if (name === "read_programs") return { ...structuredClone(programs), control_room: controlRoomFixture() };
    if (name === "read_mission_v3") return structuredClone(paired.mission);
    if (name === "read_current_window") return structuredClone(paired.window);
    throw new Error("Unexpected fixture command");
  });
  const client = await createNativeClient(invoke as never, async () => () => {}), host = bindMissionHost(client);
  const signal = new AbortController().signal;
  const acquiredPrograms = await host.readProgramsObservation!({ signal });
  const p = completeProgramsOfficeRead(captureProgramsOfficeRead(context), context,
    acquiredPrograms, "2026-11-05T12:00:00Z");
  const mission = await host.readMissionV3!({ ...selection, signal });
  const window = await host.readCurrentWindow!({ signal });
  const c = completeObservedConversation(captureObservedConversation(context), context,
    decodeMissionv3(mission, selection), window, "2026-11-05T12:00:00Z");
  if (p.kind !== "observed" || c.kind !== "observed") throw new Error("Fixture observation refused");
  const catalogue = projectOffice({ mission: null, programs: p.snapshot, result: null, conversation: null }, p.context);
  const conversation = projectOffice(c.input, c.context);
  const input = { authGeneration: 4, catalogue, conversation,
    acquisitionAllowed: true, contentAllowed: true, hasUnsentDraft: true };
  return { input, invoke, host };
}

describe("CV01 existing producer projection", () => {
  it("joins real Host/receipt adapters into distinct current and project populations without body or history acquisition", async () => {
    const { input, invoke } = await fixture(), model = composeConversationsList(input);
    expect(model.recentState).toBe("CURRENT"); expect(model.projectsState).toBe("CURRENT");
    expect(model.recent).toHaveLength(1); expect(model.projects).toHaveLength(2);
    expect(model.recent[0].locator.workRef).toBe("WS:FABRIC");
    expect(model.projects[0].locator.workRef).toBe("WS:ALPHA");
    expect(model.recent[0].title).toBeNull();
    expect(model.recent[0].observedAt).toBe(paired.window.view.observed_at);
    expect(model.recent[0].unsentDraft).toBe(true);
    expect(model.historyCoverage).toBe("NOT_ENUMERATED");
    expect(JSON.stringify(model)).not.toContain(paired.window.view.items[0].text!);
    expect(JSON.stringify(model)).not.toContain('"saved"');
    expect(invoke.mock.calls.map(([name]) => name).filter(name => name.startsWith("read_")))
      .toEqual(["read_programs", "read_mission_v3", "read_current_window"]);
    expect(isListedCurrentConversation(model, model.recent[0].locator)).toBe(true);
    expect(isListedConversationProject(model, model.projects[0].locator)).toBe(true);
    expect(Object.isFrozen(model.recent[0].locator)).toBe(true);
  });
  it("withholds every prior epoch's name and source revision", async () => {
    const { input } = await fixture(), model = composeConversationsList({ ...input, authGeneration: 5 });
    expect(model.recentState).toBe("WITHHELD"); expect(model.projectsState).toBe("WITHHELD");
    expect(model.recent).toEqual([]); expect(model.projects).toEqual([]);
    expect(model.sources.every(source => source.revision === null && source.observedAt === null)).toBe(true);
  });
  it("keeps project fallback independent of withheld conversation Content", async () => {
    const { input } = await fixture(), model = composeConversationsList({ ...input, contentAllowed: false });
    expect(model.recentState).toBe("WITHHELD"); expect(model.recent).toEqual([]);
    expect(model.projectsState).toBe("CURRENT"); expect(model.projects).toHaveLength(2);
    const denied = composeConversationsList({ ...input, acquisitionAllowed: false });
    expect(denied.recent).toEqual([]); expect(denied.projects).toEqual([]);
  });
  it("discards a superseded window revision rather than representing it as an empty conversation", async () => {
    const { input } = await fixture(); input.conversation.context.revisions.conversation = "newer";
    const model = composeConversationsList(input);
    expect(model.recentState).toBe("STALE"); expect(model.recent).toEqual([]);
  });
  it("refuses a foreign binding or a source/value identity disagreement", async () => {
    const { input } = await fixture(); input.conversation.conversation.source.ref = "foreign";
    expect(composeConversationsList(input).recentState).toBe("UNASSOCIATED");
    input.conversation.context.selection = { ...input.conversation.context.selection!, rootJobId: "JOB-777" };
    expect(composeConversationsList(input).recent).toEqual([]);
  });
  it("does not choose one duplicate project or promote missing sources to qualified empty", async () => {
    const { input } = await fixture(); const document = input.catalogue.programs.value;
    if (!document || document.state !== "AVAILABLE") throw new Error("Fixture unavailable");
    document.programs.push({ ...document.programs[0] });
    const model = composeConversationsList(input);
    expect(model.projectsState).toBe("UNASSOCIATED"); expect(model.projects).toEqual([]);
    expect(model.recent).toHaveLength(1);
    input.catalogue.programs.source.state = "UNAVAILABLE";
    expect(composeConversationsList(input).projectsState).toBe("UNAVAILABLE");
  });
  it("records genuine bounded catalogue empty separately from absent current-window evidence", async () => {
    const { input } = await fixture(); const document = input.catalogue.programs.value;
    if (!document || document.state !== "AVAILABLE") throw new Error("Fixture unavailable");
    document.programs = []; input.conversation.conversation.source.state = "UNAVAILABLE";
    const model = composeConversationsList(input);
    expect(model.projectsState).toBe("CURRENT"); expect(model.projects).toEqual([]);
    expect(model.recentState).toBe("UNAVAILABLE"); expect(model.historyCoverage).toBe("NOT_ENUMERATED");
  });
  it("pending reads do not keep prior rows actionable", async () => {
    const { input } = await fixture(), model = composeConversationsList({ ...input, programsPending: true, windowPending: true });
    expect(model.recentState).toBe("PENDING"); expect(model.projectsState).toBe("PENDING");
    expect(model.recent).toEqual([]); expect(model.projects).toEqual([]);
  });
  it("preserves every exact locator dimension and refuses extra-field identities", async () => {
    const { input } = await fixture(), model = composeConversationsList(input), current = model.recent[0].locator;
    for (const [key, value] of Object.entries(current)) {
      if (key === "kind") continue;
      expect(isListedCurrentConversation(model, { ...current, [key]: typeof value === "number" ? value + 1 : value + "-foreign" })).toBe(false);
    }
    expect(isListedCurrentConversation(model, { ...current, extra: true } as typeof current)).toBe(false);
    const project = model.projects[0].locator;
    for (const key of ["workRef", "sourceRef", "sourceRevision"] as const)
      expect(isListedConversationProject(model, { ...project, [key]: project[key] + "-foreign" })).toBe(false);
  });
});
