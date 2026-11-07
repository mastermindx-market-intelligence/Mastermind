// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SupervisionLedger } from "./SupervisionLedger";
import {
  decodeSupervisionRead,
  type SupervisionRead,
  type SupervisionRow,
} from "./supervision-read";
import controlRoomFixture from "../fixtures/control-room-b5-c20a3cf8.json";

afterEach(cleanup);

function row(overrides: Partial<SupervisionRow> = {}): SupervisionRow {
  return {
    workRef: "WS:B5",
    title: "Bounded fixture",
    state: "active",
    rootJobId: "JOB-B5",
    rootState: "RESOLVED",
    rootCandidates: ["JOB-B5"],
    accountableSeat: "ceo",
    owedSeat: "ceo",
    owedReason: "attention_targets_seat",
    freshness: "current",
    queryStatus: "ok",
    dispatchState: "RETURNED",
    dispatchHistorical: false,
    workerEffect: null,
    sources: [],
    nextAction: null,
    nextActionWithheld: false,
    ...overrides,
  };
}

const available = (
  rows: SupervisionRow[],
  counts: { failures?: number; issues?: number } = {},
): SupervisionRead => ({
  state: "AVAILABLE",
  generatedAt: "2026-09-05T00:00:00Z",
  rows,
  sourceFailureCount: counts.failures ?? 0,
  issueCount: counts.issues ?? 0,
});

const decoded = (): SupervisionRead => decodeSupervisionRead(controlRoomFixture);

describe("SupervisionLedger", () => {
  it("renders the bounded header, caution and owner generation stamp", () => {
    const { container } = render(<SupervisionLedger read={decoded()} />);
    expect(screen.getByRole("heading", { name: "Next steps" })).toBeTruthy();
    expect(
      screen.getByText(/These observations do not confirm that work is running/i),
    ).toBeTruthy();
    expect(screen.getByText("Generated at")).toBeTruthy();
    const stamp = screen.getByText("Generated at").closest("p");
    if (!stamp) throw new Error("generation stamp paragraph missing");
    expect(within(stamp).getByText("2026-09-05T00:00:00Z")).toBeTruthy();
    expect(
      screen.getByText(/Counts are diagnostic only; zero does not prove health\./),
    ).toBeTruthy();
    // Existing presentation tokens only; no new CSS surface is introduced.
    expect(container.querySelector(".card")).toBeTruthy();
    expect(container.querySelector(".ccr-list")).toBeTruthy();
    expect(container.querySelectorAll(".form-field").length).toBeGreaterThanOrEqual(2);
    // Read-only presentation: no links, no inline runtime styles.
    expect(container.querySelector("a")).toBeNull();
    expect(container.querySelector("[style]")).toBeNull();
  });

  it("renders the decoded fixture row with every reported fact", () => {
    render(<SupervisionLedger read={decoded()} />);
    const list = screen.getByRole("list", { name: "Supervision rows" });
    const item = within(list).getByRole("listitem");
    expect(within(item).getByRole("heading", { name: "Bounded fixture" })).toBeTruthy();
    expect(within(item).getByText("WS:B5")).toBeTruthy();
    expect(within(item).getByText("Reported state: active")).toBeTruthy();
    expect(within(item).getByText("Accountable seat: ceo")).toBeTruthy();
    expect(within(item).getByText("Owed turn: ceo — attention_targets_seat")).toBeTruthy();
    expect(
      within(item).getByText("Reported freshness: current · Query status: ok"),
    ).toBeTruthy();
    expect(within(item).getByText("Root: RESOLVED · JOB-B5")).toBeTruthy();
    expect(within(item).getByText("Dispatch: RETURNED · historical: no")).toBeTruthy();
    // A null current_worker is displayed as unreported, never as "none".
    expect(within(item).getByText("Worker effect not reported")).toBeTruthy();
    expect(within(item).queryByText(/worker effect: none/i)).toBeNull();
    // Two bounded source receipts are shown as refs, not links.
    expect(within(item).getByText(/Sources \(2\)/)).toBeTruthy();
    expect(within(item).getByText("agent_os · agent_os_state.workstreams:B5")).toBeTruthy();
    expect(within(item).getByText("2026-09-03T00:00:01Z")).toBeTruthy();
    expect(within(item).getByText("Next action: not supplied")).toBeTruthy();
  });

  it("keeps effect unknown explicit even when every other fact looks good", () => {
    render(
      <SupervisionLedger
        read={available([
          row({
            freshness: "current",
            queryStatus: "ok",
            dispatchState: "RETURNED",
            dispatchHistorical: false,
            rootState: "RESOLVED",
            rootJobId: "JOB-B5",
            workerEffect: "effect_unknown",
          }),
        ])}
      />,
    );
    expect(screen.getByText("Original operation held")).toBeTruthy();
    expect(screen.getByText("Reported freshness: current · Query status: ok")).toBeTruthy();
    expect(screen.getByText("Dispatch: RETURNED · historical: no")).toBeTruthy();
  });

  it("keeps an explicit reported effect distinct from an unreported one", () => {
    const view = render(<SupervisionLedger read={available([row({ workerEffect: "none" })])} />);
    expect(screen.getByText("Reported worker effect: none")).toBeTruthy();
    view.unmount();
    render(<SupervisionLedger read={available([row({ workerEffect: null })])} />);
    expect(screen.getByText("Worker effect not reported")).toBeTruthy();
    expect(screen.queryByText("Reported worker effect: none")).toBeNull();
  });

  it("opens the exact mission only for a RESOLVED ProgramCard root", () => {
    const onOpenMission = vi.fn();
    render(
      <SupervisionLedger
        read={available([
          row({ workRef: "WS:OK", title: "Resolved lane", rootState: "RESOLVED", rootJobId: "JOB-1", rootCandidates:["JOB-1"] }),
          row({
            workRef: "WS:CONF",
            title: "Conflicted lane",
            rootState: "CONFLICT",
            rootJobId: "JOB-2",
            rootCandidates: ["JOB-2", "JOB-3"],
          }),
          row({
            workRef: "WS:UNK",
            title: "Unknown lane",
            rootState: "UNKNOWN",
            rootJobId: null,
            rootCandidates: [],
            accountableSeat: null,
            owedSeat: null,
          }),
        ])}
        onOpenMission={onOpenMission}
      />,
    );
    const buttons = screen.getAllByRole("button", { name: /Open work details/ });
    expect(buttons).toHaveLength(1);
    fireEvent.click(buttons[0]);
    expect(onOpenMission).toHaveBeenCalledTimes(1);
    expect(onOpenMission).toHaveBeenCalledWith("WS:OK", "JOB-1");
    // Competing candidates stay visible as reported evidence, never as navigation.
    expect(screen.getByText("Root candidates: JOB-2, JOB-3")).toBeTruthy();
  });

  it("decodes the canonical fixture and navigates through its RESOLVED root", () => {
    const onOpenMission = vi.fn();
    render(<SupervisionLedger read={decoded()} onOpenMission={onOpenMission} />);
    fireEvent.click(screen.getByRole("button", { name: /Open work details/ }));
    expect(onOpenMission).toHaveBeenCalledTimes(1);
    expect(onOpenMission).toHaveBeenCalledWith("WS:B5", "JOB-B5");
  });

  it("never calls navigation or any action automatically", () => {
    const onOpenMission = vi.fn();
    render(<SupervisionLedger read={decoded()} onOpenMission={onOpenMission} />);
    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "nothing matches" } });
    expect(onOpenMission).not.toHaveBeenCalled();
    const effectVerbs = /dispatch|apply|wake|trigger|requeue|send|start|retry|cancel|approve/i;
    const names = screen.getAllByRole("button").map((button) => button.textContent ?? "");
    expect(names).not.toHaveLength(0);
    expect(names.every((name) => !effectVerbs.test(name))).toBe(true);
  });

  it("shows the first eight rows behind a counted show-all", () => {
    const rows = Array.from({ length: 10 }, (_, index) =>
      row({ workRef: `WS:R${index}`, title: `Lane ${index}` }),
    );
    render(<SupervisionLedger read={available(rows)} onOpenMission={vi.fn()} />);
    expect(screen.getAllByRole("listitem")).toHaveLength(8);
    expect(screen.getByText("8 of 10 shown")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Show all 10" }));
    expect(screen.getAllByRole("listitem")).toHaveLength(10);
    expect(screen.getByText("10 of 10 shown")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /Show all/ })).toBeNull();
  });

  it("filters rows by search text and by role", () => {
    const rows = Array.from({ length: 10 }, (_, index) =>
      row({
        workRef: `WS:R${index}`,
        title: `Lane ${index}`,
        owedSeat: index % 2 ? "worker" : "ceo",
        owedReason: `reason ${index}`,
      }),
    );
    render(<SupervisionLedger read={available(rows)} />);
    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "lane 9" } });
    expect(screen.getAllByRole("listitem")).toHaveLength(1);
    expect(screen.getByText("1 of 1 shown")).toBeTruthy();
    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "" } });
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "worker" } });
    expect(screen.getAllByRole("listitem")).toHaveLength(5);
    expect(screen.getByText("5 of 5 shown")).toBeTruthy();
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "unknown" } });
    expect(screen.queryByRole("listitem")).toBeNull();
    expect(
      screen.getByText("No rows match the current search or role filter."),
    ).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Clear filters" }));
    expect(screen.getAllByRole("listitem")).toHaveLength(8);
    expect(screen.getByText("8 of 10 shown")).toBeTruthy();
  });

  it("withholds the guarded next action with its caveat, per row", () => {
    render(
      <SupervisionLedger
        read={available([
          row({ nextActionWithheld: true, nextAction: null }),
          row({ workRef: "WS:N", title: "Plain lane", nextAction: "Write the summary" }),
        ])}
      />,
    );
    expect(
      screen.getByText(
        "Next action withheld by the source guard; the withheld text is not displayed.",
      ),
    ).toBeTruthy();
    expect(screen.getByText("Next action: Write the summary")).toBeTruthy();
    expect(screen.queryByText(/Write the summary.*withheld/i)).toBeNull();
  });

  it("keeps empty, unavailable and invalid sources distinct", () => {
    const view = render(<SupervisionLedger read={{ state: "UNAVAILABLE", reason: "SOURCE_UNAVAILABLE" }} />);
    expect(
      screen.getByText(
        "The bounded supervision source is unavailable. No responsibility state is inferred.",
      ),
    ).toBeTruthy();
    expect(screen.queryByRole("list")).toBeNull();
    view.unmount();
    render(<SupervisionLedger read={{ state: "UNAVAILABLE", reason: "SOURCE_INVALID" }} />);
    expect(screen.getByText(/withheld whole/)).toBeTruthy();
    expect(screen.queryByRole("list")).toBeNull();
    const empty = render(<SupervisionLedger read={available([])} />);
    expect(screen.getByText(/carries no supervision rows/)).toBeTruthy();
    expect(screen.queryByRole("list")).toBeNull();
    empty.unmount();
  });

  it("surfaces source failure and issue counts as a diagnostic caveat", () => {
    render(<SupervisionLedger read={available([row()], { failures: 2, issues: 3 })} />);
    expect(screen.getByText(/source failures: 2 · source issues: 3\./)).toBeTruthy();
    expect(screen.getByText(/Counts are diagnostic only/)).toBeTruthy();
  });

  it("renders the zh strings with parity", () => {
    render(<SupervisionLedger read={decoded()} locale="zh-CN" onOpenMission={vi.fn()} />);
    expect(screen.getByRole("heading", { name: "后续工作" })).toBeTruthy();
    expect(screen.getByText(/这些记录不能证明工作正在运行/)).toBeTruthy();
    expect(screen.getByText("生成时间")).toBeTruthy();
    expect(screen.getByText(/计数仅用于诊断；为零不代表健康。/)).toBeTruthy();
    const item = screen.getByRole("listitem");
    expect(within(item).getByText("报告状态: active")).toBeTruthy();
    expect(within(item).getByText("责任席位: ceo")).toBeTruthy();
    expect(within(item).getByText("应付回合: ceo — attention_targets_seat")).toBeTruthy();
    expect(within(item).getByText("报告的新鲜度: current · 查询状态: ok")).toBeTruthy();
    expect(within(item).getByText("调度: RETURNED · 历史: 否")).toBeTruthy();
    expect(within(item).getByText("工作效果未报告")).toBeTruthy();
    expect(within(item).getByRole("button", { name: "打开工作详情: WS:B5" })).toBeTruthy();
  });

  it("renders zh show-all, withheld caveat and source states distinctly", () => {
    const rows = Array.from({ length: 10 }, (_, index) => row({ workRef: `WS:R${index}` }));
    const view = render(<SupervisionLedger read={available(rows)} locale="zh" />);
    fireEvent.click(screen.getByRole("button", { name: "显示全部 10 行" }));
    expect(screen.getAllByRole("listitem")).toHaveLength(10);
    view.unmount();
    render(
      <SupervisionLedger
        read={available([row({ nextActionWithheld: true })])}
        locale="zh-CN"
      />,
    );
    expect(screen.getByText("下一步被来源保护隐藏；不显示被隐藏的文本。")).toBeTruthy();
    view.unmount();
    render(<SupervisionLedger read={{ state: "UNAVAILABLE", reason: "SOURCE_UNAVAILABLE" }} locale="zh-CN" />);
    expect(screen.getByText("有界监督来源不可用。不推断任何职责状态。")).toBeTruthy();
    view.unmount();
    render(<SupervisionLedger read={{ state: "UNAVAILABLE", reason: "SOURCE_INVALID" }} locale="zh-CN" />);
    expect(screen.getByText("有界监督来源无效，整体不予显示。不显示部分账本或部分绿色状态。")).toBeTruthy();
    view.unmount();
    render(<SupervisionLedger read={available([])} locale="zh-CN" />);
    expect(screen.getByText("此有界快照没有监督行。这不代表全公司没有工作。")).toBeTruthy();
  });
});
