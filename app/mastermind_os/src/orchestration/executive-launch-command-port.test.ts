import { describe, expect, it } from "vitest";
import { OperationController } from "./operation-controller";
import type {
  CommandIntent,
  OperationPointer,
  PendingPointerStore,
} from "./operation-controller";
import {
  COMMAND_ROUTE_UNAVAILABLE,
  completeOrchestratorCommandBinding,
  sessionMatchesSelection,
} from "./host-command-bindings";
import { intentIdForOperationKey, operationKeyForLaunch } from "./operation-key";
import {
  createExecutiveLaunchBinding,
  type ExecutiveToolClient,
  type ExecutiveToolEnvelope,
  type LaunchBindingConfig,
} from "./executive-launch-command-port";
import type { LaunchForm } from "./ui/LaunchOrchestrator";
import type { OrchestratorSessionPresentation } from "./host-command-bindings";

const PRINCIPAL = "scope-A";
const GENERATION = "gen-1";
const WORKSTREAM = "WS:ALPHA";
const JOB_ID = "JOB-001";

const RESEARCH_FORM: LaunchForm = {
  goal: "Ship the launch binding",
  projectRef: "research",
  profileRef: "research_only",
};

const RESEARCH_CONFIG: LaunchBindingConfig = {
  workstream: WORKSTREAM,
  priority: 0,
  projects: [{ ref: "research", label: "Research" }],
  profiles: [
    { ref: "research_only", label: "Research only" },
    { ref: "bounded_code_change", label: "Bounded code change" },
  ],
};

const BOUNDED_CONFIG: LaunchBindingConfig = {
  ...RESEARCH_CONFIG,
  allowedWritePaths: ["src/example.ts"],
  validation: {
    pytest_targets: ["tests/test_example.py"],
    git_diff_check: true,
  },
  attemptLimit: 2,
};

const SESSION: OrchestratorSessionPresentation = {
  sessionKey: "sess-1",
  title: "Session",
  messages: [{ id: "m1", role: "user", text: "hi" }],
  observedAt: null,
  connection: "connected",
  coverage: "COMPLETE",
  turnBusy: true,
  stopLabel: "Interrupt turn",
  selection: { workRef: WORKSTREAM, rootJobId: JOB_ID },
};

interface CallLogEntry {
  name: "submit_ceo_intent" | "ceo_intent_status";
  args: Readonly<Record<string, unknown>>;
}

function samePointer(a: OperationPointer, b: OperationPointer): boolean {
  return (
    a.operationKey === b.operationKey &&
    a.kind === b.kind &&
    a.targetKey === b.targetKey
  );
}

function makeStore(
  initial: Array<[string, OperationPointer]> = [],
): PendingPointerStore {
  const data = new Map<string, OperationPointer>(initial);
  return {
    read: (scope) => data.get(scope) ?? null,
    write: (scope, pointer) => {
      data.set(scope, pointer);
    },
    clear: (scope, pointer) => {
      const existing = data.get(scope);
      if (existing && samePointer(existing, pointer)) data.delete(scope);
    },
  };
}

function acceptedData(
  operationKey: string,
  extra: Record<string, unknown> = {},
): Record<string, unknown> {
  return {
    schema: "mastermind.ceo_intent_receipt.v1",
    intent_id: intentIdForOperationKey(operationKey),
    fingerprint: "f".repeat(64),
    job_id: JOB_ID,
    status: "QUEUED",
    accepted: true,
    duplicate: false,
    dispatched: false,
    authority: {
      requested: ["READ", "RESEARCH"],
      policy_sha256: "a".repeat(64),
      authority_level: "A0",
    },
    grounding: {
      mastermind_sha: "b".repeat(40),
      macro_sha: "c".repeat(40),
      boot_packet_schema: "mastermind.ceo_boot_packet.v1",
    },
    created_at_ms: 1,
    ...extra,
  };
}

function makeClient(
  respond: (
    name: "submit_ceo_intent" | "ceo_intent_status",
    args: Readonly<Record<string, unknown>>,
    signal: AbortSignal,
  ) => ExecutiveToolEnvelope | Promise<ExecutiveToolEnvelope>,
): { client: ExecutiveToolClient; log: CallLogEntry[] } {
  const log: CallLogEntry[] = [];
  const client: ExecutiveToolClient = {
    async callTool(name, args, signal) {
      log.push({ name, args });
      return respond(name, args, signal);
    },
  };
  return { client, log };
}

function makeBinding(
  client: ExecutiveToolClient,
  config: LaunchBindingConfig = RESEARCH_CONFIG,
  store: PendingPointerStore = makeStore(),
  session: OrchestratorSessionPresentation | null = SESSION,
) {
  return createExecutiveLaunchBinding(config, client, {
    context: () => ({ principalScope: PRINCIPAL, generation: GENERATION }),
    store,
    getSession: () => session,
    subscribe: () => () => {},
  });
}

function expectedResearchPayload(form: LaunchForm = RESEARCH_FORM) {
  return {
    operation_key: operationKeyForLaunch({
      principalScope: PRINCIPAL,
      workstream: WORKSTREAM,
      department: form.projectRef,
      execution_profile: form.profileRef,
      objective: form.goal,
      priority: 0,
    }),
    objective: form.goal,
    department: form.projectRef,
    priority: 0,
    execution_profile: form.profileRef,
    workstream: WORKSTREAM,
  };
}

describe("T3 makeLaunchIntent", () => {
  const idle = makeClient(() => ({ ok: false, error: { code: "not_found" } }));
  const binding = makeBinding(idle.client);

  it("returns null for each §4 refusal", () => {
    const refusals: LaunchForm[] = [
      { ...RESEARCH_FORM, goal: "" },
      { ...RESEARCH_FORM, goal: "x".repeat(4001) },
      { ...RESEARCH_FORM, projectRef: "Research" },
      { ...RESEARCH_FORM, projectRef: "unknown" },
      { ...RESEARCH_FORM, profileRef: "open_pr" },
      { ...RESEARCH_FORM, profileRef: "bounded_code_change" },
    ];
    for (const form of refusals) {
      expect(binding.makeLaunchIntent(form)).toBeNull();
    }

    const unavailableProject = makeBinding(idle.client, {
      ...RESEARCH_CONFIG,
      projects: [
        { ref: "research", label: "Research", unavailableReason: "offline" },
      ],
    });
    expect(unavailableProject.makeLaunchIntent(RESEARCH_FORM)).toBeNull();

    const unavailableProfile = makeBinding(idle.client, {
      ...RESEARCH_CONFIG,
      profiles: [
        { ref: "research_only", label: "Research only", unavailableReason: "offline" },
      ],
    });
    expect(unavailableProfile.makeLaunchIntent(RESEARCH_FORM)).toBeNull();

    const researchWithWrites = makeBinding(idle.client, {
      ...RESEARCH_CONFIG,
      allowedWritePaths: ["src/example.ts"],
    });
    expect(researchWithWrites.makeLaunchIntent(RESEARCH_FORM)).toBeNull();

    const researchWithValidation = makeBinding(idle.client, {
      ...RESEARCH_CONFIG,
      validation: { git_diff_check: true },
    });
    expect(researchWithValidation.makeLaunchIntent(RESEARCH_FORM)).toBeNull();

    const boundedForm: LaunchForm = {
      ...RESEARCH_FORM,
      profileRef: "bounded_code_change",
    };
    expect(binding.makeLaunchIntent(boundedForm)).toBeNull();
    expect(
      makeBinding(idle.client, {
        ...RESEARCH_CONFIG,
        allowedWritePaths: ["src/example.ts"],
      }).makeLaunchIntent(boundedForm),
    ).toBeNull();
    expect(
      makeBinding(idle.client, {
        ...RESEARCH_CONFIG,
        validation: { git_diff_check: true },
      }).makeLaunchIntent(boundedForm),
    ).toBeNull();
  });

  it("returns the exact launch payload on the happy path", () => {
    const intent = binding.makeLaunchIntent(RESEARCH_FORM);
    expect(intent).toEqual({
      kind: "launch",
      targetKey: WORKSTREAM,
      payload: expectedResearchPayload(),
    });

    const boundedForm: LaunchForm = {
      ...RESEARCH_FORM,
      profileRef: "bounded_code_change",
    };
    const bounded = makeBinding(idle.client, BOUNDED_CONFIG).makeLaunchIntent(
      boundedForm,
    );
    expect(bounded).toEqual({
      kind: "launch",
      targetKey: WORKSTREAM,
      payload: {
        operation_key: operationKeyForLaunch({
          principalScope: PRINCIPAL,
          workstream: WORKSTREAM,
          department: boundedForm.projectRef,
          execution_profile: "bounded_code_change",
          objective: boundedForm.goal,
          priority: 0,
          allowed_write_paths: BOUNDED_CONFIG.allowedWritePaths,
          validation: BOUNDED_CONFIG.validation,
          attempt_limit: 2,
        }),
        objective: boundedForm.goal,
        department: boundedForm.projectRef,
        priority: 0,
        execution_profile: "bounded_code_change",
        workstream: WORKSTREAM,
        allowed_write_paths: ["src/example.ts"],
        validation: {
          pytest_targets: ["tests/test_example.py"],
          git_diff_check: true,
        },
        attempt_limit: 2,
      },
    });
  });

  it("maps a throwing prepare to MALFORMED_POINTER on the controller", async () => {
    const ctrl = new OperationController(binding.port, makeStore());
    const result = await ctrl.begin({
      kind: "launch",
      targetKey: null,
      payload: { bogus: true },
    });
    expect(result.status).toBe("idle");
    expect(result.reason).toBe("MALFORMED_POINTER");
  });
});

describe("T4 submit matrix", () => {
  async function submitWith(
    envelope: ExecutiveToolEnvelope | "throw",
    extra?: { abort?: boolean },
  ) {
    const respond = async () => {
      if (envelope === "throw") throw new Error("client failed");
      return envelope;
    };
    const { client } = makeClient(respond);
    const binding = makeBinding(client);
    const intent = binding.makeLaunchIntent(RESEARCH_FORM);
    if (!intent) throw new Error("expected launch intent");
    const pointer = binding.port.prepare(intent);
    const abort = new AbortController();
    if (extra?.abort) abort.abort();
    return binding.port.submit(pointer, intent, abort.signal);
  }

  const refusedInvalidPayload = ["invalid_input"] as const;
  const refused = [
    "authority_refused",
    "backend_refused",
    "production_write_disabled",
    "identity_unverified",
    "grounding_unavailable",
    "grounding_changed",
  ] as const;
  const unknownReceipt = [
    "not_found",
    "backend_unavailable",
    "internal_error",
    "output_too_large",
  ] as const;
  const transport = ["timeout"] as const;
  const researchKey = expectedResearchPayload().operation_key;

  it.each(refusedInvalidPayload)("%s → refused/INVALID_PAYLOAD", async (code) => {
    const receipt = await submitWith({ ok: false, error: { code } });
    expect(receipt).toMatchObject({
      disposition: "refused",
      reason: "INVALID_PAYLOAD",
      kind: "launch",
      targetKey: WORKSTREAM,
    });
    expect(receipt.missionSelection).toBeUndefined();
  });

  it.each(refused)("%s → refused/REFUSED", async (code) => {
    const receipt = await submitWith({ ok: false, error: { code } });
    expect(receipt).toMatchObject({
      disposition: "refused",
      reason: "REFUSED",
      kind: "launch",
      targetKey: WORKSTREAM,
    });
    expect(receipt.missionSelection).toBeUndefined();
  });

  it.each(unknownReceipt)("%s → unknown/UNKNOWN_RECEIPT", async (code) => {
    const receipt = await submitWith({ ok: false, error: { code } });
    expect(receipt).toMatchObject({
      disposition: "unknown",
      reason: "UNKNOWN_RECEIPT",
      kind: "launch",
      targetKey: WORKSTREAM,
    });
  });

  it.each(transport)("%s → unknown/TRANSPORT_ERROR", async (code) => {
    const receipt = await submitWith({ ok: false, error: { code } });
    expect(receipt).toMatchObject({
      disposition: "unknown",
      reason: "TRANSPORT_ERROR",
      kind: "launch",
      targetKey: WORKSTREAM,
    });
  });

  it("unrecognised code → unknown/TRANSPORT_ERROR", async () => {
    const receipt = await submitWith({
      ok: false,
      error: { code: "not_a_gateway_code" },
    });
    expect(receipt).toMatchObject({
      disposition: "unknown",
      reason: "TRANSPORT_ERROR",
    });
  });

  it("thrown client error → unknown/TRANSPORT_ERROR", async () => {
    const receipt = await submitWith("throw");
    expect(receipt).toMatchObject({
      disposition: "unknown",
      reason: "TRANSPORT_ERROR",
    });
  });

  it("aborted signal → unknown/TRANSPORT_ERROR", async () => {
    const receipt = await submitWith(
      { ok: true, data: acceptedData(researchKey) },
      { abort: true },
    );
    expect(receipt).toMatchObject({
      disposition: "unknown",
      reason: "TRANSPORT_ERROR",
    });
  });

  it.each([false, true])(
    "accepted duplicate=%s → accepted/ACCEPTED with JOB-001",
    async (duplicate) => {
      const receipt = await submitWith({
        ok: true,
        data: acceptedData(researchKey, { duplicate }),
      });
      expect(receipt).toEqual({
        operationKey: researchKey,
        kind: "launch",
        targetKey: WORKSTREAM,
        disposition: "accepted",
        reason: "ACCEPTED",
        missionSelection: { workRef: WORKSTREAM, rootJobId: JOB_ID },
      });
    },
  );

  it("accepted v2 schema is still accepted", async () => {
    const receipt = await submitWith({
      ok: true,
      data: acceptedData(researchKey, {
        schema: "mastermind.ceo_intent_receipt.v2",
      }),
    });
    expect(receipt.disposition).toBe("accepted");
    expect(receipt.missionSelection).toEqual({
      workRef: WORKSTREAM,
      rootJobId: JOB_ID,
    });
  });

  it("ok-but-malformed receipt → unknown/MALFORMED_RECEIPT", async () => {
    const malformed: ExecutiveToolEnvelope[] = [
      { ok: true, data: null },
      { ok: true, data: acceptedData(researchKey, { schema: "nope" }) },
      { ok: true, data: acceptedData(researchKey, { accepted: false }) },
      { ok: true, data: acceptedData(researchKey, { dispatched: true }) },
      { ok: true, data: acceptedData(researchKey, { job_id: undefined }) },
    ];
    for (const envelope of malformed) {
      const receipt = await submitWith(envelope);
      expect(receipt).toMatchObject({
        disposition: "unknown",
        reason: "MALFORMED_RECEIPT",
        kind: "launch",
        targetKey: WORKSTREAM,
      });
    }
  });

  it("job_id that fails job() → unknown/UNKNOWN_RECEIPT", async () => {
    const receipt = await submitWith({
      ok: true,
      data: acceptedData(researchKey, { job_id: "not-a-job" }),
    });
    expect(receipt).toMatchObject({
      disposition: "unknown",
      reason: "UNKNOWN_RECEIPT",
    });
  });
});

describe("T5 readOperation", () => {
  async function readWith(envelope: ExecutiveToolEnvelope) {
    const { client, log } = makeClient(() => envelope);
    const binding = makeBinding(client);
    const intent = binding.makeLaunchIntent(RESEARCH_FORM);
    if (!intent) throw new Error("expected launch intent");
    const pointer = binding.port.prepare(intent);
    const receipt = await binding.port.readOperation(
      pointer,
      new AbortController().signal,
    );
    return { receipt, log, pointer };
  }

  it("accepted → missionSelection.workRef from pointer.targetKey", async () => {
    const key = expectedResearchPayload().operation_key;
    const { receipt, log, pointer } = await readWith({
      ok: true,
      data: acceptedData(key),
    });
    expect(pointer.targetKey).toBe(WORKSTREAM);
    expect(receipt).toEqual({
      operationKey: pointer.operationKey,
      kind: "launch",
      targetKey: WORKSTREAM,
      disposition: "accepted",
      reason: "ACCEPTED",
      missionSelection: { workRef: pointer.targetKey, rootJobId: JOB_ID },
    });
    expect(log).toHaveLength(1);
    expect(log[0]?.name).toBe("ceo_intent_status");
    expect(log[0]?.args).toHaveProperty("intent_id");
    expect(String(log[0]?.args.intent_id)).toBe(
      intentIdForOperationKey(pointer.operationKey),
    );
  });

  it("not_found → unknown/UNKNOWN_RECEIPT", async () => {
    const { receipt } = await readWith({
      ok: false,
      error: { code: "not_found" },
    });
    expect(receipt).toMatchObject({
      disposition: "unknown",
      reason: "UNKNOWN_RECEIPT",
    });
    expect(receipt.disposition).not.toBe("refused");
  });

  it("unknown codes are retained as unknown", async () => {
    for (const code of [
      "invalid_input",
      "authority_refused",
      "identity_unverified",
      "backend_refused",
      "production_write_disabled",
      "grounding_unavailable",
      "grounding_changed",
      "backend_unavailable",
      "internal_error",
      "output_too_large",
    ] as const) {
      const { receipt } = await readWith({ ok: false, error: { code } });
      expect(receipt).toMatchObject({
        disposition: "unknown",
        reason: "UNKNOWN_RECEIPT",
      });
    }
  });
});

describe("T6 SEND/STOP", () => {
  it("returns null intents and presents COMMAND_ROUTE_UNAVAILABLE", () => {
    const { client } = makeClient(() => ({
      ok: false,
      error: { code: "not_found" },
    }));
    const binding = makeBinding(client);
    expect(binding.makeMessageIntent("sess-1", "hello")).toBeNull();
    expect(binding.makeStopIntent("sess-1")).toBeNull();
    const view = binding.getView();
    expect(view.session?.unavailableReason).toBe(COMMAND_ROUTE_UNAVAILABLE);
    expect(view.session?.turnBusy).toBe(false);
    expect(view.session?.stopLabel).toBeUndefined();
  });
});

describe("T7 completeOrchestratorCommandBinding", () => {
  it("returns non-null for createExecutiveLaunchBinding", () => {
    const { client } = makeClient(() => ({
      ok: false,
      error: { code: "not_found" },
    }));
    const binding = makeBinding(client);
    expect(completeOrchestratorCommandBinding(binding)).not.toBeNull();
  });
});

describe("T8 controller integration", () => {
  it("accepts a launch and recovers the same rootJobId without a second submit", async () => {
    const researchKey = expectedResearchPayload().operation_key;
    const { client, log } = makeClient((name) => {
      if (name === "submit_ceo_intent" || name === "ceo_intent_status") {
        return { ok: true, data: acceptedData(researchKey) };
      }
      return { ok: false, error: { code: "not_found" } };
    });
    const store = makeStore();
    const binding = makeBinding(client, RESEARCH_CONFIG, store);
    const intent = binding.makeLaunchIntent(RESEARCH_FORM);
    expect(intent).not.toBeNull();
    const pointer = binding.port.prepare(intent as CommandIntent);

    const ctrl = new OperationController(binding.port, store);
    const first = await ctrl.begin(intent as CommandIntent);
    expect(first.status).toBe("accepted");
    expect(first).toMatchObject({
      reason: "ACCEPTED",
      missionSelection: { workRef: WORKSTREAM, rootJobId: JOB_ID },
    });
    expect(log.filter((entry) => entry.name === "submit_ceo_intent")).toHaveLength(
      1,
    );

    const reopenedStore = makeStore([[PRINCIPAL, pointer]]);
    const reopened = new OperationController(binding.port, reopenedStore);
    const recovered = await reopened.recover();
    expect(recovered.status).toBe("accepted");
    expect(recovered).toMatchObject({
      reason: "ACCEPTED",
      missionSelection: { workRef: WORKSTREAM, rootJobId: JOB_ID },
    });
    expect(log.filter((entry) => entry.name === "submit_ceo_intent")).toHaveLength(
      1,
    );
    expect(log.filter((entry) => entry.name === "ceo_intent_status")).toHaveLength(
      1,
    );
  });
});

const STATUS_CODE_REASONS = [
  ["invalid_input", "UNKNOWN_RECEIPT"],
  ["authority_refused", "UNKNOWN_RECEIPT"],
  ["identity_unverified", "UNKNOWN_RECEIPT"],
  ["backend_refused", "UNKNOWN_RECEIPT"],
  ["production_write_disabled", "UNKNOWN_RECEIPT"],
  ["grounding_unavailable", "UNKNOWN_RECEIPT"],
  ["grounding_changed", "UNKNOWN_RECEIPT"],
  ["not_found", "UNKNOWN_RECEIPT"],
  ["backend_unavailable", "UNKNOWN_RECEIPT"],
  ["internal_error", "UNKNOWN_RECEIPT"],
  ["output_too_large", "UNKNOWN_RECEIPT"],
  ["timeout", "TRANSPORT_ERROR"],
] as const;

describe("T9 late original completion retains the pointer", () => {
  it("T9 timeout then not_found keeps PENDING_POINTER; later JOB-001 is accepted", async () => {
    const researchKey = expectedResearchPayload().operation_key;
    let statusEnvelope: ExecutiveToolEnvelope = {
      ok: false,
      error: { code: "not_found" },
    };
    const { client, log } = makeClient((name) => {
      if (name === "submit_ceo_intent") {
        return { ok: false, error: { code: "timeout" } };
      }
      return statusEnvelope;
    });
    const store = makeStore();
    const binding = makeBinding(client, RESEARCH_CONFIG, store);
    const intent = binding.makeLaunchIntent(RESEARCH_FORM);
    if (!intent) throw new Error("expected launch intent");
    const pointer = binding.port.prepare(intent);

    const ctrl = new OperationController(binding.port, store);
    const timedOut = await ctrl.begin(intent);
    expect(timedOut.status).toBe("unknown");
    expect(store.read(PRINCIPAL)).toEqual(pointer);

    const rec1 = await ctrl.recover();
    expect(rec1.status).toBe("unknown");
    expect(rec1.reason).toBe("UNKNOWN_RECEIPT");
    expect(store.read(PRINCIPAL)).toEqual(pointer);

    const retry = await ctrl.begin(intent);
    expect(retry.status).toBe("checking");
    expect(retry.reason).toBe("PENDING_POINTER");
    expect(log.filter((entry) => entry.name === "submit_ceo_intent")).toHaveLength(
      1,
    );

    statusEnvelope = { ok: true, data: acceptedData(researchKey) };
    const rec2 = await ctrl.recover();
    expect(rec2.status).toBe("accepted");
    expect(rec2).toMatchObject({
      reason: "ACCEPTED",
      missionSelection: { workRef: WORKSTREAM, rootJobId: JOB_ID },
    });
    expect(log.filter((entry) => entry.name === "submit_ceo_intent")).toHaveLength(
      1,
    );
  });
});

describe("T10 status-read refusal retains the pointer", () => {
  it.each(STATUS_CODE_REASONS)(
    "T10 %s → unknown/%s, pointer retained, next submit PENDING_POINTER",
    async (code, reason) => {
      const { client, log } = makeClient((name) => {
        if (name === "ceo_intent_status") {
          return { ok: false, error: { code } };
        }
        return { ok: false, error: { code: "timeout" } };
      });
      const store = makeStore();
      const binding = makeBinding(client, RESEARCH_CONFIG, store);
      const intent = binding.makeLaunchIntent(RESEARCH_FORM);
      if (!intent) throw new Error("expected launch intent");
      const pointer = binding.port.prepare(intent);

      const portReceipt = await binding.port.readOperation(
        pointer,
        new AbortController().signal,
      );
      expect(portReceipt.disposition).toBe("unknown");
      expect(portReceipt.reason).toBe(reason);
      expect(portReceipt.disposition).not.toBe("refused");

      store.write(PRINCIPAL, pointer);
      const ctrl = new OperationController(binding.port, store);
      const recovered = await ctrl.recover();
      expect(recovered.status).toBe("unknown");
      expect(store.read(PRINCIPAL)).toEqual(pointer);

      const retry = await ctrl.begin(intent);
      expect(retry.reason).toBe("PENDING_POINTER");
      expect(
        log.filter((entry) => entry.name === "submit_ceo_intent"),
      ).toHaveLength(0);
    },
  );
});

describe("T11 same-principal A→B reopen reconstructs workRef from the pointer", () => {
  const WS_A = "WS:A";
  const WS_B = "WS:B";

  it("T11 launch stores pointer.targetKey as the original workstream", async () => {
    const { client } = makeClient(() => ({
      ok: false,
      error: { code: "timeout" },
    }));
    const store = makeStore();
    const binding = makeBinding(client, RESEARCH_CONFIG, store);
    const intent = binding.makeLaunchIntent(RESEARCH_FORM);
    if (!intent) throw new Error("expected launch intent");
    expect(intent.targetKey).toBe(WORKSTREAM);
    const pointer = binding.port.prepare(intent);
    expect(pointer).toEqual({
      operationKey: expectedResearchPayload().operation_key,
      kind: "launch",
      targetKey: WORKSTREAM,
    });
    const ctrl = new OperationController(binding.port, store);
    await ctrl.begin(intent);
    expect(store.read(PRINCIPAL)).toEqual(pointer);
    expect(store.read(PRINCIPAL)?.targetKey).toBe(WORKSTREAM);
  });

  it("T11 recover under WS:B keeps workRef WS:A and selectionMatches is false", async () => {
    const keyA = operationKeyForLaunch({
      principalScope: PRINCIPAL,
      workstream: WS_A,
      department: RESEARCH_FORM.projectRef,
      execution_profile: RESEARCH_FORM.profileRef,
      objective: RESEARCH_FORM.goal,
      priority: 0,
    });
    const pointerA: OperationPointer = {
      operationKey: keyA,
      kind: "launch",
      targetKey: WS_A,
    };
    const { client } = makeClient((name) => {
      if (name === "ceo_intent_status") {
        return { ok: true, data: acceptedData(keyA) };
      }
      return { ok: false, error: { code: "not_found" } };
    });
    const store = makeStore([[PRINCIPAL, pointerA]]);
    const configB: LaunchBindingConfig = { ...RESEARCH_CONFIG, workstream: WS_B };
    const bindingB = makeBinding(client, configB, store);
    const ctrlB = new OperationController(bindingB.port, store);
    const recovered = await ctrlB.recover();
    expect(recovered.status).toBe("accepted");
    expect(recovered).toMatchObject({
      reason: "ACCEPTED",
      missionSelection: { workRef: WS_A, rootJobId: JOB_ID },
    });
    expect(
      sessionMatchesSelection(
        { ...SESSION, selection: { workRef: WS_A, rootJobId: JOB_ID } },
        { workRef: WS_B, rootJobId: JOB_ID },
      ),
    ).toBe(false);
  });

  it("T11 stored pointer with targetKey null → unknown/MALFORMED_POINTER retained", async () => {
    const key = expectedResearchPayload().operation_key;
    const pointer: OperationPointer = {
      operationKey: key,
      kind: "launch",
      targetKey: null,
    };
    const { client } = makeClient(() => ({
      ok: true,
      data: acceptedData(key),
    }));
    const store = makeStore([[PRINCIPAL, pointer]]);
    const binding = makeBinding(client, RESEARCH_CONFIG, store);
    const portReceipt = await binding.port.readOperation(
      pointer,
      new AbortController().signal,
    );
    expect(portReceipt).toMatchObject({
      disposition: "unknown",
      reason: "MALFORMED_POINTER",
    });
    const ctrl = new OperationController(binding.port, store);
    const recovered = await ctrl.recover();
    expect(recovered.status).toBe("unknown");
    expect(store.read(PRINCIPAL)).toEqual(pointer);
  });

  it("T11 prepare of targetKey ≠ payload.workstream throws", () => {
    const { client } = makeClient(() => ({
      ok: false,
      error: { code: "not_found" },
    }));
    const binding = makeBinding(client);
    const intent = binding.makeLaunchIntent(RESEARCH_FORM);
    if (!intent) throw new Error("expected launch intent");
    expect(() =>
      binding.port.prepare({ ...intent, targetKey: WS_B }),
    ).toThrow("INVALID_PAYLOAD");
  });
});

describe("T12 receipt intent_id authentication", () => {
  const PINNED_KEY = "mmos-launch-0000000000000000000000000000000000000000";
  const PINNED_INTENT_ID = "mcp-bc363e20e05f2ba03efc9af32fe8f80d";
  const FOREIGN_INTENT_ID = intentIdForOperationKey(
    "mmos-launch-ffffffffffffffffffffffffffffffffffffffff",
  );

  it("T12 submit foreign intent_id → unknown/RECEIPT_MISMATCH, never AcceptedState", async () => {
    const researchKey = expectedResearchPayload().operation_key;
    const { client } = makeClient(() => ({
      ok: true,
      data: acceptedData(researchKey, { intent_id: FOREIGN_INTENT_ID }),
    }));
    const store = makeStore();
    const binding = makeBinding(client, RESEARCH_CONFIG, store);
    const intent = binding.makeLaunchIntent(RESEARCH_FORM);
    if (!intent) throw new Error("expected launch intent");
    const pointer = binding.port.prepare(intent);

    const portReceipt = await binding.port.submit(
      pointer,
      intent,
      new AbortController().signal,
    );
    expect(portReceipt).toMatchObject({
      disposition: "unknown",
      reason: "RECEIPT_MISMATCH",
    });

    const ctrl = new OperationController(binding.port, store);
    const state = await ctrl.begin(intent);
    expect(state.status).toBe("unknown");
    expect(state.status).not.toBe("accepted");
    expect(store.read(PRINCIPAL)).toEqual(pointer);
  });

  it("T12 submit missing intent_id → unknown/MALFORMED_RECEIPT, never AcceptedState", async () => {
    const researchKey = expectedResearchPayload().operation_key;
    const data = { ...acceptedData(researchKey) };
    delete data.intent_id;
    const { client } = makeClient(() => ({ ok: true, data }));
    const store = makeStore();
    const binding = makeBinding(client, RESEARCH_CONFIG, store);
    const intent = binding.makeLaunchIntent(RESEARCH_FORM);
    if (!intent) throw new Error("expected launch intent");
    const pointer = binding.port.prepare(intent);

    const portReceipt = await binding.port.submit(
      pointer,
      intent,
      new AbortController().signal,
    );
    expect(portReceipt).toMatchObject({
      disposition: "unknown",
      reason: "MALFORMED_RECEIPT",
    });

    const ctrl = new OperationController(binding.port, store);
    const state = await ctrl.begin(intent);
    expect(state.status).toBe("unknown");
    expect(state.status).not.toBe("accepted");
    expect(store.read(PRINCIPAL)).toEqual(pointer);
  });

  it("T12 status foreign intent_id via recover → unknown/RECEIPT_MISMATCH, pointer retained", async () => {
    const researchKey = expectedResearchPayload().operation_key;
    const { client } = makeClient((name) => {
      if (name === "ceo_intent_status") {
        return {
          ok: true,
          data: acceptedData(researchKey, { intent_id: FOREIGN_INTENT_ID }),
        };
      }
      return { ok: false, error: { code: "timeout" } };
    });
    const binding = makeBinding(client);
    const intent = binding.makeLaunchIntent(RESEARCH_FORM);
    if (!intent) throw new Error("expected launch intent");
    const pointer = binding.port.prepare(intent);

    const portReceipt = await binding.port.readOperation(
      pointer,
      new AbortController().signal,
    );
    expect(portReceipt).toMatchObject({
      disposition: "unknown",
      reason: "RECEIPT_MISMATCH",
    });

    const store = makeStore([[PRINCIPAL, pointer]]);
    const recoverBinding = makeBinding(client, RESEARCH_CONFIG, store);
    const ctrl = new OperationController(recoverBinding.port, store);
    const recovered = await ctrl.recover();
    expect(recovered.status).toBe("unknown");
    expect(recovered.status).not.toBe("accepted");
    expect(store.read(PRINCIPAL)).toEqual(pointer);
  });

  it("T12 status missing intent_id via recover → unknown/MALFORMED_RECEIPT, pointer retained", async () => {
    const researchKey = expectedResearchPayload().operation_key;
    const data = { ...acceptedData(researchKey) };
    delete data.intent_id;
    const { client } = makeClient((name) => {
      if (name === "ceo_intent_status") {
        return { ok: true, data };
      }
      return { ok: false, error: { code: "timeout" } };
    });
    const binding = makeBinding(client);
    const intent = binding.makeLaunchIntent(RESEARCH_FORM);
    if (!intent) throw new Error("expected launch intent");
    const pointer = binding.port.prepare(intent);

    const portReceipt = await binding.port.readOperation(
      pointer,
      new AbortController().signal,
    );
    expect(portReceipt).toMatchObject({
      disposition: "unknown",
      reason: "MALFORMED_RECEIPT",
    });

    const store = makeStore([[PRINCIPAL, pointer]]);
    const recoverBinding = makeBinding(client, RESEARCH_CONFIG, store);
    const ctrl = new OperationController(recoverBinding.port, store);
    const recovered = await ctrl.recover();
    expect(recovered.status).toBe("unknown");
    expect(recovered.status).not.toBe("accepted");
    expect(store.read(PRINCIPAL)).toEqual(pointer);
  });

  it("T12 pinned vector key with mcp-bc363e20e05f2ba03efc9af32fe8f80d is accepted", async () => {
    expect(intentIdForOperationKey(PINNED_KEY)).toBe(PINNED_INTENT_ID);
    const pointer: OperationPointer = {
      operationKey: PINNED_KEY,
      kind: "launch",
      targetKey: WORKSTREAM,
    };
    const intent: CommandIntent = {
      kind: "launch",
      targetKey: WORKSTREAM,
      payload: { operation_key: PINNED_KEY, workstream: WORKSTREAM },
    };
    const { client } = makeClient(() => ({
      ok: true,
      data: acceptedData(PINNED_KEY, { intent_id: PINNED_INTENT_ID }),
    }));
    const binding = makeBinding(client);
    const submitted = await binding.port.submit(
      pointer,
      intent,
      new AbortController().signal,
    );
    expect(submitted).toMatchObject({
      disposition: "accepted",
      reason: "ACCEPTED",
      missionSelection: { workRef: WORKSTREAM, rootJobId: JOB_ID },
    });
    const status = await binding.port.readOperation(
      pointer,
      new AbortController().signal,
    );
    expect(status.disposition).toBe("accepted");

    const store = makeStore([[PRINCIPAL, pointer]]);
    const recoverBinding = makeBinding(client, RESEARCH_CONFIG, store);
    const ctrl = new OperationController(recoverBinding.port, store);
    const recovered = await ctrl.recover();
    expect(recovered.status).toBe("accepted");
    expect(recovered).toMatchObject({
      missionSelection: { workRef: WORKSTREAM, rootJobId: JOB_ID },
    });
  });
});

