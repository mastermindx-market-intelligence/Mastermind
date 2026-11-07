// @vitest-environment jsdom
// Independently written from the original specification after the paid leaf's
// artifact-path refusal. No inaccessible worker bytes are used. Actual source
// decoder/port/controller/IndexedDB; only the external authenticated host is inert.
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { IDBFactory } from "fake-indexeddb";
import fixture from "../fixtures/project-plan-v2-owner.json";
import { decodeProjectPlan } from "./project-plan";
import { canonicalJson, sha256Hex } from "../orchestration/operation-key";
import { createIndexedDbPendingPointerStore } from "../orchestration/indexeddb-pending-pointer-store";
import type { PlanAdoptionRequest } from "./plan-adoption-request";
import type { PlanAdoptionTransport } from "./plan-adoption-port";
import type {
  PlanAdoptionWorkflowHost,
  PlanAdoptionInspection,
} from "./plan-adoption-workspace";
import { PlanAdoptionWorkflow } from "./PlanAdoptionWorkflow";
import { bindMissionHost, createNativeClient } from "../host";
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});
const workRef = "WS:PLAN-TEST",
  scope = "1".repeat(64),
  fingerprint = "2".repeat(64),
  digest = "3".repeat(64);
const id = "mmos-project-adopt-" + "4".repeat(40);
function fixtureHost() {
  const body = decodeProjectPlan(fixture.cases.available_pending, {
    work_ref: workRef,
  });
  let current = true,
    epoch = 0,
    ready = false,
    original: PlanAdoptionRequest | null = null;
  const listeners = new Set<() => void>();
  const inspection: PlanAdoptionInspection = {
    read: body,
    selection: { work_ref: workRef },
    proposalId: "PLAN-PROPOSAL",
    isCurrent: () => current,
    canRead: () => current,
  };
  const status = (requestId: string, accepted = false) => ({
    schema: "mastermind.workspace_source_operation_status.v1",
    selection: {
      action: "ADOPT_PLAN",
      request_id: requestId,
      work_ref: workRef,
    },
    owner_context: { principal_scope: scope },
    disposition: accepted ? "accepted" : "unknown",
    reason: accepted ? null : ready ? "READY_FOR_ADVANCE" : "IN_PROGRESS",
    request_sha256: original
      ? sha256Hex(canonicalJson(original))
      : "5".repeat(64),
    recipe_fingerprint_sha256: fingerprint,
    phase: accepted ? "ADOPTION" : "CANDIDATE",
    receipt: {
      kind: ready || accepted ? "SOURCE_OBSERVED" : "PHASE_ATTEMPTED",
      event_id: 2,
      recorded_at_ms: 200,
      receipt_sha256: digest,
      sources:
        ready || accepted
          ? [
              {
                repository: "macro",
                commit: "a".repeat(40),
                path: accepted
                  ? "agentos/decisions/DEC-ADOPTED.md"
                  : "planning/proposal.candidate.md",
                content_sha256: "b".repeat(64),
              },
            ]
          : [],
      proposal: null,
    },
    advance: ready && !accepted ? { phase_receipt_digest: digest } : null,
  });
  const preview = (request: PlanAdoptionRequest) => ({
    schema: "mastermind.workspace_source_operation_preview.v1",
    selection: {
      action: "ADOPT_PLAN",
      request_id: request.request_id,
      work_ref: workRef,
    },
    owner_context: { principal_scope: scope },
    request_sha256: sha256Hex(canonicalJson(request)),
    recipe_fingerprint_sha256: fingerprint,
    preview_witness: {
      original_input: {
        schema: "mastermind.terminal_original_input_reference.v1",
        input_ref: "terminal-input:" + "6".repeat(64),
        artifact_sha256: "7".repeat(64),
        payload_sha256: "8".repeat(64),
      },
      recipe_fingerprint_sha256: fingerprint,
    },
    preview: {
      schema: "mastermind.project_plan_adoption_preview.v1",
      work_ref: workRef,
      expected_commit: request.expected_commit,
      expected_adoption: request.expected_adoption,
      candidate_sha256: request.candidate_sha256,
      changed_frontmatter_fields: ["objective"],
      record_body_changed: true,
    },
  });
  const transport: PlanAdoptionTransport = {
    prepareSourceOperation: vi.fn(async (input) => {
      original = input.request;
      return preview(input.request);
    }),
    submitSourceOperation: vi.fn(async (input) => status(input.request_id)),
    readSourceOperation: vi.fn(async (input) => status(input.request_id)),
    reconcileSourceOperation: vi.fn(async (input) => {
      ready = true;
      return status(input.request_id);
    }),
    advanceSourceOperation: vi.fn(async (input) =>
      status(input.request_id, true),
    ),
  };
  const host: PlanAdoptionWorkflowHost = {
    sourceOperations: transport,
    invalidationGeneration: () => epoch,
    readSourceOperationContext: vi.fn(async () => ({
      schema: "mastermind.workspace_source_operation_context.v1",
      selection: { action: "ADOPT_PLAN", work_ref: workRef },
      owner_context: { principal_scope: scope },
      can_inspect: true,
    })),
    auth: {
      getState: () => ({
        status: "signed_in",
        reason: null,
        acquisition: true,
        content: true,
      }),
      subscribe: (listener) => {
        const notify = () =>
          listener({
            status: "signed_in",
            reason: null,
            acquisition: true,
            content: true,
          });
        listeners.add(notify);
        return () => {
          listeners.delete(notify);
        };
      },
    },
  };
  const random = vi.fn((bytes: Uint8Array) => {
    bytes.fill(10);
    return bytes;
  });
  const crypto = { getRandomValues: random } as unknown as Pick<
    Crypto,
    "getRandomValues"
  >;
  const store = createIndexedDbPendingPointerStore(new IDBFactory());
  return {
    host,
    transport,
    inspection,
    store,
    crypto,
    random,
    preview,
    status,
    setCurrent: (value: boolean) => {
      current = value;
    },
    rotate: () => {
      epoch++;
      listeners.forEach((fn) => fn());
    },
  };
}
const button = (name: string) =>
  screen.getByRole("button", { name }) as HTMLButtonElement;
async function review() {
  await waitFor(() => expect(button("Review adoption").disabled).toBe(false));
  fireEvent.click(button("Review adoption"));
  await waitFor(() => expect(button("Adopt this plan").disabled).toBe(false));
}

it("joins actual fixed native client/host, prepared review and original-operation recovery/advance", async () => {
  const f = fixtureHost();
  const signal = new AbortController().signal;
  const methods = {
    source_operation_prepare: "prepareSourceOperation",
    source_operation_read: "readSourceOperation",
    source_operation_submit: "submitSourceOperation",
    source_operation_reconcile: "reconcileSourceOperation",
    source_operation_advance: "advanceSourceOperation",
  } as const;
  const invoke = vi.fn(
    async (command: string, args?: Record<string, unknown>) => {
      if (command === "auth_status") return f.host.auth!.getState();
      if (command === "executive_auth_status")
        return { generation: 0, available: false };
      if (command === "read_source_operation_context")
        return f.host.readSourceOperationContext!({
          action: "ADOPT_PLAN",
          workRef,
          signal,
        });
      const method = methods[command as keyof typeof methods];
      if (method) return f.transport[method]!(args!.request as never, signal);
      throw Error("unexpected fixed native command");
    },
  );
  const raw = await createNativeClient(invoke as never, async () => () => {}),
    host = bindMissionHost(raw);
  render(
    <PlanAdoptionWorkflow
      workRef={workRef}
      inspection={f.inspection}
      host={host}
      store={f.store}
      crypto={f.crypto}
    />,
  );
  await review();
  fireEvent.click(button("Adopt this plan"));
  await waitFor(() =>
    expect(f.transport.submitSourceOperation).toHaveBeenCalledTimes(1),
  );
  await waitFor(() => expect(button("Check original operation").disabled).toBe(false));
  fireEvent.click(button("Check original operation"));
  await waitFor(() =>
    expect(f.transport.reconcileSourceOperation).toHaveBeenCalledTimes(1),
  );
  await waitFor(() =>
    expect(button("Continue original adoption").disabled).toBe(false),
  );
  fireEvent.click(button("Continue original adoption"));
  await waitFor(() =>
    expect(f.transport.advanceSourceOperation).toHaveBeenCalledTimes(1),
  );
  const calls = invoke.mock.calls.filter(([c]) =>
    c.startsWith("source_operation_"),
  );
  expect(calls.map(([c]) => c)).toContain("source_operation_read");
  expect(calls.filter(([c]) => c === "source_operation_submit")).toHaveLength(
    1,
  );
  expect(calls.filter(([c]) => c === "source_operation_advance")).toHaveLength(
    1,
  );
  const original = vi.mocked(f.transport.submitSourceOperation).mock.calls[0][0]
    .request_id;
  for (const [command, args] of calls) {
    const request = args!.request as Record<string, unknown>;
    expect(
      command === "source_operation_prepare"
        ? (request.request as Record<string, unknown>).request_id
        : request.request_id,
    ).toBe(original);
  }
  expect(
    vi.mocked(f.transport.advanceSourceOperation!).mock.calls[0][0]
      .phase_receipt_digest,
  ).toBe(digest);
  await waitFor(async () => expect(await f.store.read(scope)).toBeNull());
});

it("joins one actual inspection to Review then explicit Adopt with the exact witness and original ID", async () => {
  const f = fixtureHost();
  render(
    <PlanAdoptionWorkflow
      workRef={workRef}
      inspection={f.inspection}
      host={f.host}
      store={f.store}
      crypto={f.crypto}
    />,
  );
  await waitFor(() =>
    expect(f.host.readSourceOperationContext).toHaveBeenCalledTimes(1),
  );
  expect(f.random).not.toHaveBeenCalled();
  expect(f.transport.prepareSourceOperation).not.toHaveBeenCalled();
  expect(f.transport.submitSourceOperation).not.toHaveBeenCalled();
  await review();
  expect(f.random).toHaveBeenCalledTimes(1);
  expect(f.transport.submitSourceOperation).not.toHaveBeenCalled();
  fireEvent.click(button("Adopt this plan"));
  await waitFor(() =>
    expect(f.transport.submitSourceOperation).toHaveBeenCalledTimes(1),
  );
  const sent = vi.mocked(f.transport.submitSourceOperation).mock.calls[0][0];
  expect(Object.keys(sent).sort()).toEqual([
    "action",
    "preview_witness",
    "request_id",
    "work_ref",
  ]);
  expect(sent.request_id).toBe("mmos-project-adopt-" + "0a".repeat(20));
  expect((await f.store.read(scope))?.operationKey).toBe(sent.request_id);
});
it("reopens the actual IndexedDB original without a plan read; auto GET, explicit reconcile, explicit same-ID advance", async () => {
  const f = fixtureHost();
  await f.store.reserve(scope, {
    kind: "project_adopt",
    targetKey: workRef,
    operationKey: id,
  });
  const ui = () => (
    <PlanAdoptionWorkflow
      workRef={workRef}
      inspection={null}
      host={f.host}
      store={f.store}
      crypto={f.crypto}
    />
  );
  const first = render(ui());
  await waitFor(() =>
    expect(f.transport.readSourceOperation).toHaveBeenCalledTimes(1),
  );
  expect(f.transport.reconcileSourceOperation).not.toHaveBeenCalled();
  first.unmount();
  render(ui());
  await waitFor(() =>
    expect(f.transport.readSourceOperation).toHaveBeenCalledTimes(2),
  );
  await waitFor(() =>
    expect(button("Check original operation").disabled).toBe(false),
  );
  fireEvent.click(button("Check original operation"));
  await waitFor(() =>
    expect(f.transport.reconcileSourceOperation).toHaveBeenCalledTimes(1),
  );
  await waitFor(() =>
    expect(button("Continue original adoption").disabled).toBe(false),
  );
  fireEvent.click(button("Continue original adoption"));
  await waitFor(() =>
    expect(f.transport.advanceSourceOperation).toHaveBeenCalledTimes(1),
  );
  expect(
    vi.mocked(f.transport.advanceSourceOperation!).mock.calls[0][0],
  ).toEqual({
    schema: "mastermind.workspace_source_operation_advance.v1",
    action: "ADOPT_PLAN",
    request_id: id,
    work_ref: workRef,
    phase_receipt_digest: digest,
  });
  await waitFor(async () => expect(await f.store.read(scope)).toBeNull());
  expect(f.transport.prepareSourceOperation).not.toHaveBeenCalled();
  expect(f.random).not.toHaveBeenCalled();
});
it("keeps the same original request on a failed preview attempt instead of reminting", async () => {
  const f = fixtureHost();
  vi.mocked(f.transport.prepareSourceOperation).mockRejectedValueOnce(
    Error("PRIVATE_ERROR"),
  );
  render(
    <PlanAdoptionWorkflow
      workRef={workRef}
      inspection={f.inspection}
      host={f.host}
      store={f.store}
      crypto={f.crypto}
    />,
  );
  await waitFor(() => expect(button("Review adoption").disabled).toBe(false));
  fireEvent.click(button("Review adoption"));
  await waitFor(() =>
    expect(f.transport.prepareSourceOperation).toHaveBeenCalledTimes(1),
  );
  await waitFor(() => expect(button("Review adoption").disabled).toBe(false));
  fireEvent.click(button("Review adoption"));
  await waitFor(() => expect(button("Adopt this plan").disabled).toBe(false));
  const calls = vi.mocked(f.transport.prepareSourceOperation).mock.calls;
  expect(calls[0][0]).toEqual(calls[1][0]);
  expect(f.random).toHaveBeenCalledTimes(1);
  expect(document.body.textContent).not.toContain("PRIVATE_ERROR");
});
it("withdraws comparison bodies after READ loss but retains the original status route and context", async () => {
  const f = fixtureHost();
  const ui = (inspection: PlanAdoptionInspection | null) => (
    <PlanAdoptionWorkflow
      workRef={workRef}
      inspection={inspection}
      host={f.host}
      store={f.store}
      crypto={f.crypto}
    />
  );
  const view = render(ui(f.inspection));
  await review();
  fireEvent.click(button("Adopt this plan"));
  await waitFor(() =>
    expect(f.transport.submitSourceOperation).toHaveBeenCalledTimes(1),
  );
  f.setCurrent(false);
  view.rerender(ui(null));
  expect(screen.queryByRole("button", { name: "Adopt this plan" })).toBeNull();
  await waitFor(() =>
    expect(button("Check original operation").disabled).toBe(false),
  );
  fireEvent.click(button("Check original operation"));
  await waitFor(() =>
    expect(f.transport.reconcileSourceOperation).toHaveBeenCalledTimes(1),
  );
  expect(f.host.readSourceOperationContext).toHaveBeenCalledTimes(1);
  expect((await f.store.read(scope))?.kind).toBe("project_adopt");
});
it("rejects a late preview after authentication epoch rotation without resurrecting it on ABA", async () => {
  const f = fixtureHost();
  let finish!: (value: unknown) => void;
  vi.mocked(f.transport.prepareSourceOperation).mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  );
  render(
    <PlanAdoptionWorkflow
      workRef={workRef}
      inspection={f.inspection}
      host={f.host}
      store={f.store}
      crypto={f.crypto}
    />,
  );
  await waitFor(() => expect(button("Review adoption").disabled).toBe(false));
  fireEvent.click(button("Review adoption"));
  await waitFor(() =>
    expect(f.transport.prepareSourceOperation).toHaveBeenCalledTimes(1),
  );
  const request = vi.mocked(f.transport.prepareSourceOperation).mock.calls[0][0]
    .request;
  act(() => {
    f.rotate();
    f.rotate();
  });
  await act(async () => finish(f.preview(request)));
  await waitFor(() =>
    expect(f.host.readSourceOperationContext).toHaveBeenCalledTimes(2),
  );
  expect(screen.queryByRole("button", { name: "Adopt this plan" })).toBeNull();
  expect(f.transport.submitSourceOperation).not.toHaveBeenCalled();
});
it("has no context retry loop or mutation on an old host without source capabilities", async () => {
  const f = fixtureHost();
  const host = { ...f.host, sourceOperations: undefined };
  const view = render(
    <PlanAdoptionWorkflow
      workRef={workRef}
      inspection={f.inspection}
      host={host}
      store={f.store}
      crypto={f.crypto}
    />,
  );
  view.rerender(
    <PlanAdoptionWorkflow
      workRef={workRef}
      inspection={f.inspection}
      host={host}
      store={f.store}
      crypto={f.crypto}
    />,
  );
  expect(button("Review adoption").disabled).toBe(true);
  expect(f.host.readSourceOperationContext).not.toHaveBeenCalled();
  expect(f.random).not.toHaveBeenCalled();
});
it("keeps the Chinese review/adoption gesture and action-row language aligned", async () => {
  const f = fixtureHost();
  render(
    <PlanAdoptionWorkflow
      workRef={workRef}
      inspection={f.inspection}
      host={f.host}
      store={f.store}
      crypto={f.crypto}
      locale="zh-CN"
    />,
  );
  await waitFor(() => expect(button("审查采纳").disabled).toBe(false));
  expect(button("审查采纳").closest("[lang]")?.getAttribute("lang")).toBe(
    "zh-CN",
  );
  fireEvent.click(button("审查采纳"));
  await waitFor(() => expect(button("采纳此计划").disabled).toBe(false));
  expect(f.transport.submitSourceOperation).not.toHaveBeenCalled();
});
it("does not describe an unavailable pointer-store read as no pending operation", async () => {
  const f = fixtureHost();
  const store = {
    ...f.store,
    read: async () => {
      throw Error("PRIVATE_STORE_FAILURE");
    },
  };
  render(
    <PlanAdoptionWorkflow
      workRef={workRef}
      inspection={null}
      host={f.host}
      store={store}
      crypto={f.crypto}
    />,
  );
  expect(
    await screen.findByText(
      "Operation recovery is unavailable on this device. Check again when local storage is available.",
    ),
  ).toBeTruthy();
  expect(document.body.textContent).not.toContain(
    "No pending adoption was found",
  );
  expect(document.body.textContent).not.toContain("PRIVATE_STORE_FAILURE");
  expect(f.transport.readSourceOperation).not.toHaveBeenCalled();
});

it.each(["false", "throw"] as const)("caller host guard %s refuses initial context acquisition", async (mode) => {
  const f = fixtureHost();
  const isHostCurrent = () => { if (mode === "throw") throw Error("inert stale owner"); return false; };
  render(<PlanAdoptionWorkflow workRef={workRef} inspection={f.inspection} host={f.host}
    store={f.store} crypto={f.crypto} isHostCurrent={isHostCurrent}/>);
  await act(async () => {});
  expect(f.host.readSourceOperationContext).not.toHaveBeenCalled();
  expect(button("Review adoption").disabled).toBe(true);
  expect(f.transport.readSourceOperation).not.toHaveBeenCalled();
});

it.each(["false", "throw"] as const)("caller host guard %s fences a prepared submission without render", async (invalidMode) => {
  const f = fixtureHost();
  let mode: "current" | "false" | "throw" = "current";
  const isHostCurrent = vi.fn(() => { if (mode === "throw") throw Error("inert stale owner"); return mode === "current"; });
  render(<PlanAdoptionWorkflow workRef={workRef} inspection={f.inspection} host={f.host}
    store={f.store} crypto={f.crypto} isHostCurrent={isHostCurrent}/>);
  await review();
  await waitFor(() => expect(button("Check original operation").disabled).toBe(false));
  const adopt = button("Adopt this plan");
  mode = invalidMode; // no notify, rerender, host object or generation change
  isHostCurrent.mockClear();
  fireEvent.click(adopt);
  await act(async () => {});
  expect(isHostCurrent).toHaveBeenCalled();
  expect(f.transport.submitSourceOperation).not.toHaveBeenCalled();
  expect(await f.store.read(scope)).toBeNull();
});

it("caller host guard preserves the original across refused Check/Advance and permits only current recovery", async () => {
  const f = fixtureHost();
  let mode: "current" | "false" | "throw" = "current";
  const isHostCurrent = vi.fn(() => { if (mode === "throw") throw Error("inert stale owner"); return mode === "current"; });
  render(<PlanAdoptionWorkflow workRef={workRef} inspection={f.inspection} host={f.host}
    store={f.store} crypto={f.crypto} isHostCurrent={isHostCurrent}/>);
  await review();fireEvent.click(button("Adopt this plan"));
  await screen.findByText(/original adoption outcome is not known yet/);
  const original = await f.store.read(scope);
  expect(original?.kind).toBe("project_adopt");
  const beforeRead = vi.mocked(f.transport.readSourceOperation).mock.calls.length;
  mode = "false";
  fireEvent.click(button("Check original operation"));await act(async () => {});
  expect(f.transport.readSourceOperation).toHaveBeenCalledTimes(beforeRead);
  expect(f.transport.reconcileSourceOperation).not.toHaveBeenCalled();
  expect(await f.store.read(scope)).toEqual(original);
  mode = "current";
  fireEvent.click(button("Check original operation"));
  await waitFor(() => expect(button("Continue original adoption").disabled).toBe(false));
  expect(f.transport.reconcileSourceOperation).toHaveBeenCalledTimes(1);
  mode = "throw";
  fireEvent.click(button("Continue original adoption"));await act(async () => {});
  expect(f.transport.advanceSourceOperation).not.toHaveBeenCalled();
  expect(await f.store.read(scope)).toEqual(original);
  mode = "current";
  fireEvent.click(button("Continue original adoption"));
  await waitFor(() => expect(f.transport.advanceSourceOperation).toHaveBeenCalledTimes(1));
  await waitFor(async () => expect(await f.store.read(scope)).toBeNull());
  expect(f.transport.submitSourceOperation).toHaveBeenCalledTimes(1);
  expect(vi.mocked(f.transport.advanceSourceOperation!).mock.calls[0][0].request_id).toBe(original?.operationKey);
});

it.each(["false", "throw"] as const)("caller host guard %s withholds a late settlement and preserves its pending original", async (invalidMode) => {
  const f = fixtureHost();
  let mode: "current" | "false" | "throw" = "current";
  const isHostCurrent = vi.fn(() => { if (mode === "throw") throw Error("inert stale owner"); return mode === "current"; });
  let settle!: (value: unknown) => void;
  vi.mocked(f.transport.submitSourceOperation).mockImplementation(() => new Promise(resolve => { settle = resolve; }));
  render(<PlanAdoptionWorkflow workRef={workRef} inspection={f.inspection} host={f.host}
    store={f.store} crypto={f.crypto} isHostCurrent={isHostCurrent}/>);
  await review();fireEvent.click(button("Adopt this plan"));
  await waitFor(() => expect(f.transport.submitSourceOperation).toHaveBeenCalledTimes(1));
  const original = await f.store.read(scope);
  expect(original?.kind).toBe("project_adopt");
  mode = invalidMode;
  await act(async () => settle(f.status(original!.operationKey, true)));
  expect(screen.queryByText(/Publication of the original adoption is confirmed/)).toBeNull();
  expect(await f.store.read(scope)).toEqual(original);
  expect(f.transport.submitSourceOperation).toHaveBeenCalledTimes(1);
});
