// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { useState } from "react";
import { MetaCeoOffice } from "./MetaCeoOffice";
import { projectOffice, type OfficeInput, type ProjectionContext, type SourceState } from "./projection";
import { decodeMission } from "../mission";
import currentMission from "../fixtures/mission-v2-current-128c46f6.json";

afterEach(cleanup);
const context: ProjectionContext = { authGeneration: 1, selection: { workRef: "WS:ONE", rootJobId: "JOB-1" }, sessionRef: null, bindingGeneration: null, revisions: { mission: "rev:1", programs: null, result: null, conversation: null } };
function input(): OfficeInput {
  const raw = structuredClone(currentMission);
  raw.read_state = { state: "CURRENT", reason_codes: [], usable_sections: raw.read_state.usable_sections };
  return { programs: null, result: null, conversation: null, mission: {
    context,
    source: { owner: "EXECUTIVE_OS", ref: "mission:JOB-1", revision: "rev:1", observed_at: "2026-10-03T10:00:00Z", state: "CURRENT", coverage: "COMPLETE" },
    value: decodeMission(raw, context.selection!)!,
  } };
}

describe("Daily Office consumer", () => {
  it.each(["current", "stale", "unknown"] as const)("requires current owner receipts for Chairman attention: %s", freshness => {
    const reads = input();
    reads.mission!.value!.principal.owed_turn = { seat: "chairman", reason: "Reserved decision from owner.",
      source_refs: [{ owner: "EXECUTIVE_OS", ref: "decision:one", observed_at: "2026-10-04T08:00:00Z", freshness }] };
    render(<MetaCeoOffice projection={projectOffice(reads, context)} draft={{ text: "", context }} onDraftChange={() => {}} />);
    const attention = screen.getByRole("region", { name: freshness === "current" ? "The owner has requested Chairman attention." : "Chairman attention is not established." });
    expect(attention.textContent.includes("Reserved decision from owner.")).toBe(freshness === "current");
  });
  it("puts the qualified answer before movement and exposes missing producers", () => {
    render(<MetaCeoOffice projection={projectOffice(input(), context)} draft={{ text: "", context }} onDraftChange={() => {}} />);
    expect(screen.getByRole("heading", { name: "Keep the whole company moving with intention." })).toBeTruthy();
    expect(screen.getByRole("region", { name: "Meta-CEO answer" }).textContent).toContain("One");
    expect(screen.getByText(/Company total is not established/)).toBeTruthy();
    expect(screen.getByText(/Work details are unavailable/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: /^send$/i })).toBeNull();
  });

  it.each<SourceState>(["CURRENT", "STALE", "UNKNOWN", "UNAVAILABLE", "WITHHELD", "UNASSOCIATED"])("renders %s by name without substituting a healthy empty state", (state) => {
    const reads = input();
    reads.mission!.source.state = state;
    render(<MetaCeoOffice projection={projectOffice(reads, context)} draft={{ text: "", context }} onDraftChange={() => {}} />);
    expect(within(screen.getByRole("region", { name: "Source qualification" })).getAllByText(state).length).toBeGreaterThan(0);
    expect(screen.queryByText("No work")).toBeNull();
  });

  it("keeps the draft through evidence and preview inspection with keyboard focus return", () => {
    function ControlledOffice() {
      const [draft, setDraft] = useState("Keep the exact session context.");
      return <MetaCeoOffice projection={projectOffice(input(), context)} draft={{ text: draft, context }} onDraftChange={setDraft} />;
    }
    render(<ControlledOffice />);
    fireEvent.click(screen.getByRole("button", { name: "Review sources" }));
    expect(screen.getByRole("complementary", { name: "Source evidence" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Review direction preview" }));
    const preview = screen.getByRole("region", { name: "Direction preview" });
    expect(preview.textContent).toContain("EFFECT_NONE");
    expect(preview.textContent).toContain("Keep the exact session context.");
    fireEvent.keyDown(preview, { key: "Escape" });
    expect(screen.queryByRole("region", { name: "Direction preview" })).toBeNull();
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Review direction preview" }));
    expect((screen.getByRole("textbox", { name: "Direction to Meta-CEO" }) as HTMLTextAreaElement).value).toBe("Keep the exact session context.");
  });

  it("labels a receipt digest and local acquisition time without calling them an owner clock or session ref", () => {
    const reads = input();
    reads.mission!.source.ref_kind = "CONTROL_ROOM_DOCUMENT_DIGEST";
    reads.mission!.source.observed_at_kind = "LOCAL_ACQUISITION";
    render(<MetaCeoOffice projection={projectOffice(reads, context)} draft={{ text: "", context }} onDraftChange={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: "Review sources" }));
    const evidence = screen.getByRole("complementary", { name: "Source evidence" });
    expect(evidence.textContent).toContain("Control Room document digest");
    expect(evidence.textContent).toContain("Locally acquired 2026-10-03T10:00:00Z");
  });

  it("clears an obsolete private preview synchronously on auth-generation change", () => {
    const { rerender } = render(<MetaCeoOffice projection={projectOffice(input(), context)} draft={{ text: "Private draft", context }} onDraftChange={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: "Review direction preview" }));
    rerender(<MetaCeoOffice projection={projectOffice(input(), { ...context, authGeneration: 2 })} draft={{ text: "Private draft", context }} onDraftChange={() => {}} />);
    expect(screen.queryByText("Private draft")).toBeNull();
    expect(screen.queryByRole("heading", { name: /^One:/ })).toBeNull();
    expect(screen.queryByRole("region", { name: "Direction preview" })).toBeNull();
  });

  it("keeps unknown effect prominent and never offers a resend", () => {
    const reads = input();
    reads.mission!.value!.transport.dispatch_state = "EFFECT_UNKNOWN";
    render(<MetaCeoOffice projection={projectOffice(reads, context)} draft={{ text: "", context }} onDraftChange={() => {}} />);
    expect(screen.getByRole("alert").textContent).toContain("Reconcile the original operation");
    expect(screen.queryByRole("button", { name: /resend|retry|switch account/i })).toBeNull();
  });
});
