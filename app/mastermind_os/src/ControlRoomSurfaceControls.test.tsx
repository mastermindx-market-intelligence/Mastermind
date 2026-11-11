// @vitest-environment jsdom
// Component-only fixtures; App/host and installed acceptance remain separate.
import { act, cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  ControlRoomSurfaceControls,
  type ControlRoomActionPresentation,
  type ControlRoomSurfaceControlsProps,
} from "./ControlRoomSurfaceControls";
import { CONTROL_ROOM_UNKNOWN_OUTCOME, decodeControlRoomActionResult } from "./control-room";
import type { ControlRoomOperation } from "./control-room";
import type {
  ControlRoomBindingSummary, ControlRoomDiscovery, ControlRoomNavigation,
  ControlRoomProvider,
} from "./control-room-navigation";

afterEach(cleanup);

const bindingId = (n: number) => `${String(n).padStart(8, "0")}-1111-4111-8111-111111111111`;
function binding(provider: ControlRoomProvider = "claude_code", n = 1): ControlRoomBindingSummary {
  const kinds = {
    chatgpt: "chatgpt_managed_env", claude_code: "claude_code_session",
    claude_desktop: "claude_desktop_url", cursor_agent: "cursor_agent_thread",
    codex: "codex_session",
  } as const;
  return Object.freeze({
    binding_id: bindingId(n), work_ref: "WS:surface-fixture", role: "worker",
    provider, seat_ref: provider === "chatgpt" ? "fixture-seat" : null,
    locator_kind: kinds[provider], observed_at: "2026-10-19T11:00:00Z", last_verified_at: null,
  });
}
function navigation(rows: readonly ControlRoomBindingSummary[] = [binding()]): ControlRoomNavigation {
  return { state: "AVAILABLE", bindings: rows, unboundBindingIds: [], conflicts: [], capabilities: {}, bindingsPathPresent: true };
}
function discovery(count = 0): ControlRoomDiscovery {
  return {
    chatgpt_environments: { multilogin: [], gologin: [] }, claude_code_sessions: [],
    codex_sessions: Array.from({ length: count }, (_, i) => ({ session_id: `fixture-session-${i + 1}`, date: "2026-10-19" })),
    cursor: { supported: false, note: "Fixture discovery is unavailable for Cursor." },
  };
}
function result(operation: ControlRoomOperation, disposition: "OWNER_RETURNED" | "NOT_DISPATCHED" | "EFFECT_UNKNOWN", outcome: Record<string, unknown>) {
  const status = disposition === "OWNER_RETURNED" ? 200 : disposition === "NOT_DISPATCHED" ? 403 : 503;
  return decodeControlRoomActionResult({
    schema: "mastermind.workspace_control_room_action_result.v1", operation, status, disposition, outcome,
  }, operation, status);
}
function mount(overrides: Partial<ControlRoomSurfaceControlsProps> = {}) {
  const calls = {
    onDiscover: vi.fn(), onOpenSurface: vi.fn(), onBindSurface: vi.fn(),
    onUnbindSurface: vi.fn(), onRefreshBuilds: vi.fn(),
  };
  let props: ControlRoomSurfaceControlsProps = {
    navigation: navigation(), discovery: { state: "IDLE" }, action: { state: "IDLE" },
    held: false, canAct: true, ...calls, ...overrides,
  };
  const view = render(<main><ControlRoomSurfaceControls {...props} /></main>);
  return {
    calls,
    rerender(next: Partial<ControlRoomSurfaceControlsProps>) {
      props = { ...props, ...next };
      view.rerender(<main><ControlRoomSurfaceControls {...props} /></main>);
    },
  };
}
function mutationsUntouched(calls: ReturnType<typeof mount>["calls"]) {
  expect(calls.onOpenSurface).not.toHaveBeenCalled();
  expect(calls.onBindSurface).not.toHaveBeenCalled();
  expect(calls.onUnbindSurface).not.toHaveBeenCalled();
  expect(calls.onRefreshBuilds).not.toHaveBeenCalled();
}
async function beginBind(provider: ControlRoomProvider) {
  const user = userEvent.setup();
  await user.click(screen.getByText("Bind a surface"));
  await user.type(screen.getByLabelText("Work reference"), "WS:explicit-draft");
  await user.selectOptions(screen.getByLabelText("Role"), "worker");
  await user.selectOptions(screen.getByLabelText("Provider"), provider);
  return user;
}

describe("Control Room surface presentation boundaries", () => {
  it("does not display method buttons when the optional methods are absent", () => {
    mount({ onDiscover: undefined, onOpenSurface: undefined, onBindSurface: undefined,
      onUnbindSurface: undefined, onRefreshBuilds: undefined });
    expect(screen.queryAllByRole("button")).toHaveLength(0);
    expect(screen.getByRole("list", { name: "Observed surface bindings" })).toBeTruthy();
    expect(screen.getByText("Discovery has not been read.")).toBeTruthy();
  });

  it("does nothing on mount, and standard Open carries only the selected binding ID", async () => {
    const { calls } = mount();
    mutationsUntouched(calls);
    expect(calls.onDiscover).not.toHaveBeenCalled();
    await userEvent.setup().click(screen.getByRole("button", { name: `Open Claude Code binding ${bindingId(1)}` }));
    expect(calls.onOpenSurface).toHaveBeenCalledOnce();
    expect(calls.onOpenSurface.mock.calls[0][0]).toEqual({ binding_id: bindingId(1) });
    expect(Object.isFrozen(calls.onOpenSurface.mock.calls[0][0])).toBe(true);
  });

  it("uses desktop only through the explicit Claude Code button", async () => {
    const { calls } = mount();
    await userEvent.setup().click(screen.getByRole("button", { name: `Open Claude Code binding ${bindingId(1)} in Claude desktop` }));
    expect(calls.onOpenSurface).toHaveBeenCalledTimes(1);
    expect(calls.onOpenSurface).toHaveBeenCalledWith({ binding_id: bindingId(1), target_surface: "desktop" });
  });

  it("unbinds only after confirming the exact handle once, without an owed context", async () => {
    const { calls } = mount();
    await userEvent.setup().click(screen.getByRole("button", { name: `Unbind Claude Code binding ${bindingId(1)}` }));
    expect(calls.onUnbindSurface).not.toHaveBeenCalled();
    const confirmation = screen.getByRole("group", { name: "Confirm binding removal" });
    expect(within(confirmation).getByText(bindingId(1))).toBeTruthy();
    const confirm = within(confirmation).getByRole("button", { name: "Confirm Unbind" });
    act(() => { confirm.click(); confirm.click(); });
    expect(calls.onUnbindSurface).toHaveBeenCalledTimes(1);
    expect(calls.onUnbindSurface).toHaveBeenCalledWith({ binding_id: bindingId(1) });
    expect(calls.onOpenSurface).not.toHaveBeenCalled();
    expect(screen.queryByRole("group", { name: "Confirm binding removal" })).toBeNull();
  });

  it("dismisses only the local Unbind choice while retaining an unknown action hold", async () => {
    const mounted = mount();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: `Unbind Claude Code binding ${bindingId(1)}` }));
    mutationsUntouched(mounted.calls);
    mounted.rerender({ held: true, action: { state: "FAILURE", operation: "open", disposition: "EFFECT_UNKNOWN" } });
    expect((screen.getByRole("button", { name: "Confirm Unbind" }) as HTMLButtonElement).disabled).toBe(true);
    await user.click(screen.getByRole("button", { name: "Keep binding" }));
    expect(screen.queryByRole("group", { name: "Confirm binding removal" })).toBeNull();
    expect(screen.getByText("Action outcome unknown")).toBeTruthy();
    expect((screen.getByRole("button", { name: "Refresh builds" }) as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByRole("button", { name: "Discover surfaces" }) as HTMLButtonElement).disabled).toBe(false);
    mutationsUntouched(mounted.calls);
  });

  it("invokes only the explicit build-refresh callback with no caller-selected source", async () => {
    const { calls } = mount();
    await userEvent.setup().click(screen.getByRole("button", { name: "Refresh builds" }));
    expect(calls.onRefreshBuilds).toHaveBeenCalledTimes(1);
    expect(calls.onRefreshBuilds).toHaveBeenCalledWith();
    expect(calls.onDiscover).not.toHaveBeenCalled();
    expect(calls.onOpenSurface).not.toHaveBeenCalled();
    expect(calls.onBindSurface).not.toHaveBeenCalled();
    expect(calls.onUnbindSurface).not.toHaveBeenCalled();
  });

  it("keeps both conflicting rows and opens only the row explicitly chosen", async () => {
    const rows = [binding("claude_code", 1), binding("codex", 2)];
    const nav = navigation(rows);
    if (nav.state !== "AVAILABLE") throw new Error("fixture navigation");
    const { calls } = mount({ navigation: { ...nav, conflicts: [{ work_ref: rows[0].work_ref, role: "worker", binding_ids: rows.map(row => row.binding_id) }] } });
    expect(screen.getAllByText("Conflicting binding for this work role.")).toHaveLength(2);
    expect(within(screen.getByRole("list", { name: "Observed surface bindings" })).getAllByRole("listitem")).toHaveLength(2);
    mutationsUntouched(calls);
    await userEvent.setup().click(screen.getByRole("button", { name: `Open Codex binding ${bindingId(2)}` }));
    expect(calls.onOpenSurface).toHaveBeenCalledTimes(1);
    expect(calls.onOpenSurface).toHaveBeenCalledWith({ binding_id: bindingId(2) });
  });

  it("withholds ChatGPT Open alone while retaining Bind, Unbind and Discovery", async () => {
    const { calls } = mount({ navigation: navigation([binding("chatgpt")]) });
    expect(screen.queryByRole("button", { name: /^Open / })).toBeNull();
    expect(screen.getByText("Opening a ChatGPT surface is not supported here.")).toBeTruthy();
    const user = userEvent.setup();
    await user.click(screen.getByText("Bind a surface"));
    expect((screen.getByRole("button", { name: "Bind" }) as HTMLButtonElement).disabled).toBe(false);
    await user.click(screen.getByRole("button", { name: "Discover surfaces" }));
    expect(calls.onDiscover).toHaveBeenCalledOnce();
    await user.click(screen.getByRole("button", { name: `Unbind ChatGPT binding ${bindingId(1)}` }));
    expect(calls.onUnbindSurface).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Confirm Unbind" }));
    expect(calls.onUnbindSurface).toHaveBeenCalledTimes(1);
    expect(calls.onUnbindSurface).toHaveBeenCalledWith({ binding_id: bindingId(1) });
  });

  const holds: Array<[string, ControlRoomActionPresentation]> = [
    ["pending action", { state: "PENDING", operation: "open" }],
    ["unknown transport failure", { state: "FAILURE", operation: "open", disposition: "EFFECT_UNKNOWN" }],
    ["unknown result", { state: "RESULT", result: result("open", "EFFECT_UNKNOWN", { ...CONTROL_ROOM_UNKNOWN_OUTCOME }) }],
    ["uncertain returned owner outcome", { state: "RESULT", result: result("open", "OWNER_RETURNED", { ok: false, failure_kind: "effect_unknown" }) }],
    ["withheld original action", { state: "WITHHELD", held: true }],
  ];
  it.each(holds)("keeps mutations disabled but Discovery usable for %s, even with held false", async (_name, action) => {
    const { calls } = mount({ action, held: false });
    const user = userEvent.setup();
    await user.click(screen.getByText("Bind a surface"));
    const read = screen.getByRole("button", { name: "Discover surfaces" }) as HTMLButtonElement;
    for (const button of screen.getAllByRole("button")) {
      if (button !== read) expect((button as HTMLButtonElement).disabled).toBe(true);
    }
    expect(read.disabled).toBe(false);
    await user.click(read);
    expect(calls.onDiscover).toHaveBeenCalledOnce();
    mutationsUntouched(calls);
    expect(screen.queryByRole("button", { name: /retry|clear.*action|cancel.*action/i })).toBeNull();
  });

  it("retains the exact owner-returned false result without calling it not dispatched", () => {
    const returned = result("refresh-builds", "OWNER_RETURNED", { ok: false, detail: "fixture publication not confirmed" });
    const mounted = mount({ action: { state: "RESULT", result: returned } });
    expect(screen.getByText("Success was not reported")).toBeTruthy();
    expect(screen.getByText("The owner returned. This does not confirm that no change occurred.")).toBeTruthy();
    expect(screen.queryByText("Action not dispatched")).toBeNull();
    expect(screen.getByText(JSON.stringify(returned))).toBeTruthy();
    mounted.rerender({ navigation: navigation([binding("codex", 2)]), discovery: { state: "AVAILABLE", document: discovery() } });
    expect(screen.getByText(JSON.stringify(returned))).toBeTruthy();
    mutationsUntouched(mounted.calls);
  });

  it("presents a real NOT_DISPATCHED receipt separately", () => {
    const refused = result("bind", "NOT_DISPATCHED", { ok: false, failure_kind: "permission_denied" });
    mount({ action: { state: "RESULT", result: refused } });
    expect(screen.getByText("Action not dispatched")).toBeTruthy();
    expect(screen.queryByText("Success was not reported")).toBeNull();
    expect(screen.getByText(JSON.stringify(refused))).toBeTruthy();
  });

  it("removes an old receipt when App withholds it, without exposing its operation", () => {
    const returned = result("open", "OWNER_RETURNED", { ok: false, detail: "inert-private-receipt-value" });
    const mounted = mount({ action: { state: "RESULT", result: returned } });
    expect(screen.getByText(JSON.stringify(returned))).toBeTruthy();
    mounted.rerender({ action: { state: "WITHHELD", held: true } });
    expect(screen.queryByText(/inert-private-receipt-value/)).toBeNull();
    expect(screen.queryByText(/Requested action:/)).toBeNull();
    expect(screen.queryByText("Action receipt")).toBeNull();
    expect(screen.getByText("Earlier action details withheld")).toBeTruthy();
  });

  it("masks stale observations and clears local drafts when authentication presentation is removed", async () => {
    const returned = result("open", "OWNER_RETURNED", { ok: true, detail: "old-context-receipt" });
    const mounted = mount({ discovery: { state: "AVAILABLE", document: discovery(1) }, action: { state: "RESULT", result: returned } });
    await beginBind("codex");
    mounted.rerender({ canAct: false });
    expect(screen.queryByText("WS:surface-fixture")).toBeNull();
    expect(screen.queryByText("fixture-session-1")).toBeNull();
    expect(screen.queryByText(/old-context-receipt/)).toBeNull();
    expect(screen.queryByLabelText("Work reference")).toBeNull();
    mounted.rerender({ canAct: true, action: { state: "WITHHELD", held: false } });
    await userEvent.setup().click(screen.getByText("Bind a surface"));
    expect((screen.getByLabelText("Work reference") as HTMLInputElement).value).toBe("");
  });
});

describe("Control Room explicit Bind drafts", () => {
  const providerCases: Array<{
    provider: ControlRoomProvider;
    manager?: "multilogin" | "gologin";
    fields: Array<[string, string]>;
    locator: Record<string, string>;
  }> = [
    { provider: "claude_code", fields: [["Claude Code project directory", "/fixture/project"], ["Claude Code session ID", bindingId(9)]], locator: { project_dir: "/fixture/project", session_id: bindingId(9) } },
    { provider: "claude_desktop", fields: [["Claude desktop URL", "claude://fixture-chat"]], locator: { url: "claude://fixture-chat" } },
    { provider: "cursor_agent", fields: [["Cursor chat ID", "fixture-thread"], ["Cursor workspace directory (optional)", "/fixture/workspace"]], locator: { chat_id: "fixture-thread", workspace_dir: "/fixture/workspace" } },
    { provider: "codex", fields: [["Codex session ID", "fixture-session"], ["Codex working directory (optional)", "/fixture/cwd"]], locator: { session_id: "fixture-session", cwd: "/fixture/cwd" } },
    { provider: "chatgpt", manager: "multilogin", fields: [["Seat reference (required for ChatGPT)", "explicit-seat"], ["Multilogin folder ID", bindingId(8)], ["Multilogin profile ID", bindingId(9)], ["ChatGPT conversation URL", `https://chatgpt.com/c/${bindingId(7)}`]], locator: { env_manager: "multilogin", folder_id: bindingId(8), profile_id: bindingId(9), url: `https://chatgpt.com/c/${bindingId(7)}` } },
    { provider: "chatgpt", manager: "gologin", fields: [["Seat reference (required for ChatGPT)", "explicit-seat"], ["GoLogin profile ID", "0123456789abcdef01234567"], ["ChatGPT conversation URL", `https://chatgpt.com/c/${bindingId(7)}`]], locator: { env_manager: "gologin", profile_id: "0123456789abcdef01234567", url: `https://chatgpt.com/c/${bindingId(7)}` } },
  ];
  it.each(providerCases)("submits only explicit fields for $provider / $manager", async ({ provider, manager, fields, locator }) => {
    const { calls } = mount();
    const user = await beginBind(provider);
    if (manager) await user.selectOptions(screen.getByLabelText("Environment manager"), manager);
    for (const [name, value] of fields) await user.type(screen.getByLabelText(name), value);
    mutationsUntouched(calls);
    await user.click(screen.getByRole("button", { name: "Bind" }));
    const expected = { work_ref: "WS:explicit-draft", role: "worker", provider, locator, ...(provider === "chatgpt" ? { seat_ref: "explicit-seat" } : {}) };
    expect(calls.onBindSurface).toHaveBeenCalledTimes(1);
    expect(calls.onBindSurface).toHaveBeenCalledWith(expected);
    const payload = calls.onBindSurface.mock.calls[0][0];
    expect(Object.isFrozen(payload)).toBe(true);
    expect(Object.isFrozen(payload.locator)).toBe(true);
    expect(payload).not.toHaveProperty("owed_context");
    expect(payload).not.toHaveProperty("locator_kind");
    expect(payload.locator).not.toHaveProperty("workspace_id");
    if (manager === "gologin") expect(payload.locator).not.toHaveProperty("folder_id");
  });

  it("refuses a whitespace-only ChatGPT seat before invoking any callback", async () => {
    const { calls } = mount();
    const user = await beginBind("chatgpt");
    await user.selectOptions(screen.getByLabelText("Environment manager"), "gologin");
    await user.type(screen.getByLabelText("Seat reference (required for ChatGPT)"), "   ");
    await user.type(screen.getByLabelText("GoLogin profile ID"), "0123456789abcdef01234567");
    await user.type(screen.getByLabelText("ChatGPT conversation URL"), `https://chatgpt.com/c/${bindingId(7)}`);
    await user.click(screen.getByRole("button", { name: "Bind" }));
    expect(screen.getByRole("alert").textContent).toContain("required seat details");
    mutationsUntouched(calls);
  });

  it("discards the previous provider's locator draft and supports native Enter submission", async () => {
    const { calls } = mount();
    const user = await beginBind("claude_code");
    await user.type(screen.getByLabelText("Claude Code project directory"), "/fixture/old-project");
    await user.type(screen.getByLabelText("Claude Code session ID"), bindingId(9));
    await user.selectOptions(screen.getByLabelText("Provider"), "codex");
    expect((screen.getByLabelText("Codex session ID") as HTMLInputElement).value).toBe("");
    await user.type(screen.getByLabelText("Codex session ID"), "explicit-codex-session{Enter}");
    expect(calls.onBindSurface).toHaveBeenCalledTimes(1);
    expect(calls.onBindSurface).toHaveBeenCalledWith({ work_ref: "WS:explicit-draft", role: "worker", provider: "codex", locator: { session_id: "explicit-codex-session" } });
  });

  it("drops Multilogin folder and profile fields on a GoLogin manager change", async () => {
    const { calls } = mount();
    const user = await beginBind("chatgpt");
    await user.selectOptions(screen.getByLabelText("Environment manager"), "multilogin");
    await user.type(screen.getByLabelText("Multilogin folder ID"), bindingId(8));
    await user.type(screen.getByLabelText("Multilogin profile ID"), bindingId(9));
    await user.selectOptions(screen.getByLabelText("Environment manager"), "gologin");
    expect(screen.queryByLabelText("Multilogin folder ID")).toBeNull();
    expect((screen.getByLabelText("GoLogin profile ID") as HTMLInputElement).value).toBe("");
    mutationsUntouched(calls);
  });
});

describe("Control Room Discovery presentation", () => {
  it("distinguishes not read, pending, unavailable and an available empty census", async () => {
    const mounted = mount();
    expect(screen.getByText("Discovery has not been read.")).toBeTruthy();
    mounted.rerender({ discovery: { state: "PENDING" } });
    expect(screen.getByText("Reading surface discovery…")).toBeTruthy();
    mounted.rerender({ discovery: { state: "UNAVAILABLE" } });
    expect(screen.getByText("Surface discovery is unavailable.")).toBeTruthy();
    mounted.rerender({ discovery: { state: "AVAILABLE", document: discovery() } });
    await userEvent.setup().click(screen.getByText("Codex sessions"));
    expect(screen.queryByText("Surface discovery is unavailable.")).toBeNull();
    expect(screen.getAllByText("No candidates in this observation.")).toHaveLength(4);
    mutationsUntouched(mounted.calls);
    expect(mounted.calls.onDiscover).not.toHaveBeenCalled();
  });

  it("shows eight candidates before explicit expansion and never prefills a binding", async () => {
    const { calls } = mount({ discovery: { state: "AVAILABLE", document: discovery(9) } });
    const user = userEvent.setup();
    await user.click(screen.getByText("Codex sessions"));
    const list = screen.getByRole("list", { name: "Codex sessions" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(8);
    expect(screen.queryByText("fixture-session-9")).toBeNull();
    await user.click(screen.getByRole("button", { name: "See all 9 codex sessions" }));
    expect(within(list).getAllByRole("listitem")).toHaveLength(9);
    expect(screen.getByText("fixture-session-9")).toBeTruthy();
    await user.click(screen.getByText("Bind a surface"));
    expect((screen.getByLabelText("Work reference") as HTMLInputElement).value).toBe("");
    expect((screen.getByLabelText("Provider") as HTMLSelectElement).value).toBe("");
    mutationsUntouched(calls);
    expect(calls.onDiscover).not.toHaveBeenCalled();
  });

  it("retains the held unknown result while explicit Discovery invokes only its READ callback", async () => {
    const unknown = result("open", "EFFECT_UNKNOWN", { ...CONTROL_ROOM_UNKNOWN_OUTCOME });
    const mounted = mount({ held: true, action: { state: "RESULT", result: unknown } });
    await userEvent.setup().click(screen.getByRole("button", { name: "Discover surfaces" }));
    mounted.rerender({ discovery: { state: "AVAILABLE", document: discovery(1) } });
    expect(screen.getByText("Action outcome unknown")).toBeTruthy();
    expect((screen.getByRole("button", { name: "Refresh builds" }) as HTMLButtonElement).disabled).toBe(true);
    expect(mounted.calls.onDiscover).toHaveBeenCalledOnce();
    mutationsUntouched(mounted.calls);
  });

  it("provides Chinese labels without changing protocol values or the action hold", async () => {
    const { calls } = mount({ locale: "zh-CN", action: { state: "FAILURE", operation: "open", disposition: "EFFECT_UNKNOWN" } });
    expect(screen.getByRole("heading", { name: "工作区界面" })).toBeTruthy();
    expect(screen.getByText("操作结果未知")).toBeTruthy();
    expect((screen.getByRole("button", { name: "刷新构建" }) as HTMLButtonElement).disabled).toBe(true);
    await userEvent.setup().click(screen.getByRole("button", { name: "发现界面" }));
    expect(calls.onDiscover).toHaveBeenCalledOnce();
    mutationsUntouched(calls);
  });
});
