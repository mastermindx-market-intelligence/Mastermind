// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { MissionHost } from "../host";
import { fixtureSnapshot } from "./local-fabric-owner-fixture";
import { LocalFabricOwnerImport } from "./LocalFabricOwnerImport";

function native(on: boolean) {
  if (on) Object.defineProperty(window, "__TAURI_INTERNALS__", {
    value: { native: true }, configurable: true, writable: true,
  });
  else Reflect.deleteProperty(window, "__TAURI_INTERNALS__");
}
function ownerHost() {
  let state = { status: "signed_in", acquisition: true, content: false, reason: null };
  let epoch = 1;
  const callbacks = new Set<(next: typeof state) => void>();
  const host = {
    auth: {
      getState: () => ({ ...state }),
      subscribe(fn: (next: typeof state) => void) {
        callbacks.add(fn);
        return () => { callbacks.delete(fn); };
      },
    },
    invalidationGeneration: () => epoch,
  } as unknown as MissionHost;
  return {
    host,
    change(next: "signed_out" | "signed_in") {
      epoch++;
      state = { status: next, acquisition: next === "signed_in", content: false, reason: null };
      for (const cb of callbacks) cb(state);
    },
  };
}
function file(raw: unknown, filename = "local-fabric.json") {
  const text = JSON.stringify(raw);
  const f = new File([text], filename, { type: "application/json" });
  Object.defineProperty(f, "text", { value: () => Promise.resolve(text), configurable: true });
  return f;
}
async function load(raw: unknown) {
  fireEvent.change(screen.getByLabelText("Import local Fabric snapshot (JSON)"), {
    target: { files: [file(raw)] },
  });
  await screen.findByText("3 retained outcome rows");
}
beforeEach(() => native(false));
afterEach(() => { cleanup(); native(false); vi.restoreAllMocks(); });

describe("native M2 machine-owner operator import", () => {
  it("never exposes a machine-owned ledger panel in the ordinary website", () => {
    const { host } = ownerHost();
    const { container } = render(<LocalFabricOwnerImport host={host} />);
    expect(container.textContent).toBe("");
  });

  it("requires existing signed-in native acquisition, not a machine-owner login substitute", () => {
    native(true);
    const h = ownerHost();
    h.change("signed_out");
    render(<LocalFabricOwnerImport host={h.host} />);
    expect(screen.getByLabelText("Import local Fabric snapshot (JSON)").hasAttribute("disabled")).toBe(true);
    expect(screen.getByText(/Signed-in native Workspace acquisition is required/)).toBeTruthy();
  });

  it("does not install a second authentication subscriber or displace the App owner", () => {
    native(true);
    const h = ownerHost();
    const subscribe = vi.spyOn(h.host.auth!, "subscribe");
    render(<LocalFabricOwnerImport host={h.host} />);
    expect(subscribe).not.toHaveBeenCalled();
  });

  it("imports only user-chosen sanitized historical data and follows only same-root loaded links", async () => {
    native(true);
    const h = ownerHost();
    render(<LocalFabricOwnerImport host={h.host} />);
    await load(fixtureSnapshot());
    expect(screen.getByText(/Fleet total and active count unknown/)).toBeTruthy();
    const list = screen.getByRole("group", { name: "Retained local runs" });
    fireEvent.click(within(list).getByRole("button", { name: /child-01/ }));
    const detail = screen.getByText("Selected retained run").parentElement!;
    expect(within(detail).getByText("MiniMax-M3")).toBeTruthy();
    expect(within(detail).getByText("operator-01")).toBeTruthy();
    fireEvent.click(within(detail).getByRole("button", { name: /View loaded parent: operator-01/ }));
    expect(within(detail).getByText("glm-5.3-flash")).toBeTruthy();
    expect(within(detail).getByRole("button", { name: /View loaded child: child-01/ })).toBeTruthy();
    expect(within(detail).queryByText("different-root")).toBeNull();
    expect(screen.queryByText("Accepted")).toBeNull();
  });

  it("clears imported private rows after sign-out and does not make a network request", async () => {
    native(true);
    const h = ownerHost();
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const page = render(<LocalFabricOwnerImport host={h.host} />);
    await load(fixtureSnapshot());
    expect(screen.getByText("3 retained outcome rows")).toBeTruthy();
    act(() => h.change("signed_out"));
    page.rerender(<LocalFabricOwnerImport host={h.host} />);
    await waitFor(() => expect(screen.queryByText("3 retained outcome rows")).toBeNull());
    expect(screen.getByLabelText("Import local Fabric snapshot (JSON)").hasAttribute("disabled")).toBe(true);
    expect(fetchMock).not.toHaveBeenCalled();
    vi.unstubAllGlobals();
  });

  it("refuses malformed or overbudget machine files without displaying source content", async () => {
    native(true);
    const h = ownerHost();
    render(<LocalFabricOwnerImport host={h.host} />);
    const input = screen.getByLabelText("Import local Fabric snapshot (JSON)");
    fireEvent.change(input, { target: { files: [file({ ...fixtureSnapshot(), scope: "EXACT_RUN_SET" })] } });
    expect((await screen.findByRole("alert")).textContent).toBe("LOCAL_FABRIC_SNAPSHOT_INVALID");
    const large = new File(["A".repeat(70_000)], "oversized.json", { type: "application/json" });
    fireEvent.change(input, { target: { files: [large] } });
    expect((await screen.findByRole("alert")).textContent).toBe("LOCAL_FABRIC_SNAPSHOT_SIZE_REFUSED");
    expect(screen.queryByText("3 retained outcome rows")).toBeNull();
  });

  it("does not publish a file whose async read finishes after the native principal changes", async () => {
    native(true);
    const h = ownerHost();
    const page = render(<LocalFabricOwnerImport host={h.host} />);
    let deliver: (value: string) => void = () => {};
    const pending = new Promise<string>(resolve => { deliver = resolve; });
    const f = file(fixtureSnapshot());
    Object.defineProperty(f, "text", { value: () => pending });
    fireEvent.change(screen.getByLabelText("Import local Fabric snapshot (JSON)"), {
      target: { files: [f] },
    });
    act(() => h.change("signed_out"));
    page.rerender(<LocalFabricOwnerImport host={h.host} />);
    await act(async () => { deliver(JSON.stringify(fixtureSnapshot())); await pending; });
    expect(screen.queryByText("3 retained outcome rows")).toBeNull();
    expect(screen.getByLabelText("Import local Fabric snapshot (JSON)").hasAttribute("disabled")).toBe(true);
  });

  it("renders compact localized copy without recognizing historical rc as live activity", async () => {
    native(true);
    const h = ownerHost();
    render(<LocalFabricOwnerImport host={h.host} locale="zh-CN" />);
    const input = screen.getByLabelText("导入本机 Fabric 快照（JSON）");
    fireEvent.change(input, { target: { files: [file(fixtureSnapshot())] } });
    expect(await screen.findByText("3 条保留的历史记录")).toBeTruthy();
    expect(screen.getByText(/工作代理总数和运行中数量未知/)).toBeTruthy();
    expect(screen.getByRole("group", { name: "本机保留的运行" })).toBeTruthy();
  });
});
