// @vitest-environment jsdom
import {
  act,
  cleanup,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { flushSync } from "react-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";
import { bindMissionHost, createNativeClient } from "./host";
import { controlRoomFixture } from "./test-fixtures";
import programs from "./fixtures/programs-available-workspace-service.json";
import paired from "./fixtures/window-mission-association-producer.json";
import work from "./fixtures/work-service-available.json";

const signed = {
  status: "signed_in",
  reason: null,
  acquisition: true,
  content: true,
};
const visible = paired.window.view.items.find((item) => item.text)!.text!;
async function hostFixture() {
  const room = controlRoomFixture();
  room.work = [room.work[0]];
  room.autonomy.responsibilities = [room.autonomy.responsibilities[0]];
  room.work[0].work_ref = paired.selection.work_ref;
  Object.assign(room.autonomy.responsibilities[0], {
    responsibility_ref: paired.selection.work_ref,
    root_job_id: paired.selection.root_job_id,
    root_job_candidates: [paired.selection.root_job_id],
    root_job_ambiguous: false,
    runtime_root_state: "RESOLVED",
  });
  const mission = structuredClone(paired.mission);
  mission.program.title = "Private daily project";
  (mission.principal as any).owed_turn = {
    seat: "chairman",
    reason: "Private reserved decision",
    source_refs: [
      {
        owner: "EXECUTIVE_OS",
        ref: "decision:exact",
        observed_at: "2026-10-04T09:00:00Z",
        freshness: "current",
      },
    ],
  };
  let notify!: (event: { payload: unknown }) => void,
    hold = false;
  const held: Array<() => void> = [];
  const invoke = vi.fn(async (command: string) => {
    if (command === "auth_status") return signed;
    const value =
      command === "read_programs"
        ? { ...structuredClone(programs), control_room: room }
        : command === "read_mission_v3"
          ? mission
          : command === "read_work"
            ? work
            : paired.window;
    return hold
      ? new Promise((resolve) =>
          held.push(() => resolve(structuredClone(value))),
        )
      : structuredClone(value);
  });
  const client = await createNativeClient(
    invoke as never,
    async (_event, listener) => {
      notify = listener;
      return () => {};
    },
  );
  return {
    host: bindMissionHost(client),
    invoke,
    notify,
    hold: () => {
      hold = true;
    },
    settle: () => held.forEach((resolve) => resolve()),
  };
}
beforeEach(async () => {
  history.replaceState(
    null,
    "",
    "/os/?work_ref=WS%3AFABRIC&root_job_id=JOB-001",
  );
  delete (window as any).__TAURI_INTERNALS__;
  delete window.MastermindMissionHost;
  const { webcrypto } = await vi.importActual<{ webcrypto: Crypto }>(
    "node:crypto",
  );
  vi.stubGlobal("crypto", webcrypto);
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  delete window.MastermindMissionHost;
});

describe("owner-backed daily routes in App", () => {
  it("uses the existing Inbox/Knowledge/Window sources and preserves separate drafts through detours", async () => {
    const e = await hostFixture();
    window.MastermindMissionHost = e.host;
    const user = userEvent.setup();
    render(<App />);
    await waitFor(() =>
      expect(
        screen.getByRole("region", { name: "Meta-CEO answer" }).textContent,
      ).toContain("Private daily project"),
    );
    await user.type(
      screen.getByRole("textbox", { name: "Direction to Meta-CEO" }),
      "Office direction only",
    );
    await user.click(screen.getByRole("button", { name: "Inbox" }));
    expect(
      (await screen.findAllByText("Private reserved decision")).length,
    ).toBeGreaterThan(0);
    await user.click(screen.getByRole("button", { name: "Knowledge" }));
    expect(
      screen.getByRole("region", { name: "Knowledge source" }).textContent,
    ).toContain("CURRENT");
    await user.click(screen.getByRole("button", { name: "Conversations" }));
    expect(await screen.findByText(visible)).toBeTruthy();
    expect(
      screen.getByRole<HTMLTextAreaElement>("textbox", { name: "Unsent draft" })
        .value,
    ).toBe("");
    await user.type(
      screen.getByRole("textbox", { name: "Unsent draft" }),
      "Keep this conversation thought",
    );
    await user.click(screen.getByRole("button", { name: "Review evidence" }));
    expect(
      screen.getByRole("region", { name: "Conversation evidence" }),
    ).toBeTruthy();
    expect(
      e.invoke.mock.calls.filter(
        ([command]) => command === "read_current_window",
      ),
    ).toHaveLength(1);
    await user.click(screen.getByRole("button", { name: "Knowledge" }));
    await user.click(screen.getByRole("button", { name: "Conversations" }));
    expect(await screen.findByText(visible)).toBeTruthy();
    expect(
      screen.getByRole<HTMLTextAreaElement>("textbox", { name: "Unsent draft" })
        .value,
    ).toBe("Keep this conversation thought");
    expect(
      screen.getByRole<HTMLButtonElement>("button", { name: "Send message" })
        .disabled,
    ).toBe(true);
    await user.click(screen.getByRole("button", { name: "Today" }));
    expect(
      screen.getByRole<HTMLTextAreaElement>("textbox", {
        name: "Direction to Meta-CEO",
      }).value,
    ).toBe("Office direction only");
    for (const route of [
      "Today",
      "Projects",
      "Inbox",
      "Conversations",
      "Knowledge",
      "Work",
      "Open Programs",
      "Fleet & Capacity",
      "Mission Workspace",
      "Conversation",
      "Activity",
      "Connections",
      "Evidence",
    ])
      expect(screen.getByRole("button", { name: route })).toBeTruthy();
  });
  it("withdraws conversation content, evidence and draft in the first auth commit", async () => {
    const e = await hostFixture();
    window.MastermindMissionHost = e.host;
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getByRole("button", { name: "Conversations" }));
    expect(await screen.findByText(visible)).toBeTruthy();
    await user.type(
      screen.getByRole("textbox", { name: "Unsent draft" }),
      "Private draft",
    );
    await user.click(screen.getByRole("button", { name: "Review evidence" }));
    e.hold();
    try {
      flushSync(() => e.notify({ payload: signed }));
      expect(document.body.textContent).not.toContain(visible);
      expect(document.body.textContent).not.toContain(
        paired.window.selection_ref,
      );
      expect(
        screen.queryByRole("region", { name: "Conversation evidence" }),
      ).toBeNull();
      expect(
        screen.getByRole<HTMLTextAreaElement>("textbox", {
          name: "Unsent draft",
        }).value,
      ).toBe("");
    } finally {
      await act(async () => {
        e.settle();
        for (let n = 0; n < 20; n++) await Promise.resolve();
      });
    }
  });

  it("opens an exact project into the Paper five-tab local workspace without removing legacy reachability", async () => {
    const e = await hostFixture();
    window.MastermindMissionHost = e.host;
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getByRole("button", { name: "Projects" }));
    const openProject = await screen.findByRole("button", {
      name: /^Open project /,
    });
    await user.click(openProject);
    const tabs = screen.getByRole("tablist", { name: "Project workspace" });
    for (const tab of ["Overview", "Plan", "Work", "Evidence", "More"])
      expect(within(tabs).getByRole("tab", { name: tab })).toBeTruthy();
    expect(
      await screen.findByText(
        `Exact project context · ${paired.selection.root_job_id}`,
      ),
    ).toBeTruthy();
    expect(screen.getByText("Review and acceptance")).toBeTruthy();

    await user.click(within(tabs).getByRole("tab", { name: "Plan" }));
    expect(
      screen.getByText(
        "Agent OS plan content is not projected through the current approved app source.",
      ),
    ).toBeTruthy();
    expect(screen.getByText("Current project context")).toBeTruthy();

    await user.click(within(tabs).getByRole("tab", { name: "Work" }));
    expect(
      screen.getByText(
        `Exact project root ${paired.selection.root_job_id}; other roots remain outside this project view.`,
      ),
    ).toBeTruthy();

    await user.click(within(tabs).getByRole("tab", { name: "Evidence" }));
    expect(
      screen.getByRole("heading", { name: "Qualified evidence references" }),
    ).toBeTruthy();

    await user.click(within(tabs).getByRole("tab", { name: "More" }));
    expect(screen.getByRole("heading", { name: "Journal" })).toBeTruthy();
    const operations = screen.getByRole("navigation", { name: "Project operations" });
    expect(within(operations).getAllByRole("button").map(button => button.textContent)).toEqual(["Work", "Open Programs", "Fleet & Capacity"]);
    expect(
      screen.getByRole("heading", { name: "Resources & systems" }),
    ).toBeTruthy();

    for (const legacy of [
      "Work",
      "Open Programs",
      "Fleet & Capacity",
      "Mission Workspace",
      "Conversation",
      "Activity",
      "Connections",
      "Evidence",
    ])
      expect(
        screen.getAllByRole("button", { name: legacy }).length,
      ).toBeGreaterThan(0);
  });
});
