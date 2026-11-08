// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Knowledge, type KnowledgeProps } from "./Knowledge";
import { projectOffice, type OfficeInput, type ProjectionContext, type SourceState } from "../meta-ceo/projection";
import { decodeMission, type EvidenceRef } from "../mission";
import type { ResultSelection } from "../result";
import fixture from "../fixtures/mission-v2-current-128c46f6.json";

afterEach(cleanup);

const HEX = (ch: string) => ch.repeat(64);
const LIST_RUNTIME = {
  schema: "mastermind.runtime_read_observation.v1",
  state: "SAME",
  source_identity: "8f2ba172e5e975d5ab0f0965a4df9b53",
  before: 2,
  after: 2,
};
const CONTROL_ROOM = {
  instance_before: "control-room-instance",
  instance_after: "control-room-instance",
  publication_before: 11,
  publication_after: 11,
  document_digest: HEX("a"),
  source_validity_digest: HEX("b"),
  cache_currentness_digest: HEX("c"),
};

// Existing-owner index shape whose first row is the exact-read click target.
const INDEX = {
  schema: "mastermind.fabric_result_reference_index.v1",
  root_job_id: "JOB-1",
  snapshot_digest:
    "b025afa54ba7cb8ce68b287edbcd48023982a147252531b2c476b3de1937efeb",
  generation: LIST_RUNTIME,
  availability: "AVAILABLE",
  refs: [
    {
      root_job_id: "JOB-1",
      job_id: "JOB-002",
      attempt_id: "ATT-f762f805f4ab4567ab244aba0d106721",
      result_envelope_digest:
        "52780b9d310fcfe2a95fc3f7f4a21426604eb2ce7fdbef6bc69414bdec85832a",
      orchestration_role: "plan",
      validation: "UNVALIDATED",
    },
    {
      root_job_id: "JOB-1",
      job_id: "JOB-003",
      attempt_id: "ATT-0f7521645e5b462da6c3890da7575125",
      result_envelope_digest:
        "e3f365cc856fd9b205c16485cd148dd795baf794147f370530c384f3a66d3bbb",
      orchestration_role: "work",
      validation: "UNVALIDATED",
    },
  ],
  absent_job_ids: ["JOB-1"],
  omitted_job_ids: [],
  truncated: false,
};

const FIRST_REF = INDEX.refs[0];
const EXACT: ResultSelection = {
  workRef: "WS:ONE",
  rootJobId: "JOB-1",
  jobId: FIRST_REF.job_id,
  attemptId: FIRST_REF.attempt_id,
  resultEnvelopeDigest: FIRST_REF.result_envelope_digest,
};

const availableBody = (catalogueFreshness: "CURRENT" | "STALE" = "CURRENT") => ({
  schema: "mastermind.workspace_result_references.v1",
  selection: { work_ref: "WS:ONE", root_job_id: "JOB-1" },
  availability: "AVAILABLE",
  reason_codes: [],
  index: { ...INDEX },
  source_observation: {
    schema: "mastermind.workspace_source_observation.v1",
    state: "SAME",
    selection: { work_ref: "WS:ONE", root_job_id: "JOB-1" },
    control_room: CONTROL_ROOM,
    runtime: LIST_RUNTIME,
  },
  catalogue: { generated_at: "2026-10-31T15:45:00Z", freshness: catalogueFreshness },
});

const RESULT_RUNTIME = {
  schema: "mastermind.runtime_read_observation.v1",
  state: "SAME",
  source_identity: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  before: 7,
  after: 7,
};

const resultBody = (summary = "Retained work result.") => ({
  schema: "mastermind.workspace_role_result.v1",
  selection: {
    work_ref: EXACT.workRef,
    root_job_id: EXACT.rootJobId,
    job_id: EXACT.jobId,
    attempt_id: EXACT.attemptId,
    result_envelope_digest: EXACT.resultEnvelopeDigest,
  },
  availability: "AVAILABLE",
  reason_codes: [],
  source_observation: {
    schema: "mastermind.workspace_result_observation.v1",
    state: "SAME",
    selection: {
      work_ref: EXACT.workRef,
      root_job_id: EXACT.rootJobId,
      job_id: EXACT.jobId,
      attempt_id: EXACT.attemptId,
      result_envelope_digest: EXACT.resultEnvelopeDigest,
    },
    control_room: {
      instance_before: "control-room-instance",
      instance_after: "control-room-instance",
      publication_before: 3,
      publication_after: 3,
      document_digest: HEX("d"),
      source_validity_digest: HEX("e"),
      cache_currentness_digest: HEX("f"),
    },
    runtime: RESULT_RUNTIME,
  },
  result: {
    schema: "mastermind.fabric_role_result_view.v1",
    selection: {
      root_job_id: EXACT.rootJobId,
      job_id: EXACT.jobId,
      attempt_id: EXACT.attemptId,
      result_envelope_digest: EXACT.resultEnvelopeDigest,
    },
    role: "work",
    execution_status: "COMPLETED",
    acceptance: "NOT_PROJECTED",
    role_result_digest: HEX("1"),
    generation: RESULT_RUNTIME,
    availability: "AVAILABLE",
    content_complete: true,
    review: null,
    counts: { findings: null, next_actions: 1 },
    content: {
      role_result: { outcome: "retained", notes: ["Follow the exact reference through its owner."] },
      summary,
      next_actions: ["Inspect the retained result."],
    },
    omitted: [],
  },
});

const unreadableResultBody = (availability: "UNAVAILABLE" | "CONTENT_OVER_BUDGET", reason: string) => {
  const base = resultBody();
  if (availability === "CONTENT_OVER_BUDGET") return { ...base, availability, reason_codes: [reason],
    result: { ...base.result, availability, content: null, content_complete: false,
      omitted: ["role_result", "summary", "next_actions"] } };
  return { ...base, availability, reason_codes: [reason], result: null,
    source_observation: { ...base.source_observation, state: "UNKNOWN", control_room: null, runtime: null } };
};

const context: ProjectionContext = { authGeneration: 1, selection: { workRef: "WS:ONE", rootJobId: "JOB-1" },
  sessionRef: null, bindingGeneration: "host-gen-7", revisions: { mission: "rev:1", programs: null, result: null, conversation: null } };

function input(state: SourceState = "CURRENT"): OfficeInput {
  const raw = structuredClone(fixture);
  raw.read_state.state = "CURRENT";
  const mission = decodeMission(raw, context.selection!)!;
  for (const section of [mission.program, mission.mission, mission.principal, mission.execution, mission.review, mission.transport, mission.acceptance, mission.posture]) section.evidence = [];
  mission.program.evidence = [{ owner: "GITHUB", ref: "https://github.com/example/repo/pull/42", field: "review", source_revision: "exact:42",
    source_time: "2026-10-01T10:00:00Z", observed_at: "2026-10-04T08:00:00Z", freshness_state: "CURRENT" } as EvidenceRef];
  return { programs: null, result: null, conversation: null, mission: { context, value: mission,
    source: { owner: "EXECUTIVE_OS", ref: "mission:JOB-1", revision: "rev:1", observed_at: "2026-10-04T08:00:00Z", state, coverage: "COMPLETE" } } };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(res => { resolve = res; });
  return { promise, resolve: (value: T) => resolve(value) };
}

const HOST_GENERATION = "host-gen-7";

function renderKnowledge(overrides: {
  projection?: ReturnType<typeof projectOffice>;
  readResultReferences?: ReturnType<typeof vi.fn>;
  readResult?: ReturnType<typeof vi.fn>;
  hostGeneration?: string | number;
  onOpenSource?: ReturnType<typeof vi.fn>;
} = {}) {
  const readResultReferences = overrides.readResultReferences ?? vi.fn(async () => availableBody());
  const readResult = overrides.readResult ?? vi.fn(async () => resultBody());
  return {
    readResultReferences,
    readResult,
    view: (next: { projection?: ReturnType<typeof projectOffice>; hostGeneration?: string | number } = {}) =>
      <Knowledge
        projection={next.projection ?? overrides.projection ?? projectOffice(input(), context)}
        hostGeneration={next.hostGeneration ?? overrides.hostGeneration ?? HOST_GENERATION}
        readResultReferences={readResultReferences as unknown as KnowledgeProps["readResultReferences"]}
        readResult={readResult as unknown as KnowledgeProps["readResult"]}
        onOpenSource={overrides.onOpenSource as unknown as KnowledgeProps["onOpenSource"]}
      />,
  };
}

describe("Knowledge retained-result source reading", () => {
  it("mounts through real Knowledge, lists retained results and opens an exact result", async () => {
    const user = userEvent.setup();
    const k = renderKnowledge();
    render(k.view());
    await user.click(screen.getByRole("button", { name: "Show retained results" }));
    await screen.findByRole("button", { name: "Open retained result — JOB-002" });
    expect(k.readResultReferences).toHaveBeenCalledExactlyOnceWith({
      workRef: "WS:ONE", rootJobId: "JOB-1", signal: expect.any(AbortSignal),
    });
    await user.click(screen.getByRole("button", { name: "Open retained result — JOB-002" }));
    await screen.findByRole("button", { name: "Back to retained results" });
    expect(k.readResult).toHaveBeenCalledExactlyOnceWith({ ...EXACT, signal: expect.any(AbortSignal) });
    const body = document.body.textContent ?? "";
    // Exact summary, next action and the complete role_result JSON, rendered inert.
    expect(body).toContain("Retained work result.");
    expect(body).toContain("Inspect the retained result.");
    expect(body).toContain('"outcome": "retained"');
    expect(body).toContain("Follow the exact reference through its owner.");
    expect(body).toContain("Content complete");
    expect(body).toContain("Omitted fields");
    // Provenance companion: actual read receipt, unverified freshness, Executive
    // ownership, unknown source time, verbatim identifiers. No draft affordance.
    expect(body).toContain("Unchanged during this read");
    expect(body).toContain(RESULT_RUNTIME.source_identity);
    expect(body).toContain(EXACT.attemptId);
    expect(body).toContain(EXACT.resultEnvelopeDigest);
    expect(body).toContain("Not verified");
    expect(body).toContain("EXECUTIVE_OS");
    expect(body).toContain("An eligible scoped draft is unavailable. Reading does not create one.");
    expect(screen.queryByRole("button", { name: /Add excerpt/i })).toBeNull();
    await user.click(screen.getByRole("button", { name: "Back to retained results" }));
    expect(screen.queryByRole("button", { name: "Back to retained results" })).toBeNull();
    expect(screen.getByRole("button", { name: "Open retained result — JOB-002" })).toBeTruthy();
  });

  it("keeps the summary exact by default and renders the formatted preview inert", async () => {
    const user = userEvent.setup();
    const markup = 'See [notes](https://example.com/notes) now. <script>window.__marked = 1</script> <img src=x onerror="window.__broken = 1">';
    render(renderKnowledge({ readResult: vi.fn(async () => resultBody(markup)) }).view());
    await user.click(screen.getByRole("button", { name: "Show retained results" }));
    await user.click(await screen.findByRole("button", { name: "Open retained result — JOB-002" }));
    await screen.findByRole("button", { name: "Back to retained results" });
    // Default is the exact text: markup stays visible as text, nothing executed.
    expect(document.body.textContent).toContain("[notes](https://example.com/notes)");
    expect(document.querySelector("script")).toBeNull();
    await user.click(screen.getByText("Formatted preview"));
    expect(document.querySelector("script")).toBeNull();
    expect(document.querySelector("[onerror]")).toBeNull();
    const links = Array.from(document.querySelectorAll("a"));
    for (const link of links) expect((link.getAttribute("href") ?? "").startsWith("http")).toBe(false);
    expect(document.body.textContent).toContain("https://example.com/notes");
  });

  it("shows owner-reported unavailable content with verbatim reason codes and keeps the return point", async () => {
    const user = userEvent.setup();
    render(renderKnowledge({ readResult: vi.fn(async () => unreadableResultBody("UNAVAILABLE", "SOURCE_UNAVAILABLE")) }).view());
    await user.click(screen.getByRole("button", { name: "Show retained results" }));
    await user.click(await screen.findByRole("button", { name: "Open retained result — JOB-002" }));
    await screen.findByRole("button", { name: "Back to retained results" });
    const body = document.body.textContent ?? "";
    expect(body).toContain("SOURCE_UNAVAILABLE");
    expect(body).toContain("The owner did not supply this result's content.");
    // Partial source context: actual metadata stays, content does not appear.
    expect(body).toContain(EXACT.attemptId);
    expect(body).toContain(EXACT.resultEnvelopeDigest);
    expect(body).not.toContain("Retained work result.");
    expect(screen.getByRole("button", { name: "Back to retained results" })).toBeTruthy();
  });

  it("labels over-budget content as over budget without inventing content", async () => {
    const user = userEvent.setup();
    render(renderKnowledge({ readResult: vi.fn(async () => unreadableResultBody("CONTENT_OVER_BUDGET", "CONTENT_OVER_BUDGET")) }).view());
    await user.click(screen.getByRole("button", { name: "Show retained results" }));
    await user.click(await screen.findByRole("button", { name: "Open retained result — JOB-002" }));
    await screen.findByRole("button", { name: "Back to retained results" });
    const body = document.body.textContent ?? "";
    expect(body).toContain("CONTENT_OVER_BUDGET");
    expect(body).toContain("This result's content is over its display budget.");
    expect(body).not.toContain("Retained work result.");
  });

  it("says truthfully what is missing when no host result functions are supplied", () => {
    const k = renderKnowledge();
    render(<Knowledge projection={projectOffice(input(), context)} hostGeneration={HOST_GENERATION} />);
    const body = document.body.textContent ?? "";
    expect(body).toContain("the host result functions were not supplied");
    expect(body).toContain("Saved results aren’t available in this view yet.");
    expect(body).not.toContain("ACCESS_DENIED");
    expect(screen.queryByRole("button", { name: "Show retained results" })).toBeNull();
    expect(k.readResultReferences).not.toHaveBeenCalled();
  });

  it("reads historical sources as historical with catalogue freshness stated, never promoted", async () => {
    const user = userEvent.setup();
    render(renderKnowledge({
      projection: projectOffice(input("STALE"), context),
      readResultReferences: vi.fn(async () => availableBody("STALE")),
    }).view());
    await user.click(screen.getByRole("button", { name: "Show retained results" }));
    await screen.findByRole("button", { name: "Open retained result — JOB-002" });
    const body = document.body.textContent ?? "";
    expect(body).toContain("Mission state");
    expect(body).toContain("Historical");
    expect(body).toContain("Historical navigation does not establish a current Mission.");
    expect(body).toContain("Source age limit exceeded");
    expect(body).toContain("2026-10-31T15:45:00Z");
  });

  it.each([
    { label: "auth generation", rerender: (k: ReturnType<typeof renderKnowledge>) =>
      k.view({ projection: projectOffice(input(), { ...context, authGeneration: 2 }) }) },
    { label: "selection", rerender: (k: ReturnType<typeof renderKnowledge>) =>
      k.view({ projection: projectOffice(input(), { ...context, selection: { workRef: "WS:ONE", rootJobId: "JOB-009" } }) }) },
    { label: "host generation", rerender: (k: ReturnType<typeof renderKnowledge>) =>
      k.view({ hostGeneration: "host-gen-8" }) },
  ])("aborts and clears a pending list read when the $label changes, denying the late reply", async ({ rerender }) => {
    const user = userEvent.setup();
    const pending = deferred<unknown>();
    const k = renderKnowledge({ readResultReferences: vi.fn(() => pending.promise) });
    const r = render(k.view());
    await user.click(screen.getByRole("button", { name: "Show retained results" }));
    await screen.findByText("Reading the retained list…");
    const searchBefore = screen.getByRole("searchbox", { name: "Search supplied knowledge" }) as HTMLInputElement;
    expect(searchBefore.value).toBe("");
    fireEvent.change(searchBefore, { target: { value: "held search" } });
    r.rerender(rerender(k));
    expect(screen.queryByText("Reading the retained list…")).toBeNull();
    expect(screen.queryByRole("button", { name: /Open retained result/ })).toBeNull();
    expect(screen.getByRole("button", { name: "Show retained results" })).toBeTruthy();
    const searchAfter = screen.getByRole("searchbox", { name: "Search supplied knowledge" }) as HTMLInputElement;
    expect(searchAfter.value).toBe("");
    await act(async () => { pending.resolve(availableBody()); });
    expect(screen.queryByRole("button", { name: /Open retained result/ })).toBeNull();
    expect(document.body.textContent).not.toContain("JOB-002");
    expect(k.readResult).not.toHaveBeenCalled();
  });

  it("keeps the supplied evidence-reference callback compatible alongside the retained band", async () => {
    const user = userEvent.setup();
    const open = vi.fn();
    render(renderKnowledge({ onOpenSource: open }).view());
    fireEvent.click(screen.getByRole("button", { name: "Inspect Program · review" }));
    const detail = screen.getByRole("region", { name: "Selected source reference" });
    expect(detail.textContent).toContain("exact:42");
    fireEvent.click(screen.getByRole("button", { name: "Open original source" }));
    expect(open).toHaveBeenCalledExactlyOnceWith({
      owner: "GITHUB", ref: "https://github.com/example/repo/pull/42", revision: "exact:42", mode: "current",
    });
    expect(screen.getByRole("button", { name: "Show retained results" })).toBeTruthy();
  });

  it("retains the supplied-metadata search across opening a result and returning", async () => {
    const user = userEvent.setup();
    const k = renderKnowledge();
    render(k.view());
    const search = screen.getByRole("searchbox", { name: "Search supplied knowledge" }) as HTMLInputElement;
    fireEvent.change(search, { target: { value: "review" } });
    await user.click(screen.getByRole("button", { name: "Show retained results" }));
    await user.click(await screen.findByRole("button", { name: "Open retained result — JOB-002" }));
    await screen.findByRole("button", { name: "Back to retained results" });
    expect(screen.queryByRole("searchbox", {name:"Search supplied knowledge"})).toBeNull();
    expect(search.value).toBe("review");
    await user.click(screen.getByRole("button", { name: "Back to retained results" }));
    const searchAfter = screen.getByRole("searchbox", { name: "Search supplied knowledge" }) as HTMLInputElement;
    expect(searchAfter.value).toBe("review");
    expect(screen.getByRole("button", { name: "Inspect Program · review" })).toBeTruthy();
    expect(k.readResultReferences).toHaveBeenCalledTimes(1);
  });
});
