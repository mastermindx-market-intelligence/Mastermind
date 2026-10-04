// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { useState } from "react";
import { MetaCeoOffice } from "./MetaCeoOffice";
import { projectOffice, type OfficeInput, type ProjectionContext, type SourceState } from "./projection";
import { decodeMission } from "../mission";
import { missionFixture } from "../test-fixtures";

afterEach(cleanup);
const context: ProjectionContext = { authGeneration: 1, selection: { workRef: "WS:ALPHA", rootJobId: "JOB-ROOT" }, sessionRef: null, bindingGeneration: null, revisions: { mission: "rev:1", programs: null, result: null, conversation: null } };
function input(): OfficeInput {
  const raw = missionFixture();
  raw.read_state = { state: "CURRENT", reason_codes: [], usable_sections: raw.read_state.usable_sections };
  return { programs: null, result: null, conversation: null, mission: {
    context,
    source: { owner: "EXECUTIVE_OS", ref: "mission:JOB-ROOT", revision: "rev:1", observed_at: "2026-10-03T10:00:00Z", state: "CURRENT", coverage: "COMPLETE" },
    value: decodeMission(raw, context.selection!)!,
  } };
}

describe("Daily Office consumer", () => {
  it("puts the qualified answer before movement and exposes missing producers", () => {
    render(<MetaCeoOffice projection={projectOffice(input(), context)} draft={{ text: "", context }} onDraftChange={() => {}} />);
    expect(screen.getByRole("heading", { name: "Today, through one Meta-CEO." })).toBeTruthy();
    expect(screen.getByRole("region", { name: "Meta-CEO answer" }).textContent).toContain("Alpha program");
    expect(screen.getByText(/Company total is not established/)).toBeTruthy();
    expect(screen.getByText(/Work is awaiting source-custody reconciliation/)).toBeTruthy();
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

  it("clears an obsolete private preview synchronously on auth-generation change", () => {
    const { rerender } = render(<MetaCeoOffice projection={projectOffice(input(), context)} draft={{ text: "Private draft", context }} onDraftChange={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: "Review direction preview" }));
    rerender(<MetaCeoOffice projection={projectOffice(input(), { ...context, authGeneration: 2 })} draft={{ text: "Private draft", context }} onDraftChange={() => {}} />);
    expect(screen.queryByText("Private draft")).toBeNull();
    expect(screen.queryByText("Alpha program")).toBeNull();
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
