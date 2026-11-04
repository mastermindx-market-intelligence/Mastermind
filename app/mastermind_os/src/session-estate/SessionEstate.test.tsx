// @vitest-environment jsdom
/** Inert Session Estate tests: typed fixtures only. No network, storage,
 * timers, dispatch or live effects — every callback is an in-memory vi.fn(),
 * and fixture types are derived from the existing Control Room contract.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ControlRoomState } from "../control-room";
import { SessionEstate } from "./SessionEstate";
afterEach(cleanup);

type AvailableRead = Extract<ControlRoomState, { state: "AVAILABLE" }>;
type Navigation = AvailableRead["navigation"];
type NavAvailable = Extract<Navigation, { state: "AVAILABLE" }>;
type Binding = NavAvailable["bindings"][number];
type Conflict = NavAvailable["conflicts"][number];
type Program = AvailableRead["programs"][number];
type CrossPlane = AvailableRead["crossPlane"];

// The cross-plane projection is opaque to this presentation; the fixture
// carries the typed slot without interpreting it.
const crossPlane = Object.freeze({}) as unknown as CrossPlane;

const OBSERVED = "2026-11-03T09:00:00Z";
const VERIFIED = "2026-11-03T09:05:00Z";
const ALPHA_WORK = "JOB:mission-alpha";
const ALPHA_ROOT = "root-alpha-0001";

const hex = (n: number, width: number) => n.toString(16).padStart(width, "0");
const bindingId = (n: number) =>
  `${hex(n, 8)}-a1b2-4c3d-8e4f-${hex(n, 12)}`;

const LOCATOR = {
  chatgpt: "chatgpt_managed_env",
  claude_code: "claude_code_session",
  claude_desktop: "claude_desktop_url",
  cursor_agent: "cursor_agent_thread",
  codex: "codex_session",
} as const;

const makeBinding = (n: number, overrides: Partial<Binding> = {}): Binding => ({
  binding_id: bindingId(n),
  work_ref: `JOB:mission-${n}`,
  role: "worker",
  provider: "claude_code",
  seat_ref: null,
  locator_kind: LOCATOR.claude_code,
  observed_at: OBSERVED,
  last_verified_at: VERIFIED,
  ...overrides,
});

const makeNav = (
  bindings: readonly Binding[],
  overrides: Partial<Omit<NavAvailable, "state">> = {},
): NavAvailable => ({
  state: "AVAILABLE",
  bindings,
  unboundBindingIds: [],
  conflicts: [],
  capabilities: {},
  bindingsPathPresent: bindings.length > 0,
  ...overrides,
});

const makeProgram = (workRef: string, overrides: Partial<Program> = {}): Program => ({
  workRef,
  title: workRef,
  state: "RUNNING",
  nextAction: null,
  nextActionWithheld: false,
  rootJobId: null,
  rootState: "UNKNOWN",
  rootCandidates: [],
  ...overrides,
});

const makeRead = (
  overrides: Partial<Omit<AvailableRead, "state">> = {},
): AvailableRead => ({
  state: "AVAILABLE",
  programs: [],
  navigation: makeNav([]),
  observedAt: OBSERVED,
  liveBuildsActive: false,
  refreshInFlight: false,
  freshness: "OWNER_QUALIFIED",
  publicationSeq: 12,
  crossPlane,
  ownerRevision: 1,
  ...overrides,
});

const pendingState: ControlRoomState = { state: "PENDING", ownerRevision: 3 };
const unavailableState: ControlRoomState = {
  state: "UNAVAILABLE",
  reason: "CONTROL_ROOM_SOURCE_UNAVAILABLE",
  ownerRevision: 4,
};

/** Eleven decoder-valid bindings across providers/roles: eight stay on the
 * first page, three behind the counted show-all toggle.
 */
const mainRead = (overrides: Partial<Omit<AvailableRead, "state">> = {}): AvailableRead =>
  makeRead({
    programs: [
      makeProgram(ALPHA_WORK, {
        rootState: "RESOLVED",
        rootJobId: ALPHA_ROOT,
        rootCandidates: [ALPHA_ROOT],
      }),
    ],
    navigation: makeNav([
      makeBinding(1, { work_ref: ALPHA_WORK }),
      makeBinding(2),
      makeBinding(3, { work_ref: "WS:platform", provider: "codex", locator_kind: LOCATOR.codex }),
      makeBinding(4, {
        work_ref: "PR:release-11",
        provider: "chatgpt",
        locator_kind: LOCATOR.chatgpt,
        seat_ref: "seat-11",
      }),
      makeBinding(5),
      makeBinding(6),
      makeBinding(7, {
        work_ref: "JOB:mission-7",
        provider: "claude_desktop",
        locator_kind: LOCATOR.claude_desktop,
      }),
      makeBinding(8, {
        work_ref: "WS:inbound",
        provider: "cursor_agent",
        locator_kind: LOCATOR.cursor_agent,
      }),
      makeBinding(9),
      makeBinding(10),
      makeBinding(11),
    ]),
    ...overrides,
  });

function requireRow(id: string): HTMLElement {
  const row = screen.queryByTestId(`session-estate-row-${id}`);
  if (!(row instanceof HTMLElement)) throw new Error(`missing row: ${id}`);
  return row;
}

function refreshButton(): HTMLButtonElement {
  // "Refresh" and the in-flight "Refreshing…" label share one command.
  const button = screen.queryByRole("button", { name: /refresh/i });
  if (!(button instanceof HTMLButtonElement)) throw new Error("refresh button missing");
  return button;
}

async function inspect(row: HTMLElement, user: ReturnType<typeof userEvent.setup>) {
  await user.click(within(row).getByRole("button"));
}

function detailRegion(): HTMLElement {
  const region = screen.queryByRole("region", { name: "Binding detail" });
  if (!(region instanceof HTMLElement)) throw new Error("detail region missing");
  return region;
}

describe("SessionEstate", () => {
  it("does not navigate when a resolved label lacks its exact singleton root", async () => {
    const user = userEvent.setup();
    for (const roots of [[], ["foreign-root"], [ALPHA_ROOT, "foreign-root"]]) {
      const onOpenMission = vi.fn();
      const view = render(<SessionEstate state={mainRead({programs:[makeProgram(ALPHA_WORK, {
        rootState:"RESOLVED",rootJobId:ALPHA_ROOT,rootCandidates:roots,
      })]})} canRefresh onRefresh={vi.fn()} onOpenMission={onOpenMission} />);
      await inspect(requireRow(bindingId(1)), user);
      expect(screen.queryByRole("button", {name:"Open Mission"})).toBeNull();
      expect(onOpenMission).not.toHaveBeenCalled();
      view.unmount();
    }
  });
  it("never shows a count while the owner read is pending", () => {
    const onRefresh = vi.fn();
    render(
      <SessionEstate state={pendingState} canRefresh onRefresh={onRefresh} onOpenMission={vi.fn()} />,
    );
    expect(screen.getByText("Waiting for the next owner read. No count is shown.")).toBeTruthy();
    expect(screen.queryByText(/no bindings observed/i)).toBeNull();
    expect(refreshButton().disabled).toBe(true);
    expect(onRefresh).not.toHaveBeenCalled();
  });

  it("shows the owner reason for a missing source and never an empty observation", () => {
    const onRefresh = vi.fn();
    render(
      <SessionEstate
        state={unavailableState}
        canRefresh
        onRefresh={onRefresh}
        onOpenMission={vi.fn()}
      />,
    );
    expect(screen.getByText("Session estate unavailable.")).toBeTruthy();
    expect(screen.getByText("Owner reason: CONTROL_ROOM_SOURCE_UNAVAILABLE")).toBeTruthy();
    expect(screen.queryByText(/no bindings observed/i)).toBeNull();
    expect(screen.queryByLabelText("Search bindings")).toBeNull();
    expect(onRefresh).not.toHaveBeenCalled();
  });

  it("explains an unavailable navigation projection without fabricating rows", () => {
    const read = makeRead({
      navigation: { state: "UNAVAILABLE", reason: "CONTROL_ROOM_NAVIGATION_INVALID" },
    });
    render(<SessionEstate state={read} canRefresh onRefresh={vi.fn()} onOpenMission={vi.fn()} />);
    expect(
      screen.getByText("Navigation projection unavailable (CONTROL_ROOM_NAVIGATION_INVALID)."),
    ).toBeTruthy();
    expect(screen.queryByLabelText("Search bindings")).toBeNull();
    expect(screen.queryByText(/no bindings observed/i)).toBeNull();
  });

  it("reports an explicit bounded zero when the read is available but empty", () => {
    render(<SessionEstate state={makeRead()} canRefresh onRefresh={vi.fn()} onOpenMission={vi.fn()} />);
    expect(screen.getByText("Bounded read: no bindings observed.")).toBeTruthy();
    expect(screen.getByText("Showing 0 of 0.")).toBeTruthy();
    expect(screen.getByText("No bindings match this search.")).toBeTruthy();
  });

  it("refreshes only on the explicit command", async () => {
    const user = userEvent.setup();
    const onRefresh = vi.fn();
    const onOpenMission = vi.fn();
    render(
      <SessionEstate state={mainRead()} canRefresh onRefresh={onRefresh} onOpenMission={onOpenMission} />,
    );
    expect(refreshButton().disabled).toBe(false);
    await user.click(refreshButton());
    expect(onRefresh).toHaveBeenCalledTimes(1);

    await user.type(screen.getByLabelText("Search bindings"), "codex");
    expect(onRefresh).toHaveBeenCalledTimes(1);

    await inspect(requireRow(bindingId(3)), user);
    expect(onRefresh).toHaveBeenCalledTimes(1);
    expect(onOpenMission).not.toHaveBeenCalled();
  });

  it("keeps refresh disabled while pending, in flight or unauthorised", async () => {
    const user = userEvent.setup();
    const onRefresh = vi.fn();
    const inFlight: AvailableRead = makeRead({ refreshPending: true });

    const pending = render(
      <SessionEstate state={pendingState} canRefresh onRefresh={onRefresh} onOpenMission={vi.fn()} />,
    );
    expect(refreshButton().disabled).toBe(true);
    pending.unmount();

    const flight = render(
      <SessionEstate state={inFlight} canRefresh onRefresh={onRefresh} onOpenMission={vi.fn()} />,
    );
    expect(refreshButton().disabled).toBe(true);
    expect(screen.getByText("Refreshing…")).toBeTruthy();
    flight.unmount();

    const unauthorised = render(
      <SessionEstate state={mainRead()} canRefresh={false} onRefresh={onRefresh} onOpenMission={vi.fn()} />,
    );
    expect(refreshButton().disabled).toBe(true);
    await user.click(refreshButton());
    expect(onRefresh).not.toHaveBeenCalled();
    unauthorised.unmount();
  });

  it("searches bindings by provider, role, work reference and seat", async () => {
    const user = userEvent.setup();
    render(
      <SessionEstate state={mainRead()} canRefresh onRefresh={vi.fn()} onOpenMission={vi.fn()} />,
    );
    const search = screen.getByLabelText("Search bindings");

    await user.type(search, "codex");
    expect(screen.getByTestId(`session-estate-row-${bindingId(3)}`)).toBeTruthy();
    expect(screen.queryByTestId(`session-estate-row-${bindingId(1)}`)).toBeNull();

    await user.clear(search);
    await user.type(search, "PR:release-11");
    expect(screen.getByTestId(`session-estate-row-${bindingId(4)}`)).toBeTruthy();
    expect(screen.queryByTestId(`session-estate-row-${bindingId(3)}`)).toBeNull();

    await user.clear(search);
    await user.type(search, "seat-11");
    expect(screen.getByTestId(`session-estate-row-${bindingId(4)}`)).toBeTruthy();

    await user.clear(search);
    await user.type(search, "chairman");
    expect(screen.getByText("No bindings match this search.")).toBeTruthy();
    expect(document.querySelector(".session-estate__inspect")).toBeNull();
    expect(document.querySelector(".session-estate__toggle")).toBeNull();
  });

  it("shows the first eight rows behind a counted show-all toggle", async () => {
    const user = userEvent.setup();
    render(
      <SessionEstate state={mainRead()} canRefresh onRefresh={vi.fn()} onOpenMission={vi.fn()} />,
    );
    expect(screen.getAllByTestId(/^session-estate-row-/)).toHaveLength(8);
    expect(screen.getByText("Showing 8 of 11."));

    await user.click(screen.getByRole("button", { name: "Show all 11 bindings" }));
    expect(screen.getAllByTestId(/^session-estate-row-/)).toHaveLength(11);
    expect(screen.getByText("Showing 11 of 11."));

    await user.click(screen.getByRole("button", { name: "Show the first 8 bindings" }));
    expect(screen.getAllByTestId(/^session-estate-row-/)).toHaveLength(8);
  });

  it("inspects the exact selected binding and switches with the row", async () => {
    const user = userEvent.setup();
    render(
      <SessionEstate state={mainRead()} canRefresh onRefresh={vi.fn()} onOpenMission={vi.fn()} />,
    );
    await inspect(requireRow(bindingId(1)), user);
    let detail = detailRegion();
    expect(within(detail).getByText(bindingId(1))).toBeTruthy();
    expect(within(detail).getByText(ALPHA_WORK)).toBeTruthy();
    expect(within(detail).getByText("claude_code")).toBeTruthy();
    expect(within(detail).getByText(OBSERVED)).toBeTruthy();
    expect(within(detail).getByText("None observed for this binding.")).toBeTruthy();

    await inspect(requireRow(bindingId(3)), user);
    detail = detailRegion();
    expect(within(detail).getByText(bindingId(3))).toBeTruthy();
    expect(within(detail).getByText("WS:platform")).toBeTruthy();
    expect(within(detail).getByText("codex")).toBeTruthy();
    expect(within(detail).queryByText(bindingId(1))).toBeNull();
    // WS:platform has no observed programme, so navigation stays withheld.
    expect(within(detail).queryByRole("button", { name: "Open Mission" })).toBeNull();
    expect(
      within(detail).getByText("No programme is observed for this work reference."),
    ).toBeTruthy();
  });

  it("opens the exact mission with the work reference and resolved root job id", async () => {
    const user = userEvent.setup();
    const onOpenMission = vi.fn();
    render(
      <SessionEstate state={mainRead()} canRefresh onRefresh={vi.fn()} onOpenMission={onOpenMission} />,
    );
    await inspect(requireRow(bindingId(1)), user);
    expect(
      within(detailRegion()).getByText(
        "Read navigation only; it does not open or activate any runtime surface.",
      ),
    ).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "Open Mission" }));
    expect(onOpenMission).toHaveBeenCalledTimes(1);
    expect(onOpenMission).toHaveBeenCalledWith(ALPHA_WORK, ALPHA_ROOT);
  });

  it("suppresses mission navigation for an unbound surface", async () => {
    const user = userEvent.setup();
    const onOpenMission = vi.fn();
    const id = bindingId(20);
    const read = makeRead({
      programs: [makeProgram("PR:docs", { rootState: "RESOLVED", rootJobId: "root-docs-1" })],
      navigation: makeNav([makeBinding(20, { work_ref: "PR:docs" })], {
        unboundBindingIds: [id],
      }),
    });
    render(
      <SessionEstate state={read} canRefresh onRefresh={vi.fn()} onOpenMission={onOpenMission} />,
    );
    await inspect(requireRow(id), user);
    expect(screen.queryByRole("button", { name: "Open Mission" })).toBeNull();
    expect(
      within(detailRegion()).getByText(
        "This binding is outside the current programme observation, so no mission was guessed.",
      ),
    ).toBeTruthy();
    expect(
      within(detailRegion()).getByText("Work reference outside this programme observation"),
    ).toBeTruthy();
    expect(onOpenMission).not.toHaveBeenCalled();
  });

  it("suppresses mission navigation for a conflicting work/role group", async () => {
    const user = userEvent.setup();
    const onOpenMission = vi.fn();
    const idA = bindingId(30);
    const idB = bindingId(31);
    const conflict: Conflict = {
      work_ref: "JOB:dup",
      role: "worker",
      binding_ids: [idA, idB],
    };
    const read = makeRead({
      programs: [makeProgram("JOB:dup", { rootState: "RESOLVED", rootJobId: "root-dup-1" })],
      navigation: makeNav(
        [makeBinding(30, { work_ref: "JOB:dup" }), makeBinding(31, { work_ref: "JOB:dup" })],
        { conflicts: [conflict] },
      ),
    });
    render(
      <SessionEstate state={read} canRefresh onRefresh={vi.fn()} onOpenMission={onOpenMission} />,
    );
    await inspect(requireRow(idA), user);
    const detail = detailRegion();
    expect(within(detail).getByText("Ambiguous group (2): " + [idA, idB].join(", "))).toBeTruthy();
    expect(
      within(detail).getByText(
        "This binding sits in a conflicting work/role group, so no exact mission is offered.",
      ),
    ).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Open Mission" })).toBeNull();

    await inspect(requireRow(idB), user);
    expect(within(detailRegion()).getByText(bindingId(31))).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Open Mission" })).toBeNull();
    expect(onOpenMission).not.toHaveBeenCalled();
  });

  it("suppresses mission navigation for duplicate programmes on one work reference", async () => {
    const user = userEvent.setup();
    const onOpenMission = vi.fn();
    const read = makeRead({
      programs: [
        makeProgram("JOB:dup", { rootState: "RESOLVED", rootJobId: "root-dup-1" }),
        makeProgram("JOB:dup", { rootState: "RESOLVED", rootJobId: "root-dup-2" }),
      ],
      navigation: makeNav([makeBinding(40, { work_ref: "JOB:dup" })]),
    });
    render(
      <SessionEstate state={read} canRefresh onRefresh={vi.fn()} onOpenMission={onOpenMission} />,
    );
    await inspect(requireRow(bindingId(40)), user);
    expect(screen.queryByRole("button", { name: "Open Mission" })).toBeNull();
    expect(
      within(detailRegion()).getByText(
        "Several programmes share this work reference, so the mission is ambiguous.",
      ),
    ).toBeTruthy();
    expect(onOpenMission).not.toHaveBeenCalled();
  });

  it("suppresses mission navigation for unresolved, conflicting or rootless programmes", async () => {
    const user = userEvent.setup();
    const onOpenMission = vi.fn();

    const unresolved = makeRead({
      programs: [makeProgram("JOB:solo")],
      navigation: makeNav([makeBinding(50, { work_ref: "JOB:solo" })]),
    });
    const first = render(
      <SessionEstate state={unresolved} canRefresh onRefresh={vi.fn()} onOpenMission={onOpenMission} />,
    );
    await inspect(requireRow(bindingId(50)), user);
    expect(screen.queryByRole("button", { name: "Open Mission" })).toBeNull();
    expect(
      within(detailRegion()).getByText("The root job for this work reference is not resolved."),
    ).toBeTruthy();
    first.unmount();

    const conflicting = makeRead({
      programs: [
        makeProgram("JOB:solo", {
          rootState: "CONFLICT",
          rootCandidates: ["root-a", "root-b"],
        }),
      ],
      navigation: makeNav([makeBinding(50, { work_ref: "JOB:solo" })]),
    });
    const second = render(
      <SessionEstate
        state={conflicting}
        canRefresh
        onRefresh={vi.fn()}
        onOpenMission={onOpenMission}
      />,
    );
    await inspect(requireRow(bindingId(50)), user);
    expect(screen.queryByRole("button", { name: "Open Mission" })).toBeNull();
    expect(
      within(detailRegion()).getByText("The root candidates for this work reference conflict."),
    ).toBeTruthy();
    second.unmount();

    const rootless = makeRead({
      programs: [makeProgram("JOB:solo", { rootState: "RESOLVED", rootJobId: null })],
      navigation: makeNav([makeBinding(50, { work_ref: "JOB:solo" })]),
    });
    const third = render(
      <SessionEstate state={rootless} canRefresh onRefresh={vi.fn()} onOpenMission={onOpenMission} />,
    );
    await inspect(requireRow(bindingId(50)), user);
    expect(screen.queryByRole("button", { name: "Open Mission" })).toBeNull();
    expect(
      within(detailRegion()).getByText("The resolved programme carries no root job identifier."),
    ).toBeTruthy();
    third.unmount();

    const orphan = makeRead({
      navigation: makeNav([makeBinding(51, { work_ref: "JOB:orphan" })]),
    });
    const fourth = render(
      <SessionEstate state={orphan} canRefresh onRefresh={vi.fn()} onOpenMission={onOpenMission} />,
    );
    await inspect(requireRow(bindingId(51)), user);
    expect(
      within(detailRegion()).getByText("No programme is observed for this work reference."),
    ).toBeTruthy();
    fourth.unmount();

    expect(onOpenMission).not.toHaveBeenCalled();
  });

  it("invalidates the detail when the selected binding leaves the current read", async () => {
    const user = userEvent.setup();
    const view = render(
      <SessionEstate state={mainRead()} canRefresh onRefresh={vi.fn()} onOpenMission={vi.fn()} />,
    );
    await inspect(requireRow(bindingId(1)), user);
    expect(within(detailRegion()).getByText(bindingId(1))).toBeTruthy();

    const base = mainRead();
    const nextNavigation =
      base.navigation.state === "AVAILABLE" ? base.navigation : null;
    if (!nextNavigation) throw new Error("navigation missing");
    const survivors = nextNavigation.bindings.filter(
      (binding) => binding.binding_id !== bindingId(1),
    );
    view.rerender(
      <SessionEstate
        state={makeRead({
          ownerRevision: 2,
          navigation: makeNav(survivors),
        })}
        canRefresh
        onRefresh={vi.fn()}
        onOpenMission={vi.fn()}
      />,
    );
    expect(
      screen.getByText(
        "The selected binding is no longer present in the current read. Inspect another binding.",
      ),
    ).toBeTruthy();
    expect(screen.queryByText(bindingId(1))).toBeNull();
    expect(screen.queryByRole("button", { name: "Open Mission" })).toBeNull();
    expect(within(detailRegion()).queryByText(ALPHA_ROOT)).toBeNull();
  });

  it("renders the Chinese labels end to end", async () => {
    const user = userEvent.setup();
    const onOpenMission = vi.fn();
    render(
      <SessionEstate
        state={mainRead()}
        locale="zh-CN"
        canRefresh
        onRefresh={vi.fn()}
        onOpenMission={onOpenMission}
      />,
    );
    expect(screen.getByText("会话工作区")).toBeTruthy();
    expect(screen.getByText("已保存的绑定不代表会话正在运行。")).toBeTruthy();
    expect(screen.getByText("有界读取：观察到 11 条绑定。")).toBeTruthy();
    expect(screen.getByLabelText("搜索绑定")).toBeTruthy();
    expect(screen.getByRole("button", { name: "显示全部 11 条绑定" })).toBeTruthy();

    await inspect(requireRow(bindingId(1)), user);
    expect(screen.getByRole("region", { name: "绑定详情" })).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "打开任务" }));
    expect(onOpenMission).toHaveBeenCalledTimes(1);
    expect(onOpenMission).toHaveBeenCalledWith(ALPHA_WORK, ALPHA_ROOT);
  });

  it("keeps the parent command controls as children and adds no command surface", () => {
    const onRefresh = vi.fn();
    render(
      <SessionEstate state={mainRead()} canRefresh onRefresh={onRefresh} onOpenMission={vi.fn()}>
        <div data-testid="surface-controls">
          <button type="button">Parent control</button>
        </div>
      </SessionEstate>,
    );
    expect(screen.getByTestId("surface-controls")).toBeTruthy();
    expect(screen.getAllByRole("button", { name: /refresh/i })).toHaveLength(1);
    expect(screen.queryByRole("button", { name: /new session/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /activate/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /open surface/i })).toBeNull();
    expect(onRefresh).not.toHaveBeenCalled();
  });
});
