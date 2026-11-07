// @vitest-environment jsdom
import { useRef, useState } from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { KnowledgeDraftCompanion, knowledgeDraftBinding, type KnowledgeDraftPort } from "./KnowledgeDraftCompanion";
import { appendDraftSource, emptyDrafts, readDraft, readDraftInsertion, readDraftRevision,
  undoDraftSource, writeDraft, type ConversationDrafts, type DraftSource } from "../conversations/drafts";
import type { Missionv3Document } from "../mission";
import { observedMissionAssociation, type WindowDocument } from "../workspace-contract";
import type { ResultSelection } from "../result";
import { sameTarget, type OfficeProjection, type ProjectionContext,
  type SourceClaim, type SourceState } from "../meta-ceo/projection";

afterEach(cleanup);

const ATTEMPT = "ATT-f762f805f4ab4567ab244aba0d106721";
const DIGEST = "52780b9d310fcfe2a95fc3f7f4a21426604eb2ce7fdbef6bc69414bdec85832a";

const SELECTION: ResultSelection = { workRef: "WS:ONE", rootJobId: "JOB-001", jobId: "JOB-002",
  attemptId: ATTEMPT, resultEnvelopeDigest: DIGEST };
const SOURCE: DraftSource = { identity: "plan-result-job002",
  excerpt: "The plan keeps the original scope and defers delivery ownership.",
  label: `Executive plan result · WS:ONE · JOB-002 · Revision ${DIGEST} · CURRENT observation · Freshness unverified · Acceptance not projected` };

function scopedContext(): ProjectionContext {
  return { authGeneration: 7, selection: { workRef: "WS:ONE", rootJobId: "JOB-001" },
    sessionRef: null, bindingGeneration: null,
    revisions: { mission: "m1", programs: null, result: null, conversation: "w1" } };
}

// Qualification fixtures are checked by the real observedMissionAssociation
// below, never by a mocked helper. The plan child, binding and attempt all
// describe one RUNNING job under the selected root.
function qualifiedWindow(binding = { job_id: "JOB-002", attempt_id: ATTEMPT }): WindowDocument {
  return { schema: "mastermind.workspace.window_read_candidate.v2",
    selection_ref: "managed-window:plan-original", view: { epoch: "original-window-epoch", terminal: false, coverage: "OBSERVED_WINDOW", observed_at: "2026-11-04T00:00:00Z" },
    observation_binding: binding } as unknown as WindowDocument;
}

function qualifiedMission(child: Record<string, unknown> = {},
  readState: "CURRENT" | "STALE" = "CURRENT"): Missionv3Document {
  return { schema: "mastermind.mission_workspace.v3", generated_at: "2026-11-04T00:00:00Z",
    program: { work_ref: "WS:ONE" },
    mission: { root_job_id: "JOB-001", runtime_root_state: "RESOLVED", root_job_ambiguous: false },
    read_state: { state: readState, reason_codes: [], usable_sections: ["program", "mission", "children"] },
    children: { state: "AVAILABLE", coverage: "COMPLETE", total_count: 1, overflow_count: null, items: [{
      job_id: "JOB-002", orchestration_role: "plan", parent_job_id: "JOB-001", depth: 1, status: "RUNNING",
      current_attempt_id: ATTEMPT,
      latest_attempt: { attempt_id: ATTEMPT, status: "RUNNING" }, ...child }] },
    source: { owner_observation: { state: "SAME", runtime: { schema: "mastermind.runtime_read_observation.v1",
      state: "SAME", after: 2, before: 2, snapshot_digest: "b025afa54ba7cb8ce68b287edbcd48023982a147252531b2c476b3de1937efeb",
      source_identity: "8f2ba172e5e975d5ab0f0965a4df9b53" } } } } as unknown as Missionv3Document;
}

function projectionFor(portContext: ProjectionContext, overrides: {
  missionState?: SourceState; conversationState?: SourceState;
  mission?: Missionv3Document; window?: WindowDocument } = {}): OfficeProjection {
  const claim = (owner: string, state: SourceState, coverage: string): SourceClaim =>
    ({ owner, ref: `private:${owner.toLowerCase()}`, revision: "r1", observed_at: "2026-11-04T00:00:00Z", state, coverage });
  return { schema: "mastermind.product_projection.v1", context: portContext,
    mission: { source: claim("EXECUTIVE_OS", overrides.missionState ?? "CURRENT", "COMPLETE"),
      value: overrides.mission ?? qualifiedMission(), reason: null },
    programs: { source: claim("EXECUTIVE_OS", "UNAVAILABLE", "NONE"), value: null, reason: "PROGRAMS_NOT_PROJECTED" },
    result: { source: claim("EXECUTIVE_OS", "UNAVAILABLE", "NONE"), value: null, reason: "RESULT_NOT_PROJECTED" },
    conversation: { source: claim("CURRENT_WINDOW", overrides.conversationState ?? "CURRENT", "OBSERVED_WINDOW"),
      value: overrides.window ?? qualifiedWindow(), reason: null },
    companyTotal: null,
    receipts: { delivery: null, pickup: null, start: null, effect: null, return: null, review: null, acceptance: null },
    work: { state: "UNAVAILABLE", reason: "WORK_PENDING_CUSTODY" },
    direction: { state: "UNAVAILABLE", reason: "MISSING_PRODUCER" } };
}

// The real drafts.ts reducers own all draft state here, exactly as the shell's
// useObservedConversation does; the companion only receives the typed port.
function Harness({ context, projection, source, selection, locale = "en", seed = "",
  withPort = true, portOverride, edit, userWriteText = "Newer user text." }: {
  context: ProjectionContext; projection: OfficeProjection; source: DraftSource | null;
  selection: ResultSelection; locale?: "en" | "zh-CN"; seed?: string; withPort?: boolean;
  portOverride?: (port: KnowledgeDraftPort) => KnowledgeDraftPort; edit?: () => void;
  userWriteText?: string;
}) {
  const [drafts, setDrafts] = useState<ConversationDrafts>(() => {
    const initial = emptyDrafts(context.authGeneration);
    return seed ? writeDraft(initial, context, seed) : initial;
  });
  const latest = useRef(drafts); latest.current = drafts;
  const publish = (next: ConversationDrafts): boolean => {
    if (next === latest.current) return false;
    latest.current = next; setDrafts(next); return true;
  };
  const owner: KnowledgeDraftPort = {
    projection,
    text: readDraft(drafts, projection.context),
    revision: readDraftRevision(drafts, projection.context),
    insertion: readDraftInsertion(drafts, projection.context),
    append: (appended, expectedRevision) => publish(appendDraftSource(latest.current, projection.context, expectedRevision, appended)),
    undo: (identity, expectedRevision) => publish(undoDraftSource(latest.current, projection.context, expectedRevision, identity)),
    edit,
  };
  const readBinding = useRef(knowledgeDraftBinding(context, owner));
  return <>
    <button type="button" onClick={() => publish(writeDraft(latest.current, context, userWriteText))}>Simulate user edit</button>
    <KnowledgeDraftCompanion source={source} selection={selection} context={context}
      port={withPort ? (portOverride ? portOverride(owner) : owner) : undefined} readBinding={readBinding.current} locale={locale} />
  </>;
}

function section(name = "Original draft"): HTMLElement {
  return screen.getByRole("region", { name });
}
function draftText(name = "Original draft"): string {
  return section(name).querySelector("p.knowledge-muted")?.textContent ?? "";
}
function unavailable(): void {
  expect(screen.queryByRole("button", { name: "Add excerpt to draft" })).toBeNull();
  expect(screen.queryByRole("button", { name: "Undo source insertion" })).toBeNull();
  expect(screen.getByRole("status").textContent).toBe("An eligible scoped draft is unavailable. Reading does not create one.");
}

describe("fixture qualification against the real association helper", () => {
  it("observes exactly the selected plan job and rejects broken shapes", () => {
    const context = scopedContext();
    const mission = qualifiedMission();
    expect(observedMissionAssociation(qualifiedWindow(), mission, context.selection)).toEqual({
      state: "OBSERVED_MISSION_ASSOCIATION", job_id: "JOB-002", attempt_id: ATTEMPT,
      window_observed_at: "2026-11-04T00:00:00Z", mission_generated_at: "2026-11-04T00:00:00Z" });
    expect(observedMissionAssociation(qualifiedWindow({ job_id: "JOB-009", attempt_id: ATTEMPT }), mission, context.selection)).toBeNull();
    expect(observedMissionAssociation(qualifiedWindow(), qualifiedMission({}, "STALE"), context.selection)).toBeNull();
    expect(sameTarget(context, structuredClone(context))).toBe(true);
    expect(sameTarget(context, { ...context, sessionRef: "session-b" })).toBe(false);
  });
});

describe("exact excerpt insertion and conditional undo", () => {
  it("shows the literal draft, inserts the exact excerpt and label once, then undo preserves the original", () => {
    const context = scopedContext();
    render(<Harness context={context} projection={projectionFor(context)} source={SOURCE} selection={SELECTION}
      seed="Keep my original question." />);
    expect(draftText()).toBe("Keep my original question.");
    expect(screen.getByRole("heading", { name: "Your unsent notes" })).toBeTruthy();
    expect(screen.getByText("Adds the excerpt and its source label to the original draft. Nothing is sent.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /send/i })).toBeNull();
    const add = screen.getByRole<HTMLButtonElement>("button", { name: "Add excerpt to draft" });
    expect(add.disabled).toBe(false);
    fireEvent.click(add);
    expect(draftText()).toBe(`Keep my original question.\n\n“${SOURCE.excerpt}”\nSource: ${SOURCE.label}`);
    expect(screen.getByRole("status").textContent).toBe("Added to draft · Not sent");
    expect(section().querySelector("blockquote")?.textContent).toBe(SOURCE.excerpt);
    expect(section().querySelector("details p")?.textContent).toBe(SOURCE.label);
    expect(add.disabled).toBe(true);
    fireEvent.click(screen.getByRole<HTMLButtonElement>("button", { name: "Undo source insertion" }));
    expect(draftText()).toBe("Keep my original question.");
    expect(screen.getByRole("status").textContent).toBe("Source insertion removed. Your original draft is preserved.");
    expect(screen.queryByRole("button", { name: "Undo source insertion" })).toBeNull();
    expect(screen.getByRole<HTMLButtonElement>("button", { name: "Add excerpt to draft" }).disabled).toBe(true);
  });

  it("never overwrites a newer user edit, even if the text is edited back", () => {
    const context = scopedContext();
    const edit = vi.fn();
    const harness = (userWriteText: string) => <Harness context={context} projection={projectionFor(context)}
      source={SOURCE} selection={SELECTION} seed="Keep my original question." edit={edit} userWriteText={userWriteText} />;
    const { rerender } = render(harness("Newer user text."));
    fireEvent.click(screen.getByRole<HTMLButtonElement>("button", { name: "Add excerpt to draft" }));
    const inserted = draftText();
    fireEvent.click(screen.getByRole<HTMLButtonElement>("button", { name: "Simulate user edit" }));
    expect(draftText()).toBe("Newer user text.");
    expect(screen.queryByRole("button", { name: "Undo source insertion" })).toBeNull();
    fireEvent.click(screen.getByRole<HTMLButtonElement>("button", { name: "Edit draft" }));
    expect(edit).toHaveBeenCalledTimes(1);
    rerender(harness(inserted));
    fireEvent.click(screen.getByRole<HTMLButtonElement>("button", { name: "Simulate user edit" }));
    expect(draftText()).toBe(inserted);
    expect(screen.queryByRole("button", { name: "Undo source insertion" })).toBeNull();
    expect(screen.getByRole<HTMLButtonElement>("button", { name: "Edit draft" })).toBeTruthy();
    expect(edit).toHaveBeenCalledTimes(1);
  });

  it("re-captures the revision baseline when the exact source changes", () => {
    const context = scopedContext();
    const next: DraftSource = { ...SOURCE, identity: "plan-result-job002-v2",
      excerpt: "The revised plan narrows the delivery scope." };
    const harness = (source: DraftSource) => <Harness context={context} projection={projectionFor(context)}
      source={source} selection={SELECTION} seed="Original question." />;
    const { rerender } = render(harness(SOURCE));
    fireEvent.click(screen.getByRole<HTMLButtonElement>("button", { name: "Simulate user edit" }));
    expect(screen.getByRole<HTMLButtonElement>("button", { name: "Add excerpt to draft" }).disabled).toBe(true);
    rerender(harness(next));
    const add = screen.getByRole<HTMLButtonElement>("button", { name: "Add excerpt to draft" });
    expect(add.disabled).toBe(false);
    fireEvent.click(add);
    expect(draftText()).toBe(`Newer user text.\n\n“${next.excerpt}”\nSource: ${next.label}`);
    expect(screen.getByRole("status").textContent).toBe("Added to draft · Not sent");
    fireEvent.click(screen.getByRole<HTMLButtonElement>("button", { name: "Undo source insertion" }));
    expect(draftText()).toBe("Newer user text.");
  });
});

describe("qualification gates", () => {
  it("hides the draft and every action when the port is missing", () => {
    const context = scopedContext();
    render(<Harness context={context} projection={projectionFor(context)} source={SOURCE} selection={SELECTION}
      seed="Keep my original question." withPort={false} />);
    expect(section().textContent).not.toContain("Keep my original question.");
    expect(section().textContent).not.toContain(SOURCE.excerpt);
    unavailable();
  });

  const MISMATCHES: [string, (context: ProjectionContext) => {
    projection?: OfficeProjection; selection?: ResultSelection;
    portOverride?: (port: KnowledgeDraftPort) => KnowledgeDraftPort }][] = [
    ["auth generation", context => {
      const portContext = { ...context, authGeneration: context.authGeneration + 1 };
      return { projection: projectionFor(portContext),
        portOverride: port => ({ ...port, text: "STALE PORT TEXT" }) };
    }],
    ["session target", context => ({ projection: projectionFor({ ...context, sessionRef: "session-b" }) })],
    ["selection tuple", () => ({ selection: { ...SELECTION, workRef: "WS:TWO" } })],
    ["window association", context => ({ projection: projectionFor(context,
      { window: qualifiedWindow({ job_id: "JOB-009", attempt_id: ATTEMPT }) }) })],

  ];
  it.each(MISMATCHES)("hides the draft for a %s mismatch", (_name, build) => {
    const context = scopedContext();
    const extra = build(context);
    render(<Harness context={context} projection={extra.projection ?? projectionFor(context)}
      source={SOURCE} selection={extra.selection ?? SELECTION} seed="Keep my original question."
      portOverride={extra.portOverride} />);
    expect(section().textContent).not.toContain("Keep my original question.");
    expect(section().textContent).not.toContain("STALE PORT TEXT");
    expect(section().textContent).not.toContain(SOURCE.excerpt);
    unavailable();
  });

  it("requires a current destination observation and suppresses revoked content", () => {
    const context = scopedContext();
    const common = { context, source: SOURCE, selection: SELECTION, seed: "Keep my original question." };
    const { rerender } = render(<Harness {...common} projection={projectionFor(context)} />);
    expect(screen.getByRole<HTMLButtonElement>("button", { name: "Add excerpt to draft" })).toBeTruthy();
    for (const projection of [projectionFor(context, { conversationState: "STALE" }),
      projectionFor(context, { missionState: "STALE" }),
      projectionFor(context, { conversationState: "WITHHELD" }),
      projectionFor(context, { mission: qualifiedMission({}, "STALE") })]) {
      rerender(<Harness {...common} projection={projection} />);
      expect(section().textContent).not.toContain("Keep my original question.");
      unavailable();
    }
  });

  it("adds a qualified same-root completed source from a different child to the original plan draft", () => {
    const context = scopedContext();
    const sourceSelection = { ...SELECTION, jobId: "JOB-003", attemptId: "ATT-00000000000000000000000000000003" };
    render(<Harness context={context} projection={projectionFor(context)} selection={sourceSelection}
      source={SOURCE} seed="Original planning question." />);
    fireEvent.click(screen.getByRole<HTMLButtonElement>("button", { name: "Add excerpt to draft" }));
    expect(draftText()).toBe(`Original planning question.\n\n“${SOURCE.excerpt}”\nSource: ${SOURCE.label}`);
  });

  it("withholds the draft after original destination binding changes during a read", () => {
    const context = scopedContext();
    const common = { context, source: SOURCE, selection: SELECTION, seed: "Private original draft." };
    const { rerender } = render(<Harness {...common} projection={projectionFor(context)} />);
    const attempt = "ATT-00000000000000000000000000000000";
    rerender(<Harness {...common} projection={projectionFor(context, {
      window: qualifiedWindow({ job_id: "JOB-002", attempt_id: attempt }),
      mission: qualifiedMission({ current_attempt_id: attempt,
        latest_attempt: { attempt_id: attempt, status: "RUNNING" } }) })} />);
    unavailable();
    expect(section().textContent).not.toContain("Private original draft.");
  });

  it("checks revocation immediately before append even without a parent repaint", () => {
    const context = scopedContext(), projection = projectionFor(context), append = vi.fn(() => true);
    const port: KnowledgeDraftPort = { projection, text: "Private text", revision: 1, insertion: null,
      append, undo: vi.fn(() => true) };
    const binding = knowledgeDraftBinding(context, port);
    render(<KnowledgeDraftCompanion source={SOURCE} selection={SELECTION} context={context}
      port={port} readBinding={binding} />);
    projection.conversation.source.state = "WITHHELD";
    fireEvent.click(screen.getByRole<HTMLButtonElement>("button", { name: "Add excerpt to draft" }));
    expect(append).not.toHaveBeenCalled();
    expect(section().textContent).not.toContain("Private text");
    unavailable();
  });
});

describe("composition safety", () => {
  it("never appends from an IME composition Enter and keeps the action available", () => {
    const context = scopedContext();
    render(<Harness context={context} projection={projectionFor(context)} source={SOURCE} selection={SELECTION}
      seed="Keep my original question." />);
    const add = screen.getByRole<HTMLButtonElement>("button", { name: "Add excerpt to draft" });
    expect(fireEvent.keyDown(add, { key: "Enter", keyCode: 229 })).toBe(false);
    expect(draftText()).toBe("Keep my original question.");
    expect(fireEvent.keyDown(add, { key: "Enter", isComposing: true })).toBe(false);
    expect(draftText()).toBe("Keep my original question.");
    expect(fireEvent.keyDown(add, { key: "Enter" })).toBe(true);
    fireEvent.click(add);
    expect(draftText()).toBe(`Keep my original question.\n\n“${SOURCE.excerpt}”\nSource: ${SOURCE.label}`);
  });
});

describe("static zh-CN copy", () => {
  it("localizes the companion without translating the source bytes", () => {
    const context = scopedContext();
    render(<Harness context={context} projection={projectionFor(context)} source={SOURCE} selection={SELECTION}
      seed="保留我的问题。" locale="zh-CN" />);
    expect(screen.getByRole("region", { name: "原草稿" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "你的未发送笔记" })).toBeTruthy();
    expect(screen.getByText("原草稿")).toBeTruthy();
    expect(screen.getByText("将摘录和来源标注添加到原草稿。不会发送任何内容。")).toBeTruthy();
    fireEvent.click(screen.getByRole<HTMLButtonElement>("button", { name: "将摘录添加到草稿" }));
    expect(screen.getByRole("status").textContent).toBe("已添加到草稿 · 未发送");
    expect(draftText("原草稿")).toBe(`保留我的问题。\n\n“${SOURCE.excerpt}”\nSource: ${SOURCE.label}`);
    expect(section("原草稿").querySelector("blockquote")?.textContent).toBe(SOURCE.excerpt);
    fireEvent.click(screen.getByRole<HTMLButtonElement>("button", { name: "撤销来源插入" }));
    expect(draftText("原草稿")).toBe("保留我的问题。");
    expect(screen.getByRole("status").textContent).toBe("已移除插入的来源，原草稿已保留。");
    expect(section("原草稿").querySelector("details summary")?.textContent).toBe("草稿中的来源标注");
  });
});
