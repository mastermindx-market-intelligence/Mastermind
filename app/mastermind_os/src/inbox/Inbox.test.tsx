// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Inbox } from "./Inbox";
import { decodeMission } from "../mission";
import { projectOffice, type OfficeInput, type ProjectionContext, type SourceState } from "../meta-ceo/projection";
import fixture from "../fixtures/mission-v2-current-128c46f6.json";

afterEach(cleanup);
const context: ProjectionContext = {
  authGeneration: 3, selection: { workRef: "WS:ONE", rootJobId: "JOB-1" },
  sessionRef: "session:one", bindingGeneration: 4,
  revisions: { mission: "mission:1", programs: null, result: null, conversation: null },
};
function input(): OfficeInput {
  const raw = structuredClone(fixture);
  raw.read_state = { ...raw.read_state, state: "CURRENT", reason_codes: [] };
  const value = decodeMission(raw, context.selection!)!;
  value.principal.owed_turn = { seat: "chairman", reason: "Decide the exact release scope.",
    source_refs: [{ owner: "EXECUTIVE_OS", ref: "private:attention-one", observed_at: "2026-10-04T07:00:00Z", freshness: "current" }] };
  return { programs: null, result: null, conversation: null, mission: { context,
    source: { owner: "EXECUTIVE_OS", ref: "private:mission-one", revision: "mission:1", observed_at: "2026-10-04T07:00:01Z", state: "CURRENT", coverage: "COMPLETE" }, value } };
}

describe("owner-defined Inbox", () => {
  it("shows a source-backed Chairman request and navigates only the exact project", () => {
    const navigate = vi.fn();
    render(<Inbox projection={projectOffice(input(), context)} onNavigateMission={navigate} />);
    expect(screen.getByRole("region", { name: "Needs you" }).textContent).toContain("Decide the exact release scope.");
    fireEvent.click(screen.getByRole("button", { name: "Open project" }));
    expect(navigate).toHaveBeenCalledExactlyOnceWith(context.selection, "current");
    expect(screen.getByText("Company-wide attention coverage is not established.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /approve|submit|send|dismiss|retry/i })).toBeNull();
  });

  it.each(["ceo", "coo", "worker"] as const)("keeps the %s turn with its actual owner", seat => {
    const reads = input(); reads.mission!.value!.principal.owed_turn!.seat = seat;
    render(<Inbox projection={projectOffice(reads, context)} />);
    expect(screen.getByRole("region", { name: "With the team" }).textContent).toContain(seat.toUpperCase());
    expect(screen.getByRole("region", { name: "Needs you" }).textContent).not.toContain("Decide the exact release scope.");
    expect(screen.getByText("No Chairman request is qualified in the supplied scope.")).toBeTruthy();
  });

  it.each(["missing turn", "missing references", "unknown seat", "stale reference"])("does not invent attention from %s", mode => {
    const reads = input(), m = reads.mission!.value!;
    m.execution.state = "FAILED"; m.review.verdict = "reject";
    if (mode === "missing turn") m.principal.owed_turn = null;
    if (mode === "missing references") m.principal.owed_turn!.source_refs = [];
    if (mode === "unknown seat") m.principal.owed_turn!.seat = "unknown";
    if (mode === "stale reference") m.principal.owed_turn!.source_refs[0]!.freshness = "stale";
    render(<Inbox projection={projectOffice(reads, context)} />);
    expect(screen.getByText("No Chairman request is qualified in the supplied scope.")).toBeTruthy();
    expect(screen.queryByText("Decide the exact release scope.")).toBeNull();
    expect(screen.queryByText(/all clear|nothing needs/i)).toBeNull();
  });

  it.each<SourceState>(["STALE", "UNKNOWN", "UNAVAILABLE", "WITHHELD", "UNASSOCIATED"])("keeps %s distinct without claiming current attention", state => {
    const reads = input(); reads.mission!.source.state = state;
    render(<Inbox projection={projectOffice(reads, context)} />);
    expect(screen.getByText(state)).toBeTruthy();
    expect(screen.getByRole("region", { name: "Needs you" }).textContent).not.toContain("Decide the exact release scope.");
    expect(screen.queryByRole("button", { name: "Open project" })).toBeNull();
    if (state === "WITHHELD") expect(document.body.textContent).not.toContain("private:");
  });

  it("exposes retained attention only as history", () => {
    const reads = input(); reads.mission!.source.state = "STALE";
    const navigate = vi.fn();
    render(<Inbox projection={projectOffice(reads, context)} onNavigateMission={navigate} />);
    expect(screen.getByText("Retained owner request; current attention is not established.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Inspect retained project history" }));
    expect(navigate).toHaveBeenCalledExactlyOnceWith(context.selection, "history");
  });

  it("preserves independent receipt states and freezes unknown-effect commands", () => {
    const reads = input(), m = reads.mission!.value!;
    m.transport.dispatch_state = "EFFECT_UNKNOWN";
    m.review.verdict = "approve"; m.acceptance.state = "NOT_PROJECTED";
    render(<Inbox projection={projectOffice(reads, context)} />);
    expect(screen.getByRole("alert").textContent).toContain("Reconcile the original operation");
    const receipts = screen.getByRole("region", { name: "Independent receipts" });
    expect(receipts.textContent).toContain("reviewapprove");
    expect(receipts.textContent).toContain("acceptanceNOT_PROJECTED");
    expect(screen.queryByRole("button", { name: /resend|retry|launch|failover/i })).toBeNull();
  });

  it("opens exact evidence with keyboard focus and returns focus without navigation", () => {
    const navigate = vi.fn();
    render(<Inbox projection={projectOffice(input(), context)} onNavigateMission={navigate} />);
    fireEvent.click(screen.getByRole("button", { name: "View evidence" }));
    const evidence = screen.getByRole("region", { name: "Attention evidence" });
    expect(document.activeElement).toBe(evidence);
    expect(within(evidence).getByText("private:attention-one")).toBeTruthy();
    expect(within(evidence).getByText("private:mission-one")).toBeTruthy();
    fireEvent.keyDown(evidence, { key: "Escape" });
    expect(screen.queryByRole("region", { name: "Attention evidence" })).toBeNull();
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "View evidence" }));
    expect(navigate).not.toHaveBeenCalled();
  });

  it.each(["auth", "target", "revision"])("clears open private evidence synchronously on %s change", change => {
    const reads = input();
    const { rerender } = render(<Inbox projection={projectOffice(reads, context)} />);
    fireEvent.click(screen.getByRole("button", { name: "View evidence" }));
    const next = structuredClone(context);
    if (change === "auth") next.authGeneration += 1;
    if (change === "target") next.selection!.rootJobId = "JOB-2";
    if (change === "revision") next.revisions.mission = "mission:2";
    rerender(<Inbox projection={projectOffice(reads, next)} />);
    expect(screen.queryByRole("region", { name: "Attention evidence" })).toBeNull();
    expect(screen.queryByText("Decide the exact release scope.")).toBeNull();
    expect(screen.queryByText("private:attention-one")).toBeNull();
  });
});
