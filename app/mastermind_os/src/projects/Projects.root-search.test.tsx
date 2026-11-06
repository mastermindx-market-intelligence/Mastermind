// @vitest-environment jsdom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ProgramCard, MissionSelection } from "../mission";
import type { OfficeProjection, SourceState } from "../meta-ceo/projection";
import { projectOffice } from "../meta-ceo/projection";
import { captureProgramsOfficeRead, completeProgramsOfficeRead } from "../meta-ceo/programs-adapter";
import { decodeProgramsObservation } from "../programs-observation";
import availablePrograms from "../fixtures/programs-available-workspace-service.json";
import controlRoom from "../fixtures/control-room-b5-c20a3cf8.json";
import { Projects } from "./Projects";

const one: ProgramCard = { workRef: "WS:ONE", title: "Shared project", state: "In review", nextAction: "Inspect the return", nextActionWithheld: false, rootJobId: "JOB-001", rootState: "RESOLVED", rootCandidates: ["JOB-001"] };
const two: ProgramCard = { ...one, workRef: "WS:TWO", rootJobId: "JOB-002", rootCandidates: ["JOB-002"] };
function read(state: SourceState = "CURRENT", programs = [one, two]): OfficeProjection["programs"] {
  return { source: { owner: "AGENT_OS", ref: "control:projects", revision: "rev:1", observed_at: "2026-10-14T04:00:00Z", state, coverage: "SUPPLIED_SCOPE" }, value: { programs, state: "AVAILABLE", reason: "AVAILABLE" }, reason: null };
}

describe("Projects visible Mission identity search", () => {
  let container: HTMLDivElement, root: Root;
  beforeEach(() => {
    (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
    container = document.createElement("div"); document.body.append(container);
    root = createRoot(container);
  });
  afterEach(() => { act(() => root.unmount()); container.remove(); });
  const render = (programs = read(), navigate?: (selection: MissionSelection, mode: "current" | "history") => void) =>
    act(() => root.render(<Projects programs={programs} onNavigateMission={navigate} />));
  const search = (value: string) => {
    const input = container.querySelector<HTMLInputElement>('input[type="search"]')!;
    act(() => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(input, value);
      input.dispatchEvent(new Event("input", { bubbles: true }));
    });
  };
  const rows = () => Array.from(container.querySelectorAll("article"));

  it("finds the exact root supplied through the real Programs decoder, adapter and Office projection", () => {
    const context = { authGeneration: 1, selection: null, sessionRef: null, bindingGeneration: null,
      revisions: { mission: null, programs: null, result: null, conversation: null } };
    const completed = completeProgramsOfficeRead(captureProgramsOfficeRead(context), context,
      // Combine the frozen service receipt with the full reducer fixture for this
      // in-process presentation test; this is not a live service attestation.
      decodeProgramsObservation({ ...availablePrograms, control_room: controlRoom }), "2026-10-14T04:00:00Z");
    expect(completed.kind).toBe("observed");
    if (completed.kind !== "observed") throw new Error("Fixture observation was discarded");
    const programs = projectOffice({ mission: null, programs: completed.snapshot, result: null, conversation: null }, completed.context).programs;
    expect(programs.source.state).toBe("CURRENT");
    const navigate = vi.fn(); render(programs, navigate);
    expect(container.textContent).toContain("Mission JOB-B5");
    search("  job-b5  "); expect(rows()).toHaveLength(1);
    act(() => rows()[0].querySelector("button")!.click());
    expect(navigate).toHaveBeenCalledTimes(1);
    expect(navigate).toHaveBeenLastCalledWith({ workRef: "WS:B5", rootJobId: "JOB-B5" }, "current");
  });

  it.each(["JOB-002", "  job-002  "])("finds the displayed resolved root %s and navigates its unchanged exact pair", query => {
    const navigate = vi.fn(); render(read(), navigate);
    expect(container.textContent).toContain("Mission JOB-002");
    search(query);
    expect(rows()).toHaveLength(1);
    expect(rows()[0].textContent).toContain("WS:TWO");
    expect(container.textContent).toContain("1 match in 2 supplied projects");
    act(() => rows()[0].querySelector("button")!.click());
    expect(navigate).toHaveBeenCalledTimes(1); expect(navigate).toHaveBeenLastCalledWith({ workRef: "WS:TWO", rootJobId: "JOB-002" }, "current");
  });

  it("preserves title/work-reference search, supplied order, clearing and unmatched feedback", () => {
    render(); search("shared project");
    expect(rows().map(row => row.querySelector(".projects-ref")!.textContent)).toEqual(["WS:ONE", "WS:TWO"]);
    search("ws:one"); expect(rows()).toHaveLength(1); expect(rows()[0].textContent).toContain("WS:ONE");
    search("JOB-UNSUPPLIED"); expect(rows()).toHaveLength(0);
    expect(container.textContent).toContain("No supplied projects match this search.");
    search(""); expect(rows()).toHaveLength(2);
  });

  it("finds displayed conflict candidates without creating a navigation action", () => {
    const navigate = vi.fn(); render(read("CURRENT", [{ ...one, rootState: "CONFLICT", rootCandidates: ["JOB-001", "JOB-CONFLICT"] }, two]), navigate);
    expect(container.textContent).toContain("Root conflict: JOB-001, JOB-CONFLICT");
    search("job-conflict"); expect(rows()).toHaveLength(1);
    expect(rows()[0].querySelector("button")).toBeNull(); expect(navigate).not.toHaveBeenCalled();
  });

  it.each([
    { ...one, rootState: "UNKNOWN" as const, rootJobId: "JOB-HIDDEN", rootCandidates: ["JOB-HIDDEN"] },
    { ...one, rootState: "CONFLICT" as const, rootJobId: "JOB-HIDDEN", rootCandidates: ["JOB-VISIBLE"] },
  ])("does not match a root ID that the card does not display: %j", card => {
    render(read("CURRENT", [card])); expect(container.textContent).not.toContain("JOB-HIDDEN");
    search("job-hidden"); expect(rows()).toHaveLength(0);
  });

  it("keeps retained-root matches historical and does not invent the absent history route", () => {
    render(read("STALE")); search("JOB-002"); expect(rows()).toHaveLength(1);
    expect(container.textContent).toContain("Retained history."); expect(rows()[0].querySelector("button")).toBeNull();
    const navigate = vi.fn(); render(read("STALE"), navigate);
    act(() => rows()[0].querySelector("button")!.click());
    expect(navigate).toHaveBeenCalledTimes(1); expect(navigate).toHaveBeenLastCalledWith({ workRef: "WS:TWO", rootJobId: "JOB-002" }, "history");
  });

  it.each(["UNKNOWN", "UNAVAILABLE", "WITHHELD", "UNASSOCIATED"] as const)("hides both matches and search for %s source facts", state => {
    render(); search("JOB-002"); render(read(state));
    expect(rows()).toHaveLength(0); expect(container.querySelector('input[type="search"]')).toBeNull();
    expect(container.textContent).not.toContain("JOB-002");
    render(); expect(container.querySelector<HTMLInputElement>("input")!.value).toBe("");
  });

  it("resets the search on a new source revision and never navigates the former root", () => {
    const navigate = vi.fn(); render(read(), navigate); search("JOB-002");
    const next = read("CURRENT", [{ ...two, rootJobId: "JOB-NEW", rootCandidates: ["JOB-NEW"] }]);
    next.source.revision = "rev:2"; render(next, navigate);
    expect(container.querySelector<HTMLInputElement>("input")!.value).toBe("");
    search("JOB-002"); expect(rows()).toHaveLength(0); expect(navigate).not.toHaveBeenCalled();
    search("JOB-NEW"); expect(rows()).toHaveLength(1); act(() => rows()[0].querySelector("button")!.click());
    expect(navigate).toHaveBeenCalledTimes(1); expect(navigate).toHaveBeenLastCalledWith({ workRef: "WS:TWO", rootJobId: "JOB-NEW" }, "current");
  });
});
