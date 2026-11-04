// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { App } from "./App";
import { createFixtureCommandBinding } from "./browser-proof-command-fixture";
import type { PendingPointerStore } from "./orchestration/operation-controller";
import { DisplayPreferences, DisplayPreferencesRoot } from "./preferences/DisplayPreferences";
import { DISPLAY_PREFERENCES_STORAGE_KEY } from "./preferences/display-preferences";

function Product() {
  return <DisplayPreferencesRoot>{({theme,locale,control}) => <App theme={theme} locale={locale}
    preferencesControl={<DisplayPreferences control={control}/>}/>}</DisplayPreferencesRoot>;
}
beforeEach(() => { localStorage.clear(); delete window.MastermindMissionHost; });
afterEach(() => { cleanup(); localStorage.clear(); delete window.MastermindMissionHost; });
it("changes real shell theme/language without remounting its current route, then restores on reload", () => {
  const view = render(<Product/>);
  const nav = screen.getByRole("navigation", {name:"Company navigation"});
  fireEvent.click(within(nav).getByRole("button", {name:"Knowledge"}));
  fireEvent.click(screen.getByRole("button", {name:"Display settings"}));
  fireEvent.change(screen.getByLabelText("Theme"), {target:{value:"light"}});
  fireEvent.change(screen.getByLabelText("Language"), {target:{value:"zh-CN"}});
  expect(view.container.querySelector(".shell")?.getAttribute("data-theme")).toBe("light");
  expect(within(nav).getByRole("button", {name:"知识"}).getAttribute("aria-current")).toBe("page");
  expect(localStorage.getItem(DISPLAY_PREFERENCES_STORAGE_KEY)).toBe('{"version":1,"theme":"light","locale":"zh-CN"}');
  view.unmount();
  const reloaded = render(<Product/>);
  expect(reloaded.container.querySelector(".shell")?.getAttribute("data-theme")).toBe("light");
  expect(screen.getByRole("button", {name:"显示设置"})).toBeTruthy();
});

it("mounts the ready fixture in real Today and preserves the launch draft on its explicit refusal", async () => {
  const store: PendingPointerStore = { read: () => null, reserve: () => ({reserved:true}), clearIfEqual: () => true };
  const binding = createFixtureCommandBinding(store);
  const submit = vi.spyOn(binding.port, "submit");
  window.MastermindMissionHost = { commandBinding: binding, auth: {
    getState: () => ({status:"signed_in",reason:null,acquisition:false,content:false}),
    subscribe: () => () => {}, signIn: async () => {}, signOut: async () => {},
  }};
  render(<Product/>);
  expect((screen.getByLabelText("Project") as HTMLSelectElement).value).toBe("source-fixture-project");
  expect((screen.getByLabelText("Profile") as HTMLSelectElement).value).toBe("governed_project");
  expect((screen.getByLabelText("Requested CEO") as HTMLSelectElement).value).toBe("fixture-ceo");
  const goal = screen.getByLabelText("Goal") as HTMLTextAreaElement;
  fireEvent.change(goal, {target:{value:"Do not dispatch this fixture"}});
  await waitFor(() => expect((screen.getByRole("button", {name:"Launch"}) as HTMLButtonElement).disabled).toBe(false));
  fireEvent.submit(goal.closest("form")!);
  await waitFor(() => expect(submit).toHaveBeenCalledTimes(1));
  await waitFor(() => expect((screen.getByRole("button", {name:"Launch"}) as HTMLButtonElement).disabled).toBe(false));
  expect(goal.value).toBe("Do not dispatch this fixture");
  expect(screen.getByRole("alert").textContent).toContain("REFUSED");
});


it("opens the actual display owner from Sources without replacing the current view",async()=>{
  const view=render(<Product/>);
  fireEvent.click(screen.getByRole("button",{name:"Sources"}));
  fireEvent.click(await screen.findByRole("button",{name:"Open display preferences"}));
  await waitFor(()=>expect(screen.getByRole("button",{name:"Display settings"}).getAttribute("aria-expanded")).toBe("true"));
  expect(document.activeElement).toBe(screen.getByRole("button",{name:"Display settings"}));
  fireEvent.change(screen.getByLabelText("Theme"),{target:{value:"light"}});
  expect(view.container.querySelector(".shell")?.getAttribute("data-active-route")).toBe("Sources");
  expect(view.container.querySelector(".shell")?.getAttribute("data-theme")).toBe("light");
  expect(screen.getAllByRole("heading",{level:1})).toHaveLength(1);
});
