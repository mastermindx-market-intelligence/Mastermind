// @vitest-environment jsdom
import { useRef, useState } from "react";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Knowledge } from "./Knowledge";
import type { KnowledgeDraftPort } from "./KnowledgeDraftCompanion";
import { appendDraftSource, emptyDrafts, readDraft, readDraftInsertion, readDraftRevision, undoDraftSource, writeDraft } from "../conversations/drafts";
import { decodeMissionv3 } from "../mission";
import { decodeWindow, observedMissionAssociation } from "../workspace-contract";
import { decodeResultEnvelope, type ResultSelection } from "../result";
import { decodeResultReferencesEnvelope, type ResultReferencesDocument } from "../result-references";
import { projectOffice, type OfficeProjection, type ProjectionContext } from "../meta-ceo/projection";
import type { MissionResultRead } from "../host";
import windowFixture from "../fixtures/window-mission-association-producer.json";
import resultFixture from "../fixtures/result-design-available-reject-unicode.json";

afterEach(cleanup);

async function fixture() {
  const context: ProjectionContext = { authGeneration: 3,
    selection: { workRef: windowFixture.selection.work_ref, rootJobId: windowFixture.selection.root_job_id },
    sessionRef: null, bindingGeneration: null,
    revisions: { mission: "m1", programs: null, result: null, conversation: "w1" } };
  const window = await decodeWindow(structuredClone(windowFixture.window));
  const mission = decodeMissionv3(structuredClone(windowFixture.mission), context.selection!);
  if (!window || !mission) throw new Error("Actual producer fixture must decode");
  const claim = { owner: "EXECUTIVE_OS", ref: "private:mission", revision: "m1",
    observed_at: "2026-10-04T08:00:00Z", state: "CURRENT" as const, coverage: "COMPLETE" };
  const projection = projectOffice({ programs: null, result: null,
    mission: { context, source: claim, value: mission },
    conversation: { context, source: { ...claim, owner: "CURRENT_WINDOW", ref: "private:window", revision: "w1", coverage: "OBSERVED_WINDOW" }, value: window },
  }, context);
  const result = structuredClone(resultFixture);
  result.selection.work_ref = context.selection!.workRef;
  result.selection.root_job_id = context.selection!.rootJobId;
  result.result.selection.root_job_id = context.selection!.rootJobId;
  result.source_observation.selection = { ...result.selection };
  const exact: ResultSelection = { workRef: result.selection.work_ref, rootJobId: result.selection.root_job_id,
    jobId: result.selection.job_id, attemptId: result.selection.attempt_id, resultEnvelopeDigest: result.selection.result_envelope_digest };
  const decodedResult = decodeResultEnvelope(result, exact);
  expect(decodedResult).not.toBeNull();
  const association = observedMissionAssociation(window, mission, context.selection);
  expect(association).not.toBeNull();
  expect(association!.job_id).not.toBe(exact.jobId);
  const list = decodeResultReferencesEnvelope({
    schema: "mastermind.workspace_result_references.v1", selection: { work_ref: exact.workRef, root_job_id: exact.rootJobId },
    availability: "AVAILABLE", reason_codes: [],
    index: { schema: "mastermind.fabric_result_reference_index.v1", root_job_id: exact.rootJobId,
      snapshot_digest: "b".repeat(64), generation: result.result.generation, availability: "AVAILABLE",
      refs: [{ ...result.result.selection, orchestration_role: result.result.role, validation: "UNVALIDATED" }],
      absent_job_ids: [exact.rootJobId], omitted_job_ids: [], truncated: false },
    source_observation: { ...result.source_observation, schema: "mastermind.workspace_source_observation.v1",
      selection: { work_ref: exact.workRef, root_job_id: exact.rootJobId } },
    catalogue: { generated_at: "2026-10-31T15:45:00Z", freshness: "CURRENT" },
  }, context.selection!);
  if (!list) throw new Error("Fixed owner index fixture must decode");
  return { projection, result, exact, list, context };
}

function Harness({ projection, draftProjection = projection, list, read, locale = "en" }: {
  projection: OfficeProjection; draftProjection?: OfficeProjection; list: ResultReferencesDocument;
  read: MissionResultRead; locale?: "en" | "zh-CN";
}) {
  const context = projection.context;
  const [drafts, setDrafts] = useState(() => writeDraft(emptyDrafts(context.authGeneration), context, "Keep my original question."));
  const latest = useRef(drafts); latest.current = drafts;
  const publish = (next: typeof drafts) => {
    if (next === latest.current) return false;
    latest.current = next; setDrafts(next); return true;
  };
  const readList = useRef(async () => list).current;
  const port: KnowledgeDraftPort = { projection: draftProjection,
    text: readDraft(drafts, context), revision: readDraftRevision(drafts, context), insertion: readDraftInsertion(drafts, context),
    append: (source, revision) => publish(appendDraftSource(latest.current, context, revision, source)),
    undo: (identity, revision) => publish(undoDraftSource(latest.current, context, revision, identity)) };
  return <Knowledge projection={projection} hostGeneration={8} locale={locale}
    readResultReferences={readList} readResult={read} draftPort={port} />;
}

async function open(jobId: string) {
  fireEvent.click(screen.getByRole("button", { name: "Show retained results" }));
  fireEvent.click(await screen.findByRole("button", { name: `Open retained result — ${jobId}` }));
}
function pending() {
  let resolve!: (value: unknown) => void;
  const promise = new Promise<unknown>(yes => { resolve = yes; });
  return { promise, resolve };
}

describe("Knowledge exact source to original scoped draft", () => {
  it("opens a decoded completed source from another same-root child, appends exact bytes and conditionally undoes", async () => {
    const f = await fixture(), read = vi.fn(async () => f.result);
    render(<Harness projection={f.projection} list={f.list} read={read} />);
    const search = screen.getByRole<HTMLInputElement>("searchbox", { name: "Search supplied knowledge" });
    fireEvent.change(search, { target: { value: "my evidence query" } });
    await open(f.exact.jobId);
    fireEvent.click(await screen.findByRole("button", { name: "Add excerpt to draft" }));
    const draft = screen.getByRole("region", { name: "Original draft" });
    expect(draft.textContent).toContain(`Keep my original question.\n\n“${f.result.result.content.summary}”\nSource: Executive review result`);
    expect(draft.textContent).toContain(f.exact.resultEnvelopeDigest);
    expect(draft.textContent).toContain("Freshness unverified");
    expect(draft.textContent).toContain("Added to draft · Not sent");
    expect(read).toHaveBeenCalledExactlyOnceWith({ ...f.exact, signal: expect.any(AbortSignal) });
    fireEvent.click(screen.getByRole("button", { name: "Undo source insertion" }));
    expect(draft.querySelector("p.knowledge-muted")?.textContent).toBe("Keep my original question.");
    fireEvent.click(screen.getByRole("button", { name: "Back to retained results" }));
    expect(search.value).toBe("my evidence query");
    expect(screen.queryByRole("button", { name: /send/i })).toBeNull();
  });

  it.each(["auth", "root", "session", "revocation", "window epoch"])("keeps source readable but withholds a draft whose %s changed during acquisition", async kind => {
    const f = await fixture(), held = pending(), read = vi.fn<MissionResultRead>(() => held.promise);
    const view = render(<Harness projection={f.projection} list={f.list} read={read} />);
    await open(f.exact.jobId);
    await screen.findByText("Reading the exact result…");
    const changed = structuredClone(f.projection);
    if (kind === "auth") changed.context.authGeneration++;
    if (kind === "root") changed.context.selection = { ...changed.context.selection!, rootJobId: "JOB-999" };
    if (kind === "session") changed.context.sessionRef = "another-original-session";
    if (kind === "revocation") changed.conversation.source.state = "WITHHELD";
    if (kind === "window epoch") changed.conversation.value!.view.epoch = "e".repeat(64);
    view.rerender(<Harness projection={f.projection} draftProjection={changed} list={f.list} read={read} />);
    await act(async () => { held.resolve(f.result); });
    expect(await screen.findByRole("article", { name: "Retained result document" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Add excerpt to draft" })).toBeNull();
    const draft = screen.getByRole("region", { name: "Original draft" });
    expect(draft.textContent).not.toContain("Keep my original question.");
    expect(draft.textContent).toContain("An eligible scoped draft is unavailable");
  });

  it("aborts a pending source and rejects late completion after the source auth epoch changes", async () => {
    const f = await fixture(), held = pending(), read = vi.fn<MissionResultRead>(() => held.promise);
    const view = render(<Harness projection={f.projection} list={f.list} read={read} />);
    await open(f.exact.jobId);
    await screen.findByText("Reading the exact result…");
    const next = structuredClone(f.projection); next.context.authGeneration++;
    view.rerender(<Harness projection={next} list={f.list} read={read} />);
    expect(read.mock.calls[0][0].signal.aborted).toBe(true);
    await act(async () => { held.resolve(f.result); });
    expect(screen.queryByRole("article", { name: "Retained result document" })).toBeNull();
    expect(screen.queryByRole("region", { name: "Original draft" })).toBeNull();
  });
});
