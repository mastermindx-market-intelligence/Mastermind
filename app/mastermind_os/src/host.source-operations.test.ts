import { expect, it, vi } from "vitest";
import { bindMissionHost, createNativeClient } from "./host";
const signed = {
  status: "signed_in" as const,
  reason: null,
  acquisition: true,
  content: false,
};
const id = "mmos-project-adopt-" + "a".repeat(40);
const lookup = {
  schema: "mastermind.workspace_source_operation_lookup.v1" as const,
  action: "ADOPT_PLAN" as const,
  request_id: id,
  work_ref: "WS:TEST",
};
const status = () => ({
  schema: "mastermind.workspace_source_operation_status.v1",
  selection: {
    action: lookup.action,
    request_id: id,
    work_ref: lookup.work_ref,
  },
  owner_context: { principal_scope: "a".repeat(64) },
  disposition: "unknown",
  reason: "ORIGINAL_OPERATION_NOT_OBSERVED",
  request_sha256: null,
  recipe_fingerprint_sha256: null,
  phase: null,
  receipt: null,
  advance: null,
});
async function setup(response = async () => status() as unknown) {
  const invoke = vi.fn(
    async (command: string, _args?: Record<string, unknown>) => {
      if (command === "auth_status") return signed;
      if (command === "executive_auth_status")
        return { generation: 0, available: false };
      if (command.startsWith("source_operation_")) return response();
      throw Error("unexpected native call");
    },
  );
  const raw = await createNativeClient(invoke as never, async () => () => {});
  return { raw, invoke, host: bindMissionHost(raw) };
}
it("joins actual native client and host to fixed body-free GET/status and explicit reconciliation", async () => {
  const e = await setup(),
    signal = new AbortController().signal;
  expect(
    await e.host.sourceOperations!.readSourceOperation(lookup, signal),
  ).toEqual(status());
  await e.host.sourceOperations!.reconcileSourceOperation(lookup, signal);
  expect(
    e.invoke.mock.calls.filter(([c]) => c.startsWith("source_operation_")),
  ).toEqual([
    ["source_operation_read", { request: lookup }],
    ["source_operation_reconcile", { request: lookup }],
  ]);
});
it("omits an incomplete legacy source port and refuses a replaced method before I/O", async () => {
  const e = await setup();
  expect(
    bindMissionHost({ ...e.raw, sourceOperations: undefined }).sourceOperations,
  ).toBeUndefined();
  const replacement = vi.fn(async () => status());
  e.raw.sourceOperations!.readSourceOperation = replacement;
  await expect(
    e.host.sourceOperations!.readSourceOperation(
      lookup,
      new AbortController().signal,
    ),
  ).rejects.toThrow("SOURCE_OPERATION_UNAUTHORIZED");
  expect(replacement).not.toHaveBeenCalled();
  expect(
    e.invoke.mock.calls.filter(([c]) => c.startsWith("source_operation_")),
  ).toHaveLength(0);
});
it("discards a late same-display auth generation result and never retries", async () => {
  let resolve!: (v: unknown) => void;
  const pending = new Promise<unknown>((yes) => (resolve = yes));
  const e = await setup(() => pending);
  let epoch = 0;
  e.raw.invalidationGeneration = () => epoch;
  const host = bindMissionHost(e.raw);
  const read = host.sourceOperations!.readSourceOperation(
    lookup,
    new AbortController().signal,
  );
  const rejected = expect(read).rejects.toThrow("READ_CANCELLED");
  epoch++;
  resolve(status());
  await rejected;
  expect(
    e.invoke.mock.calls.filter(([c]) => c.startsWith("source_operation_")),
  ).toHaveLength(1);
});
it("refuses response substitution and signed-out dispatch without calling the source owner", async () => {
  const e = await setup(async () => ({
    ...status(),
    selection: { ...status().selection, work_ref: "WS:OTHER" },
  }));
  await expect(
    e.host.sourceOperations!.readSourceOperation(
      lookup,
      new AbortController().signal,
    ),
  ).rejects.toThrow("SOURCE_OPERATION_RESPONSE_INVALID");
  await e.raw.signOut().catch(() => {});
  e.invoke.mockClear();
  await expect(
    e.host.sourceOperations!.readSourceOperation(
      lookup,
      new AbortController().signal,
    ),
  ).rejects.toThrow("SOURCE_OPERATION_UNAUTHORIZED");
  expect(e.invoke).not.toHaveBeenCalled();
});
