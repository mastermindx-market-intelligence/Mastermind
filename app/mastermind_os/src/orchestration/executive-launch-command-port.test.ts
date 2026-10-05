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
import {
  intentIdForOperationKey,
  operationKeyForLaunch,
  requestRefForOperationKey,
} from "./operation-key";
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
const PINNED_KEY = "mmos-launch-" + "0".repeat(40);
const PINNED_INTENT_ID = "auto-ed35746b0a835165994569a8dc713270";

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

const SUBMIT_CODE_TABLE = [
  ["invalid_input", "refused", "INVALID_PAYLOAD"],
  ["authority_refused", "refused", "REFUSED"],
  ["production_write_disabled", "refused", "REFUSED"],
  ["identity_unverified", "refused", "REFUSED"],
  ["grounding_unavailable", "refused", "REFUSED"],
  ["grounding_changed", "refused", "REFUSED"],
  ["backend_refused", "unknown", "UNKNOWN_RECEIPT"],
  ["not_found", "unknown", "UNKNOWN_RECEIPT"],
  ["backend_unavailable", "unknown", "UNKNOWN_RECEIPT"],
  ["internal_error", "unknown", "UNKNOWN_RECEIPT"],
  ["output_too_large", "unknown", "UNKNOWN_RECEIPT"],
  ["timeout", "unknown", "TRANSPORT_ERROR"],
] as const;

const NON_TERMINAL_STATUSES = [
  "operation_conflict",
  "ingress_unavailable",
  "effect_unknown",
] as const;

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

const STATUS_UNKNOWN_CODES = [
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
] as const;

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
      requested: [],
      policy_sha256: "a".repeat(64),
      authority_level: "A0",
    },
    grounding: {},
    created_at_ms: 0,
    ...extra,
  };
}

function appAccepted(
  operationKey: string,
  extra: Record<string, unknown> = {},
): ExecutiveToolEnvelope {
  return {
    ok: true,
    status: "accepted",
    request_ref: requestRefForOperationKey(operationKey),
    receipt: acceptedData(operationKey, extra),
  };
}

function appRefused(
  operationKey: string,
  code: string,
  status:
    | "refused"
    | "operation_conflict"
    | "ingress_unavailable"
    | "effect_unknown" = "refused",
): ExecutiveToolEnvelope {
  return {
    ok: false,
    status,
    request_ref: requestRefForOperationKey(operationKey),
    error: { code, message: code },
  };
}

function barePreflight(code: string): ExecutiveToolEnvelope {
  return { ok: false, error: { code, message: code } };
}

function e1Envelope(
  tool: "submit_ceo_intent" | "ceo_intent_status",
  ok: boolean,
  data: unknown,
  error: { code: string; message: string; intent_id?: string } | null,
  serverVersion = "1.2.0",
): ExecutiveToolEnvelope {
  return {
    schema: "mastermind.executive_mcp_result.v1",
    tool,
    ok,
    server_version: serverVersion,
    mode: "readonly",
    generated_at: "2026-10-02T00:00:00Z",
    grounding: {},
    data,
    degraded: [],
    bounded: [],
    error,
  } as ExecutiveToolEnvelope;
}

function statusAccepted(
  operationKey: string,
  extra: Record<string, unknown> = {},
): ExecutiveToolEnvelope {
  return e1Envelope(
    "ceo_intent_status",
    true,
    acceptedData(operationKey, extra),
    null,
  );
}

function statusError(
  code: string,
  extra?: { intent_id?: string },
): ExecutiveToolEnvelope {
  const error: { code: string; message: string; intent_id?: string } = {
    code,
    message: code,
  };
  if (extra?.intent_id !== undefined) error.intent_id = extra.intent_id;
  return e1Envelope("ceo_intent_status", false, null, error);
}

function submitE1Error(
  code: string,
  extra?: { intent_id?: string },
): ExecutiveToolEnvelope {
  const error: { code: string; message: string; intent_id?: string } = {
    code,
    message: code,
  };
  if (extra?.intent_id !== undefined) error.intent_id = extra.intent_id;
  return e1Envelope("submit_ceo_intent", false, null, error);
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
  const idle = makeClient(() => barePreflight("not_found"));
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
    envelope: ExecutiveToolEnvelope | Record<string, unknown> | "throw",
    extra?: { abort?: boolean },
  ) {
    const respond = async () => {
      if (envelope === "throw") throw new Error("client failed");
      return envelope as ExecutiveToolEnvelope;
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

  const researchKey = expectedResearchPayload().operation_key;

  it.each(SUBMIT_CODE_TABLE)(
    "F3(b) %s → %s/%s",
    async (code, disposition, reason) => {
      const receipt = await submitWith(appRefused(researchKey, code));
      expect(receipt).toMatchObject({
        disposition,
        reason,
        kind: "launch",
        targetKey: WORKSTREAM,
      });
      expect(receipt.missionSelection).toBeUndefined();
    },
  );

  it("F3(b) unrecognised code → unknown/TRANSPORT_ERROR", async () => {
    const receipt = await submitWith(
      appRefused(researchKey, "not_a_gateway_code"),
    );
    expect(receipt).toMatchObject({
      disposition: "unknown",
      reason: "TRANSPORT_ERROR",
    });
  });

  it.each(NON_TERMINAL_STATUSES)(
    "F3(c) status %s → unknown/UNKNOWN_RECEIPT",
    async (status) => {
      const receipt = await submitWith(
        appRefused(researchKey, "invalid_input", status),
      );
      expect(receipt).toMatchObject({
        disposition: "unknown",
        reason: "UNKNOWN_RECEIPT",
      });
    },
  );

  it.each(SUBMIT_CODE_TABLE)(
    "F3(d) %s → %s/%s",
    async (code, disposition, reason) => {
      const receipt = await submitWith(barePreflight(code));
      expect(receipt).toMatchObject({
        disposition,
        reason,
        kind: "launch",
        targetKey: WORKSTREAM,
      });
      expect(receipt.missionSelection).toBeUndefined();
    },
  );

  it("F3(d) scope_refused → unknown/TRANSPORT_ERROR", async () => {
    const receipt = await submitWith(barePreflight("scope_refused"));
    expect(receipt).toMatchObject({
      disposition: "unknown",
      reason: "TRANSPORT_ERROR",
    });
  });

  it.each(SUBMIT_CODE_TABLE)(
    "F3(e) %s → %s/%s",
    async (code, disposition, reason) => {
      const receipt = await submitWith(submitE1Error(code));
      expect(receipt).toMatchObject({
        disposition,
        reason,
        kind: "launch",
        targetKey: WORKSTREAM,
      });
      expect(receipt.missionSelection).toBeUndefined();
    },
  );

  it("F3(e) error.intent_id foreign → unknown/RECEIPT_MISMATCH", async () => {
    const receipt = await submitWith(
      submitE1Error("invalid_input", {
        intent_id: intentIdForOperationKey(
          "mmos-launch-ffffffffffffffffffffffffffffffffffffffff",
        ),
      }),
    );
    expect(receipt).toMatchObject({
      disposition: "unknown",
      reason: "RECEIPT_MISMATCH",
    });
  });

  it("F3(e) error.intent_id matching authority_refused → refused/REFUSED", async () => {
    const receipt = await submitWith(
      submitE1Error("authority_refused", {
        intent_id: intentIdForOperationKey(researchKey),
      }),
    );
    expect(receipt).toMatchObject({
      disposition: "refused",
      reason: "REFUSED",
    });
  });

  it("F3(e) error.intent_id matching backend_refused → unknown/UNKNOWN_RECEIPT", async () => {
    const receipt = await submitWith(
      submitE1Error("backend_refused", {
        intent_id: intentIdForOperationKey(researchKey),
      }),
    );
    expect(receipt).toMatchObject({
      disposition: "unknown",
      reason: "UNKNOWN_RECEIPT",
    });
  });

  it("F3(e) unrecognised code → unknown/MALFORMED_RECEIPT", async () => {
    const receipt = await submitWith(submitE1Error("not_a_gateway_code"));
    expect(receipt).toMatchObject({
      disposition: "unknown",
      reason: "MALFORMED_RECEIPT",
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
    const receipt = await submitWith(appAccepted(researchKey), { abort: true });
    expect(receipt).toMatchObject({
      disposition: "unknown",
      reason: "TRANSPORT_ERROR",
    });
  });

  it.each([false, true])(
    "accepted duplicate=%s → accepted/ACCEPTED with JOB-001",
    async (duplicate) => {
      const receipt = await submitWith(
        appAccepted(researchKey, { duplicate }),
      );
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
    const receipt = await submitWith(
      appAccepted(researchKey, {
        schema: "mastermind.ceo_intent_receipt.v2",
      }),
    );
    expect(receipt.disposition).toBe("accepted");
    expect(receipt.missionSelection).toEqual({
      workRef: WORKSTREAM,
      rootJobId: JOB_ID,
    });
  });

  it("receipt intent_id foreign → unknown/RECEIPT_MISMATCH", async () => {
    const receipt = await submitWith(
      appAccepted(researchKey, {
        intent_id: intentIdForOperationKey(
          "mmos-launch-ffffffffffffffffffffffffffffffffffffffff",
        ),
      }),
    );
    expect(receipt).toMatchObject({
      disposition: "unknown",
      reason: "RECEIPT_MISMATCH",
    });
  });

  it("receipt intent_id missing → unknown/MALFORMED_RECEIPT", async () => {
    const doc = acceptedData(researchKey);
    delete doc.intent_id;
    const receipt = await submitWith({
      ok: true,
      status: "accepted",
      request_ref: requestRefForOperationKey(researchKey),
      receipt: doc,
    });
    expect(receipt).toMatchObject({
      disposition: "unknown",
      reason: "MALFORMED_RECEIPT",
    });
  });

  it("ok-but-malformed receipt → unknown/MALFORMED_RECEIPT", async () => {
    const malformed: ExecutiveToolEnvelope[] = [
      {
        ok: true,
        status: "accepted",
        request_ref: requestRefForOperationKey(researchKey),
        receipt: null,
      },
      appAccepted(researchKey, { schema: "nope" }),
      appAccepted(researchKey, { accepted: false }),
      appAccepted(researchKey, { dispatched: true }),
      appAccepted(researchKey, { job_id: undefined }),
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
    const receipt = await submitWith(
      appAccepted(researchKey, { job_id: "not-a-job" }),
    );
    expect(receipt).toMatchObject({
      disposition: "unknown",
      reason: "UNKNOWN_RECEIPT",
    });
  });
});

describe("T5 readOperation", () => {
  async function readWith(envelope: ExecutiveToolEnvelope | Record<string, unknown>) {
    const { client, log } = makeClient(() => envelope as ExecutiveToolEnvelope);
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
    const { receipt, log, pointer } = await readWith(statusAccepted(key));
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

  it("accepts the source-qualified V3 E1 version and rejects unqualified versions", async () => {
    const key = expectedResearchPayload().operation_key;
    const acceptedV3 = await readWith(
      e1Envelope("ceo_intent_status", true, acceptedData(key), null, "1.4.0"),
    );
    expect(acceptedV3.receipt).toMatchObject({
      disposition: "accepted",
      reason: "ACCEPTED",
      missionSelection: { workRef: WORKSTREAM, rootJobId: JOB_ID },
    });

    const unsupported = await readWith(
      e1Envelope("ceo_intent_status", true, acceptedData(key), null, "1.3.1"),
    );
    expect(unsupported.receipt).toMatchObject({
      disposition: "unknown",
      reason: "MALFORMED_RECEIPT",
    });
  });

  it("not_found → unknown/UNKNOWN_RECEIPT", async () => {
    const { receipt } = await readWith(statusError("not_found"));
    expect(receipt).toMatchObject({
      disposition: "unknown",
      reason: "UNKNOWN_RECEIPT",
    });
    expect(receipt.disposition).not.toBe("refused");
  });

  it("unknown codes are retained as unknown", async () => {
    for (const code of STATUS_UNKNOWN_CODES) {
      const { receipt } = await readWith(statusError(code));
      expect(receipt).toMatchObject({
        disposition: "unknown",
        reason: "UNKNOWN_RECEIPT",
      });
      expect(receipt.disposition).not.toBe("refused");
    }
  });

  it("timeout → unknown/TRANSPORT_ERROR", async () => {
    const { receipt } = await readWith(statusError("timeout"));
    expect(receipt).toMatchObject({
      disposition: "unknown",
      reason: "TRANSPORT_ERROR",
    });
    expect(receipt.disposition).not.toBe("refused");
  });

  it("unrecognised E1 code → unknown/MALFORMED_RECEIPT", async () => {
    const { receipt } = await readWith(statusError("not_a_gateway_code"));
    expect(receipt).toMatchObject({
      disposition: "unknown",
      reason: "MALFORMED_RECEIPT",
    });
  });

  it("foreign error.intent_id → unknown/RECEIPT_MISMATCH", async () => {
    const { receipt } = await readWith(
      statusError("not_found", {
        intent_id: intentIdForOperationKey(
          "mmos-launch-ffffffffffffffffffffffffffffffffffffffff",
        ),
      }),
    );
    expect(receipt).toMatchObject({
      disposition: "unknown",
      reason: "RECEIPT_MISMATCH",
    });
  });

  it("matching error.intent_id still maps the code row", async () => {
    const key = expectedResearchPayload().operation_key;
    const { receipt } = await readWith(
      statusError("not_found", { intent_id: intentIdForOperationKey(key) }),
    );
    expect(receipt).toMatchObject({
      disposition: "unknown",
      reason: "UNKNOWN_RECEIPT",
    });
  });
});

describe("T6 SEND/STOP", () => {
  it("returns null intents and presents COMMAND_ROUTE_UNAVAILABLE", () => {
    const { client } = makeClient(() => barePreflight("not_found"));
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
    const { client } = makeClient(() => barePreflight("not_found"));
    const binding = makeBinding(client);
    expect(completeOrchestratorCommandBinding(binding)).not.toBeNull();
  });
});

describe("T8 controller integration", () => {
  it("accepts a launch and recovers the same rootJobId without a second submit", async () => {
    const researchKey = expectedResearchPayload().operation_key;
    const { client, log } = makeClient((name) => {
      if (name === "submit_ceo_intent") return appAccepted(researchKey);
      if (name === "ceo_intent_status") return statusAccepted(researchKey);
      return statusError("not_found");
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

describe("T9 late original completion retains the pointer", () => {
  it("T9 timeout then not_found keeps PENDING_POINTER; later JOB-001 is accepted", async () => {
    const researchKey = expectedResearchPayload().operation_key;
    let statusEnvelope: ExecutiveToolEnvelope = statusError("not_found");
    const { client, log } = makeClient((name) => {
      if (name === "submit_ceo_intent") {
        return appRefused(researchKey, "timeout");
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

    statusEnvelope = statusAccepted(researchKey);
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
          return statusError(code);
        }
        return appRefused(expectedResearchPayload().operation_key, "timeout");
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
  const WS_A = "WS:PROJECT-A";
  const WS_B = "WS:PROJECT-B";

  it("T11 launch stores pointer.targetKey as the original workstream", async () => {
    const { client } = makeClient(() =>
      appRefused(expectedResearchPayload().operation_key, "timeout"),
    );
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
        return statusAccepted(keyA);
      }
      return statusError("not_found");
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
    const { client } = makeClient(() => statusAccepted(key));
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
    const { client } = makeClient(() => barePreflight("not_found"));
    const binding = makeBinding(client);
    const intent = binding.makeLaunchIntent(RESEARCH_FORM);
    if (!intent) throw new Error("expected launch intent");
    expect(() =>
      binding.port.prepare({ ...intent, targetKey: WS_B }),
    ).toThrow("INVALID_PAYLOAD");
  });
});

describe("T12 receipt intent_id authentication", () => {
  const FOREIGN_INTENT_ID = intentIdForOperationKey(
    "mmos-launch-ffffffffffffffffffffffffffffffffffffffff",
  );

  it("T12 submit foreign intent_id → unknown/RECEIPT_MISMATCH, never AcceptedState", async () => {
    const researchKey = expectedResearchPayload().operation_key;
    const { client } = makeClient(() =>
      appAccepted(researchKey, { intent_id: FOREIGN_INTENT_ID }),
    );
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
    const doc = { ...acceptedData(researchKey) };
    delete doc.intent_id;
    const { client } = makeClient(() => ({
      ok: true,
      status: "accepted",
      request_ref: requestRefForOperationKey(researchKey),
      receipt: doc,
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
        return statusAccepted(researchKey, { intent_id: FOREIGN_INTENT_ID });
      }
      return appRefused(researchKey, "timeout");
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
        return e1Envelope("ceo_intent_status", true, data, null);
      }
      return appRefused(researchKey, "timeout");
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

  it("T12 pinned vector key with auto-ed35746b0a835165994569a8dc713270 is accepted", async () => {
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
    const { client } = makeClient((name) => {
      if (name === "submit_ceo_intent") {
        return appAccepted(PINNED_KEY, { intent_id: PINNED_INTENT_ID });
      }
      return statusAccepted(PINNED_KEY, { intent_id: PINNED_INTENT_ID });
    });
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

describe("T13 sink-before-finalization regression + late authenticated recovery", () => {
  it("T13 backend_refused → unknown/UNKNOWN_RECEIPT, pointer retained; later JOB-001 accepted without a second submit", async () => {
    const researchKey = expectedResearchPayload().operation_key;
    let statusEnvelope: ExecutiveToolEnvelope = statusError("not_found");
    const { client, log } = makeClient((name) => {
      if (name === "submit_ceo_intent") {
        return appRefused(researchKey, "backend_refused");
      }
      return statusEnvelope;
    });
    const store = makeStore();
    const binding = makeBinding(client, RESEARCH_CONFIG, store);
    const intent = binding.makeLaunchIntent(RESEARCH_FORM);
    if (!intent) throw new Error("expected launch intent");
    const pointer = binding.port.prepare(intent);

    const ctrl = new OperationController(binding.port, store);
    const first = await ctrl.begin(intent);
    expect(first.status).toBe("unknown");
    expect(first.status).not.toBe("accepted");
    expect(store.read(PRINCIPAL)).toEqual(pointer);

    const retry = await ctrl.begin(intent);
    expect(retry.status).toBe("checking");
    expect(retry.reason).toBe("PENDING_POINTER");
    expect(store.read(PRINCIPAL)).toEqual(pointer);
    expect(log.filter((entry) => entry.name === "submit_ceo_intent")).toHaveLength(
      1,
    );

    statusEnvelope = statusAccepted(researchKey);
    const recovered = await ctrl.recover();
    expect(recovered.status).toBe("accepted");
    expect(recovered).toMatchObject({
      reason: "ACCEPTED",
      missionSelection: { workRef: WORKSTREAM, rootJobId: JOB_ID },
    });
    expect(log.filter((entry) => entry.name === "submit_ceo_intent")).toHaveLength(
      1,
    );
  });

  it("T13 authority_refused → refused/REFUSED (pointer-clearing); dispositions differ from backend_refused", async () => {
    const researchKey = expectedResearchPayload().operation_key;
    const { client: backendClient } = makeClient(() =>
      appRefused(researchKey, "backend_refused"),
    );
    const backendBinding = makeBinding(backendClient);
    const backendIntent = backendBinding.makeLaunchIntent(RESEARCH_FORM);
    if (!backendIntent) throw new Error("expected launch intent");
    const backendPointer = backendBinding.port.prepare(backendIntent);
    const backendReceipt = await backendBinding.port.submit(
      backendPointer,
      backendIntent,
      new AbortController().signal,
    );

    const store = makeStore();
    const { client } = makeClient(() =>
      appRefused(researchKey, "authority_refused"),
    );
    const binding = makeBinding(client, RESEARCH_CONFIG, store);
    const intent = binding.makeLaunchIntent(RESEARCH_FORM);
    if (!intent) throw new Error("expected launch intent");
    const pointer = binding.port.prepare(intent);
    const authorityReceipt = await binding.port.submit(
      pointer,
      intent,
      new AbortController().signal,
    );
    expect(authorityReceipt).toMatchObject({
      disposition: "refused",
      reason: "REFUSED",
    });
    expect(backendReceipt.disposition).toBe("unknown");
    expect(backendReceipt.reason).toBe("UNKNOWN_RECEIPT");
    expect(authorityReceipt.disposition).not.toBe(backendReceipt.disposition);

    const ctrl = new OperationController(binding.port, store);
    const state = await ctrl.begin(intent);
    expect(state.status).toBe("refused");
    expect(state.status).not.toBe("accepted");
    expect(store.read(PRINCIPAL)).toBeNull();
  });
});

describe("T14 App-outcome shape matrix", () => {
  async function submitWith(
    envelope: ExecutiveToolEnvelope | Record<string, unknown>,
  ) {
    const { client } = makeClient(() => envelope as ExecutiveToolEnvelope);
    const binding = makeBinding(client);
    const intent = binding.makeLaunchIntent(RESEARCH_FORM);
    if (!intent) throw new Error("expected launch intent");
    const pointer = binding.port.prepare(intent);
    return binding.port.submit(pointer, intent, new AbortController().signal);
  }

  async function readWith(
    envelope: ExecutiveToolEnvelope | Record<string, unknown>,
  ) {
    const { client } = makeClient(() => envelope as ExecutiveToolEnvelope);
    const binding = makeBinding(client);
    const intent = binding.makeLaunchIntent(RESEARCH_FORM);
    if (!intent) throw new Error("expected launch intent");
    const pointer = binding.port.prepare(intent);
    return binding.port.readOperation(pointer, new AbortController().signal);
  }

  const researchKey = expectedResearchPayload().operation_key;

  it("T14 request_ref missing → unknown/MALFORMED_RECEIPT", async () => {
    const receipt = await submitWith({
      ok: true,
      status: "accepted",
      receipt: acceptedData(researchKey),
    });
    expect(receipt).toMatchObject({
      disposition: "unknown",
      reason: "MALFORMED_RECEIPT",
    });
  });

  it("T14 request_ref ≠ requestRefForOperationKey → unknown/RECEIPT_MISMATCH", async () => {
    const receipt = await submitWith({
      ok: true,
      status: "accepted",
      request_ref: "req-deadbeefdeadbeefdeadbeefdeadbeef",
      receipt: acceptedData(researchKey),
    });
    expect(receipt).toMatchObject({
      disposition: "unknown",
      reason: "RECEIPT_MISMATCH",
    });
  });

  it("T14 extra top-level key → unknown/MALFORMED_RECEIPT", async () => {
    const receipt = await submitWith({
      ...appAccepted(researchKey),
      extra: true,
    });
    expect(receipt).toMatchObject({
      disposition: "unknown",
      reason: "MALFORMED_RECEIPT",
    });
  });

  it("T14 ok inconsistent with status → unknown/MALFORMED_RECEIPT", async () => {
    const receipt = await submitWith({
      ok: false,
      status: "accepted",
      request_ref: requestRefForOperationKey(researchKey),
      error: { code: "invalid_input", message: "invalid_input" },
    });
    expect(receipt).toMatchObject({
      disposition: "unknown",
      reason: "MALFORMED_RECEIPT",
    });
  });

  it("T14 accepted + error key → unknown/MALFORMED_RECEIPT", async () => {
    const receipt = await submitWith({
      ok: true,
      status: "accepted",
      request_ref: requestRefForOperationKey(researchKey),
      receipt: acceptedData(researchKey),
      error: { code: "invalid_input", message: "invalid_input" },
    });
    expect(receipt).toMatchObject({
      disposition: "unknown",
      reason: "MALFORMED_RECEIPT",
    });
  });

  it("T14 refused + receipt key → unknown/MALFORMED_RECEIPT", async () => {
    const receipt = await submitWith({
      ok: false,
      status: "refused",
      request_ref: requestRefForOperationKey(researchKey),
      error: { code: "authority_refused", message: "authority_refused" },
      receipt: acceptedData(researchKey),
    });
    expect(receipt).toMatchObject({
      disposition: "unknown",
      reason: "MALFORMED_RECEIPT",
    });
  });

  it("T14 legacy { ok: true, data } on submit → unknown/MALFORMED_RECEIPT", async () => {
    const receipt = await submitWith({
      ok: true,
      data: acceptedData(researchKey),
    });
    expect(receipt).toMatchObject({
      disposition: "unknown",
      reason: "MALFORMED_RECEIPT",
    });
  });

  it("T14 legacy { ok: true, data } on status → unknown/MALFORMED_RECEIPT", async () => {
    const receipt = await readWith({
      ok: true,
      data: acceptedData(researchKey),
    });
    expect(receipt).toMatchObject({
      disposition: "unknown",
      reason: "MALFORMED_RECEIPT",
    });
  });

  it("T14 bare { ok: false, error } on status → unknown/MALFORMED_RECEIPT", async () => {
    const receipt = await readWith(barePreflight("not_found"));
    expect(receipt).toMatchObject({
      disposition: "unknown",
      reason: "MALFORMED_RECEIPT",
    });
  });

  it("T14 ok not boolean → unknown/MALFORMED_RECEIPT", async () => {
    const receipt = await submitWith({
      ok: "true",
      status: "accepted",
      request_ref: requestRefForOperationKey(researchKey),
      receipt: acceptedData(researchKey),
    });
    expect(receipt).toMatchObject({
      disposition: "unknown",
      reason: "MALFORMED_RECEIPT",
    });
  });

  it("T14 receipt containing NaN → unknown/MALFORMED_RECEIPT", async () => {
    const receipt = await submitWith(
      appAccepted(researchKey, { created_at_ms: Number.NaN }),
    );
    expect(receipt).toMatchObject({
      disposition: "unknown",
      reason: "MALFORMED_RECEIPT",
    });
  });

  it("T14 data containing Infinity → unknown/MALFORMED_RECEIPT", async () => {
    const receipt = await readWith(
      statusAccepted(researchKey, { created_at_ms: Number.POSITIVE_INFINITY }),
    );
    expect(receipt).toMatchObject({
      disposition: "unknown",
      reason: "MALFORMED_RECEIPT",
    });
  });

  it("T14 cyclic envelope → unknown/MALFORMED_RECEIPT without throwing", async () => {
    const envelope: Record<string, unknown> = {
      ok: true,
      status: "accepted",
      request_ref: requestRefForOperationKey(researchKey),
      receipt: acceptedData(researchKey),
    };
    (envelope.receipt as Record<string, unknown>).cycle = envelope;
    let thrown: unknown;
    let receipt: Awaited<ReturnType<typeof submitWith>> | undefined;
    try {
      receipt = await submitWith(envelope);
    } catch (error) {
      thrown = error;
    }
    expect(thrown).toBeUndefined();
    expect(receipt).toMatchObject({
      disposition: "unknown",
      reason: "MALFORMED_RECEIPT",
    });
  });

  it("T14 shared acyclic object referenced twice is classified by content", async () => {
    const shared = { token: "shared" };
    const receipt = await submitWith(
      appAccepted(researchKey, {
        grounding: { left: shared, right: shared },
      }),
    );
    expect(receipt).toEqual({
      operationKey: researchKey,
      kind: "launch",
      targetKey: WORKSTREAM,
      disposition: "accepted",
      reason: "ACCEPTED",
      missionSelection: { workRef: WORKSTREAM, rootJobId: JOB_ID },
    });
  });

  it("T14 array nested 100000 levels deep → unknown/MALFORMED_RECEIPT without stack overflow", async () => {
    let deep: unknown = null;
    for (let i = 0; i < 100000; i += 1) {
      deep = [deep];
    }
    let thrown: unknown;
    let receipt: Awaited<ReturnType<typeof submitWith>> | undefined;
    try {
      receipt = await submitWith({
        ok: true,
        status: "accepted",
        request_ref: requestRefForOperationKey(researchKey),
        receipt: deep,
      });
    } catch (error) {
      thrown = error;
    }
    expect(thrown).toBeUndefined();
    expect(receipt).toMatchObject({
      disposition: "unknown",
      reason: "MALFORMED_RECEIPT",
    });
  });

  it("T14 Object.create({polluted: true}) prototype → unknown/MALFORMED_RECEIPT", async () => {
    const envelope = Object.create({ polluted: true }) as ExecutiveToolEnvelope;
    Object.assign(envelope, appAccepted(researchKey));
    const receipt = await submitWith(envelope);
    expect(receipt).toMatchObject({
      disposition: "unknown",
      reason: "MALFORMED_RECEIPT",
    });
  });
});
