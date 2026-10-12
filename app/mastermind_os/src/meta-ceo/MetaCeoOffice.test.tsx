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
    const sourcesButton = screen.getByRole("button", { name: "Review sources" });
    const previewButton = screen.getByRole("button", { name: "Review direction preview" });
    sourcesButton.focus();
    fireEvent.click(sourcesButton);
    const sources = screen.getByRole("complementary", { name: "Source evidence" });
    expect(document.activeElement).toBe(sources);
    previewButton.focus();
    fireEvent.click(previewButton);
    const preview = screen.getByRole("region", { name: "Direction preview" });
    expect(document.activeElement).toBe(preview);
    expect(preview.textContent).toContain("EFFECT_NONE");
    expect(preview.textContent).toContain("Keep the exact session context.");
    fireEvent.keyDown(document.activeElement!, { key: "Escape" });
    expect(screen.queryByRole("region", { name: "Direction preview" })).toBeNull();
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Review direction preview" }));
    expect(screen.getByRole("complementary", { name: "Source evidence" })).toBe(sources);
    sources.focus();
    fireEvent.keyDown(document.activeElement!, { key: "Escape" });
    expect(screen.queryByRole("complementary", { name: "Source evidence" })).toBeNull();
    expect(document.activeElement).toBe(sourcesButton);
    expect((screen.getByRole("textbox", { name: "Direction to Meta-CEO" }) as HTMLTextAreaElement).value).toBe("Keep the exact session context.");
  });

  it.each([
    ["Review sources", "complementary", "Source evidence", "Close sources"],
    ["Review direction preview", "region", "Direction preview", "Close preview"],
  ] as const)("opens and closes %s repeatedly with stable controls and focus", (triggerName, role, panelName, closeName) => {
    render(<MetaCeoOffice projection={projectOffice(input(), context)} draft={{ text: "Keep this draft.", context }} onDraftChange={() => {}} />);
    const trigger = screen.getByRole("button", { name: triggerName });
    expect(trigger.getAttribute("aria-expanded")).toBe("false");
    const panelId = trigger.getAttribute("aria-controls");
    expect(panelId).toBeTruthy();
    for (const dismissal of ["escape", "button", "escape"]) {
      trigger.focus();
      fireEvent.click(trigger);
      const panel = screen.getByRole(role, { name: panelName });
      expect(panel.id).toBe(panelId);
      expect(panel.tabIndex).toBe(-1);
      expect(trigger.getAttribute("aria-expanded")).toBe("true");
      expect(document.activeElement).toBe(panel);
      if (dismissal === "escape") fireEvent.keyDown(document.activeElement!, { key: "Escape" });
      else {
        const close = screen.getByRole("button", { name: closeName });
        close.focus();
        fireEvent.click(close);
      }
      expect(screen.queryByRole(role, { name: panelName })).toBeNull();
      expect(trigger.getAttribute("aria-expanded")).toBe("false");
      expect(document.activeElement).toBe(trigger);
    }
  });

  it("closes sources without closing the independently open preview", () => {
    render(<MetaCeoOffice projection={projectOffice(input(), context)} draft={{ text: "Keep this draft.", context }} onDraftChange={() => {}} />);
    const previewButton = screen.getByRole("button", { name: "Review direction preview" });
    previewButton.focus();
    fireEvent.click(previewButton);
    const preview = screen.getByRole("region", { name: "Direction preview" });
    const sourcesButton = screen.getByRole("button", { name: "Review sources" });
    sourcesButton.focus();
    fireEvent.click(sourcesButton);
    expect(document.activeElement).toBe(screen.getByRole("complementary", { name: "Source evidence" }));
    fireEvent.keyDown(document.activeElement!, { key: "Escape" });
    expect(document.activeElement).toBe(sourcesButton);
    expect(screen.getByRole("region", { name: "Direction preview" })).toBe(preview);
    preview.focus();
    fireEvent.keyDown(document.activeElement!, { key: "Escape" });
    expect(document.activeElement).toBe(previewButton);
  });

  it("does not refocus or dismiss either nonmodal panel on ordinary rerenders or outside focus", () => {
    const office = (text: string) => <MetaCeoOffice projection={projectOffice(input(), { ...context })} draft={{ text, context }} onDraftChange={() => {}} />;
    const { rerender } = render(office("Original draft"));
    fireEvent.click(screen.getByRole("button", { name: "Review sources" }));
    fireEvent.click(screen.getByRole("button", { name: "Review direction preview" }));
    const sources = screen.getByRole("complementary", { name: "Source evidence" });
    const preview = screen.getByRole("region", { name: "Direction preview" });
    const textbox = screen.getByRole("textbox", { name: "Direction to Meta-CEO" });
    textbox.focus();
    fireEvent.click(textbox);
    fireEvent.keyDown(document.activeElement!, { key: "Escape" });
    rerender(office("Edited draft"));
    expect(document.activeElement).toBe(textbox);
    expect(screen.getByRole("complementary", { name: "Source evidence" })).toBe(sources);
    expect(screen.getByRole("region", { name: "Direction preview" })).toBe(preview);
    expect(preview.textContent).toContain("Original draft");
    expect(preview.textContent).not.toContain("Edited draft");
    expect((textbox as HTMLTextAreaElement).value).toBe("Edited draft");
    sources.focus();
    rerender(office("Edited again"));
    expect(document.activeElement).toBe(sources);
    expect(preview.getAttribute("aria-modal")).toBeNull();
    expect(sources.getAttribute("aria-modal")).toBeNull();
  });

  it("focuses a newly generated preview without reopening or refocusing sources", () => {
    const office = (text: string) => <MetaCeoOffice projection={projectOffice(input(), context)} draft={{ text, context }} onDraftChange={() => {}} />;
    const { rerender } = render(office("Original draft"));
    fireEvent.click(screen.getByRole("button", { name: "Review sources" }));
    const sources = screen.getByRole("complementary", { name: "Source evidence" });
    const trigger = screen.getByRole("button", { name: "Review direction preview" });
    for (const text of ["Original draft", "Edited draft", "Edited draft"]) {
      rerender(office(text));
      trigger.focus();
      fireEvent.click(trigger);
      const preview = screen.getByRole("region", { name: "Direction preview" });
      expect(document.activeElement).toBe(preview);
      expect(preview.textContent).toContain(text);
      expect(screen.getByRole("complementary", { name: "Source evidence" })).toBe(sources);
    }
  });

  it.each([
    [{ ...context, authGeneration: 2 }, ""],
    [{ ...context, selection: { workRef: "WS:TWO", rootJobId: "JOB-1" } }, ""],
    [{ ...context, selection: { workRef: "WS:ONE", rootJobId: "JOB-2" } }, ""],
    [{ ...context, sessionRef: "session:other" }, ""],
    [{ ...context, bindingGeneration: 2 }, ""],
    [{ ...context, revisions: { ...context.revisions, mission: "rev:2" } }, "Private draft"],
  ] as const)("invalidates a preview without restoring or stealing outside focus: %j", (changedContext, expectedDraft) => {
    const office = (currentContext: ProjectionContext) => <MetaCeoOffice projection={projectOffice(input(), currentContext)} draft={{ text: "Private draft", context }} onDraftChange={() => {}} />;
    const { rerender } = render(office(context));
    fireEvent.click(screen.getByRole("button", { name: "Review direction preview" }));
    fireEvent.click(screen.getByRole("button", { name: "Review sources" }));
    const closeSources = screen.getByRole("button", { name: "Close sources" });
    closeSources.focus();
    rerender(office(changedContext));
    expect(screen.queryByRole("region", { name: "Direction preview" })).toBeNull();
    expect(screen.getByRole("button", { name: "Review direction preview" }).getAttribute("aria-expanded")).toBe("false");
    expect(document.activeElement).toBe(closeSources);
    expect((screen.getByRole("textbox", { name: "Direction to Meta-CEO" }) as HTMLTextAreaElement).value).toBe(expectedDraft);
    rerender(office(context));
    expect(screen.getByRole("region", { name: "Direction preview" })).toBeTruthy();
    expect(document.activeElement).toBe(closeSources);
    expect((screen.getByRole("textbox", { name: "Direction to Meta-CEO" }) as HTMLTextAreaElement).value).toBe("Private draft");
  });

  it("does not restore trigger focus during unmount", () => {
    const { unmount } = render(<MetaCeoOffice projection={projectOffice(input(), context)} draft={{ text: "Keep this draft.", context }} onDraftChange={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: "Review sources" }));
    fireEvent.click(screen.getByRole("button", { name: "Review direction preview" }));
    const outside = document.createElement("button");
    document.body.append(outside);
    outside.focus();
    unmount();
    expect(document.activeElement).toBe(outside);
    outside.remove();
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
