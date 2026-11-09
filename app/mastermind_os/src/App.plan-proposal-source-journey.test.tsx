// @vitest-environment jsdom
// @vitest-environment-options {"url":"https://mcp.mastermind-x.com/os/"}
/** Whole single-run4fa supplier replay. Actual NativeClient/Host/App/ports and
 * incumbent IndexedDB run; native invoke/listen DATA and signed-in enrollment
 * are declared inert boundaries. No raw response or request is rewritten. */
import { afterEach, it, expect, vi } from "vitest";
import {
  render,
  screen,
  fireEvent,
  waitFor,
  cleanup,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { IDBFactory } from "fake-indexeddb";
import { createIndexedDbPendingPointerStore } from "./orchestration/indexeddb-pending-pointer-store";
import { App } from "./App";
import { createNativeClient } from "./host";
import { composeMissionHost } from "./compose-mission-host";
import { decodeLaunchBindingConfig } from "./launch-config";
import { canonicalJson } from "./orchestration/operation-key";
import supplier from "./fixtures/project-plan-proposal-source-issued-4fa354.json";
type Row = {
  sequence: number;
  edge: string;
  operation: string;
  request: unknown;
  response: unknown;
  status_code?: number;
};
const rows = supplier.samples as unknown as Row[],
  same = (a: unknown, b: unknown) => canonicalJson(a) === canonicalJson(b);
const raw = (n: number) =>
  structuredClone(rows.find((r) => r.sequence === n)!.response);
const request = (n: number) => rows.find((r) => r.sequence === n)!.request;
let dispose = () => {};
afterEach(() => {
  cleanup();
  dispose();
  vi.restoreAllMocks();
  delete window.MastermindMissionHost;
  history.replaceState(null, "", "/os/");
});
async function setup(losePublication = false, losePreparation = false) {
  vi.spyOn(Date, "now").mockReturnValue(supplier.recorded_at_ms);
  const originalRandom = crypto.getRandomValues.bind(crypto),
    entropy = [0xbb, 0x88];
  vi.spyOn(crypto, "getRandomValues").mockImplementation(((
    array: ArrayBufferView,
  ) => {
    if (array instanceof Uint8Array && array.length === 20) {
      const byte = entropy.shift();
      if (byte !== undefined) {
        array.fill(byte);
        return array;
      }
    }
    return originalRandom(array);
  }) as typeof crypto.getRandomValues);
  let published = false,
    kept = false,
    lost = losePublication,
    preparationCount = 0;
  const served: number[] = [];
  const serve = (n: number, value: unknown) => {
    expect(value).toEqual(request(n));
    served.push(n);
    return raw(n);
  };
  const invoke = vi.fn(
    async (command: string, args?: Record<string, unknown>) => {
      const value = args?.request ?? args?.selection ?? args ?? {};
      if (command === "auth_status")
        return {
          status: "signed_in",
          reason: null,
          acquisition: true,
          content: true,
        };
      if (command === "executive_auth_status")
        return { generation: 4, available: true };
      if (command === "executive_context") return serve(8, args ?? {});
      if (command === "read_source_operation_context")
        return serve(
          (value as { action: string }).action === "publish_project_proposal"
            ? 1
            : 2,
          value,
        );
      if (command === "source_operation_options") return serve(4, value);
      if (command === "source_operation_prepare") return serve(5, value);
      if (command === "source_operation_submit") {
        if ((value as { action: string }).action === "publish_project_proposal")
          return serve(6, value);
        const response = serve(17, value);
        if (lost) {
          lost = false;
          throw Error("INERT_LOST_PUBLICATION_RESPONSE");
        }
        return response;
      }
      if (command === "source_operation_reconcile") {
        if ((value as { action: string }).action === "publish_project_proposal")
          return serve(7, value);
        published = true;
        return serve(18, value);
      }
      if (command === "source_operation_read") return serve(20, value);
      if (command === "read_project_plan")
        return serve(published ? 19 : 3, value);
      if (command === "executive_project_planning") {
        const op = args?.operation,
          wrapped = { arguments: args?.arguments };
        if (op === "submit") return serve(9, wrapped);
        if (op === "status") return serve(10, wrapped);
        if (op === "result") return serve(published ? 22 : 11, wrapped);
        if (op === "consume") {
          kept = true;
          return serve(13, wrapped);
        }
        if (op === "prepare_proposal") {
          expect(kept).toBe(true);
          const response = serve(preparationCount++ === 0 ? 15 : 16, wrapped);
          if (losePreparation) {
            losePreparation = false;
            throw Error("INERT_LOST_PREPARATION_RESPONSE");
          }
          return response;
        }
      }
      throw Error("Unrecorded inert native boundary: " + command);
    },
  );
  const client = await createNativeClient(
    invoke as never,
    async () => () => {},
  );
  const config = decodeLaunchBindingConfig(
    JSON.stringify({
      v: 1,
      workstream: "WS:JOURNEY-INTEG",
      priority: 0,
      attemptLimit: 1,
      projects: [{ ref: "executive-infrastructure", label: "Infrastructure" }],
      profiles: [
        { ref: "research_only", label: "Research" },
        { ref: "native_research_only", label: "Native research" },
      ],
    }),
  )!;
  const idb = new IDBFactory(),
    composed = composeMissionHost(client, config, idb);
  await composed.ready;
  window.MastermindMissionHost = composed.host;
  const page = render(<App />);
  dispose = () => {
    page.unmount();
    composed.dispose();
  };
  return {
    invoke,
    served,
    page,
    host: composed.host,
    idb,
    lose: () => {
      lost = true;
    },
    markPublished: () => {
      published = true;
    },
    withdraw: () => {
      window.MastermindMissionHost = undefined;
    },
  };
}
async function driveToKept(
  h: Awaited<ReturnType<typeof setup>>,
  prepareAfterKeep = true,
) {
  fireEvent.click(await screen.findByRole("button", { name: "Projects" }));
  fireEvent.click(await screen.findByRole("button", { name: "New project" }));
  fireEvent.change(await screen.findByLabelText("Your goal"), {
    target: { value: supplier.consumer_inputs.create_goal },
  });
  fireEvent.click(screen.getByRole("button", { name: "Options" }));
  fireEvent.click(screen.getByRole("button", { name: "Load project options" }));
  const profile = (raw(4) as { profiles: { label: { en: string } }[] })
    .profiles[0];
  fireEvent.click(await screen.findByRole("radio", { name: profile.label.en }));
  fireEvent.click(screen.getByRole("button", { name: "Prepare preview" }));
  fireEvent.click(
    await screen.findByRole("button", { name: "Create project" }),
  );
  fireEvent.click(
    await screen.findByRole("button", { name: "Check project creation" }),
  );
  await screen.findAllByText("Project created.");
  fireEvent.click(screen.getByRole("radio", { name: "Plan" }));
  fireEvent.change(screen.getByLabelText("Initial request"), {
    target: { value: supplier.consumer_inputs.initial_request },
  });
  fireEvent.click(
    screen.getByRole("button", { name: "Send initial planning request" }),
  );
  fireEvent.click(
    await screen.findByRole("button", { name: "Read planning result" }),
  );
  const prepare = await screen.findByRole("button", {
    name: "Prepare planning proposal",
  });
  expect((prepare as HTMLButtonElement).disabled).toBe(true);
  fireEvent.click(await screen.findByRole("button", { name: "Keep result" }));
  await screen.findByText("This result is kept.");
  if (prepareAfterKeep) {
    await userEvent.setup().click(screen.getByRole("button",{name:"Prepare planning proposal"}));
    await waitFor(() =>
      expect(h.served, "exact served source sequence").toContain(15),
    );
    const publish=await screen.findByRole("button", { name: "Publish planning proposal" });
    await waitFor(()=>expect(document.activeElement).toBe(publish));
  }
}
it("actual App Keep→fixed preparation→separate publication→current Compare→Back/reopen retains exact original", async () => {
  const h = await setup();
  await driveToKept(h);
  fireEvent.click(
    screen.getByRole("button", { name: "Publish planning proposal" }),
  );
  await waitFor(() => expect(h.served).toContain(17));
  fireEvent.click(
    screen.getByRole("button", { name: "Check proposal publication" }),
  );
  await screen.findByText(
    "Proposal published. Compare it with the current plan; adoption is a separate step.",
  );
  await waitFor(() =>
    expect(
      (
        screen.getByRole("button", {
          name: "View current Plan and Compare",
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(false),
  );
  expect(screen.queryByText('Publication outcome is unknown. Check this original request instead of sending it again.')).toBeNull();
  fireEvent.click(
    screen.getByRole("button", { name: "View current Plan and Compare" }),
  );
  await screen.findByRole("region", { name: "Project plan" });
  expect(h.served).toContain(19);
  const select = await screen.findByRole("combobox", {
    name: "Recorded proposal to inspect",
  });
  expect((select as HTMLSelectElement).value).toBe(
    "PLAN-" + supplier.identities.plan_request_id.slice(-40),
  );
  const compare = screen.getByText("Compare plans");
  fireEvent.click(compare);
  expect(compare.closest("details")?.open).toBe(true);
  const candidate = (raw(19) as any).continuity.proposals.items[0].comparison
    .candidate_text;
  expect(
    screen.getByText(
      (_, element) =>
        element?.tagName === "PRE" && element.textContent === candidate,
    ),
  ).toBeTruthy();
  await userEvent.setup().click(screen.getByRole("button",{name:"Back to proposal"}));
  await waitFor(()=>expect(document.activeElement).toBe(screen.getByRole("button",{name:"View current Plan and Compare"})));
  fireEvent.click(screen.getByRole("button", { name: "Read planning result" }));
  await waitFor(() => expect(h.served).toContain(22));
  expect(
    screen.getByRole("button", { name: "View current Plan and Compare" }),
  ).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Back to projects" }));
  fireEvent.click(
    await screen.findByRole("button", { name: "Continue project setup" }),
  );
  fireEvent.click(
    await screen.findByRole("button", { name: "Check original proposal" }),
  );
  await screen.findByText(
    "Proposal published. Compare it with the current plan; adoption is a separate step.",
  );
  expect(
    h.invoke.mock.calls.filter(
      ([name, args]) =>
        name === "source_operation_submit" &&
        (args?.request as { action: string })?.action ===
          "publish_project_plan_proposal",
    ),
  ).toHaveLength(1);
  expect(
    h.invoke.mock.calls.filter(
      ([name, args]) =>
        name === "executive_project_planning" && args?.operation === "submit",
    ),
  ).toHaveLength(1);
  expect(h.served.filter((n) => n === 15)).toHaveLength(1);
  expect(h.served.filter((n) => n === 13)).toHaveLength(1);
  expect(location.href).toContain("project_plan_proposal_original=");
  expect(location.href).not.toContain("Private+first+request");
}, 15000);

it("lost preparation restores the same safe original and opaque preview; no new Job or publication", async () => {
  const h = await setup(false, true);
  await driveToKept(h, false);
  fireEvent.click(
    screen.getByRole("button", { name: "Prepare planning proposal" }),
  );
  await screen.findByText(
    "The proposal operation is unavailable. Check the original request; no replacement was created.",
  );
  const href = location.href;
  expect(href).toContain("project_plan_proposal_original=");
  const restore = screen.getByRole("button", {
    name: "Restore original proposal preview",
  });
  await waitFor(() =>
    expect((restore as HTMLButtonElement).disabled).toBe(false),
  );
  fireEvent.click(restore);
  await screen.findByRole("button", { name: "Publish planning proposal" });
  expect(location.href).toBe(href);
  expect(h.served.filter((n) => n === 15 || n === 16)).toEqual([15, 16]);
  expect(
    h.invoke.mock.calls.filter(
      ([name, args]) =>
        name === "source_operation_submit" &&
        (args?.request as { action: string })?.action ===
          "publish_project_plan_proposal",
    ),
  ).toHaveLength(0);
  expect(
    h.invoke.mock.calls.filter(
      ([name, args]) =>
        name === "executive_project_planning" && args?.operation === "submit",
    ),
  ).toHaveLength(1);
}, 15000);
it("lost publication survives real IDB/Back and recovers only the original reconcile, without another submit or preparation", async () => {
  const h = await setup(true);
  await driveToKept(h);
  fireEvent.click(
    screen.getByRole("button", { name: "Publish planning proposal" }),
  );
  await screen.findByText(
    "Publication outcome is unknown. Check this original request instead of sending it again.",
  );
  const href = location.href;
  fireEvent.click(screen.getByRole("button", { name: "Back to projects" }));
  fireEvent.click(
    await screen.findByRole("button", { name: "Continue project setup" }),
  );
  expect(location.href).toBe(href);
  fireEvent.click(
    await screen.findByRole("button", { name: "Check proposal publication" }),
  );
  await screen.findByText(
    "Proposal published. Compare it with the current plan; adoption is a separate step.",
  );
  expect(h.served.filter((n) => n === 17)).toHaveLength(1);
  expect(h.served.filter((n) => n === 15 || n === 16)).toEqual([15]);
  expect(h.served).toContain(18);
}, 15000);
it("no-render actual global Host withdrawal refuses the prepared publication gesture before transport", async () => {
  const h = await setup();
  await driveToKept(h);
  h.withdraw();
  fireEvent.click(
    screen.getByRole("button", { name: "Publish planning proposal" }),
  );
  await screen.findByText(
    "The proposal operation is unavailable. Check the original request; no replacement was created.",
  );
  expect(h.served).not.toContain(17);
  expect(h.served.filter((n) => n === 15)).toHaveLength(1);
}, 15000);

it("same-Host binding.store replacement at enabled publication refuses with zero submit or id mint", async () => {
  const h = await setup();
  await driveToKept(h);
  const originalStore = h.host.commandBinding!.store;
  const randomCalls = vi.mocked(crypto.getRandomValues).mock.calls.length;
  (h.host.commandBinding as unknown as { store: unknown }).store =
    createIndexedDbPendingPointerStore(new IDBFactory());
  fireEvent.click(
    screen.getByRole("button", { name: "Publish planning proposal" }),
  );
  await screen.findByText(
    /The proposal operation is unavailable|Publication outcome is unknown/,
  );
  expect(h.served).not.toContain(17);
  expect(vi.mocked(crypto.getRandomValues).mock.calls).toHaveLength(
    randomCalls,
  );
  expect(
    await originalStore.read(supplier.identities.workspace_scope),
  ).toBeNull();
}, 15000);
it("Back/remount cannot bless a replacement store or abandon the real original UNKNOWN pointer", async () => {
  const h = await setup(true);
  await driveToKept(h);
  fireEvent.click(
    screen.getByRole("button", { name: "Publish planning proposal" }),
  );
  await screen.findByText(
    "Publication outcome is unknown. Check this original request instead of sending it again.",
  );
  const originalStore = h.host.commandBinding!.store;
  const original = await originalStore.read(
    supplier.identities.workspace_scope,
  );
  expect(original).not.toBeNull();
  (h.host.commandBinding as unknown as { store: unknown }).store =
    createIndexedDbPendingPointerStore(new IDBFactory());
  fireEvent.click(screen.getByRole("button", { name: "Back to projects" }));
  fireEvent.click(
    await screen.findByRole("button", { name: "Continue project setup" }),
  );
  const check = screen.queryByRole("button", {
    name: "Check original proposal",
  }) as HTMLButtonElement | null;
  expect(check === null || check.disabled).toBe(true);
  expect(await originalStore.read(supplier.identities.workspace_scope)).toEqual(
    original,
  );
  expect(h.served.filter((n) => n === 17)).toHaveLength(1);
  expect(h.served).not.toContain(20);
}, 15000);
