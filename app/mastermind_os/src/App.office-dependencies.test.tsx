// @vitest-environment jsdom
/** ONE whole canonical authored graph -> signed owner DTO -> real NativeClient/Host/App/IDB. */
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { IDBFactory } from "fake-indexeddb";
import { App } from "./App";
import { createNativeClient } from "./host";
import { composeMissionHost } from "./compose-mission-host";
import { decodeLaunchBindingConfig } from "./launch-config";
import source from "./fixtures/office-dependencies-source.json";
let dispose = () => {};
beforeEach(async () => {
  history.replaceState(null, "", "/os/");
  delete window.MastermindMissionHost;
  const { webcrypto } = await vi.importActual<{ webcrypto: Crypto }>(
    "node:crypto",
  );
  vi.stubGlobal("crypto", webcrypto);
  vi.spyOn(Date, "now").mockReturnValue(source.clock.verified_at * 1000);
});
afterEach(() => {
  cleanup();
  dispose();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  delete window.MastermindMissionHost;
});
async function setup(locale: "en" | "zh-CN" = "en") {
  const events = new Map<string, Set<(e: { payload: unknown }) => void>>();
  const invoke = vi.fn(async (command: string): Promise<unknown> => {
    if (command === "auth_status")
      return {
        status: "signed_in",
        reason: null,
        acquisition: true,
        content: false,
      };
    if (command === "executive_auth_status")
      return { generation: 0, available: false };
    if (command === "read_programs")
      return structuredClone(source.responses.programs.body);
    if (command === "read_project_plan")
      return structuredClone(source.responses.objective.body);
    throw Error("Unrecorded capability; no effect permitted");
  });
  const client = await createNativeClient(
    invoke as never,
    async (name, listener) => {
      const s = events.get(name) ?? new Set();
      s.add(listener);
      events.set(name, s);
      return () => s.delete(listener);
    },
  );
  const cfg = decodeLaunchBindingConfig(
    JSON.stringify({
      v: 1,
      workstream: "WS:EXECUTIVE-ECOSYSTEM-COMPLETION",
      priority: 0,
      attemptLimit: 1,
      projects: [{ ref: "executive-infrastructure", label: "Infrastructure" }],
      profiles: [{ ref: "research_only", label: "Research" }],
    }),
  )!;
  const composed = composeMissionHost(client, cfg, new IDBFactory(), "native");
  await composed.ready;
  await composed.sessionReady;
  window.MastermindMissionHost = composed.host;
  const view = render(<App locale={locale} />);
  dispose = () => {
    view.unmount();
    composed.dispose();
  };
  fireEvent.click(
    screen.getByRole("button", { name: locale === "en" ? "Projects" : "项目" }),
  );
  fireEvent.click(
    await screen.findByRole("button", {
      name: `${locale === "en" ? "Open project" : "打开项目"} Source-backed programme`,
    }),
  );
  fireEvent.click(
    screen.getByRole("button", {
      name: locale === "en" ? "Meta-CEO" : "Meta-CEO 办公室",
    }),
  );
  await screen.findByRole("region", {
    name: locale === "en" ? "Meta-CEO office" : "Meta-CEO 办公室",
  });
  fireEvent.click(
    screen.getByText(
      locale === "en"
        ? "Returns, dependencies and journal"
        : "返回结果、依赖和日志",
    ),
  );
  return {
    invoke,
    host: composed.host,
    notify: (payload: unknown) =>
      events.get("mastermind-auth-state")?.forEach((fn) => fn({ payload })),
  };
}
it("shows real authored unmet edges, inspects/returns/reopens without extra reads or grants, and retains the draft through project navigation", async () => {
  const e = await setup(),
    office = screen.getByRole("region", { name: "Meta-CEO office" }),
    reads = e.invoke.mock.calls.length;
  const draft = within(office).getByRole("textbox", {
    name: "Direction to Meta-CEO",
  });
  fireEvent.change(draft, {
    target: { value: "Keep this unsent Office draft." },
  });
  const trigger = within(office).getByRole("button", {
    name: "Inspect dependencies for Source-backed programme",
  });
  fireEvent.click(trigger);
  expect(
    screen.getByRole("heading", { level: 3, name: "Source-backed programme" }),
  ).toBe(document.activeElement);
  expect(
    within(office).getByText("WS:RESEARCH-INPUT", { selector: "p" }),
  ).toBeTruthy();
  expect(
    within(office).getByText("Research input", { selector: "span" }),
  ).toBeTruthy();
  fireEvent.click(within(office).getByText("Source details"));
  expect(
    within(office).getByText("agentos/workstreams/WS-DIRECTION-TEST.md"),
  ).toBeTruthy();
  fireEvent.click(
    within(office).getByRole("button", { name: "Back to dependencies" }),
  );
  expect(document.activeElement).toBe(
    within(office).getByRole("button", {
      name: "Inspect dependencies for Source-backed programme",
    }),
  );
  fireEvent.click(
    within(office).getByRole("button", {
      name: "Inspect dependencies for Research input",
    }),
  );
  expect(
    within(office).getByText("No dependencies were declared for this record."),
  ).toBeTruthy();
  fireEvent.keyDown(document.activeElement!, { key: "Escape" });
  expect(e.invoke.mock.calls.length).toBe(reads);
  fireEvent.click(within(office).getByRole("button", { name: "View project" }));
  expect(screen.queryByRole("region", { name: "Meta-CEO office" })).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Meta-CEO" }));
  expect(
    (
      (await screen.findByRole("textbox", {
        name: "Direction to Meta-CEO",
      })) as HTMLTextAreaElement
    ).value,
  ).toBe("Keep this unsent Office draft.");
  expect(
    e.invoke.mock.calls.filter(([c]) =>
      /submit|prepare|send|consume|resume|pause/.test(c),
    ),
  ).toHaveLength(0);
});
it("withdraws inspected graph on actual auth departure", async () => {
  const e = await setup();
  fireEvent.click(
    screen.getByRole("button", {
      name: "Inspect dependencies for Source-backed programme",
    }),
  );
  act(() =>
    e.notify({
      status: "signed_out",
      reason: null,
      acquisition: false,
      content: false,
    }),
  );
  expect(screen.queryByText("WS:RESEARCH-INPUT")).toBeNull();
  expect(
    screen.queryByRole("button", { name: "Back to dependencies" }),
  ).toBeNull();
});
it("cannot preserve inspected graph through actual Host replacement and return", async () => {
  const e = await setup();
  fireEvent.click(
    screen.getByRole("button", {
      name: "Inspect dependencies for Source-backed programme",
    }),
  );
  window.MastermindMissionHost = { ...e.host };
  fireEvent.click(screen.getByRole("button", { name: "Today" }));
  expect(
    screen.queryByRole("button", { name: "Back to dependencies" }),
  ).toBeNull();
});

it("uses localized declared/unmet labels and explicit Back in the mounted ZH Office", async () => {
  const e = await setup("zh-CN"),
    count = e.invoke.mock.calls.length;
  fireEvent.click(
    screen.getByRole("button", { name: "查看 Source-backed programme 的依赖" }),
  );
  expect(screen.getByRole("heading", { name: "尚未满足的依赖" })).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "返回依赖列表" }));
  expect(document.activeElement).toBe(
    screen.getByRole("button", { name: "查看 Source-backed programme 的依赖" }),
  );
  expect(e.invoke.mock.calls.length).toBe(count);
});
