// @vitest-environment jsdom
import { useState } from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { ConversationWindow } from "./ConversationWindow";
import { emptyDrafts, readDraft, writeDraft } from "./drafts";
import { decodeMissionv3 } from "../mission";
import { decodeWindow } from "../workspace-contract";
import { decodeResultEnvelope } from "../result";
import { projectOffice, type OfficeInput, type OfficeProjection, type ProjectionContext, type SourceState } from "../meta-ceo/projection";
import fixture from "../fixtures/window-mission-association-producer.json";
import resultFixture from "../fixtures/result-design-available-reject-unicode.json";

afterEach(cleanup);
async function input() {
  const context: ProjectionContext = { authGeneration: 3,
    selection: { workRef: fixture.selection.work_ref, rootJobId: fixture.selection.root_job_id },
    sessionRef: null, bindingGeneration: null,
    revisions: { mission: "m1", programs: null, result: null, conversation: "w1" } };
  const source = { owner: "EXECUTIVE_OS", ref: "private:mission", revision: "m1", observed_at: "2026-10-04T08:00:00Z", state: "CURRENT" as const, coverage: "COMPLETE" };
  const reads: OfficeInput = { programs: null, result: null,
    mission: { context, source, value: decodeMissionv3(structuredClone(fixture.mission), context.selection!) },
    conversation: { context, source: { ...source, owner: "CURRENT_WINDOW", ref: "private:window", revision: "w1", coverage: "OBSERVED_WINDOW" }, value: await decodeWindow(structuredClone(fixture.window)) } };
  return { reads, context, projection: projectOffice(reads, context) };
}
function Harness({ projection }: { projection: OfficeProjection }) {
  const [drafts, setDrafts] = useState(() => emptyDrafts(projection.context.authGeneration));
  const [away, setAway] = useState(false);
  return <><button onClick={() => setAway(value => !value)}>Navigation detour</button>
    {!away && <ConversationWindow projection={projection} draft={readDraft(drafts, projection.context)}
      onDraftChange={text => setDrafts(state => writeDraft(state, projection.context, text))} />}</>;
}

describe("Atelier observed conversation window", () => {
  it.each([false, true])("attaches result evidence only to the observed Job/Attempt, exact=%s", async exact => {
    const { reads, context } = await input();
    const result = decodeResultEnvelope(structuredClone(resultFixture), {
      workRef: resultFixture.selection.work_ref, rootJobId: resultFixture.selection.root_job_id,
      jobId: resultFixture.selection.job_id, attemptId: resultFixture.selection.attempt_id,
      resultEnvelopeDigest: resultFixture.selection.result_envelope_digest,
    })!;
    const window = reads.conversation!.value!;
    if (window.schema !== "mastermind.workspace.window_read_candidate.v2") throw new Error("V2 fixture required");
    const binding = window.observation_binding;
    const job = exact ? binding.job_id : "JOB-987";
    const attempt = exact ? binding.attempt_id : "ATT-" + "b".repeat(32);
    // Labelled composition fixture: two individually valid owner result tuples
    // under one Mission, while the observed window remains tied to its own tuple.
    result.selection = { ...result.selection, work_ref: context.selection!.workRef,
      root_job_id: context.selection!.rootJobId, job_id: job, attempt_id: attempt };
    result.source_observation.selection = { ...result.selection };
    result.result!.selection = { ...result.result!.selection, root_job_id: context.selection!.rootJobId,
      job_id: job, attempt_id: attempt };
    result.result!.content!.summary = "Only the exact returned result.";
    const mission = reads.mission!.value!;
    if (mission.schema !== "mastermind.mission_workspace.v3") throw new Error("V3 fixture required");
    mission.result_refs.refs = [
      { ...result.result!.selection, orchestration_role: result.result!.role, validation: "UNVALIDATED" },
      { ...result.result!.selection, job_id: exact ? "JOB-987" : binding.job_id,
        attempt_id: exact ? "ATT-" + "b".repeat(32) : binding.attempt_id,
        result_envelope_digest: "c".repeat(64), orchestration_role: result.result!.role, validation: "UNVALIDATED" },
    ];
    mission.source.owner_observation!.control_room = structuredClone(result.source_observation.control_room);
    mission.result_refs.generation = { ...result.result!.generation };
    context.revisions.result = "r1";
    reads.result = { context, source: { ...reads.mission!.source, ref: "private:other-result", revision: "r1" }, value: result };
    const projection = projectOffice(reads, context);
    expect(projection.result.source.state).toBe("CURRENT");
    expect(projection.result.value).not.toBeNull();
    expect(projection.conversation.value).not.toBeNull();
    render(<Harness projection={projection} />);
    fireEvent.click(screen.getByRole("button", { name: "Review evidence" }));
    expect(!!screen.queryByText("Only the exact returned result.")).toBe(exact);
    expect(!!screen.queryByText("private:other-result")).toBe(exact);
    if (!exact) expect(screen.getByText("Result source · UNASSOCIATED for this window. Review and acceptance remain separate.")).toBeTruthy();
  });
  it("renders the decoded owner window without inventing a session or transcript", async () => {
    const { projection } = await input();
    render(<Harness projection={projection} />);
    const text = projection.conversation.value!.view.items.find(item => item.text)!.text!;
    expect(screen.getByText(text)).toBeTruthy();
    expect(screen.getByText("Observed Job/Attempt association")).toBeTruthy();
    expect(screen.getByText("Session identity has not been supplied for this window.")).toBeTruthy();
    expect(screen.getByRole<HTMLButtonElement>("button", { name: "Send message" }).disabled).toBe(true);
    expect(document.body.textContent).not.toContain("All conversations");
  });
  it("preserves an unsent draft through evidence, context and navigation detours", async () => {
    render(<Harness projection={(await input()).projection} />);
    fireEvent.change(screen.getByRole("textbox", { name: "Unsent draft" }), { target: { value: "Retain my exact draft.\n继续" } });
    fireEvent.click(screen.getByRole("button", { name: "Review evidence" }));
    const panel = screen.getByRole("region", { name: "Conversation evidence" });
    expect(document.activeElement).toBe(panel);
    expect(screen.getByText("private:window")).toBeTruthy();
    fireEvent.keyDown(panel, { key: "Escape" });
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Review evidence" }));
    fireEvent.click(screen.getByRole("button", { name: "Context" }));
    fireEvent.click(screen.getByRole("button", { name: "Close context" }));
    fireEvent.click(screen.getByRole("button", { name: "Navigation detour" }));
    fireEvent.click(screen.getByRole("button", { name: "Navigation detour" }));
    expect(screen.getByRole<HTMLTextAreaElement>("textbox", { name: "Unsent draft" }).value).toBe("Retain my exact draft.\n继续");
  });
  it.each<SourceState>(["STALE", "UNKNOWN", "UNAVAILABLE", "WITHHELD", "UNASSOCIATED"])("retains truthful %s semantics", async state => {
    const { reads, context } = await input(); reads.conversation!.source.state = state;
    render(<Harness projection={projectOffice(reads, context)} />);
    expect(screen.getByText(state)).toBeTruthy();
    const text = reads.conversation!.value!.view.items.find(item => item.text)!.text!;
    if (state !== "STALE") expect(screen.queryByText(text)).toBeNull();
    if (state === "STALE") expect(screen.getByText("Retained window; current conversation state is not established.")).toBeTruthy();
    if (state === "WITHHELD") { expect(document.body.textContent).not.toContain("private:"); expect(screen.queryByRole("textbox")).toBeNull(); }
  });
  it.each(["auth", "target", "revision", "session", "binding"])("withdraws inspected content synchronously at a %s boundary", async boundary => {
    const { reads, context, projection } = await input();
    const { rerender } = render(<Harness projection={projection} />);
    fireEvent.click(screen.getByRole("button", { name: "Review evidence" }));
    const next = structuredClone(context);
    if (boundary === "auth") next.authGeneration++;
    if (boundary === "target") next.selection!.rootJobId = "JOB-999";
    if (boundary === "revision") next.revisions.conversation = "w2";
    if (boundary === "session") next.sessionRef = "new-session";
    if (boundary === "binding") next.bindingGeneration = 2;
    rerender(<Harness projection={projectOffice(reads, next)} />);
    expect(screen.queryByRole("region", { name: "Conversation evidence" })).toBeNull();
    expect(document.body.textContent).not.toContain("private:window");
    expect(screen.queryByText(reads.conversation!.value!.view.items.find(item => item.text)!.text!)).toBeNull();
  });
  it("keeps unknown effect and independent receipts visible without a resend control", async () => {
    const { reads, context } = await input(); reads.mission!.value!.transport.dispatch_state = "EFFECT_UNKNOWN";
    render(<Harness projection={projectOffice(reads, context)} />);
    expect(screen.getByRole("alert").textContent).toContain("original operation");
    expect(screen.getByRole("region", { name: "Independent receipts" }).textContent).toContain("acceptanceNOT_PROJECTED");
    expect(screen.queryByRole("button", { name: /retry|resend|failover|stop/i })).toBeNull();
  });
});
