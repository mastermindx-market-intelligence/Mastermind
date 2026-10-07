// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ProgramCard } from "../mission";
import type { OfficeProjection, SourceState } from "../meta-ceo/projection";
import { Projects } from "./Projects";

afterEach(cleanup);
const one: ProgramCard = { workRef: "WS:ONE", title: "Shared title", state: "In review", nextAction: "Inspect returned evidence", rootJobId: "JOB-1", rootState: "RESOLVED", rootCandidates: ["JOB-1"] };
const two: ProgramCard = { ...one, workRef: "WS:TWO", rootJobId: "JOB-2", rootCandidates: ["JOB-2"] };
function read(state: SourceState = "CURRENT", programs = [one, two]): OfficeProjection["programs"] {
  return { source: { owner: "AGENT_OS", ref: "control:projects", revision: "rev:1", observed_at: "2026-10-04T05:00:00Z", state, coverage: "SUPPLIED_SCOPE" }, value: { programs, state: "AVAILABLE", reason: "AVAILABLE" }, reason: null };
}

describe("Atelier Projects", () => {
  it("shows supplied scope, exact identities and provenance without promoting a company total", () => {
    render(<Projects programs={read()} />);
    expect(screen.getByRole("heading", { name: "Your projects, in perspective." })).toBeTruthy();
    expect(screen.getByText("2 projects supplied")).toBeTruthy();
    expect(screen.getAllByText("Shared title")).toHaveLength(2);
    expect(screen.getByText("WS:ONE")).toBeTruthy();
    expect(screen.getByText("WS:TWO")).toBeTruthy();
    expect(screen.getByText("SUPPLIED_SCOPE")).toBeTruthy();
    expect(screen.getByText("control:projects")).toBeTruthy();
    expect(screen.queryByText(/all projects|company total: 2/i)).toBeNull();
    expect(screen.queryByRole("button", { name: /create|send|launch|retry|new project/i })).toBeNull();
  });

  it("navigates only with the exact supplied work/root pair", () => {
    const navigate = vi.fn();
    render(<Projects programs={read()} onNavigateMission={navigate} />);
    fireEvent.click(within(screen.getAllByRole("article")[1]!).getByRole("button", { name: "Open project Shared title" }));
    expect(navigate).toHaveBeenCalledExactlyOnceWith({ workRef: "WS:TWO", rootJobId: "JOB-2" }, "current");
  });

  it.each<ProgramCard>([
    { ...one, rootState: "CONFLICT" },
    { ...one, rootState: "UNKNOWN" },
    { ...one, rootJobId: null },
    { ...one, rootCandidates: ["JOB-1", "JOB-OTHER"] },
    { ...one, rootCandidates: ["JOB-OTHER"] },
  ])("keeps inconsistent root identity non-actionable: %j", (card) => {
    const navigate = vi.fn();
    render(<Projects programs={read("CURRENT", [card])} onNavigateMission={navigate} />);
    expect(screen.queryByRole("button", { name: /open project/i })).toBeNull();
    expect(screen.getByText(/Root conflict|Root unknown/)).toBeTruthy();
    expect(navigate).not.toHaveBeenCalled();
  });

  it("rejects duplicate work references without choosing either row", () => {
    render(<Projects programs={read("CURRENT", [one, { ...two, workRef: one.workRef }])} onNavigateMission={vi.fn()} />);
    expect(screen.getByText("DUPLICATE_WORK_REF")).toBeTruthy();
    expect(screen.queryByRole("article")).toBeNull();
    expect(screen.queryByText("2 projects supplied")).toBeNull();
  });

  it.each(["CURRENT", "STALE"] as const)("rejects invalid route identifiers in %s input without guessing a replacement", (state) => {
    const navigate = vi.fn();
    const forged = [{ ...one, workRef: "../private" }, { ...two, rootJobId: "JOB/unsafe", rootCandidates: ["JOB/unsafe"] }];
    render(<Projects programs={read(state, forged)} onNavigateMission={navigate} />);
    expect(screen.queryByRole("button", { name: /Open project|Inspect retained history/ })).toBeNull();
    expect(navigate).not.toHaveBeenCalled();
  });

  it("exposes retained projects only through explicitly historical navigation", () => {
    const navigate = vi.fn();
    render(<Projects programs={read("STALE", [one])} onNavigateMission={navigate} />);
    expect(screen.getByText("STALE")).toBeTruthy();
    expect(screen.getByText(/Retained history/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: /open project/i })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Inspect retained history for Shared title" }));
    expect(navigate).toHaveBeenCalledExactlyOnceWith({ workRef: "WS:ONE", rootJobId: "JOB-1" }, "history");
  });

  it.each<SourceState>(["UNKNOWN", "UNAVAILABLE", "WITHHELD", "UNASSOCIATED"])("clears cards and search for %s even if an input carries values", (state) => {
    render(<Projects programs={read(state)} onNavigateMission={vi.fn()} />);
    expect(screen.getByText(state)).toBeTruthy();
    expect(screen.queryByRole("article")).toBeNull();
    expect(screen.queryByRole("searchbox")).toBeNull();
    expect(screen.queryByText("Shared title")).toBeNull();
    expect(screen.queryByText(/0 projects supplied/)).toBeNull();
    if (state === "WITHHELD") expect(screen.queryByText("control:projects")).toBeNull();
  });

  it("clears a prior search and private cards synchronously when access is withheld", () => {
    const { rerender } = render(<Projects programs={read()} />);
    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "private search" } });
    rerender(<Projects programs={read("WITHHELD")} />);
    expect(screen.queryByDisplayValue("private search")).toBeNull();
    rerender(<Projects programs={read()} />);
    expect((screen.getByRole("searchbox") as HTMLInputElement).value).toBe("");
  });

  it.each(["ref", "revision", "observed_at"] as const)("cannot display current projects with missing %s", (field) => {
    const source = read(); source.source[field] = null;
    render(<Projects programs={source} />);
    expect(screen.getByText("PROVENANCE_INCOMPLETE")).toBeTruthy();
    expect(screen.queryByRole("article")).toBeNull();
  });

  it("keeps source unavailability distinct from a supplied empty collection", () => {
    const source = read(); source.value = { state: "UNAVAILABLE", reason: "CLOCK_MISMATCH", programs: [one] };
    const { rerender } = render(<Projects programs={source} />);
    expect(screen.getByText("CLOCK_MISMATCH")).toBeTruthy();
    expect(screen.queryByRole("article")).toBeNull();
    rerender(<Projects programs={read("CURRENT", [])} />);
    expect(screen.getByText("No projects were supplied. This does not establish zero company work.")).toBeTruthy();
  });

  it("searches only supplied title or exact work ref, preserving scope and source order", () => {
    render(<Projects programs={read()} />);
    fireEvent.change(screen.getByRole("searchbox", { name: "Find a supplied project" }), { target: { value: "ws:two" } });
    expect(screen.queryByText("WS:ONE")).toBeNull();
    expect(screen.getByText("WS:TWO")).toBeTruthy();
    expect(screen.getByText("1 match in 2 supplied projects")).toBeTruthy();
    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "not supplied" } });
    expect(screen.getByText("No supplied projects match this search.")).toBeTruthy();
    expect(screen.queryByText(/No projects were supplied/)).toBeNull();
  });

  it("features only an explicitly selected exact pair, never the first or a title match", () => {
    const { rerender } = render(<Projects programs={read()} selectedProject={{ workRef: "WS:TWO", rootJobId: "JOB-2" }} />);
    expect(within(screen.getByRole("region", { name: "Selected project" })).getByText("WS:TWO")).toBeTruthy();
    rerender(<Projects programs={read()} selectedProject={{ workRef: "WS:TWO", rootJobId: "JOB-WRONG" }} />);
    expect(screen.queryByRole("region", { name: "Selected project" })).toBeNull();
    expect(screen.getAllByRole("article")).toHaveLength(2);
  });
});
