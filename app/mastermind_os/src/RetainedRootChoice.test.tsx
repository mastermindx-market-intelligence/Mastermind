// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { RetainedRootChoice } from "./RetainedRootChoice";
import type { RetainedRootChoiceProps } from "./RetainedRootChoice";

afterEach(cleanup);

// Fixture vectors only: every candidate below is a plain job token and no
// test touches a browser account, host, provider, credential or network.
// The component renders the parent's data as given; nothing here is proof of
// any authenticated programme root, only of this read-only choice surface.
const CONFLICTED = ["JOB-101", "JOB-102", "JOB-103"];

function setup(overrides: Partial<RetainedRootChoiceProps> = {}) {
  const onChooseRoot = vi.fn();
  const props: RetainedRootChoiceProps = {
    workRef: "WS:ONE",
    rootCandidates: CONFLICTED,
    rootState: "CONFLICT",
    selectedRootJobId: null,
    locale: "en",
    onChooseRoot,
    ...overrides,
  };
  return { props, onChooseRoot };
}

describe("RetainedRootChoice", () => {
  it("never auto-chooses: no callback and no selection before an explicit click", () => {
    const { props, onChooseRoot } = setup();
    const { container } = render(<RetainedRootChoice {...props} />);
    expect(onChooseRoot).not.toHaveBeenCalled();
    const buttons = screen.getAllByRole("button");
    expect(buttons).toHaveLength(3);
    for (const button of buttons)
      expect(button.getAttribute("aria-pressed")).toBe("false");
    expect(screen.queryByText("Selected")).toBeNull();
    expect(container.querySelector("details")).toBeNull();
    expect(
      container
        .querySelector("ul.items")
        ?.getAttribute("aria-label"),
    ).toBe("Available missions");
  });

  it("emits the exact (workRef, rootJobId) pair exactly once per choice", () => {
    const { props, onChooseRoot } = setup();
    const { container } = render(<RetainedRootChoice {...props} />);
    fireEvent.click(screen.getByRole("button", { name: "JOB-102" }));
    expect(onChooseRoot).toHaveBeenCalledTimes(1);
    const [selection] = onChooseRoot.mock.calls[0] as Array<{
      workRef: string;
      rootJobId: string;
    }>;
    expect(selection).toEqual({ workRef: "WS:ONE", rootJobId: "JOB-102" });
    expect(Object.keys(selection).sort()).toEqual(["rootJobId", "workRef"]);
    expect(container.textContent).toContain(
      "the current Mission stays unresolved",
    );
  });

  it("renders a single RESOLVED root as one choice and emits it on click", () => {
    const { props, onChooseRoot } = setup({
      rootCandidates: ["JOB-201"],
      rootState: "RESOLVED",
    });
    render(<RetainedRootChoice {...props} />);
    const buttons = screen.getAllByRole("button");
    expect(buttons).toHaveLength(1);
    fireEvent.click(buttons[0]);
    expect(onChooseRoot).toHaveBeenCalledTimes(1);
    expect(onChooseRoot).toHaveBeenCalledWith({
      workRef: "WS:ONE",
      rootJobId: "JOB-201",
    });
  });

  it("follows the parent's selectedRootJobId only, never the URL", () => {
    window.history.replaceState(null, "", "/os/?root=JOB-102");
    const { props } = setup();
    const view = render(
      <RetainedRootChoice {...props} selectedRootJobId="JOB-101" />,
    );
    expect(
      screen.getByRole("button", { name: "JOB-101" }).getAttribute("aria-pressed"),
    ).toBe("true");
    expect(
      screen.getByRole("button", { name: "JOB-102" }).getAttribute("aria-pressed"),
    ).toBe("false");
    expect(screen.getAllByText("Selected")).toHaveLength(1);
    view.rerender(
      <RetainedRootChoice {...props} selectedRootJobId="JOB-103" />,
    );
    expect(
      screen.getByRole("button", { name: "JOB-103" }).getAttribute("aria-pressed"),
    ).toBe("true");
    expect(
      screen.getByRole("button", { name: "JOB-101" }).getAttribute("aria-pressed"),
    ).toBe("false");
    view.rerender(<RetainedRootChoice {...props} selectedRootJobId={null} />);
    expect(screen.queryByText("Selected")).toBeNull();
    window.history.replaceState(null, "", "/");
  });

  it("rejects malformed, duplicate, mismatched and over-budget vectors without choices", () => {
    const cases: Partial<RetainedRootChoiceProps>[] = [
      { rootCandidates: [] },
      { rootCandidates: ["JOB-101", "JOB-101", "JOB-102"] },
      { rootCandidates: ["nope", "JOB-101"] },
      { rootCandidates: ["JOB-101", "JOB-102"], rootState: "RESOLVED" },
      { rootCandidates: ["JOB-101"], rootState: "CONFLICT" },
      {
        rootCandidates: Array.from({ length: 51 }, (_, i) => `JOB-${100 + i}`),
        rootState: "CONFLICT",
      },
    ];
    for (const overrides of cases) {
      const { props, onChooseRoot } = setup(overrides);
      const view = render(<RetainedRootChoice {...props} />);
      expect(view.container.querySelectorAll("button")).toHaveLength(0);
      expect(view.container.textContent).toContain("invalid");
      expect(onChooseRoot).not.toHaveBeenCalled();
      view.unmount();
    }
  });

  it("offers no choice when the root source state is UNKNOWN", () => {
    const { props, onChooseRoot } = setup({ rootState: "UNKNOWN" });
    const { container } = render(<RetainedRootChoice {...props} />);
    expect(container.querySelectorAll("button")).toHaveLength(0);
    expect(container.textContent).toContain("unknown");
    expect(onChooseRoot).not.toHaveBeenCalled();
  });

  it("never marks or emits a root that is not among the candidates", () => {
    const { props, onChooseRoot } = setup({ selectedRootJobId: "JOB-999" });
    const { container } = render(<RetainedRootChoice {...props} />);
    expect(container.textContent).toContain(
      "not among the reported candidates",
    );
    for (const button of screen.getAllByRole("button"))
      expect(button.getAttribute("aria-pressed")).toBe("false");
    fireEvent.click(screen.getByRole("button", { name: "JOB-102" }));
    expect(onChooseRoot).toHaveBeenCalledTimes(1);
    expect(onChooseRoot).toHaveBeenCalledWith({
      workRef: "WS:ONE",
      rootJobId: "JOB-102",
    });
  });

  it("shows the same information in zh-CN, including selection and notices", () => {
    const { props } = setup({ locale: "zh-CN", selectedRootJobId: "JOB-101" });
    const view = render(<RetainedRootChoice {...props} />);
    expect(screen.getByText("选择工作和审阅历史")).not.toBeNull();
    expect(screen.getByText("已选择")).not.toBeNull();
    expect(
      screen.getByRole("button", { name: "JOB-101" }).getAttribute("aria-pressed"),
    ).toBe("true");
    expect(view.container.textContent).toContain("此项目关联多个任务");
    expect(view.container.textContent).toContain(
      "当前任务仍未确定",
    );
    view.rerender(<RetainedRootChoice {...props} rootState="UNKNOWN" />);
    expect(view.container.textContent).toContain("项目根来源状态未知");
    view.rerender(
      <RetainedRootChoice {...props} rootCandidates={[]} />,
    );
    expect(view.container.textContent).toContain("报告的项目根列表无效");
  });

  it("uses the exact retained-result pair grammar before emitting choices", () => {
    for (const bad of [
      { workRef: "WS:bad space" },
      { rootCandidates: ["JOB-alpha", "JOB-102"] },
      { rootState: "OTHER" as any },
    ]) {
      const { props, onChooseRoot } = setup(bad);
      const view = render(<RetainedRootChoice {...props} />);
      expect(view.queryAllByRole("button")).toHaveLength(0);
      expect(onChooseRoot).not.toHaveBeenCalled();
      view.unmount();
    }
  });

  it("keeps choices natively focusable and keyboard-operable", () => {
    const { props, onChooseRoot } = setup();
    const { container } = render(<RetainedRootChoice {...props} />);
    const buttons = screen.getAllByRole("button");
    for (const button of buttons)
      expect(button.getAttribute("tabindex")).toBeNull();
    // jsdom synthesizes no Enter/Space activation; a native button's
    // keyboard activation is browser behavior, so this pins focusability
    // and the same click delivery that activation produces.
    const first = buttons[0];
    first.focus();
    expect(document.activeElement).toBe(first);
    fireEvent.click(first);
    expect(onChooseRoot).toHaveBeenCalledTimes(1);
    expect(onChooseRoot).toHaveBeenCalledWith({
      workRef: "WS:ONE",
      rootJobId: "JOB-101",
    });
    expect(container.querySelector("form")).toBeNull();
  });

  it("caps visible choices at eight and discloses the bounded remainder", () => {
    const many = Array.from({ length: 12 }, (_, i) => `JOB-${200 + i}`);
    const { props, onChooseRoot } = setup({
      rootCandidates: many,
      rootState: "CONFLICT",
    });
    const { container } = render(<RetainedRootChoice {...props} />);
    const lists = container.querySelectorAll("ul.items");
    expect(lists[0].children).toHaveLength(8);
    expect(container.querySelector("details")?.open).toBe(false);
    const details = container.querySelector("details");
    if (!details) throw new Error("disclosure missing");
    expect(details.querySelector("summary")?.textContent).toBe(
      "More missions (4)",
    );
    expect(details.querySelectorAll("button")).toHaveLength(4);
    details.open = true;
    const offered = Array.from(
      container.querySelectorAll("button"),
    ).map((button) => button.textContent);
    expect(offered).toEqual(many);
    fireEvent.click(container.querySelectorAll("button")[11]);
    expect(onChooseRoot).toHaveBeenCalledTimes(1);
    expect(onChooseRoot).toHaveBeenCalledWith({
      workRef: "WS:ONE",
      rootJobId: "JOB-211",
    });
  });

  it("renders only type=button choices inside no form, so choosing never submits", () => {
    const { props } = setup();
    const { container } = render(<RetainedRootChoice {...props} />);
    expect(container.querySelector("form")).toBeNull();
    const buttons = container.querySelectorAll("button");
    expect(buttons.length).toBeGreaterThan(0);
    for (const button of buttons)
      expect(button.getAttribute("type")).toBe("button");
  });
});
