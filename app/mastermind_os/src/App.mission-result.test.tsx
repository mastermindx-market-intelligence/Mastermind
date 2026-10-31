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

const APP_POSITIVE_DIR = "MISSION_RESULT_APP_POSITIVE_DIR";
const APP_FALLBACK_DIR = "MISSION_RESULT_APP_FALLBACK_DIR";
const SELECTION_KEYS = ["work_ref", "root_job_id", "job_id", "attempt_id", "result_envelope_digest"] as const;

function appEnv(key: string): string | undefined {
  const env = (globalThis as { process?: { env?: Record<string, string | undefined> } }).process?.env;
  if (!env || !Object.prototype.hasOwnProperty.call(env, key)) return undefined;
  return env[key];
}

type ExplicitKind = "positive" | "fallback";
type ExportBody = {
  availability?: string;
  mission: {
    read_state?: { state?: string };
    result_refs?: { generation?: { source_identity?: string; state?: string } };
    source?: { owner_observation?: { state?: string; runtime?: { source_identity?: string } } };
  };
  role_result: {
    availability?: string;
    source_observation?: { runtime?: { source_identity?: string } };
    result?: { content?: { summary?: string } | null };
  };
  selection: Record<string, string>;
};
type ExportProvenance = {
  content_fallback?: string;
  http_body_sha256?: string;
  http_body_bytes?: number;
  mission_runtime_source_identity?: string;
  role_result_runtime_source_identity?: string;
  selection?: Record<string, string>;
};

async function nodeIo() {
  // @ts-expect-error node builtins are resolved by the vitest worker.
  const fs = (await import("node:fs/promises")) as {
    readFile(path: string): Promise<Uint8Array>;
    writeFile(path: string, data: string | Uint8Array): Promise<void>;
    mkdir(path: string, options?: { recursive?: boolean }): Promise<void>;
    mkdtemp(prefix: string): Promise<string>;
  };
  // @ts-expect-error node builtins are resolved by the vitest worker.
  const path = (await import("node:path")) as { join(...parts: string[]): string };
  // @ts-expect-error node builtins are resolved by the vitest worker.
  const os = (await import("node:os")) as { tmpdir(): string };
  return { fs, path, os };
}

function refuse(detail: string): never {
  throw new Error(`refusing to substitute the committed export (${detail})`);
}

/** Read one attempt-owned directory. Never opens the committed fixture. */
async function loadExplicitExport(directory: string, kind: ExplicitKind) {
  if (!directory.trim()) refuse("directory is empty");
  const { fs, path } = await nodeIo();
  const pairPath = path.join(directory, "actual-pair.json");
  const provenancePath = path.join(directory, "fixture-provenance.json");
  let bytes: Uint8Array;
  let provenanceBytes: Uint8Array;
  try {
    bytes = new Uint8Array(await fs.readFile(pairPath));
    provenanceBytes = new Uint8Array(await fs.readFile(provenancePath));
  } catch (err) {
    refuse((err as Error).message);
  }
  if (bytes.byteLength === 0 || provenanceBytes.byteLength === 0) refuse("export file is empty");
  const hash = await sha256(bytes);
  const provenance = JSON.parse(new TextDecoder().decode(provenanceBytes)) as ExportProvenance;
  if (provenance.http_body_sha256 !== hash) refuse("http_body_sha256 mismatch");
  if (provenance.http_body_bytes !== bytes.byteLength) refuse("http_body_bytes mismatch");
  const parsed = JSON.parse(new TextDecoder().decode(bytes)) as ExportBody;
  const bodySelection = parsed.selection ?? {};
  const provenanceSelection = provenance.selection ?? {};
  for (const key of SELECTION_KEYS) {
    if (!bodySelection[key] || bodySelection[key] !== provenanceSelection[key])
      refuse(`selection ${key} mismatch`);
  }
  const identity = parsed.role_result.source_observation?.runtime?.source_identity;
  if (
    !identity
    || parsed.mission.result_refs?.generation?.source_identity !== identity
    || parsed.mission.source?.owner_observation?.runtime?.source_identity !== identity
    || provenance.mission_runtime_source_identity !== identity
    || provenance.role_result_runtime_source_identity !== identity
  ) refuse("runtime identity is not one shared observation");
  if (parsed.mission.read_state?.state !== "CURRENT") refuse("mission is not CURRENT");
  if (parsed.availability !== "AVAILABLE") refuse("compound is not AVAILABLE");
  if (kind === "positive") {
    if (provenance.content_fallback !== "not_captured") refuse("positive content_fallback");
    if (parsed.role_result.availability !== "AVAILABLE") refuse("positive role availability");
  } else {
    if (provenance.content_fallback !== "mounted_producer_CONTENT_OVER_BUDGET")
      refuse("fallback content_fallback");
    if (parsed.role_result.availability !== "CONTENT_OVER_BUDGET") refuse("fallback role availability");
    if (parsed.role_result.result?.content !== null) refuse("fallback invented content");
  }
  const selection = normalizeResultSelection({
    workRef: bodySelection.work_ref,
    rootJobId: bodySelection.root_job_id,
    jobId: bodySelection.job_id,
    attemptId: bodySelection.attempt_id,
    resultEnvelopeDigest: bodySelection.result_envelope_digest,
  });
  if (!selection) refuse("producer selection missing");
  const decoded = decodeMissionResultBytes(bytes, selection);
  if (!decoded.ok || decoded.document.availability !== "AVAILABLE")
    refuse("decoder rejected the explicit export");
  return { bytes, parsed, selection, decoded: decoded.document, provenance, hash };
}

function oneProgramRoom(workRef = "WS:ONE", rootJobId = "JOB-001") {
  const room = controlRoomFixture();
  room.work = [room.work[0]];
  room.autonomy.responsibilities = [room.autonomy.responsibilities[0]];
  room.work[0].work_ref = workRef;
  room.work[0].agent_os.title = "One";
  Object.assign(room.autonomy.responsibilities[0], {
    responsibility_ref: workRef,
    root_job_id: rootJobId,
    root_job_candidates: [rootJobId],
    root_job_ambiguous: false,
    runtime_root_state: "RESOLVED",
  });
  return room;
}

type Producer = Awaited<ReturnType<typeof loadProducer>>;

function setup(mode: Mode = "bytes", load: () => Promise<Producer> = loadProducer) {
  let count = 0;
  const callbacks = new Set<(event: MessageEvent) => void>();
  const listeners = new Set<(state: ReturnType<ReturnType<typeof createWebAuth>["getState"]>) => void>();
  const popup = { location: "", closed: false, close: vi.fn() };
  const queue: Array<{ digest: string | null; resolve: (value: Response) => void }> = [];
  let producer: Producer;
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
      return response({
        ...structuredClone(programsFixture),
        control_room: oneProgramRoom(producer.selection.workRef, producer.selection.rootJobId),
      });
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
      producer = await load();
      if (load === loadProducer) expect(await sha256(producer.bytes)).toBe(PINNED_SHA256);
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

function sourceRow(name: string) {
  const sources = document.querySelector(".office-sources");
  if (!sources) throw new Error("source qualification missing");
  const row = [...sources.children].find((node) => node.querySelector("span")?.textContent === name);
  if (!row) throw new Error(`${name} source row missing`);
  return row;
}

async function expectOfficeHalvesEmpty(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole("button", { name: "Today" }));
  expect(screen.getByText("The current operating answer is not yet available.")).toBeTruthy();
  expect(screen.getByText("No exactly associated return has been qualified for this view.")).toBeTruthy();
  expect(screen.queryByText("bounded typed fixture result")).toBeNull();
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

  it("refuses an empty, missing, empty-file, or mismatched explicit directory without the committed file", async () => {
    await expect(loadExplicitExport("", "positive")).rejects.toThrow(/refusing to substitute the committed export/);
    await expect(loadExplicitExport("   ", "fallback")).rejects.toThrow(/refusing to substitute the committed export/);
    const { fs, path, os } = await nodeIo();
    const root = await fs.mkdtemp(path.join(os.tmpdir(), "mm-app-export-"));
    await expect(loadExplicitExport(path.join(root, "missing"), "positive")).rejects.toThrow(
      /refusing to substitute the committed export/,
    );
    const emptyDir = path.join(root, "empty");
    await fs.mkdir(emptyDir);
    await fs.writeFile(path.join(emptyDir, "actual-pair.json"), "");
    await fs.writeFile(path.join(emptyDir, "fixture-provenance.json"), "{}");
    await expect(loadExplicitExport(emptyDir, "fallback")).rejects.toThrow(/refusing to substitute the committed export/);
    const badDir = path.join(root, "bad-hash");
    await fs.mkdir(badDir);
    const payload = new TextEncoder().encode("{\"selection\":{}}");
    await fs.writeFile(path.join(badDir, "actual-pair.json"), payload);
    await fs.writeFile(path.join(badDir, "fixture-provenance.json"), JSON.stringify({
      http_body_sha256: "0".repeat(64),
      http_body_bytes: payload.byteLength,
      selection: {},
    }));
    await expect(loadExplicitExport(badDir, "positive")).rejects.toThrow(/http_body_sha256/);
    const cwd = (globalThis as { process?: { cwd?: () => string } }).process?.cwd?.();
    if (!cwd) throw new Error("producer fixture path requires the vitest worker cwd");
    const committed = new Uint8Array(await fs.readFile(
      `${cwd}/src/meta-ceo/fixtures/mission-result-producer/actual-pair.json`,
    ));
    expect(await sha256(committed)).toBe(PINNED_SHA256);
  });

  it("withholds a still-owned pick when the mounted typed method changes before the queued call", async () => {
    const e = setup("bytes");
    await e.ready();
    render(<App />);
    const user = await openProject();
    const button = await screen.findByRole("button", { name: /JOB-004/ });
    const installed = window.MastermindMissionHost!.readMissionResult!;
    let capturedCalls = 0;
    window.MastermindMissionHost!.readMissionResult = (async (input) => {
      capturedCalls += 1;
      return installed(input);
    }) as typeof installed;
    let replacementCalls = 0;
    const onClick = () => {
      window.MastermindMissionHost!.readMissionResult = (async () => {
        replacementCalls += 1;
        throw new Error("replacement must not run");
      }) as typeof installed;
    };
    document.addEventListener("click", onClick);
    const before = e.calls("/workspace/mission-result/current").length;
    try {
      await act(async () => {
        button.dispatchEvent(new MouseEvent("click", { bubbles: true }));
        await flush();
      });
    } finally {
      document.removeEventListener("click", onClick);
    }
    expect(capturedCalls).toBe(0);
    expect(replacementCalls).toBe(0);
    expect(e.calls("/workspace/mission-result/current")).toHaveLength(before);
    expect(screen.getByText("READ_CANCELLED")).toBeTruthy();
    expect(screen.queryByText("Reading the exact selected tuple…")).toBeNull();
    await expectOfficeHalvesEmpty(user);
  });

  it("settles READ_CANCELLED when the mounted method changes while the compound read is in flight", async () => {
    const e = setup("queue");
    const producer = await e.ready();
    render(<App />);
    const user = await openProject();
    await user.click(await screen.findByRole("button", { name: /JOB-004/ }));
    await waitFor(() => expect(e.queue).toHaveLength(1));
    let replacementCalls = 0;
    window.MastermindMissionHost!.readMissionResult = (async () => {
      replacementCalls += 1;
      throw new Error("replacement must not run");
    }) as NonNullable<NonNullable<typeof window.MastermindMissionHost>["readMissionResult"]>;
    await act(async () => {
      e.queue[0].resolve(new Response(producer.bytes, { headers: { "content-type": "application/json" } }));
      await flush();
    });
    expect(replacementCalls).toBe(0);
    expect(screen.queryByText("bounded typed fixture result")).toBeNull();
    expect(screen.getByText("READ_CANCELLED")).toBeTruthy();
    expect(screen.queryByText("Reading the exact selected tuple…")).toBeNull();
    await expectOfficeHalvesEmpty(user);
  });

  it.each(["host replacement", "silent host-generation drift"] as const)(
    "settles a still-owned read after %s without an auth event",
    async (kind) => {
      const e = setup("queue");
      const producer = await e.ready();
      render(<App />);
      const user = await openProject();
      await user.click(await screen.findByRole("button", { name: /JOB-004/ }));
      await waitFor(() => expect(e.queue).toHaveLength(1));
      const host = window.MastermindMissionHost!;
      if (kind === "host replacement") {
        window.MastermindMissionHost = { ...host };
      } else {
        const originalGeneration = host.invalidationGeneration!;
        host.invalidationGeneration = () => originalGeneration() + 1;
      }
      await act(async () => {
        e.queue[0].resolve(new Response(producer.bytes, { headers: { "content-type": "application/json" } }));
        await flush();
      });
      expect(await screen.findByText("READ_CANCELLED")).toBeTruthy();
      expect(screen.queryByText("Reading the exact selected tuple…")).toBeNull();
      expect(screen.queryByText("bounded typed fixture result")).toBeNull();
      await expectOfficeHalvesEmpty(user);
    },
  );

  it("settles a still-owned cancellation when the raw client method is replaced", async () => {
    const e = setup("queue");
    const producer = await e.ready();
    render(<App />);
    const user = await openProject();
    await user.click(await screen.findByRole("button", { name: /JOB-004/ }));
    await waitFor(() => expect(e.queue).toHaveLength(1));
    const host = window.MastermindMissionHost!;
    const typed = host.readMissionResult;
    const generation = host.invalidationGeneration?.();
    let replacementCalls = 0;
    e.client.readMissionResult = (async () => {
      replacementCalls += 1;
      throw new Error("raw replacement invoked");
    }) as typeof e.client.readMissionResult;
    expect(window.MastermindMissionHost).toBe(host);
    expect(host.readMissionResult).toBe(typed);
    expect(host.invalidationGeneration?.()).toBe(generation);
    await act(async () => {
      e.queue[0].resolve(new Response(producer.bytes, { headers: { "content-type": "application/json" } }));
      await flush();
    });
    expect(replacementCalls).toBe(0);
    expect(screen.getByText("READ_CANCELLED")).toBeTruthy();
    expect(screen.queryByText("Reading the exact selected tuple…")).toBeNull();
    expect(screen.queryByText("bounded typed fixture result")).toBeNull();
    expect(screen.queryByText("SOURCE_READ_PENDING")).toBeNull();
    await expectOfficeHalvesEmpty(user);
  });

  it("rejects a crossed newer typed pair without letting an older callback clear its ticket", async () => {
    const e = setup("queue");
    const producer = await e.ready();
    render(<App />);
    const user = await openProject();
    await user.click(await screen.findByRole("button", { name: /JOB-004/ }));
    await waitFor(() => expect(e.queue).toHaveLength(1));
    let releaseSecond: (value: Producer["decoded"]) => void = () => {};
    const second = new Promise<Producer["decoded"]>((resolve) => { releaseSecond = resolve; });
    window.MastermindMissionHost!.readMissionResult = (async () => second) as NonNullable<
      NonNullable<typeof window.MastermindMissionHost>["readMissionResult"]
    >;
    await user.click(await screen.findByRole("button", { name: /JOB-002/ }));
    expect(screen.getByText("Reading the exact selected tuple…")).toBeTruthy();
    await act(async () => {
      e.queue[0].resolve(new Response(producer.bytes, { headers: { "content-type": "application/json" } }));
      await flush();
    });
    expect(screen.queryByText("bounded typed fixture result")).toBeNull();
    expect(screen.getByText("Reading the exact selected tuple…")).toBeTruthy();
    expect(screen.queryByText("READ_CANCELLED")).toBeNull();
    await act(async () => {
      // JOB-002 was requested; this typed host returns the JOB-004 producer.
      // No crossed five-field tuple may publish to App or either Office half.
      releaseSecond(producer.decoded);
      await flush();
    });
    expect(await screen.findByText("MISSION_RESULT_RESPONSE_INVALID")).toBeTruthy();
    expect(screen.queryByText("bounded typed fixture result")).toBeNull();
    expect(screen.queryByText("Reading the exact selected tuple…")).toBeNull();
    expect(e.calls("/workspace/result/current")).toHaveLength(0);
    await expectOfficeHalvesEmpty(user);
  });

  it.each(["workRef", "rootJobId", "jobId", "attemptId", "resultEnvelopeDigest"] as const)(
    "refuses a crossed typed compound selection field: %s",
    async (field) => {
      const e = setup("bytes");
      const producer = await e.ready();
      window.MastermindMissionHost!.readMissionResult = async () => ({
        ...producer.decoded,
        selection: {
          ...producer.decoded.selection,
          [field]: `${producer.decoded.selection[field]}-CROSSED`,
        },
      });
      render(<App />);
      const user = await openProject();
      await user.click(await screen.findByRole("button", { name: /JOB-004/ }));
      expect(await screen.findByText("MISSION_RESULT_RESPONSE_INVALID")).toBeTruthy();
      expect(screen.queryByText("bounded typed fixture result")).toBeNull();
      expect(e.calls("/workspace/result/current")).toHaveLength(0);
      await expectOfficeHalvesEmpty(user);
    },
  );

  it("rejects a matching outer typed selection wrapping a sibling Job's nested Result", async () => {
    const e = setup("bytes");
    const producer = await e.ready();
    window.MastermindMissionHost!.readMissionResult = async (request) => ({
      ...producer.decoded,
      selection: {
        workRef: request.workRef,
        rootJobId: request.rootJobId,
        jobId: request.jobId,
        attemptId: request.attemptId,
        resultEnvelopeDigest: request.resultEnvelopeDigest,
      },
    });
    render(<App />);
    const user = await openProject();
    await user.click(await screen.findByRole("button", { name: /JOB-002/ }));
    // Outer selection is the JOB-002 click, but the role Result and its
    // source observation still belong to JOB-004. Neither may publish.
    expect(await screen.findByText("MISSION_RESULT_RESPONSE_INVALID")).toBeTruthy();
    expect(screen.queryByText("bounded typed fixture result")).toBeNull();
    expect(e.calls("/workspace/result/current")).toHaveLength(0);
    await expectOfficeHalvesEmpty(user);
  });

  it.each([
    ["role-result", "work_ref"],
    ["role-result", "root_job_id"],
    ["role-result", "job_id"],
    ["role-result", "attempt_id"],
    ["role-result", "result_envelope_digest"],
    ["source-observation", "work_ref"],
    ["source-observation", "root_job_id"],
    ["source-observation", "job_id"],
    ["source-observation", "attempt_id"],
    ["source-observation", "result_envelope_digest"],
  ] as const)("rejects a crossed nested %s field %s", async (layer, field) => {
    const e = setup("bytes");
    const producer = await e.ready();
    const forged = structuredClone(producer.decoded);
    const target = layer === "role-result"
      ? forged.roleResult.selection
      : forged.roleResult.source_observation.selection;
    target[field] = `${target[field]}-CROSSED`;
    window.MastermindMissionHost!.readMissionResult = async () => forged;
    render(<App />);
    const user = await openProject();
    await user.click(await screen.findByRole("button", { name: /JOB-004/ }));
    expect(await screen.findByText("MISSION_RESULT_RESPONSE_INVALID")).toBeTruthy();
    expect(screen.queryByText("bounded typed fixture result")).toBeNull();
    await expectOfficeHalvesEmpty(user);
  });

  it("rejects a crossed nested role-view selector even when both wire selectors match", async () => {
    const e = setup("bytes");
    const producer = await e.ready();
    const forged = structuredClone(producer.decoded);
    if (!forged.roleResult.result) throw new Error("positive producer role view missing");
    forged.roleResult.result.selection.job_id = "JOB-002";
    window.MastermindMissionHost!.readMissionResult = async () => forged;
    render(<App />);
    const user = await openProject();
    await user.click(await screen.findByRole("button", { name: /JOB-004/ }));
    expect(await screen.findByText("MISSION_RESULT_RESPONSE_INVALID")).toBeTruthy();
    expect(screen.queryByText("bounded typed fixture result")).toBeNull();
    await expectOfficeHalvesEmpty(user);
  });

  it("rejects a crossed typed UNAVAILABLE selection before showing its source reason", async () => {
    const e = setup("bytes");
    const producer = await e.ready();
    window.MastermindMissionHost!.readMissionResult = async () => ({
      schema: producer.decoded.schema,
      availability: "UNAVAILABLE" as const,
      selection: { ...producer.decoded.selection, jobId: "JOB-002" },
      reasonCodes: ["SOURCE_CHANGED"] as const,
      mission: null,
      roleResult: null,
    });
    render(<App />);
    const user = await openProject();
    await user.click(await screen.findByRole("button", { name: /JOB-004/ }));
    expect(await screen.findByText("MISSION_RESULT_RESPONSE_INVALID")).toBeTruthy();
    expect(screen.queryByText("SOURCE_CHANGED")).toBeNull();
    await expectOfficeHalvesEmpty(user);
  });

});

async function renderExplicit(kind: ExplicitKind, directory: string) {
  const held: { current?: Awaited<ReturnType<typeof loadExplicitExport>> } = {};
  const e = setup("bytes", async () => {
    const loaded = await loadExplicitExport(directory, kind);
    held.current = loaded;
    const bytes = new Uint8Array(loaded.bytes.byteLength);
    bytes.set(loaded.bytes);
    return {
      bytes,
      parsed: loaded.parsed as Producer["parsed"],
      selection: loaded.selection,
      decoded: loaded.decoded,
    };
  });
  await e.ready();
  const loaded = held.current;
  if (!loaded) throw new Error("explicit export was not loaded");
  expect(loaded.hash).not.toBe(PINNED_SHA256);
  expect(loaded.provenance.http_body_sha256).toBe(loaded.hash);
  expect(loaded.provenance.http_body_bytes).toBe(loaded.bytes.byteLength);
  expect(loaded.provenance.mission_runtime_source_identity).toBe(
    loaded.provenance.role_result_runtime_source_identity,
  );
  render(<App />);
  const user = await openProject();
  const before = e.calls("/workspace/mission-result/current").length;
  await user.click(await screen.findByRole("button", {
    name: (name) => name.includes(loaded.selection.jobId),
  }));
  expect(e.calls("/workspace/mission-result/current")).toHaveLength(before + 1);
  expect(e.calls("/workspace/result/current")).toHaveLength(0);
  const served = new URL(String(e.calls("/workspace/mission-result/current").at(-1)![0]));
  expect(served.searchParams.get("work_ref")).toBe(loaded.selection.workRef);
  expect(served.searchParams.get("root_job_id")).toBe(loaded.selection.rootJobId);
  expect(served.searchParams.get("job_id")).toBe(loaded.selection.jobId);
  expect(served.searchParams.get("attempt_id")).toBe(loaded.selection.attemptId);
  expect(served.searchParams.get("result_envelope_digest")).toBe(loaded.selection.resultEnvelopeDigest);
  return { e, user, loaded };
}

const positiveDir = appEnv(APP_POSITIVE_DIR);
const fallbackDir = appEnv(APP_FALLBACK_DIR);

describe.skipIf(positiveDir === undefined)("App fresh mounted positive export", () => {
  it("consumes that directory's unchanged whole HTTP bytes", async () => {
    const { user, loaded } = await renderExplicit("positive", positiveDir ?? "");
    expect(loaded.provenance.content_fallback).toBe("not_captured");
    const summary = loaded.parsed.role_result.result?.content?.summary;
    if (!summary) throw new Error("fresh positive summary missing");
    expect(await screen.findByText(summary)).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "Today" }));
    const returns = document.getElementById("office-returns-title")?.closest("section");
    if (!returns) throw new Error("Returns to review is missing");
    expect(within(returns).getByText(summary)).toBeTruthy();
    expect(within(returns).getByText(loaded.selection.jobId)).toBeTruthy();
    expect(within(returns).getByText(new RegExp(loaded.selection.attemptId))).toBeTruthy();
    expect(within(returns).getByText(/NOT_PROJECTED/)).toBeTruthy();
    expect(sourceRow("Return").textContent).toContain("CURRENT");
    expect(sourceRow("Return").textContent).toContain("COMPLETE");
    expect(sourceRow("Mission").textContent).toContain("CURRENT");
  });
});

describe.skipIf(fallbackDir === undefined)("App fresh mounted content fallback", () => {
  it("consumes the genuine CONTENT_OVER_BUDGET body with incomplete coverage", async () => {
    const { user, loaded } = await renderExplicit("fallback", fallbackDir ?? "");
    expect(loaded.provenance.content_fallback).toBe("mounted_producer_CONTENT_OVER_BUDGET");
    expect(loaded.parsed.role_result.availability).toBe("CONTENT_OVER_BUDGET");
    expect(loaded.parsed.role_result.result?.content).toBeNull();
    expect(await screen.findByText(/Content omitted by owner/)).toBeTruthy();
    expect(screen.queryByText("bounded typed fixture result")).toBeNull();
    await user.click(screen.getByRole("button", { name: "Today" }));
    const returns = document.getElementById("office-returns-title")?.closest("section");
    if (!returns) throw new Error("Returns to review is missing");
    expect(within(returns).getByText(loaded.selection.jobId)).toBeTruthy();
    expect(within(returns).getByText(/Content is withheld or outside the bounded response/)).toBeTruthy();
    expect(within(returns).getByText(/NOT_PROJECTED/)).toBeTruthy();
    expect(within(returns).queryByText("bounded typed fixture result")).toBeNull();
    expect(sourceRow("Return").textContent).toContain("CURRENT");
    expect(sourceRow("Return").textContent).toContain("INCOMPLETE");
  });
});
