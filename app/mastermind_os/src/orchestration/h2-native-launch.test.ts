import { describe, expect, it, vi } from "vitest";
import { decodeLaunchBindingConfig } from "../launch-config";
import {
  ExecutiveLaunchCommandPort,
  type ExecutiveToolEnvelope,
} from "./executive-launch-command-port";
import {
  intentIdForOperationKey,
  operationKeyForLaunch,
  requestRefForOperationKey,
} from "./operation-key";

const manifest = {
  v: 1,
  workstream: "WS:H2-FIXTURE",
  priority: 0,
  attemptLimit: 1,
  projects: [{ ref: "executive-infrastructure", label: "Infrastructure" }],
  profiles: [
    { ref: "research_only", label: "Research" },
    { ref: "native_research_only", label: "Direct native research" },
  ],
};
const form = {
  goal: "Analyze supplied fixture evidence.",
  projectRef: "executive-infrastructure",
  profileRef: "native_research_only",
};
const owner = () => ({ principalScope: "scope-A", generation: "auth-1" });
function setup() {
  const config = decodeLaunchBindingConfig(JSON.stringify(manifest))!;
  const callTool =
    vi.fn<(...args: unknown[]) => Promise<ExecutiveToolEnvelope>>();
  const port = new ExecutiveLaunchCommandPort(config, { callTool }, owner);
  const intent = port.makeLaunchIntent(form)!;
  return { config, callTool, port, intent, pointer: port.prepare(intent) };
}
function receipt(key: string) {
  return {
    schema: "mastermind.ceo_direct_native_receipt.v1",
    intent_id: intentIdForOperationKey(key),
    fingerprint: "f".repeat(64),
    job_id: "JOB-123",
    status: "QUEUED",
    accepted: true,
    duplicate: false,
    dispatched: false,
    authority: {
      requested: ["READ", "RESEARCH"],
      policy_sha256: "a".repeat(64),
      authority_level: "A0",
    },
    grounding: {},
    created_at_ms: 0,
    work_ref: manifest.workstream,
  };
}
function submitted(key: string, data: unknown): ExecutiveToolEnvelope {
  return {
    ok: true,
    status: "accepted",
    request_ref: requestRefForOperationKey(key),
    receipt: data,
  };
}
function status(data: unknown): ExecutiveToolEnvelope {
  return {
    schema: "mastermind.executive_mcp_result.v1",
    tool: "ceo_intent_status",
    ok: true,
    server_version: "1.5.0",
    mode: "readonly",
    generated_at: "2026-10-24T00:00:00Z",
    grounding: {},
    data,
    degraded: [],
    bounded: [],
    error: null,
  } as ExecutiveToolEnvelope;
}
describe("explicit direct-native Launch producer", () => {
  it("uses only the listed native profile and existing hashed identity", () => {
    const { port, intent } = setup();
    expect(intent.payload).toEqual({
      operation_key: operationKeyForLaunch({
        principalScope: "scope-A",
        workstream: manifest.workstream,
        department: form.projectRef,
        execution_profile: form.profileRef,
        objective: form.goal,
        priority: 0,
        attempt_limit: 1,
      }),
      objective: form.goal,
      department: form.projectRef,
      priority: 0,
      execution_profile: form.profileRef,
      workstream: manifest.workstream,
      attempt_limit: 1,
    });
    const coo = port.makeLaunchIntent({
      ...form,
      profileRef: "research_only",
    })!;
    expect(coo.payload.operation_key).not.toBe(intent.payload.operation_key);
    expect(
      port.makeLaunchIntent({ ...form, profileRef: "codex-01" }),
    ).toBeNull();
    const config = decodeLaunchBindingConfig(
      JSON.stringify({ ...manifest, profiles: manifest.profiles.slice(0, 1) }),
    )!;
    expect(
      new ExecutiveLaunchCommandPort(
        config,
        { callTool: vi.fn() },
        owner,
      ).makeLaunchIntent(form),
    ).toBeNull();
  });
  it.each([
    {},
    { attemptLimit: 2 },
    { attemptLimit: 3 },
    { attemptLimit: true },
    { allowedWritePaths: ["research/change.md"] },
    { validation: { git_diff_check: true } },
    { validation: { pytest_targets: ["tests/test_example.py"] } },
  ])("rejects unqualified native manifest %j", (change) => {
    const input = { ...manifest, ...change };
    if (Object.keys(change).length === 0)
      delete (input as Partial<typeof manifest>).attemptLimit;
    expect(decodeLaunchBindingConfig(JSON.stringify(input))).toBeNull();
  });
  it("keeps the existing legacy operation-key vector", () => {
    expect(
      operationKeyForLaunch({
        principalScope: "scope-A",
        workstream: "WS:ALPHA",
        department: "research",
        execution_profile: "research_only",
        objective: "Ship the launch binding",
        priority: 0,
      }),
    ).toBe("mmos-launch-bb349455c5a5907291d4169e77147e639e763e46");
  });
  it("accepts correlated direct admission and same-pointer status without guessing mode", async () => {
    const { callTool, port, pointer, intent } = setup();
    callTool.mockResolvedValueOnce(
      submitted(pointer.operationKey, receipt(pointer.operationKey)),
    );
    expect(
      (await port.submit(pointer, intent, new AbortController().signal))
        .missionSelection,
    ).toEqual({ workRef: manifest.workstream, rootJobId: "JOB-123" });
    callTool.mockResolvedValueOnce(
      status({
        ...receipt(pointer.operationKey),
        status: "COMPLETED",
        duplicate: true,
      }),
    );
    expect(
      (await port.readOperation(pointer, new AbortController().signal))
        .disposition,
    ).toBe("accepted");
    expect(callTool.mock.calls[1][0]).toBe("ceo_intent_status");
    expect(callTool.mock.calls[1][1]).toEqual({
      intent_id: intentIdForOperationKey(pointer.operationKey),
    });
  });
  it.each([
    "intent",
    "work",
    "extras",
    "dispatched",
    "write",
    "fingerprint",
    "duplicate",
    "status",
    "schema",
  ])("holds malformed or conflicting direct receipt %s", async (fault) => {
    const { callTool, port, pointer, intent } = setup();
    const data: Record<string, unknown> = receipt(pointer.operationKey);
    if (fault === "intent") data.intent_id = "auto-foreign";
    if (fault === "work") data.work_ref = "WS:FOREIGN";
    if (fault === "extras") data.worker_id = "codex-01";
    if (fault === "dispatched") data.dispatched = true;
    if (fault === "write")
      data.authority = {
        requested: ["READ", "WRITE_BRANCH"],
        policy_sha256: "a".repeat(64),
        authority_level: "A0",
      };
    if (fault === "fingerprint") data.fingerprint = "not-a-digest";
    if (fault === "duplicate") data.duplicate = "false";
    if (fault === "status") data.status = "PRODUCT_ACCEPTED";
    if (fault === "schema")
      data.schema = "mastermind.direct_native_result_response.v1";
    callTool.mockResolvedValueOnce(submitted(pointer.operationKey, data));
    expect(
      (await port.submit(pointer, intent, new AbortController().signal))
        .disposition,
    ).toBe("unknown");
  });
});
