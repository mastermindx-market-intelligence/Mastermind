// @vitest-environment jsdom
// Actual NativeClient -> bound Host -> App. Raw retained Work/Journal bodies
// stay unchanged. Auth/native invocation are explicit inert test seams.
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { App } from "./App";
import { createNativeClient, bindMissionHost } from "./host";
import source from "./fixtures/office-existing-reads-source.json";
const programs = source.responses.programs.body,
  plan = source.responses.objective.body,
  journal = source.responses.journal.body;
import work from "./fixtures/work-service-available.json";
let dispose = () => {};
beforeEach(() => {
  vi.spyOn(Date, "now").mockReturnValue(source.clock.verified_at * 1000);
  history.replaceState(null, "", "/os/");
  delete window.MastermindMissionHost;
});
afterEach(() => {
  cleanup();
  dispose();
  delete window.MastermindMissionHost;
  vi.restoreAllMocks();
});
async function setup(hold: "journal" | "work" | null = null) {
  let resolve!: (v: unknown) => void;
  const pending = new Promise((r) => (resolve = r));
  const listeners = new Map<string, (event: { payload: unknown }) => void>();
  const invoke = vi.fn(async (command: string, args?: unknown) => {
    if (command === "auth_status")
      return {
        status: "signed_in",
        reason: null,
        acquisition: true,
        content: false,
      };
    if (command === "read_programs") return structuredClone(programs);
    if (command === "read_work")
      return hold === "work" ? pending : structuredClone(work);
    if (command === "read_project_plan") return structuredClone(plan);
    if (command === "read_project_journal") {
      expect(args).toEqual({ selection: { work_ref: source.work_ref } });
      return hold === "journal" ? pending : structuredClone(journal);
    }
    throw Error("No Mission/write/Executive capability");
  });
  const client = await createNativeClient(
    invoke as never,
    async (name, listener) => {
      listeners.set(name, listener);
      return () => listeners.delete(name);
    },
  );
  const host = bindMissionHost(client);
  window.MastermindMissionHost = host;
  render(<App />);
  dispose = () => listeners.clear();
  const nav = (name: string) => {
    const button = screen.queryByRole("button", { name });
    if (!button)
      fireEvent.click(document.querySelector(".nav-advanced > summary")!);
    fireEvent.click(screen.getByRole("button", { name }));
  };
  nav("Projects");
  const title = programs.control_room.work[0].agent_os.title;
  fireEvent.click(
    await screen.findByRole("button", { name: `Open project ${title}` }),
  );
  nav("Meta-CEO");
  await screen.findByRole("region", { name: "Meta-CEO office" });
  return {
    host,
    invoke,
    resolve,
    nav,
    notify: () => {
      for (const fn of listeners.values())
        fn({
          payload: {
            status: "signed_out",
            reason: "AUTHENTICATION_REQUIRED",
            acquisition: false,
            content: false,
          },
        });
    },
    count: (c: string) => invoke.mock.calls.filter(([x]) => x === c).length,
  };
}
it("joins existing Work and explicit selected-project Journal, then returns with the same unsent Office draft and no extra effects", async () => {
  const f = await setup();
  const office = screen.getByRole("region", { name: "Meta-CEO office" });
  fireEvent.click(
    within(office).getByText("Movement and mission lanes", {
      selector: "summary",
    }),
  );
  expect(
    await within(office).findByRole("region", {
      name: "Work items in this view",
    }),
  ).toBeTruthy();
  expect(within(office).getByText("Work item JOB-1")).toBeTruthy();
  expect(f.count("read_work")).toBe(1);
  expect(f.count("read_project_journal")).toBe(0);
  expect(
    within(
      document.getElementById("office-journal-title")!.closest("section")!,
    ).queryByText("Project not selected"),
  ).toBeNull();
  const draft = within(office).getByRole("textbox", {
    name: "Direction to Meta-CEO",
  });
  fireEvent.change(draft, {
    target: { value: "Keep this exact Office draft." },
  });
  fireEvent.click(
    within(office).getByText("Returns, critical path and journal", {
      selector: "summary",
    }),
  );
  fireEvent.click(
    within(office).getByRole("button", { name: "Read project journal" }),
  );
  await within(office).findByText(journal.journal!.entries[0].title);
  expect(f.count("read_project_journal")).toBe(1);
  fireEvent.click(within(office).getByRole("button", { name: "Inspect Work" }));
  expect(screen.queryByRole("region", { name: "Meta-CEO office" })).toBeNull();
  f.nav("Meta-CEO");
  expect(
    (
      screen.getByRole("textbox", {
        name: "Direction to Meta-CEO",
      }) as HTMLTextAreaElement
    ).value,
  ).toBe("Keep this exact Office draft.");
  expect(f.count("read_work")).toBe(1);
  expect(f.count("read_project_journal")).toBe(1);
  expect(
    f.invoke.mock.calls.filter(([c]) =>
      /submit|send|prepare|pause|resume|consume/.test(c),
    ),
  ).toHaveLength(0);
});
it.each(["host", "auth", "generation"] as const)(
  "withholds late journal after actual %s departure",
  async (damage) => {
    const f = await setup("journal");
    fireEvent.click(
      screen.getByText("Returns, critical path and journal", {
        selector: "summary",
      }),
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Read project journal" }),
    );
    await waitFor(() => expect(f.count("read_project_journal")).toBe(1));
    if (damage === "host") window.MastermindMissionHost = { ...f.host };
    else if (damage === "generation") {
      const old = f.host.invalidationGeneration!();
      vi.spyOn(f.host, "invalidationGeneration").mockReturnValue(old + 1);
    } else act(() => f.notify());
    await act(async () => f.resolve(journal));
    expect(screen.queryByText(journal.journal!.entries[0].title)).toBeNull();
  },
);
it("never publishes a late Work response from the replaced actual Host into Office", async () => {
  const f = await setup("work");
  window.MastermindMissionHost = { ...f.host };
  await act(async () => f.resolve(work));
  fireEvent.click(
    screen.getByText("Movement and mission lanes", { selector: "summary" }),
  );
  expect(screen.queryByText("JOB-1")).toBeNull();
  expect(
    screen.getByText(
      "Work information is unavailable. This does not mean there is no work.",
    ),
  ).toBeTruthy();
  expect(f.count("read_work")).toBe(1);
});

it("rejects a foreign project journal response without touching the Office draft or sending", async () => {
  const f = await setup("journal");
  const draft = screen.getByRole("textbox", { name: "Direction to Meta-CEO" });
  fireEvent.change(draft, {
    target: { value: "Original private Office text" },
  });
  fireEvent.click(
    screen.getByText("Returns, critical path and journal", {
      selector: "summary",
    }),
  );
  fireEvent.click(screen.getByRole("button", { name: "Read project journal" }));
  await waitFor(() => expect(f.count("read_project_journal")).toBe(1));
  await act(async () =>
    f.resolve({ ...journal, selection: { work_ref: "WS:FOREIGN" } }),
  );
  expect(screen.queryByText(journal.journal!.entries[0].title)).toBeNull();
  expect((draft as HTMLTextAreaElement).value).toBe(
    "Original private Office text",
  );
  expect(
    f.invoke.mock.calls.filter(([c]) => /submit|send|prepare|consume/.test(c)),
  ).toHaveLength(0);
});
