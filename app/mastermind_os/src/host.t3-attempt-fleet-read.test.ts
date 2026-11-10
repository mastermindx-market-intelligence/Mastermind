import { expect, it, vi } from "vitest";
import { bindMissionHost, createNativeClient } from "./host";

const signed = { status: "signed_in" as const, reason: null, acquisition: true, content: false };
/** Run ids contain `/`; this one exercises the slash (plus `:`, `%`, `=`) through the seam. */
const RUN_ID = "runs/2026-11-09/worker-7:seat%3D3";
/** A typed refusal is an honest schema-bearing body, never a transport error. */
const refusal = { schema: "mastermind.t3_attempt_fleet/v1", refusal: "SOURCE_UNAVAILABLE", attempts: [] };

export async function fleetHost(read: () => Promise<unknown> = async () => refusal) {
  let notify = (_: unknown) => {};
  const invoke = vi.fn(async (command: string) => {
    if (command === "auth_status") return signed;
    if (command === "executive_auth_status") return { generation: 0, available: false };
    if (command === "read_t3_attempt_fleet") return read();
    throw Error("unexpected native command");
  });
  const raw = await createNativeClient(invoke as never, async (_event, listener) => { notify = payload => listener({ payload }); return () => {}; });
  return { raw, host: bindMissionHost(raw), invoke, notify };
}
const commands = (env: Awaited<ReturnType<typeof fleetHost>>) =>
  env.invoke.mock.calls.filter(([command]) => command === "read_t3_attempt_fleet");

it("issues exactly one fixed native read for a run id that contains '/'", async () => {
  const env = await fleetHost();
  const result = await env.host.readT3AttemptFleet!({ attemptId: RUN_ID, signal: new AbortController().signal });
  expect(result).toEqual({ state: "AVAILABLE", document: { kind: "refusal", refusal: "SOURCE_UNAVAILABLE" } });
  expect(commands(env)).toEqual([["read_t3_attempt_fleet", { selection: { attempt_id: RUN_ID } }]]);
});

it("refuses unsafe and secret-shaped attempt ids before any native command, at both layers", async () => {
  const env = await fleetHost();
  // Each passes the raw grammar shape check only where noted; all are refused
  // client-side: `xoxb-`/`ghp_`/`bearer`/`sk-…` are secret-shaped, the rest
  // violate the run-id grammar itself.
  for (const attemptId of ["", "../runs/1", "runs/1 x", "runs/1?extra=2", "runs/xoxb-0123456789abcdef",
    "runs/GHP_" + "a".repeat(30), "runs/bearer/1", "runs/sk-" + "c".repeat(16)]) {
    await expect(env.host.readT3AttemptFleet!({ attemptId, signal: new AbortController().signal }))
      .rejects.toThrow("T3_ATTEMPT_SELECTION_INVALID");
    await expect(env.raw.readT3AttemptFleet!({ attemptId, signal: new AbortController().signal }))
      .rejects.toThrow("T3_ATTEMPT_SELECTION_INVALID");
  }
  expect(commands(env)).toEqual([]);
});

it("mounts the read-union command on the native client (union membership itself is proven by typecheck)", async () => {
  const env = await fleetHost();
  expect(typeof env.raw.readT3AttemptFleet).toBe("function");
  expect(typeof env.host.readT3AttemptFleet).toBe("function");
});
