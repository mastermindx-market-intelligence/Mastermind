// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import acceptedFixture from "../fixtures/mission-v4-owner-accepted.json";
import partialFixture from "../fixtures/mission-v3-owner-current-operator-harness.json";
import runningFixture from "../fixtures/window-mission-association-producer.json";
import { decodeMissionv3 } from "../mission";
import { captureMissionOfficeRead, completeMissionOfficeRead } from "../meta-ceo/mission-adapter";
import { projectOffice, type ProjectionContext } from "../meta-ceo/projection";
import { OrganizationWorkspace } from "./OrganizationWorkspace";

afterEach(cleanup);

// These are committed owner-produced regression exports. They are never live-app proof.
// The v4 envelope contributes only its existing v3 Mission, not product acceptance.
function observed(raw = acceptedFixture.mission, workRef = "WS:FIXTURE") {
  const context: ProjectionContext = {
    authGeneration: 3, selection: { workRef, rootJobId: "JOB-001" },
    sessionRef: null, bindingGeneration: null,
    revisions: { mission: null, programs: null, result: null, conversation: null },
  };
  const mission = decodeMissionv3(structuredClone(raw), context.selection!);
  if (!mission) throw new Error("Owner fixture failed the existing decoder");
  const receipt = completeMissionOfficeRead(captureMissionOfficeRead(context), context, mission, "2026-11-07T05:00:00Z");
  if (receipt.kind !== "observed") throw new Error("Owner fixture not observed");
  const projection = projectOffice({ mission: receipt.snapshot, programs: null, result: null, conversation: null }, receipt.context);
  return { projection, binding: receipt.context, mission };
}

describe("OrganizationWorkspace with the incumbent Mission projection", () => {
  it("shows retained operation evidence without claiming live enrollment or product acceptance", () => {
    const { projection, binding } = observed();
    render(<OrganizationWorkspace binding={binding} missionState="CURRENT" missionProjection={projection} />);
    expect(screen.getByRole("region", { name: "Operation progress" })).toBeTruthy();
    expect(screen.getByRole("region", { name: "Agents and work" })).toBeTruthy();
    expect(screen.getByText("Availability unknown")).toBeTruthy();
    expect(screen.getByText(/Job completion does not establish parent or product acceptance/)).toBeTruthy();
    expect(screen.queryByText("Meta-CEO")).toBeNull();
    expect(screen.getByText(/not evidence of no team or no work/)).toBeTruthy();
    const results = screen.getByRole("region", { name: "Retained results" });
    expect(within(results).getAllByRole("listitem")).toHaveLength(5);
  });

  it("opens the exact project and inspects a real retained result tuple", () => {
    const { projection, binding, mission } = observed();
    const openProject = vi.fn(), inspect = vi.fn();
    render(<OrganizationWorkspace binding={binding} missionState="CURRENT" missionProjection={projection}
      onOpenProject={openProject} onInspectWorkerResult={inspect} />);
    fireEvent.click(screen.getByRole("button", { name: "Open project" }));
    expect(openProject).toHaveBeenCalledWith({ workRef: "WS:FIXTURE", rootJobId: "JOB-001" });
    const jobs = screen.getByRole("list", { name: "Observed jobs" });
    fireEvent.click(within(jobs).getByRole("button", { name: /JOB-003/ }));
    const detail = screen.getByRole("region", { name: "Job JOB-003" });
    expect(within(detail).getByText("step-0")).toBeTruthy();
    expect(document.activeElement).toBe(detail);
    fireEvent.click(within(detail).getByRole("button", { name: "Open result" }));
    const ref = mission.result_refs.refs.find(item => item.job_id === "JOB-003")!;
    expect(inspect).toHaveBeenCalledWith({
      workRef: "WS:FIXTURE", rootJobId: ref.root_job_id, jobId: ref.job_id,
      attemptId: ref.attempt_id, resultEnvelopeDigest: ref.result_envelope_digest,
    });
  });

  it("supports an observed-worker inspector and local search without inventing an agent URL", () => {
    const { projection, binding } = observed();
    render(<OrganizationWorkspace binding={binding} missionState="CURRENT" missionProjection={projection} />);
    fireEvent.change(screen.getByRole("searchbox", { name: "Find agent or job" }), { target: { value: "JOB-005" } });
    const jobs = screen.getByRole("list", { name: "Observed jobs" });
    expect(within(jobs).getAllByRole("button")).toHaveLength(1);
    expect(screen.getByRole("region", { name: "Job JOB-005" })).toBeTruthy();
    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "not-present" } });
    expect(screen.getByText("No matching jobs")).toBeTruthy();
    expect(screen.queryByRole("region", { name: "Job JOB-005" })).toBeNull();
  });

  it.each(["auth", "session", "binding", "revision", "work", "root"] as const)(
    "removes private operation details and actions on the same render after %s changes", change => {
      const { projection, binding } = observed();
      const next = structuredClone(binding);
      if (change === "auth") next.authGeneration++;
      if (change === "session") next.sessionRef = "another-session";
      if (change === "binding") next.bindingGeneration = 7;
      if (change === "revision") next.revisions.mission = "another-revision";
      if (change === "work") next.selection!.workRef = "WS:OTHER";
      if (change === "root") next.selection!.rootJobId = "JOB-OTHER";
      const props = { missionState: "CURRENT" as const, missionProjection: projection,
        onInspectWorkerResult: vi.fn(), onOpenProject: vi.fn() };
      const view = render(<OrganizationWorkspace {...props} binding={binding} />);
      view.rerender(<OrganizationWorkspace {...props} binding={next} />);
      expect(screen.queryByText("One")).toBeNull();
      expect(screen.queryByRole("region", { name: "Agents and work" })).toBeNull();
      expect(screen.queryByRole("button")).toBeNull();
      expect(screen.getByText(/Activity remains unknown/)).toBeTruthy();
    });

  it.each(["STALE", "UNKNOWN", "UNAVAILABLE", "WITHHELD", "UNASSOCIATED"] as const)(
    "does not render a live activity claim from a %s Mission", missionState => {
      const { projection, binding } = observed();
      render(<OrganizationWorkspace binding={binding} missionState={missionState} missionProjection={projection} />);
      expect(screen.queryByRole("region", { name: "Operation progress" })).toBeNull();
      expect(screen.getByText(/Activity remains unknown/)).toBeTruthy();
    });

  it("uses a real loading state and suppresses old source content during acquisition", () => {
    const { projection, binding } = observed();
    const view = render(<OrganizationWorkspace binding={binding} missionState="CURRENT" missionProjection={projection} loading />);
    expect(screen.getByRole("region", { name: "Organization" }).getAttribute("aria-busy")).toBe("true");
    expect(screen.getByRole("status").textContent).toBe("Reading organization…");
    expect(screen.queryByText("One")).toBeNull();
    expect(screen.queryByRole("button")).toBeNull();
    view.rerender(<OrganizationWorkspace binding={binding} missionState="CURRENT" missionProjection={projection} />);
    expect(screen.getByRole("region", { name: "Agents and work" })).toBeTruthy();
  });

  it("does not convert current-but-incomplete child coverage into an empty team or zero total", () => {
    const { projection, binding } = observed(partialFixture as typeof acceptedFixture.mission, "WS:ONE");
    render(<OrganizationWorkspace binding={binding} missionState="CURRENT" missionProjection={projection} />);
    expect(screen.getByText("Coverage is incomplete. Counts and overall progress remain unknown.")).toBeTruthy();
    expect(screen.getByText("Child-job coverage is unavailable or incomplete.")).toBeTruthy();
    expect(screen.queryByText("No child jobs in this observation.")).toBeNull();
    expect(screen.getAllByText("Unknown").length).toBeGreaterThanOrEqual(2);
  });

  it("does not turn a running job without an observed worker into an active agent", () => {
    const { projection, binding } = observed(runningFixture.mission as typeof acceptedFixture.mission, "WS:FABRIC");
    render(<OrganizationWorkspace binding={binding} missionState="CURRENT" missionProjection={projection} />);
    expect(screen.getAllByText("Activity unknown")).toHaveLength(2);
    expect(screen.getByText("Some job activity is unknown. Activity totals are withheld.")).toBeTruthy();
    expect(within(screen.getByRole("region", { name: "Operation progress" })).getAllByText("Unknown")).toHaveLength(2);
    expect(screen.getByText("Availability unknown")).toBeTruthy();
    expect(screen.getAllByText("Worker not observed")).toHaveLength(2);
    expect(screen.queryByRole("button", { name: "Open result" })).toBeNull();
  });

  it("uses the supplied authenticated plan reader only on the existing explicit inspect action", async () => {
    const { projection, binding } = observed();
    const read = vi.fn(async () => { throw new Error("test read unavailable"); });
    render(<OrganizationWorkspace binding={binding} missionState="CURRENT" missionProjection={projection}
      planReader={{ read, sourceGeneration: () => 3, canRead: () => true }} />);
    expect(read).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Inspect plan" }));
    expect(read).toHaveBeenCalledWith({ work_ref: "WS:FIXTURE", root_job_id: "JOB-001", signal: expect.any(AbortSignal) });
    expect(await screen.findByText("Plan read unavailable; no progress inferred.")).toBeTruthy();
  });

  it("preserves the independent authenticated plan workflow when Mission is unavailable", async () => {
    const { projection, binding } = observed();
    const read = vi.fn(async () => { throw new Error("test read unavailable"); });
    render(<OrganizationWorkspace binding={binding} missionState="UNAVAILABLE" missionProjection={projection}
      planReader={{ read, sourceGeneration: () => 3, canRead: () => true }} />);
    expect(screen.queryByRole("region", { name: "Agents and work" })).toBeNull();
    expect(read).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Inspect plan" }));
    expect(read).toHaveBeenCalledWith({ work_ref: "WS:FIXTURE", root_job_id: "JOB-001", signal: expect.any(AbortSignal) });
    expect(await screen.findByText("Plan read unavailable; no progress inferred.")).toBeTruthy();
  });

  it("offers the existing Projects navigation when the observation is unavailable, without making a read", () => {
    const { projection, binding } = observed();
    const onOpenProjects = vi.fn();
    render(<OrganizationWorkspace binding={binding} missionState="UNAVAILABLE" missionProjection={projection}
      onOpenProjects={onOpenProjects} />);
    expect(onOpenProjects).not.toHaveBeenCalled();
    expect(screen.queryByRole("region", { name: "Agents and work" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Open Projects" }));
    expect(onOpenProjects).toHaveBeenCalledTimes(1);
  });

  it("renders the same observed-work controls in Chinese", () => {
    const { projection, binding } = observed();
    render(<OrganizationWorkspace binding={binding} missionState="CURRENT" missionProjection={projection} locale="zh-CN" />);
    expect(screen.getByRole("region", { name: "代理与工作" })).toBeTruthy();
    expect(screen.getByText("可用性未知")).toBeTruthy();
    expect(screen.getByRole("searchbox", { name: "查找代理或任务" })).toBeTruthy();
  });
});
