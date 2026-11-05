// @vitest-environment jsdom
// Focused component tests for the read-only planning continuity presenter.
// The real component, the real decoder types and the real captured owner
// fixture are used; nothing is mocked. Derived cases below only reshape the
// recorded fixture into other producer-valid DTO shapes (extra recorded
// proposal, RECORD_INVALID entries, closed comparison reasons, explicit
// display revision, identical bodies) so every presenter branch is exercised
// against the actual data contract.
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { ProjectPlanContinuity } from "./ProjectPlanContinuity";
import { decodeProjectPlanContinuity, type ProjectPlanContinuityRead } from "./project-plan-continuity";
import ownerFixture from "../fixtures/project-plan-continuity-owner.json";

afterEach(() => cleanup());

const BASE_TEXT = "# Recorded baseline\n";
const CANDIDATE_TEXT = "# Improved candidate\n";
const DIFF_TEXT =
  "--- recorded-base\n+++ proposal-candidate\n@@ -1 +1 @@\n-# Recorded baseline\n+# Improved candidate\n";

const cases = (ownerFixture as unknown as { cases: Record<string, unknown> }).cases;
const read = (name: string): ProjectPlanContinuityRead =>
  decodeProjectPlanContinuity(cases[name], "WS:PLAN-TEST");
const derive = (
  name: string,
  mutate: (value: ProjectPlanContinuityRead) => void,
): ProjectPlanContinuityRead => {
  const value = read(name);
  mutate(value);
  return value;
};

/** Recorded fixture reshaped so the capture lists two recorded proposals in
 * producer order (never sorted or elected by date). */
const withSecondProposal = (): ProjectPlanContinuityRead =>
  derive("available_pending", (value) => {
    if (value.adoption.state === "AVAILABLE" && value.proposals.state === "AVAILABLE") {
      const second = JSON.parse(JSON.stringify(value.proposals.items[0])) as typeof value.proposals.items[0];
      if (second.state === "RECORDED_PROPOSAL") {
        second.proposal_id = "PLAN-PROPOSAL-B";
        second.rationale = "A second recorded proposal.";
        value.proposals.items.push(second);
      }
    }
  });

const invalidEntry = (source: { repository: string; path: string; commit: string; content_sha256: string }) => ({
  proposal_source: source,
  state: "UNAVAILABLE" as const,
  reason: "RECORD_INVALID" as const,
});

function preTexts(container: HTMLElement): string[] {
  return Array.from(container.querySelectorAll("pre")).map((element) => element.textContent ?? "");
}
function hasPre(container: HTMLElement, text: string): boolean {
  return preTexts(container).includes(text);
}
/** Raw closed reasons must never surface outside a source disclosure. */
function expectReasonOnlyInsideDetails(reason: string) {
  const matches = screen.getAllByText(reason);
  expect(matches.length).toBeGreaterThan(0);
  for (const element of matches) {
    expect(element.closest("details")).not.toBeNull();
  }
}

describe("ProjectPlanContinuity presenter", () => {
  it("renders the available recorded baseline and the pending recorded proposal with exact captured bodies", () => {
    const view = render(<ProjectPlanContinuity data={read("available_pending")} />);
    expect(screen.getByRole("heading", { name: "Plan comparison", level: 3 })).toBeTruthy();
    expect(screen.getByText("The current plan baseline is available (recorded baseline).")).toBeTruthy();
    expect(screen.getByText("Recorded baseline")).toBeTruthy();
    expect(screen.getByText("DEC:PLAN-FIRST")).toBeTruthy();
    expect(screen.getByText("fixture-owner")).toBeTruthy();
    expect(screen.getByText("2026-11-04")).toBeTruthy();
    expect(screen.getByText("View current plan")).toBeTruthy();
    const select = screen.getByRole("combobox", { name: "Recorded proposal to inspect" }) as HTMLSelectElement;
    expect(select.value).toBe("PLAN-PROPOSAL");
    expect(Array.from(select.querySelectorAll("option")).map((option) => option.textContent))
      .toEqual(["PLAN-PROPOSAL"]);
    expect(screen.getByText("A concrete proposed change.")).toBeTruthy();
    expect(screen.getByText("Recorded proposal; not referenced by the current adoption decision.")).toBeTruthy();
    expect(screen.getByText("Compared against the adopted plan content.")).toBeTruthy();
    expect(screen.getByText("1 line added, 1 line removed.")).toBeTruthy();
    expect(screen.queryByText("More recorded items (")).toBeNull();
    const pres = preTexts(view.container);
    expect(pres.includes(BASE_TEXT)).toBe(true);
    expect(pres.includes(CANDIDATE_TEXT)).toBe(true);
    expect(pres.includes(DIFF_TEXT)).toBe(true);
    expect(screen.getByText("agentos/decisions/DEC-PLAN-FIRST.md")).toBeTruthy();
    expect(screen.getAllByText("mastermindx-market-intelligence/macro").length).toBeGreaterThan(0);
    expect(screen.getAllByText("a".repeat(40)).length).toBeGreaterThan(0);
    expect(screen.getByText("1e8b858fc52986327beb62ec4632f63d3029a7cea876a9c780df0220e07f28cf")).toBeTruthy();
  });

  it("shows a declared adoption as declaration only while its recorded source is unavailable", () => {
    const view = render(<ProjectPlanContinuity data={read("declared_source_unavailable")} />);
    expect(screen.getByText("The current plan baseline is not available from the captured sources.")).toBeTruthy();
    expect(screen.getByText("Adoption recorded; plan content unavailable")).toBeTruthy();
    expect(screen.getByText("DEC:PLAN-FIRST")).toBeTruthy();
    expect(screen.queryByText("View current plan")).toBeNull();
    expect(hasPre(view.container, BASE_TEXT)).toBe(false);
    expect(screen.getByText("Recorded proposal.")).toBeTruthy();
    expect(screen.getByText("Compared against the declared adoption source (declaration only).")).toBeTruthy();
    expect(screen.getByText("This comparison is not shown because a comparison source could not be read.")).toBeTruthy();
    expect(screen.queryByText("Compare plans")).toBeNull();
    expectReasonOnlyInsideDetails("SOURCE_UNAVAILABLE");
  });

  it("compares against the recorded source when no adoption is declared and never claims adoption", () => {
    const view = render(<ProjectPlanContinuity data={read("recorded_source_only")} />);
    expect(screen.getByText("The current plan baseline is not available from the captured sources.")).toBeTruthy();
    expect(screen.getByText("No current plan adoption is declared in the captured sources.")).toBeTruthy();
    expectReasonOnlyInsideDetails("NOT_DECLARED");
    expect(screen.queryByText("View current plan")).toBeNull();
    expect(screen.getByText("Recorded proposal.")).toBeTruthy();
    expect(screen.getByText("Compared against the recorded planning source.")).toBeTruthy();
    expect(screen.getByText("Compare plans")).toBeTruthy();
    expect(hasPre(view.container, BASE_TEXT)).toBe(true);
    expect(hasPre(view.container, CANDIDATE_TEXT)).toBe(true);
    expect(hasPre(view.container, DIFF_TEXT)).toBe(true);
  });

  it("describes a proposal referenced by the actual current adoption decision", () => {
    const view = render(<ProjectPlanContinuity data={read("current_references_proposal")} />);
    expect(screen.getByText("Referenced by the current adoption decision.")).toBeTruthy();
    expect(screen.getByText("The current plan baseline is available (recorded baseline).")).toBeTruthy();
    expect(screen.getByText("DEC:PLAN-SECOND")).toBeTruthy();
    expect(screen.getByText("Predecessor decision: DEC:PLAN-FIRST")).toBeTruthy();
    expect(screen.getByText("Base decision: DEC:PLAN-FIRST")).toBeTruthy();
    expect(screen.getByText("Compared against the recorded predecessor plan.")).toBeTruthy();
    expect(hasPre(view.container, "# Improved candidate\n")).toBe(true);
    expect(screen.getAllByText("planning/adopted.md").length).toBeGreaterThan(0);
    expect(screen.getAllByText("planning/proposal.md").length).toBeGreaterThan(0);
  });

  it("reports lineage conflicts without inventing a baseline, proposals, or a zero/healthy state", () => {
    const view = render(<ProjectPlanContinuity data={read("lineage_invalid")} />);
    expect(screen.getByText("The current plan baseline is not available from the captured sources.")).toBeTruthy();
    expect(screen.getByText("The recorded plan lineage could not be followed to a valid current adoption.")).toBeTruthy();
    expect(screen.getByText("The recorded plan lineage could not be followed, so recorded proposals are not shown.")).toBeTruthy();
    expectReasonOnlyInsideDetails("LINEAGE_INVALID");
    expect(screen.queryByText("View current plan")).toBeNull();
    expect(screen.queryByText("No proposal is available from the captured planning sources.")).toBeNull();
    expect(screen.queryByRole("combobox")).toBeNull();
    expect(hasPre(view.container, BASE_TEXT)).toBe(false);
    expect(hasPre(view.container, CANDIDATE_TEXT)).toBe(false);
  });

  it("states empty capture scope instead of claiming there are no proposals elsewhere", () => {
    const view = render(<ProjectPlanContinuity data={read("no_captured_proposal")} />);
    expect(screen.getByText("No proposal is available from the captured planning sources.")).toBeTruthy();
    expect(screen.getByText("This listing covers only the planning sources captured with this record; proposals recorded elsewhere are not included.")).toBeTruthy();
    expect(screen.queryByRole("combobox")).toBeNull();
    expect(screen.queryByText("Recorded proposal; not referenced by the current adoption decision.")).toBeNull();
    expect(screen.getByText("View current plan")).toBeTruthy();
    expect(hasPre(view.container, BASE_TEXT)).toBe(true);
  });

  it("shows the explicit display revision when present and stays neutral when it is null", () => {
    const derived = derive("available_pending", (value) => {
      if (value.adoption.state === "AVAILABLE") value.adoption.adoption.display_revision = "R7";
    });
    render(<ProjectPlanContinuity data={derived} />);
    expect(screen.getByText("The current plan baseline is available (revision R7).")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "R7", level: 4 })).toBeTruthy();
    cleanup();
    render(<ProjectPlanContinuity data={read("available_pending")} />);
    expect(screen.getByRole("heading", { name: "Recorded baseline", level: 4 })).toBeTruthy();
    expect(screen.queryByText(/revision/)).toBeNull();
  });

  it("preserves producer order and switches between multiple recorded proposals without caching bodies", () => {
    render(<ProjectPlanContinuity data={withSecondProposal()} />);
    let select = screen.getByRole("combobox", { name: "Recorded proposal to inspect" }) as HTMLSelectElement;
    expect(Array.from(select.querySelectorAll("option")).map((option) => option.textContent))
      .toEqual(["PLAN-PROPOSAL", "PLAN-PROPOSAL-B"]);
    expect(select.value).toBe("PLAN-PROPOSAL");
    expect(screen.getByText("A concrete proposed change.")).toBeTruthy();
    fireEvent.change(select, { target: { value: "PLAN-PROPOSAL-B" } });
    select = screen.getByRole("combobox", { name: "Recorded proposal to inspect" }) as HTMLSelectElement;
    expect(select.value).toBe("PLAN-PROPOSAL-B");
    expect(Array.from(select.querySelectorAll("option")).map((option) => option.textContent))
      .toEqual(["PLAN-PROPOSAL", "PLAN-PROPOSAL-B"]);
    expect(screen.getByText("A second recorded proposal.")).toBeTruthy();
    expect(screen.queryByText("A concrete proposed change.")).toBeNull();
  });

  it("keeps unreadable recorded proposals visible as notices with exact source details", () => {
    const allInvalid = derive("available_pending", (value) => {
      if (value.proposals.state === "AVAILABLE") {
        const source = value.proposals.items[0].proposal_source;
        value.proposals.items = [invalidEntry(source)];
      }
    });
    const view = render(<ProjectPlanContinuity data={allInvalid} />);
    expect(screen.getByText("A recorded proposal could not be read from the captured sources.")).toBeTruthy();
    expect(screen.queryByRole("combobox")).toBeNull();
    expectReasonOnlyInsideDetails("RECORD_INVALID");
    expect(screen.getByText("planning/proposal.md")).toBeTruthy();
    cleanup();
    const mixed = derive("available_pending", (value) => {
      if (value.proposals.state === "AVAILABLE") {
        value.proposals.items.push(invalidEntry(value.proposals.items[0].proposal_source));
      }
    });
    render(<ProjectPlanContinuity data={mixed} />);
    expect(screen.getByRole("combobox")).toBeTruthy();
    expect(screen.getByText("A recorded proposal could not be read from the captured sources.")).toBeTruthy();
    expect(screen.getByText("A concrete proposed change.")).toBeTruthy();
  });

  it("folds a long list of unreadable items into one counted disclosure", () => {
    const derived = derive("available_pending", (value) => {
      if (value.proposals.state === "AVAILABLE") {
        const readable = value.proposals.items[0];
        const source = readable.proposal_source;
        value.proposals.items = [readable];
        for (let index = 0; index < 10; index += 1) {
          value.proposals.items.push(invalidEntry(source));
        }
      }
    });
    const view = render(<ProjectPlanContinuity data={derived} />);
    expect(screen.getByText("More recorded items (10)")).toBeTruthy();
    expect(view.container.querySelectorAll("li").length).toBe(10);
    expect(screen.getByRole("combobox")).toBeTruthy();
  });

  it("explains a stale predecessor comparison instead of rendering diff styling", () => {
    const derived = derive("recorded_source_only", (value) => {
      const item = value.proposals.state === "AVAILABLE" ? value.proposals.items[0] : null;
      if (item !== null && item.state === "RECORDED_PROPOSAL") {
        item.comparison = { state: "UNAVAILABLE", reason: "STALE_PREDECESSOR" };
      }
    });
    const view = render(<ProjectPlanContinuity data={derived} />);
    expect(screen.getByText("This comparison is not shown because the recorded predecessor plan is stale and may no longer match this proposal.")).toBeTruthy();
    expect(screen.queryByText("Compare plans")).toBeNull();
    expectReasonOnlyInsideDetails("STALE_PREDECESSOR");
    expect(hasPre(view.container, BASE_TEXT)).toBe(false);
    expect(hasPre(view.container, CANDIDATE_TEXT)).toBe(false);
    expect(hasPre(view.container, DIFF_TEXT)).toBe(false);
  });

  it("states an identical comparison truthfully with zero line counts", () => {
    const derived = derive("available_pending", (value) => {
      const item = value.proposals.state === "AVAILABLE" ? value.proposals.items[0] : null;
      if (item !== null && item.state === "RECORDED_PROPOSAL" && item.comparison.state === "AVAILABLE") {
        item.comparison.candidate_text = item.comparison.base_text;
        item.comparison.diff = "";
        item.comparison.identical = true;
        item.comparison.added_lines = 0;
        item.comparison.removed_lines = 0;
      }
    });
    const view = render(<ProjectPlanContinuity data={derived} />);
    expect(screen.getByText("The proposal text is identical to the base text. 0 lines added, 0 lines removed.")).toBeTruthy();
    expect(screen.queryByText("1 line added, 1 line removed.")).toBeNull();
    expect(preTexts(view.container)).toContain("");
  });

  it("renders native phrasing for controls and closed reasons in zh-CN", () => {
    render(<ProjectPlanContinuity data={read("declared_source_unavailable")} locale="zh-CN" />);
    expect(screen.getByRole("heading", { name: "计划对比", level: 3 })).toBeTruthy();
    expect(screen.getByText("当前计划基线无法从已捕获的来源中读取。")).toBeTruthy();
    expect(screen.getByText("已记录采纳；计划内容不可用")).toBeTruthy();
    expect(screen.getByText("要查看的已记录提案")).toBeTruthy();
    expect(screen.getByText("对比来源无法读取，因此不显示此对比。")).toBeTruthy();
    expect(screen.queryByText("对比计划")).toBeNull();
    expectReasonOnlyInsideDetails("SOURCE_UNAVAILABLE");
    cleanup();
    render(<ProjectPlanContinuity data={read("no_captured_proposal")} locale="zh-CN" />);
    expect(screen.getByText("已捕获的规划来源中没有可读取的提案。")).toBeTruthy();
    expect(screen.getByText("查看当前计划")).toBeTruthy();
    expect(screen.getByText("这份列表只覆盖随此记录一起捕获的规划来源；其他地方记录的提案不包含在内。")).toBeTruthy();
  });

  it("removes previous bodies when rerendered with different or unavailable data", () => {
    const view = render(<ProjectPlanContinuity data={read("available_pending")} />);
    expect(hasPre(view.container, CANDIDATE_TEXT)).toBe(true);
    view.rerender(<ProjectPlanContinuity data={read("lineage_invalid")} />);
    expect(hasPre(view.container, CANDIDATE_TEXT)).toBe(false);
    expect(screen.queryByRole("combobox")).toBeNull();
    view.rerender(<ProjectPlanContinuity data={withSecondProposal()} />);
    const select = screen.getByRole("combobox", { name: "Recorded proposal to inspect" }) as HTMLSelectElement;
    fireEvent.change(select, { target: { value: "PLAN-PROPOSAL-B" } });
    expect(screen.getByText("A second recorded proposal.")).toBeTruthy();
    view.rerender(<ProjectPlanContinuity data={read("available_pending")} />);
    // The stale selection id is not part of the new capture: the lookup falls
    // back to the current items and no previous body survives.
    expect(screen.getByText("A concrete proposed change.")).toBeTruthy();
    expect(screen.queryByText("A second recorded proposal.")).toBeNull();
    expect((screen.getByRole("combobox") as HTMLSelectElement).value).toBe("PLAN-PROPOSAL");
    expect(hasPre(view.container, CANDIDATE_TEXT)).toBe(true);
  });

  it("offers no write, launch, adoption, or external navigation controls", () => {
    for (const name of ["available_pending", "declared_source_unavailable", "recorded_source_only", "lineage_invalid", "no_captured_proposal"]) {
      const view = render(<ProjectPlanContinuity data={read(name)} />);
      expect(view.container.querySelector("button, a[href], form, input, textarea")).toBeNull();
      cleanup();
    }
  });
});

it("keeps proposal evidence behind closed Planning sources while count and comparison stay visible", () => {
  const data = derive("available_pending", value => {
    if (value.proposals.state === "AVAILABLE" && value.proposals.items[0].state === "RECORDED_PROPOSAL")
      value.proposals.items[0].evidence = [value.proposals.items[0].base_source];
  });
  render(<ProjectPlanContinuity data={data} />);
  const entry = screen.getByText("Evidence 1");
  const disclosure = entry.closest("details")!;
  expect(disclosure).not.toBeNull();
  expect(disclosure.open).toBe(false);
  expect(disclosure.querySelector("summary")?.textContent).toBe("Planning sources");
  const count = screen.getByText("Evidence: 1");
  expect(count.closest("details")).toBeNull();
  expect(screen.getByText("A concrete proposed change.").closest("details")).toBeNull();
  expect(screen.getByText("Compare plans")).toBeTruthy();
});
