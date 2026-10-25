// @vitest-environment jsdom
// @vitest-environment-options {"url":"https://mcp.mastermind-x.com/os/"}
import { afterEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { IDBFactory } from "fake-indexeddb";
import { createWebAuth } from "./web-auth";
import { composeMissionHost } from "./compose-mission-host";
import { App } from "./App";
import { ORIGIN } from "./public-config";
import programsFixture from "./fixtures/programs-available-workspace-service.json";
import { controlRoomFixture } from "./test-fixtures";
import { decodeMissionResultBytes } from "./mission-result";
import { normalizeResultSelection } from "./result";

const PINNED_SHA256 = "9ca1a0a5522ce549950d5ea542ad6acd7345e298119dbebe2625676dce67a9f2";
const flush = async () => { for (let n = 0; n < 30; n++) await Promise.resolve(); };
const response = (value: unknown, status = 200) => new Response(JSON.stringify(value), {
  status, headers: { "content-type": "application/json" },
});
const disposals: Array<() => void> = [];

async function sha256(bytes: Uint8Array): Promise<string> {
  const copy = new Uint8Array(bytes.byteLength);
  copy.set(bytes);
  const digest = await crypto.subtle.digest("SHA-256", copy);
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

type Mode = "bytes" | "queue" | "fail" | "unavailable" | "synthetic-budget" | "standalone";

async function loadProducer() {
  const cwd = (globalThis as { process?: { cwd?: () => string } }).process?.cwd?.();
  if (!cwd) throw new Error("producer fixture path requires the vitest worker cwd");
  // @ts-expect-error node:fs/promises is resolved by the vitest worker.
  const fs = (await import("node:fs/promises")) as { readFile(path: string): Promise<Uint8Array> };
  const bytes = new Uint8Array(await fs.readFile(
    `${cwd}/src/meta-ceo/fixtures/mission-result-producer/actual-pair.json`,
  ));
  const parsed = JSON.parse(new TextDecoder().decode(bytes)) as {
    mission: unknown;
    role_result: unknown;
    selection: Record<string, string>;
  };
  const selection = normalizeResultSelection({
    workRef: parsed.selection.work_ref,
    rootJobId: parsed.selection.root_job_id,
    jobId: parsed.selection.job_id,
    attemptId: parsed.selection.attempt_id,
    resultEnvelopeDigest: parsed.selection.result_envelope_digest,
  });
  if (!selection) throw new Error("producer selection missing");
  const decoded = decodeMissionResultBytes(bytes, selection);
  if (!decoded.ok || decoded.document.availability !== "AVAILABLE")
    throw new Error("producer bytes are not an available pair");
  return { bytes, parsed, selection, decoded: decoded.document };
}

function oneProgramRoom() {
  const room = controlRoomFixture();
  room.work = [room.work[0]];
  room.autonomy.responsibilities = [room.autonomy.responsibilities[0]];
  room.work[0].work_ref = "WS:ONE";
  room.work[0].agent_os.title = "One";
  Object.assign(room.autonomy.responsibilities[0], {
    responsibility_ref: "WS:ONE",
    root_job_id: "JOB-001",
    root_job_candidates: ["JOB-001"],
    root_job_ambiguous: false,
    runtime_root_state: "RESOLVED",
  });
  return room;
}

function setup(mode: Mode = "bytes") {
  let count = 0;
  const callbacks = new Set<(event: MessageEvent) => void>();
  const listeners = new Set<(state: ReturnType<ReturnType<typeof createWebAuth>["getState"]>) => void>();
  const popup = { location: "", closed: false, close: vi.fn() };
  const queue: Array<{ digest: string | null; resolve: (value: Response) => void }> = [];
  let producer: Awaited<ReturnType<typeof loadProducer>>;
  const fetcher = vi.fn<typeof fetch>(async (url) => {
    const path = new URL(String(url)).pathname;
    if (path.endsWith("/oauth/token")) {
      return response({
        token_type: "Bearer",
        access_token: "inert-fixture-token",
        expires_in: 3600,
        scope: new URL(popup.location).searchParams.get("scope"),
      });
    }
    if (path === "/workspace/programs/current") {
      return response({ ...structuredClone(programsFixture), control_room: oneProgramRoom() });
    }
    if (path === "/workspace/mission/v3/current") return response(producer.parsed.mission);
    if (path === "/workspace/work/current") return response({}, 503);
    if (path === "/workspace/result/current") return response(producer.parsed.role_result);
    if (path === "/workspace/mission-result/current") {
      const digest = new URL(String(url)).searchParams.get("result_envelope_digest");
      if (mode === "queue") return new Promise((resolve) => queue.push({ digest, resolve }));
      if (mode === "fail") return response({ refused: true }, 500);
      if (mode === "unavailable") {
        return response({
          schema: "mastermind.workspace_mission_result.v1",
          selection: producer.parsed.selection,
          availability: "UNAVAILABLE",
          reason_codes: ["SOURCE_CHANGED"],
          mission: null,
          role_result: null,
        }, 503);
      }
      if (mode === "synthetic-budget") return response(syntheticBudget(producer));
      return new Response(producer.bytes, { headers: { "content-type": "application/json" } });
    }
    return response({}, 503);
  });
  const client = createWebAuth({
    config: { webClientId: "inert-public-client" },
    fetchFn: fetcher,
    openPopup: () => popup,
    crypto: {
      getRandomValues(target: Uint8Array) { target.fill(++count); return target; },
      subtle: { digest: async () => new ArrayBuffer(32) },
    } as unknown as Crypto,
    addEventListener: ((_type: string, fn: (event: MessageEvent) => void) => callbacks.add(fn)) as typeof window.addEventListener,
    removeEventListener: ((_type: string, fn: (event: MessageEvent) => void) => callbacks.delete(fn)) as typeof window.removeEventListener,
  });
  const subscribe = client.subscribe.bind(client);
  client.subscribe = (listener) => {
    listeners.add(listener);
    const release = subscribe(listener);
    return () => { listeners.delete(listener); release(); };
  };
  const generation = client.invalidationGeneration!.bind(client);
  let shift = 0;
  client.invalidationGeneration = () => generation() + shift;
  const callback = () => {
    for (const fn of [...callbacks]) fn({
      source: popup, origin: ORIGIN,
      data: { type: "mastermind-auth-callback", state: new URL(popup.location).searchParams.get("state"), code: "inert-code" },
    } as unknown as MessageEvent);
  };
  const login = async () => {
    const pending = client.signIn();
    await flush(); callback(); await flush(); callback(); await pending;
  };
  const composed = composeMissionHost(client, null, new IDBFactory());
  disposals.push(composed.dispose);
  const calls = (path: string) => fetcher.mock.calls.filter(([url]) => new URL(String(url)).pathname === path);
  return {
    client, host: composed.host, fetcher, queue, calls, login, listeners,
    async ready() {
      producer = await loadProducer();
      expect(await sha256(producer.bytes)).toBe(PINNED_SHA256);
      await login();
      window.MastermindMissionHost = composed.host;
      return producer;
    },
    sameStateGeneration() {
      const visible = client.getState();
      shift += 1;
      for (const listener of [...listeners]) listener(client.getState());
      return visible;
    },
  };
}

function syntheticBudget(producer: Awaited<ReturnType<typeof loadProducer>>) {
  const body = structuredClone(producer.parsed) as {
    role_result: {
      availability: string;
      reason_codes: string[];
      result: { availability: string; content: unknown; content_complete: boolean; omitted: string[] };
    };
  };
  body.role_result.availability = "CONTENT_OVER_BUDGET";
  body.role_result.reason_codes = ["CONTENT_OVER_BUDGET"];
  body.role_result.result.availability = "CONTENT_OVER_BUDGET";
  body.role_result.result.content = null;
  body.role_result.result.content_complete = false;
  body.role_result.result.omitted = ["role_result", "summary", "next_actions"];
  return body;
}

function syntheticSummary(producer: Awaited<ReturnType<typeof loadProducer>>, summary: string) {
  const body = structuredClone(producer.parsed) as {
    role_result: { result: { content: { summary: string } } };
  };
  body.role_result.result.content.summary = summary;
  return body;
}

afterEach(() => {
  cleanup();
  disposals.splice(0).forEach((fn) => fn());
  delete window.MastermindMissionHost;
  history.replaceState(null, "", "/os/");
  vi.restoreAllMocks();
});

async function openProject() {
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: "Projects" }));
  await user.click(await screen.findByRole("button", { name: "Open project One" }));
  return user;
}

describe("App compound Mission/Result consumption", () => {
  it("shows one compound pair through the web host and keeps it across its own Mission update, rerender and Today", async () => {
    const e = setup("bytes");
    const producer = await e.ready();
    const ui = render(<App />);
    const user = await openProject();
    const before = e.calls("/workspace/mission-result/current").length;
    expect(e.calls("/workspace/result/current")).toHaveLength(0);
    await user.click(await screen.findByRole("button", { name: /JOB-004/ }));
    expect(await screen.findByText("bounded typed fixture result")).toBeTruthy();
    await act(async () => { await flush(); });
    expect(screen.getByText("bounded typed fixture result")).toBeTruthy();
    expect(screen.getAllByText("One").length).toBeGreaterThan(0);
    expect(screen.getByText(/Review verdict: reject/)).toBeTruthy();
    expect(e.calls("/workspace/mission-result/current")).toHaveLength(before + 1);
    expect(e.calls("/workspace/result/current")).toHaveLength(0);
    const served = new URL(String(e.calls("/workspace/mission-result/current").at(-1)![0]));
    expect(served.searchParams.get("work_ref")).toBe(producer.selection.workRef);
    expect(served.searchParams.get("job_id")).toBe("JOB-004");
    ui.rerender(<App />);
    await act(async () => { await flush(); });
    expect(e.calls("/workspace/mission-result/current")).toHaveLength(before + 1);
    await user.click(screen.getByRole("button", { name: "Today" }));
    const returns = document.getElementById("office-returns-title")?.closest("section");
    if (!returns) throw new Error("Returns to review is missing");
    expect(within(returns).getByText("bounded typed fixture result")).toBeTruthy();
    expect(within(returns).getByText("JOB-004")).toBeTruthy();
    expect(within(returns).getByText(/NOT_PROJECTED/)).toBeTruthy();
    expect(e.calls("/workspace/mission-result/current")).toHaveLength(before + 1);
    await user.click(screen.getByRole("button", { name: "Projects" }));
    await user.click(await screen.findByRole("button", { name: "Open project One" }));
    await user.click(await screen.findByRole("button", { name: /JOB-004/ }));
    await screen.findByText("bounded typed fixture result");
    expect(e.calls("/workspace/mission-result/current")).toHaveLength(before + 2);
  });

  it("lets only the newest A/B/A ticket publish, including a synthetic stale success and a late failure", async () => {
    const e = setup("queue");
    const producer = await e.ready();
    render(<App />);
    const user = await openProject();
    await user.click(await screen.findByRole("button", { name: /JOB-004/ }));
    await user.click(await screen.findByRole("button", { name: /JOB-002/ }));
    await user.click(screen.getByRole("button", { name: /JOB-004/ }));
    await waitFor(() => expect(e.queue).toHaveLength(3));
    const [first, second, third] = e.queue.splice(0, 3);
    expect(first.digest).toBe(producer.selection.resultEnvelopeDigest);
    expect(second.digest).not.toBe(first.digest);
    expect(third.digest).toBe(first.digest);
    await act(async () => { third.resolve(response(JSON.parse(new TextDecoder().decode(producer.bytes)))); await flush(); });
    expect(await screen.findByText("bounded typed fixture result")).toBeTruthy();
    await act(async () => {
      first.resolve(response(syntheticSummary(producer, "SYNTHETIC_STALE_SHOULD_NOT_APPEAR")));
      second.resolve(response({ refused: true }, 500));
      await flush();
    });
    expect(screen.queryByText("SYNTHETIC_STALE_SHOULD_NOT_APPEAR")).toBeNull();
    expect(screen.getByText("bounded typed fixture result")).toBeTruthy();
    expect(e.calls("/workspace/result/current")).toHaveLength(0);
  });

  it("keeps the legacy Result card and no Office pair when the compound method is absent", async () => {
    const e = setup("standalone");
    await e.ready();
    delete e.client.readMissionResult;
    const composed = composeMissionHost(e.client, null, new IDBFactory());
    disposals.push(composed.dispose);
    expect(composed.host.readMissionResult).toBeUndefined();
    window.MastermindMissionHost = composed.host;
    render(<App />);
    const user = await openProject();
    await user.click(await screen.findByRole("button", { name: /JOB-004/ }));
    expect(await screen.findByText("bounded typed fixture result")).toBeTruthy();
    expect(e.calls("/workspace/mission-result/current")).toHaveLength(0);
    expect(e.calls("/workspace/result/current")).toHaveLength(1);
    await user.click(screen.getByRole("button", { name: "Today" }));
    const returns = document.getElementById("office-returns-title")?.closest("section");
    if (!returns) throw new Error("Returns to review is missing");
    expect(within(returns).getByText(/No exactly associated return/)).toBeTruthy();
    expect(within(returns).queryByText("bounded typed fixture result")).toBeNull();
  });

  it("does not fall back to the standalone Result route when the compound read fails or is typed unavailable", async () => {
    const failed = setup("fail");
    await failed.ready();
    render(<App />);
    const user = await openProject();
    await user.click(await screen.findByRole("button", { name: /JOB-004/ }));
    expect(await screen.findByText("RESULT_SOURCE_UNAVAILABLE")).toBeTruthy();
    expect(failed.calls("/workspace/result/current")).toHaveLength(0);
    cleanup();
    delete window.MastermindMissionHost;
    const unavailable = setup("unavailable");
    await unavailable.ready();
    render(<App />);
    const again = await openProject();
    await again.click(await screen.findByRole("button", { name: /JOB-004/ }));
    expect(await screen.findByText("SOURCE_CHANGED")).toBeTruthy();
    expect(unavailable.calls("/workspace/result/current")).toHaveLength(0);
    await again.click(screen.getByRole("button", { name: "Today" }));
    const returns = document.getElementById("office-returns-title")?.closest("section");
    expect(returns?.textContent).toMatch(/No exactly associated return/);
    expect(returns?.textContent).not.toMatch(/bounded typed fixture result/);
  });

  it("clears private text immediately on sign-out and on a same-visible-state generation change", async () => {
    const e = setup("queue");
    const producer = await e.ready();
    render(<App />);
    const user = await openProject();
    await user.click(await screen.findByRole("button", { name: /JOB-004/ }));
    await waitFor(() => expect(e.queue).toHaveLength(1));
    await act(async () => {
      e.queue[0].resolve(new Response(producer.bytes, { headers: { "content-type": "application/json" } }));
      await flush();
    });
    expect(await screen.findByText("bounded typed fixture result")).toBeTruthy();
    const visible = e.client.getState();
    await act(async () => { e.sameStateGeneration(); });
    expect(e.client.getState()).toEqual(visible);
    expect(screen.queryByText("bounded typed fixture result")).toBeNull();
    await user.click(await screen.findByRole("button", { name: /JOB-004/ }));
    await waitFor(() => expect(e.queue.length).toBeGreaterThan(1));
    const late = e.queue.at(-1)!;
    await act(async () => { await e.client.signOut(); });
    expect(screen.queryByText("bounded typed fixture result")).toBeNull();
    await act(async () => {
      late.resolve(new Response(producer.bytes, { headers: { "content-type": "application/json" } }));
      await flush();
    });
    expect(screen.queryByText("bounded typed fixture result")).toBeNull();
  });

  it("labels a synthetic content-budget body as incomplete and associated", async () => {
    const e = setup("synthetic-budget");
    await e.ready();
    render(<App />);
    const user = await openProject();
    await user.click(await screen.findByRole("button", { name: /JOB-004/ }));
    expect(await screen.findByText(/Content omitted by owner/)).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "Today" }));
    const returns = document.getElementById("office-returns-title")?.closest("section");
    expect(within(returns!).getByText("JOB-004")).toBeTruthy();
    expect(within(returns!).getByText(/Content is withheld or outside the bounded response/)).toBeTruthy();
    expect(e.calls("/workspace/result/current")).toHaveLength(0);
  });

  it("does not publish a late body after unmount", async () => {
    const e = setup("queue");
    const producer = await e.ready();
    const ui = render(<App />);
    const user = await openProject();
    await user.click(await screen.findByRole("button", { name: /JOB-004/ }));
    await waitFor(() => expect(e.queue).toHaveLength(1));
    ui.unmount();
    await act(async () => {
      e.queue[0].resolve(new Response(producer.bytes, { headers: { "content-type": "application/json" } }));
      await flush();
    });
    expect(screen.queryByText("bounded typed fixture result")).toBeNull();
  });
});
