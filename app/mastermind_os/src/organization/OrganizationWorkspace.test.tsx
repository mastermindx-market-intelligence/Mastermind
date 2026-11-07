// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { ProjectionContext } from "../meta-ceo/projection";
import { OrganizationWorkspace, qualifyOrganization, type OrganizationObservation } from "./OrganizationWorkspace";

afterEach(cleanup);

const binding: ProjectionContext = {
  authGeneration: 4,
  selection: { workRef: "WS:CURRENT", rootJobId: "job-current" },
  sessionRef: "session-1", bindingGeneration: 2,
  revisions: { mission: "rev:1", programs: null, result: null, conversation: null },
};

function ownerValue() {
  return {
    schema: "mastermind.hermes_organization_context.v1",
    state: "SOURCE_LINKED_ADVISORY",
    reporting_lines_are_authoritative: false,
    assignments_are_authoritative: false,
    admitted: false, dispatched: false, reasoning_wake: false,
    organization: {
      human_root: { key: "chairman", title: "Chairman" },
      seats: [
        { key: "meta_ceo", title: "Meta-CEO", reports_to: "chairman", live_enrollment: "NOT_OBSERVED", authority_grant: false },
        { key: "engineering", title: "Engineering Lead", reports_to: "meta_ceo", live_enrollment: "NOT_OBSERVED", authority_grant: false },
        { key: "reliability", title: "Reliability Lead", reports_to: "engineering", live_enrollment: "NOT_OBSERVED", authority_grant: false },
      ],
      caller: { charter_key: "reliability", advisory_reporting_path: ["chairman", "meta_ceo", "engineering", "reliability"] },
    },
    goal_lineage: {
      company_goal: { state: "NOT_PROJECTED" },
      workstream: { work_ref: "WS:CURRENT", title: "Real work", state: "ACTIVE", next_action: "Review source" },
      execution_root: { selected_root_job_id: "job-current", role_to_job_assignment: "NOT_ESTABLISHED", job_status: "RUNNING" },
      evidence: { result_reference_count: 1, review_verdict: "PENDING", acceptance_state: "NOT_ACCEPTED",
        original_parent_consumption: "NOT_ESTABLISHED", product_acceptance: "NOT_ESTABLISHED" },
      source: { mission_fingerprint: "a".repeat(64), generated_at: "2026-11-07T01:00:00Z", scope: "single_mission", full_fleet: false },
    },
  };
}

function observation(value: unknown = ownerValue()): OrganizationObservation {
  return { context: structuredClone(binding), missionRevision: "rev:1", sourceState: "CURRENT", value };
}

describe("Paperclip-inspired read-only organization consumer", () => {
  it("shows qualified hierarchy and lineage without an enrollment, dispatch or acceptance claim", () => {
    render(<OrganizationWorkspace binding={binding} missionState="CURRENT" observation={observation()} />);
    expect(screen.getByRole("region", { name: "Organization" }).textContent).toContain("Meta-CEO");
    expect(screen.getByText("Engineering Lead")).toBeTruthy();
    expect(screen.getAllByText("Enrollment not observed")).toHaveLength(3);
    expect(screen.getByText("Real work")).toBeTruthy();
    expect(screen.getByText("job-current")).toBeTruthy();
    expect(screen.getByText("Original parent consumption not established")).toBeTruthy();
    expect(screen.getByText("Product acceptance not established")).toBeTruthy();
    expect(screen.queryByRole("button")).toBeNull();
    fireEvent.click(screen.getByText("Source detail"));
    expect(screen.getByText("a".repeat(64))).toBeTruthy();
  });


  it.each([
    ["en", "Pending", "Not accepted"],
    ["zh-CN", "待审查", "未验收"],
  ] as const)("localizes supplied advisory review and acceptance (%s)", (locale, review, acceptance) => {
    render(<OrganizationWorkspace binding={binding} missionState="CURRENT" observation={observation()} locale={locale} />);
    expect(screen.getByText(review)).toBeTruthy();
    expect(screen.getByText(acceptance)).toBeTruthy();
    expect(screen.queryByText("PENDING")).toBeNull();
    expect(screen.queryByText("NOT_ACCEPTED")).toBeNull();
  });

  it("shows a truthful unbound state, not an empty-company assertion", () => {
    render(<OrganizationWorkspace binding={binding} missionState="CURRENT" />);
    expect(screen.getByRole("status").textContent).toMatch(/not evidence of no team or no work/);
    expect(screen.queryByText("Engineering Lead")).toBeNull();
  });

  it.each(["STALE", "UNKNOWN", "UNAVAILABLE", "WITHHELD", "UNASSOCIATED"] as const)(
    "suppresses all data when Mission becomes %s", state => {
      render(<OrganizationWorkspace binding={binding} missionState={state} observation={observation()} />);
      expect(screen.queryByText("Real work")).toBeNull();
    });

  it("revokes views across auth, session, revision and workstream change", () => {
    const changed = [
      { ...binding, authGeneration: 5 },
      { ...binding, sessionRef: "another" },
      { ...binding, revisions: { ...binding.revisions, mission: "rev:2" } },
      { ...binding, selection: { workRef: "WS:OTHER", rootJobId: "job-current" } },
    ];
    for (const next of changed) {
      expect(qualifyOrganization(next, "CURRENT", observation())).toBeNull();
    }
  });

  it("does not display stale or denied observations", () => {
    expect(qualifyOrganization(binding, "CURRENT", { ...observation(), sourceState: "STALE" })).toBeNull();
    expect(qualifyOrganization(binding, "CURRENT", { ...observation(), sourceState: "WITHHELD" })).toBeNull();
  });

  it("rejects cycles, duplicate roles and imported privilege claims", () => {
    const cycle = ownerValue();
    cycle.organization.seats[0]!.reports_to = "reliability";
    expect(qualifyOrganization(binding, "CURRENT", observation(cycle))).toBeNull();
    const duplicate = ownerValue();
    duplicate.organization.seats[2]!.key = "engineering";
    expect(qualifyOrganization(binding, "CURRENT", observation(duplicate))).toBeNull();
    const privilege = ownerValue();
    privilege.organization.seats[1]!.authority_grant = true;
    expect(qualifyOrganization(binding, "CURRENT", observation(privilege))).toBeNull();
    const assignment = ownerValue();
    assignment.goal_lineage.execution_root.role_to_job_assignment = "ADMITTED";
    expect(qualifyOrganization(binding, "CURRENT", observation(assignment))).toBeNull();
  });

  it("rejects mismatched root, fleet-wide and unknown acceptance claims", () => {
    const root = ownerValue();
    root.goal_lineage.execution_root.selected_root_job_id = "job-unrelated";
    expect(qualifyOrganization(binding, "CURRENT", observation(root))).toBeNull();
    const fleet = ownerValue();
    fleet.goal_lineage.source.full_fleet = true;
    expect(qualifyOrganization(binding, "CURRENT", observation(fleet))).toBeNull();
    const received = ownerValue();
    received.goal_lineage.evidence.product_acceptance = "ACCEPTED";
    expect(qualifyOrganization(binding, "CURRENT", observation(received))).toBeNull();
  });

  it("renders multilingual view while React escapes untrusted title text", () => {
    const input = ownerValue();
    input.organization.seats[1]!.title = "<img src=x onerror=alert(1)>";
    const view = render(<OrganizationWorkspace binding={binding} missionState="CURRENT"
      observation={observation(input)} locale="zh-CN" />);
    expect(screen.getByText("组织架构")).toBeTruthy();
    expect(view.container.querySelector("img")).toBeNull();
  });
});
