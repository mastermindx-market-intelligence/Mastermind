// @vitest-environment jsdom
import { act as reactAct, cleanup, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createAppControl, type AppControl, type AppObservation, type ControlContext } from "./control";
import { installAppControl } from "./install";
import { App } from "../App";
import { DisplayPreferences, DisplayPreferencesRoot } from "../preferences/DisplayPreferences";
import { controlRoomFixture } from "../test-fixtures";

let context: ControlContext;
const disposers: (() => void)[] = [];
beforeEach(() => {
  localStorage.clear();
  history.replaceState(null, "", "/os/");
  context = { owner: {}, generation: 1, auth: "signed_in", content: true, acquisition: true };
  vi.spyOn(HTMLElement.prototype, "getClientRects").mockReturnValue([new DOMRect(0, 0, 100, 20)] as unknown as DOMRectList);
});
afterEach(() => { disposers.splice(0).forEach(dispose => dispose()); cleanup(); delete window.MastermindMissionHost; vi.restoreAllMocks(); delete (document as unknown as { modelContext?: unknown }).modelContext; });
function fixture(html: string) {
  const root = document.createElement("div"); root.innerHTML = html; document.body.append(root);
  const control = createAppControl(root, () => context);
  disposers.push(() => { control.dispose(); root.remove(); });
  return { root, control };
}
function snapshot(control: AppControl): AppObservation {
  const value = control.inspect();
  if (!("access" in value)) throw new Error(JSON.stringify(value));
  return value;
}
const target = (view: AppObservation, name: string) => {
  const values = view.controls.filter(row => row.name === name);
  expect(values).toHaveLength(1);
  return values[0].ref;
};
async function perform(control: AppControl, name: string, action: string, rest: object = {}) {
  const view = snapshot(control);
  let result;
  await reactAct(async () => { result = await control.act({ observation: view.observation, target: target(view, name), action, ...rest }); });
  return result;
}

describe("app semantic control", () => {
  it("uses real React field, select, checkbox and button handlers", async () => {
    const send = vi.fn();
    function Form() {
      const [draft, setDraft] = useState(""); const [checked, setChecked] = useState(false); const [choice, setChoice] = useState("dark");
      return <><label>Draft<textarea value={draft} onChange={event => setDraft(event.target.value)} /></label>
        <label>Consent<input type="checkbox" checked={checked} onChange={event => setChecked(event.target.checked)} /></label>
        <label>Theme<select value={choice} onChange={event => setChoice(event.target.value)}><option>dark</option><option>light</option></select></label>
        <button disabled={!draft || !checked} onClick={() => send({ draft, choice })}>Preview</button></>;
    }
    const view = render(<Form />); const control = createAppControl(view.container, () => context); disposers.push(control.dispose);
    expect(snapshot(control).controls.find(row => row.name === "Preview")?.enabled).toBe(false);
    await perform(control, "Draft", "fill", { value: "Investigate launch\nKeep original owner" });
    await perform(control, "Theme", "select", { value: "light" });
    await perform(control, "Consent", "set_checked", { checked: true });
    await perform(control, "Preview", "activate");
    expect(send).toHaveBeenCalledExactlyOnceWith({ draft: "Investigate launch\nKeep original owner", choice: "light" });
  });
  it("withholds the entire private view immediately when the auth owner changes", async () => {
    const { root, control } = fixture('<h1>Private plan</h1><textarea aria-label="Draft">not exported</textarea><button>Send</button>');
    const send = vi.fn(); root.querySelector("button")!.onclick = send;
    const before = snapshot(control); context = { ...context, auth: "signed_out", content: false };
    expect(await control.act({ observation: before.observation, target: target(before, "Send"), action: "activate" })).toMatchObject({ status: "REFUSED", code: "OWNER_CHANGED" });
    const after = snapshot(control);
    expect(after).toMatchObject({ access: "AUTH_REQUIRED", text: "", controls: [], headings: [], routes: [], route: null });
    expect(JSON.stringify(after)).not.toContain("Private plan"); expect(send).not.toHaveBeenCalled();
  });
  it("omits private subtrees, hidden controls, passwords, tokens and file inputs", () => {
    const { control } = fixture('<h1>Overview</h1><section data-agent-private><h2>secret tree</h2><button>Private action</button></section><input type=password value=pass-secret aria-label=Password><input name=provider_token value=token-secret><input type=file aria-label=Upload><textarea hidden>hidden-secret</textarea><button hidden>Hidden</button><details><summary>Details</summary><button>Closed</button><p>closed-secret</p></details><button>Allowed</button>');
    const view = snapshot(control), encoded = JSON.stringify(view);
    for (const forbidden of ["secret tree", "Private action", "pass-secret", "token-secret", "hidden-secret", "closed-secret", "Upload"]) expect(encoded).not.toContain(forbidden);
    expect(view.controls.map(row => row.name)).toEqual(["Details", "Allowed"]);
  });
  it("recognizes sensitive semantic labels and placeholders before exporting values", () => {
    const { control } = fixture('<label for="x">API key</label><input id="x" value="label-secret"><span id="hint">Access token</span><textarea aria-labelledby="hint">aria-secret</textarea><input placeholder="Client secret" value="placeholder-secret"><label>Public draft<input value="visible"></label>');
    const view = snapshot(control);
    expect(view.controls).toHaveLength(1);
    expect(view.controls[0]).toMatchObject({ name: "Public draft", value: "visible" });
    for (const value of ["label-secret", "aria-secret", "placeholder-secret"]) expect(JSON.stringify(view)).not.toContain(value);
  });
  it.each(["dom", "generation", "owner", "property"])("refuses a stale %s target before any event", async mode => {
    const { root, control } = fixture('<input aria-label="Draft" value="before"><button>Send</button>');
    const view = snapshot(control), input = root.querySelector("input")!;
    const change = vi.fn(); input.addEventListener("input", change);
    if (mode === "dom") root.append(document.createElement("p"));
    if (mode === "generation") context = { ...context, generation: 2 };
    if (mode === "owner") context = { ...context, owner: {} };
    if (mode === "property") input.value = "newer human edit";
    const result = await control.act({ observation: view.observation, target: target(view, "Draft"), action: "fill", value: "overwrite" });
    expect(result.status).toBe("REFUSED"); expect(change).not.toHaveBeenCalled();
    expect(input.value).not.toBe("overwrite");
  });
  it("consumes an observation before dispatch and never replays its event", async () => {
    const { root, control } = fixture('<button>Run</button>'); const run = vi.fn(); root.querySelector("button")!.onclick = run;
    const view = snapshot(control), request = { observation: view.observation, target: target(view, "Run"), action: "activate" };
    const original = control.act(request); const duplicate = await control.act(request);
    expect(duplicate).toMatchObject({ status: "REFUSED", code: "STALE_OBSERVATION" });
    expect(await original).toMatchObject({ status: "DISPATCHED" }); expect(run).toHaveBeenCalledTimes(1);
  });
  it("allows unchanged navigation during content refresh but refuses changed routes and owners", async () => {
    const { root, control } = fixture('<section data-active-route="Today"><button data-agent-route="Projects">Projects</button><p>Loading</p></section>');
    const click = vi.fn(); root.querySelector("button")!.onclick = click;
    let view = snapshot(control); root.querySelector("p")!.textContent = "Read complete";
    expect(await control.navigate({ observation: view.observation, route: "Projects" })).toMatchObject({ status: "DISPATCHED" });
    expect(click).toHaveBeenCalledTimes(1);
    view = snapshot(control); root.querySelector("section")!.dataset.activeRoute = "Inbox";
    expect(await control.navigate({ observation: view.observation, route: "Projects" })).toMatchObject({ code: "STALE_OBSERVATION" });
    view = snapshot(control); context = { ...context, owner: {} };
    expect(await control.navigate({ observation: view.observation, route: "Projects" })).toMatchObject({ code: "OWNER_CHANGED" });
    expect(click).toHaveBeenCalledTimes(1);
  });
  it("supports existing disclosure and Enter handlers while preserving preventDefault", async () => {
    const { root, control } = fixture('<details><summary>Details</summary><p>Expanded facts</p></details><button>Run</button>');
    await perform(control, "Details", "activate"); expect(root.querySelector("details")!.open).toBe(true);
    const run = vi.fn(), button = root.querySelector("button")!; button.onclick = run;
    button.onkeydown = event => { event.preventDefault(); };
    await perform(control, "Run", "press", { key: "Enter" }); expect(run).not.toHaveBeenCalled();
    button.onkeydown = null; await perform(control, "Run", "press", { key: "Enter" }); expect(run).toHaveBeenCalledTimes(1);
  });
  it("does not enable disabled fields, readonly inputs, or external links", async () => {
    const { control } = fixture('<fieldset disabled><button>Disabled</button></fieldset><div aria-disabled=true><button>Inherited</button></div><input aria-label=ReadOnly readonly value=keep><a href="https://example.com/">External</a><a href="javascript:void(0)">Script</a>');
    const view = snapshot(control);
    expect(view.controls.filter(row => ["Disabled", "Inherited"].includes(row.name)).every(row => !row.enabled && row.actions.length === 0)).toBe(true);
    expect(view.controls.find(row => row.name === "ReadOnly")?.actions).toEqual(["focus"]);
    for (const name of ["External", "Script"]) expect(view.controls.find(row => row.name === name)?.actions).toEqual([]);
    expect(await control.act({ observation: view.observation, target: target(view, "ReadOnly"), action: "fill", value: "overwrite" })).toMatchObject({ code: "ACTION_UNSUPPORTED" });
  });
  it("validates every action and option before touching the UI", async () => {
    const { root, control } = fixture('<select aria-label=Choice><option value=a>A</option><optgroup label=Held disabled><option value=b>B</option></optgroup></select>');
    const change = vi.fn(); root.querySelector("select")!.onchange = change;
    const view = snapshot(control), ref = target(view, "Choice");
    for (const request of [
      { action: "select", value: "b" }, { action: "select", value: "missing" }, { action: "evaluate", value: "fetch('/secret')" },
      { action: "select", value: "a", url: "https://example.com" }, { action: "press", key: "Control+A" },
    ]) expect((await control.act({ observation: view.observation, target: ref, ...request })).status).toBe("REFUSED");
    expect(change).not.toHaveBeenCalled();
  });
  it("bounds observations, marks truncation and reports incomplete evidence honestly", () => {
    const { control } = fixture('<h1>Ready</h1>' + '<textarea aria-label="Long">'.concat("x".repeat(9000), '</textarea>').repeat(60) + '<p>End evidence</p>');
    const view = snapshot(control);
    expect(new TextEncoder().encode(JSON.stringify(view)).length).toBeLessThan(64000); expect(view.truncated).toBe(true);
    expect(control.check({ textIncludes: "absent" })).toMatchObject({ status: "FAIL", checks: [{ pass: false, actual: "NOT_OBSERVED_IN_BOUNDED_OUTPUT" }] });
    expect(control.check({ textIncludes: "Ready", horizontalOverflowAtMost: 0 })).toMatchObject({ status: "PASS" });
  });
});

describe("product mount and WebMCP", () => {
  it.each([true, false])("navigates the actual App with Workspace Content=%s and edits existing preferences", async content => {
    window.MastermindMissionHost = {
      readPrograms: async () => controlRoomFixture(), readMission: async () => { throw new Error("source fixture unavailable"); },
      auth: { getState: () => ({ status: "signed_in", reason: null, acquisition: true, content }), subscribe: () => () => {}, signIn: async () => {}, signOut: async () => {} },
    };
    const view = render(<DisplayPreferencesRoot>{({ theme, locale, control }) => <App theme={theme} locale={locale} preferencesControl={<DisplayPreferences control={control} />} />}</DisplayPreferencesRoot>);
    const installed = installAppControl(view.container); disposers.push(installed.dispose);
    await reactAct(async () => { await Promise.resolve(); });
    const api = installed.api; let observed = await api.call("mastermind_os_inspect") as AppObservation;
    expect(observed.routes).toEqual(expect.arrayContaining(["Today", "Projects", "Inbox", "Conversations", "Knowledge", "Search", "Fleet & Capacity"]));
    await reactAct(async () => { await api.call("mastermind_os_navigate", { observation: observed.observation, route: "Projects" }); });
    expect(document.querySelector(".shell")?.getAttribute("data-active-route")).toBe("Projects");
    observed = await api.call("mastermind_os_inspect") as AppObservation;
    const preference = observed.controls.find(row => row.name === "Display settings");
    expect(preference).toBeTruthy();
    await reactAct(async () => { await api.call("mastermind_os_act", { observation: observed.observation, target: preference!.ref, action: "activate" }); });
    observed = await api.call("mastermind_os_inspect") as AppObservation;
    await reactAct(async () => { await api.call("mastermind_os_act", { observation: observed.observation, target: target(observed, "Theme"), action: "select", value: "light" }); });
    expect(document.querySelector(".shell")?.getAttribute("data-theme")).toBe("light");
    expect(await api.call("mastermind_os_check", { route: "Projects" })).toMatchObject({ status: "PASS" });
  });
  it("publishes four document-scoped tools and retires only its own registrations", async () => {
    const registrations: { tool: { name: string; execute: (input: unknown, options?: { signal?: AbortSignal }) => Promise<unknown> }; signal: AbortSignal }[] = [];
    Object.assign(document, { modelContext: { registerTool: vi.fn(async (tool, options) => { registrations.push({ tool, signal: options.signal }); }) } });
    const view = render(<button>Run</button>), click = vi.fn(); screen.getByRole("button").onclick = click;
    const installed = installAppControl(view.container, () => context); disposers.push(installed.dispose); await installed.ready;
    expect(installed.api.transport()).toBe("WEBMCP"); expect(registrations).toHaveLength(4);
    const observed = await registrations[0].tool.execute({}) as AppObservation;
    const aborted = new AbortController(); aborted.abort();
    expect(await registrations.find(row => row.tool.name === "mastermind_os_act")!.tool.execute({ observation: observed.observation, target: observed.controls[0].ref, action: "activate" }, { signal: aborted.signal })).toMatchObject({ code: "CANCELLED_BEFORE_DISPATCH" });
    expect(click).not.toHaveBeenCalled(); installed.dispose();
    expect(registrations.every(row => row.signal.aborted)).toBe(true); expect(window.MastermindAppControl).toBeUndefined();
  });
  it("fails registration without breaking ordinary app controls or replacing another producer", async () => {
    const registerTool = vi.fn().mockRejectedValue(new Error("name already owned")); Object.assign(document, { modelContext: { registerTool } });
    const view = render(<button>Run</button>), installed = installAppControl(view.container, () => context); disposers.push(installed.dispose); await installed.ready;
    expect(installed.api.transport()).toBe("REGISTRATION_FAILED"); expect(registerTool).toHaveBeenCalledTimes(1);
    expect(() => installAppControl(view.container, () => context)).toThrow("APP_CONTROL_ALREADY_INSTALLED");
    expect((await installed.api.call("mastermind_os_inspect") as AppObservation).access).toBe("AVAILABLE");
  });
});
