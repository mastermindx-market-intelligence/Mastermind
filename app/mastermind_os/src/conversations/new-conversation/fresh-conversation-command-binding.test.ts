/**
 * Focused vitest coverage for the fresh conversation command binding.
 *
 * Fixtures: every non-vector frame below is explicitly SYNTHETIC and labelled
 * `unit`. The request/create_request/preview/create/read vectors are the
 * included ACTUAL owner-run source vectors (canonical 20-byte client key
 * minted before preview; a deterministic 20-byte stub in this harness
 * reproduces exactly that key, so the actual frames decode against the real
 * selectors). No live transport, no Runtime session and no signed status
 * canonical-key vector is fabricated here — that compatibility proof belongs
 * to the parent's own suite.
 *
 * The controller and decoder under test are the ACTUAL incumbent sources; the
 * pending-pointer store is an atomic, durable-shaped in-memory double that
 * never overwrites a reservation and clears only on an exact match.
 */

import { afterEach, describe, expect, it, vi, type Mock } from "vitest";

import { CONVERSATION_CREATE_KEY_PREFIX } from "../../orchestration/indexeddb-pending-pointer-store";
import type {
  CommandIntent,
  OperationPointer,
  OwnerContext,
  PendingPointerStore,
} from "../../orchestration/operation-controller";
import {
  decodeFreshConversationResult,
  type FreshConversationData,
} from "./fresh-conversation";
import {
  createFreshConversationBinding,
  FRESH_CONVERSATION_BINDING_CLOSED,
  sameConversationOwner,
  type FreshConversationBinding,
  type FreshConversationTransport,
} from "./fresh-conversation-command-binding";

// ── Actual source vectors (canonical key minted before preview) ──────────────

const GENUINE_WORK_REF = "WS:ONE";
const GENUINE_KEY = "mmos-conversation-create-0102030405060708090a0b0c0d0e0f1011121314";
const GENUINE_MESSAGE = "  新对话\nRead source.  ";

const GENUINE_REQUEST = {
  work_ref: GENUINE_WORK_REF,
  operation_key: GENUINE_KEY,
  message: GENUINE_MESSAGE,
} as const;

const GENUINE_CREATE_REQUEST = {
  ...GENUINE_REQUEST,
  preview_digest: "c0f93f2ce3a9800224631acd9a8fe0db1e1588c31ea26bea2222d83cdccdfa6d",
} as const;

const GENUINE_PREVIEW_FRAME: Record<string, unknown> = {
  schema: "mastermind.executive.fresh_conversation_result.v1",
  operation: "preview",
  ok: true,
  data: {
    schema: "mastermind.executive.fresh_conversation_data.v1",
    operation_key: GENUINE_KEY,
    work_ref: GENUINE_WORK_REF,
    state: "PREVIEW_READY",
    effect: "NONE",
    parent_consumed: false,
    preview: {
      digest: "c0f93f2ce3a9800224631acd9a8fe0db1e1588c31ea26bea2222d83cdccdfa6d",
      profile_digest: "ef9460d90e76c9f3842f55bfd0625fddaf4764e0da9742f3993ebb347dbc1dd8",
      source_digest: "996518188792d3c3ab31d4e9c46b57e702fe6237d3e825e39a3aa53734808eb6",
      grounding: {
        mastermind_sha: "ffb90680084041016afbf5eea1670b00aca20e1f",
        macro_sha: "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        boot_packet_schema: "mastermind.ceo_boot_packet.v1",
      },
      attempt_limit: 1,
      worker_account: "REGISTERED_NOT_SESSION_ATTESTED",
    },
    locator: null,
    session: null,
    result: null,
    can_send: false,
  },
  error: null,
};

const GENUINE_CREATE_FRAME: Record<string, unknown> = {
  schema: "mastermind.executive.fresh_conversation_result.v1",
  operation: "create",
  ok: true,
  data: {
    schema: "mastermind.executive.fresh_conversation_data.v1",
    operation_key: GENUINE_KEY,
    work_ref: GENUINE_WORK_REF,
    state: "CREATED",
    effect: "ADMITTED",
    parent_consumed: false,
    preview: null,
    locator: {
      work_ref: GENUINE_WORK_REF,
      root_job_id: "JOB-001",
      job_id: "JOB-002",
      attempt_id: "ATT-1001248864954eaf9e246de727de959c",
    },
    session: {
      attempt_id: "ATT-1001248864954eaf9e246de727de959c",
      generation: "ohf-generation-d50fcd019440495e901ed6aa82f202cd",
      binding_digest: "e5910f8c8540d269400d2e13e767e1fb0447b8594d00376690b68178af1bfb92",
    },
    result: null,
    can_send: false,
  },
  error: null,
};

const GENUINE_READ_FRAME: Record<string, unknown> = {
  schema: "mastermind.executive.fresh_conversation_result.v1",
  operation: "read",
  ok: true,
  data: {
    schema: "mastermind.executive.fresh_conversation_data.v1",
    operation_key: GENUINE_KEY,
    work_ref: GENUINE_WORK_REF,
    state: "CREATED",
    effect: "NONE",
    parent_consumed: false,
    preview: null,
    locator: {
      work_ref: GENUINE_WORK_REF,
      root_job_id: "JOB-001",
      job_id: "JOB-002",
      attempt_id: "ATT-1001248864954eaf9e246de727de959c",
    },
    session: {
      attempt_id: "ATT-1001248864954eaf9e246de727de959c",
      generation: "ohf-generation-d50fcd019440495e901ed6aa82f202cd",
      binding_digest: "e5910f8c8540d269400d2e13e767e1fb0447b8594d00376690b68178af1bfb92",
    },
    result: {
      digest: "97a59d862b96dc0d9d4415a460ec973dca4a024424cf9d5e4d7001698ab48809",
      envelope: {
        current_state: "complete",
        errors: [],
        job_id: "JOB-002",
        next_actions: [],
        role: "plan",
        role_result: {
          plan_attempt_id: "ATT-1001248864954eaf9e246de727de959c",
          root_job_id: "JOB-001",
          schema_version: "mastermind.execution_plan/v1",
          steps: [
            {
              allowed_write_paths: [],
              attempt_limit: 1,
              business_impact: "routine",
              cost_class: "small",
              objective: "Perform one bounded read-only follow-up.",
              ordinal: 0,
              requested_authorities: ["READ"],
              review_required: false,
              step_id: "step-1",
              validation_ids: [],
            },
          ],
        },
        run_id: "ATT-1001248864954eaf9e246de727de959c",
        schema_version: "mastermind.executive_orchestration_result/v1",
        status: "COMPLETED",
        summary: "Recovered one exact planner session.",
        validations: [],
        worker_id: "worker-a",
      },
    },
    can_send: false,
  },
  error: null,
};

// ── Unit-only synthetic frames (labelled; parent holds the signed status vector) ──

const UNIT_LOCATOR = {
  work_ref: GENUINE_WORK_REF,
  root_job_id: "JOB-001",
  job_id: "JOB-002",
  attempt_id: "ATT-1001248864954eaf9e246de727de959c",
};

const UNIT_SESSION = {
  attempt_id: "ATT-1001248864954eaf9e246de727de959c",
  generation: "ohf-generation-d50fcd019440495e901ed6aa82f202cd",
  binding_digest: "e5910f8c8540d269400d2e13e767e1fb0447b8594d00376690b68178af1bfb92",
};

/** Unit-only synthetic status frame; never a stand-in for a signed vector. */
function unitStatusOkFrame(
  dataOverrides: Record<string, unknown> = {},
): Record<string, unknown> {
  return {
    schema: "mastermind.executive.fresh_conversation_result.v1",
    operation: "status",
    ok: true,
    data: {
      schema: "mastermind.executive.fresh_conversation_data.v1",
      operation_key: GENUINE_KEY,
      work_ref: GENUINE_WORK_REF,
      state: "CREATED",
      effect: "NONE",
      parent_consumed: false,
      preview: null,
      locator: UNIT_LOCATOR,
      session: UNIT_SESSION,
      result: null,
      can_send: false,
      ...dataOverrides,
    },
    error: null,
  };
}

/** Unit-only synthetic status error frame. */
function unitStatusErrorFrame(error: unknown): Record<string, unknown> {
  return {
    schema: "mastermind.executive.fresh_conversation_result.v1",
    operation: "status",
    ok: false,
    data: null,
    error,
  };
}

/** Unit-only synthetic create frame for a non-terminal producer state. */
function unitCreateFrame(
  state: string,
  effect: string,
  locator: Record<string, unknown> | null,
): Record<string, unknown> {
  return {
    schema: "mastermind.executive.fresh_conversation_result.v1",
    operation: "create",
    ok: true,
    data: {
      schema: "mastermind.executive.fresh_conversation_data.v1",
      operation_key: GENUINE_KEY,
      work_ref: GENUINE_WORK_REF,
      state,
      effect,
      parent_consumed: false,
      preview: null,
      locator,
      session: null,
      result: null,
      can_send: false,
    },
    error: null,
  };
}

/** Unit-only synthetic create error frame. */
function unitCreateErrorFrame(error: unknown): Record<string, unknown> {
  return {
    schema: "mastermind.executive.fresh_conversation_result.v1",
    operation: "create",
    ok: false,
    data: null,
    error,
  };
}

const UNIT_CREATE_ADMITTED = unitCreateFrame("ADMITTED", "ADMITTED", {
  work_ref: GENUINE_WORK_REF,
  root_job_id: "JOB-001",
  job_id: null,
  attempt_id: null,
});
const UNIT_CREATE_ABSENT = unitCreateFrame("ABSENT", "NONE", null);
const UNIT_CREATE_RECONCILIATION_REQUIRED = unitCreateFrame(
  "RECONCILIATION_REQUIRED",
  "NONE",
  { work_ref: GENUINE_WORK_REF, root_job_id: "JOB-001", job_id: null, attempt_id: null },
);

// ── Harness ──────────────────────────────────────────────────────────────────

const SCOPE = "9f".repeat(32);
const OTHER_SCOPE = "ee".repeat(32);
/** A valid-looking but foreign-prefix key (still wire-grammatical). */
const FOREIGN_PREFIX_KEY = `mmos-launch-${"ab".repeat(20)}`;
/** A different but fully ordinary conversation-create key. */
const OTHER_KEY = `${CONVERSATION_CREATE_KEY_PREFIX}${"ab".repeat(20)}`;

const GENUINE_POINTER: OperationPointer = {
  operationKey: GENUINE_KEY,
  kind: "conversation_create",
  targetKey: GENUINE_WORK_REF,
};

const ACCEPTED_STATE = { status: "accepted", pointer: null, reason: "ACCEPTED" };
const UNKNOWN_STATE = { status: "unknown", pointer: GENUINE_POINTER, reason: "UNKNOWN_RECEIPT" };

function makeOwner(generation = "gen-1"): OwnerContext {
  return { principalScope: SCOPE, generation };
}

/** Deterministic 20-byte boundary stub: reproduces the genuine canonical key. */
function stubCanonicalKey(): void {
  vi.stubGlobal("crypto", {
    getRandomValues(bytes: Uint8Array): Uint8Array {
      for (let i = 0; i < bytes.length; i++) bytes[i] = (i + 1) & 0xff;
      return bytes;
    },
  });
}

class InMemPendingPointerStore implements PendingPointerStore {
  private readonly pointers = new Map<string, OperationPointer>();

  async read(scope: string): Promise<OperationPointer | null> {
    const existing = this.pointers.get(scope);
    return existing ? { ...existing } : null;
  }

  async reserve(
    scope: string,
    pointer: OperationPointer,
  ): Promise<
    | { readonly reserved: true }
    | { readonly reserved: false; readonly pointer: OperationPointer }
  > {
    const existing = this.pointers.get(scope);
    // Never overwrites — even an identical pointer loses the reservation.
    if (existing) return { reserved: false, pointer: { ...existing } };
    this.pointers.set(scope, { ...pointer });
    return { reserved: true };
  }

  async clearIfEqual(scope: string, pointer: OperationPointer): Promise<boolean> {
    const existing = this.pointers.get(scope);
    if (!existing) return false;
    if (
      existing.operationKey !== pointer.operationKey ||
      existing.kind !== pointer.kind ||
      existing.targetKey !== pointer.targetKey
    ) {
      return false;
    }
    this.pointers.delete(scope);
    return true;
  }
}

interface TransportHarness {
  readonly transport: FreshConversationTransport;
  readonly preview: Mock;
  readonly create: Mock;
  readonly status: Mock;
  readonly read: Mock;
}

function makeTransport(): TransportHarness {
  const preview: Mock = vi.fn(async () => GENUINE_PREVIEW_FRAME);
  const create: Mock = vi.fn(async () => GENUINE_CREATE_FRAME);
  const status: Mock = vi.fn(async () => unitStatusOkFrame());
  const read: Mock = vi.fn(async () => GENUINE_READ_FRAME);
  return {
    transport: {
      preview: preview as unknown as FreshConversationTransport["preview"],
      create: create as unknown as FreshConversationTransport["create"],
      status: status as unknown as FreshConversationTransport["status"],
      read: read as unknown as FreshConversationTransport["read"],
    },
    preview,
    create,
    status,
    read,
  };
}

function makeHarness(store: PendingPointerStore = new InMemPendingPointerStore()) {
  const t = makeTransport();
  let owner: OwnerContext | null = makeOwner();
  let available = true;
  const binding = createFreshConversationBinding({
    owner: () => owner,
    canPreviewCreate: () => available,
    transport: t.transport,
    store,
  });
  return {
    binding,
    store,
    preview: t.preview,
    create: t.create,
    status: t.status,
    read: t.read,
    setOwner: (next: OwnerContext | null) => {
      owner = next;
    },
    bumpGeneration: (generation: string) => {
      owner = { principalScope: SCOPE, generation };
    },
    setAvailable: (next: boolean) => {
      available = next;
    },
  };
}

type Harness = ReturnType<typeof makeHarness>;

function deferred<T>(): {
  promise: Promise<T>;
  resolve: (value: T) => void;
  reject: (reason?: unknown) => void;
} {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

/** Decode the actual preview vector through the actual parent decoder. */
function genuinePreviewData(): FreshConversationData {
  const decoded = decodeFreshConversationResult(GENUINE_PREVIEW_FRAME, "preview", {
    work_ref: GENUINE_WORK_REF,
    operation_key: GENUINE_KEY,
  });
  if (decoded === null || !decoded.ok) {
    throw new Error("harness defect: the actual preview vector must decode");
  }
  return decoded.data;
}

/** Mint + decode + intent through the binding; requires the canonical stub. */
function genuineIntent(binding: FreshConversationBinding): CommandIntent {
  stubCanonicalKey();
  const request = binding.makePreviewRequest(GENUINE_WORK_REF, GENUINE_MESSAGE);
  if (request === null || request.operation_key !== GENUINE_KEY) {
    throw new Error("harness defect: canonical stub must reproduce the genuine key");
  }
  const intent = binding.makeCreateIntent(request, genuinePreviewData());
  if (intent === null) {
    throw new Error("harness defect: the actual vectors must build an intent");
  }
  return intent;
}

async function seedPointer(store: PendingPointerStore): Promise<void> {
  const reserved = await store.reserve(SCOPE, GENUINE_POINTER);
  if (!reserved.reserved) throw new Error("harness defect: seed reservation failed");
}

afterEach(() => {
  vi.unstubAllGlobals();
});

// ── Key minting ──────────────────────────────────────────────────────────────

describe("makePreviewRequest minting", () => {
  it("mints the store-prefix ordinary key from exactly 20 random bytes", () => {
    const h = makeHarness();
    const lengths: number[] = [];
    vi.stubGlobal("crypto", {
      getRandomValues(bytes: Uint8Array): Uint8Array {
        lengths.push(bytes.length);
        for (let i = 0; i < bytes.length; i++) bytes[i] = (i + 1) & 0xff;
        return bytes;
      },
    });
    const request = h.binding.makePreviewRequest(GENUINE_WORK_REF, GENUINE_MESSAGE);
    expect(lengths).toEqual([20]);
    expect(request).not.toBeNull();
    expect(request?.operation_key).toBe(GENUINE_KEY);
    expect(request?.operation_key.startsWith(CONVERSATION_CREATE_KEY_PREFIX)).toBe(true);
    expect(request?.operation_key).toMatch(/^mmos-conversation-create-[0-9a-f]{40}$/);
    // Exact three-field wire request, no aliases.
    expect(request).toEqual({
      work_ref: GENUINE_WORK_REF,
      operation_key: GENUINE_KEY,
      message: GENUINE_MESSAGE,
    });
  });

  it("mints a distinct ordinary key on every explicit call", () => {
    const h = makeHarness();
    const first = h.binding.makePreviewRequest(GENUINE_WORK_REF, GENUINE_MESSAGE);
    const second = h.binding.makePreviewRequest(GENUINE_WORK_REF, GENUINE_MESSAGE);
    expect(first?.operation_key).toMatch(/^mmos-conversation-create-[0-9a-f]{40}$/);
    expect(second?.operation_key).toMatch(/^mmos-conversation-create-[0-9a-f]{40}$/);
    expect(first?.operation_key).not.toBe(second?.operation_key);
  });

  it("validates wire inputs before minting anything", () => {
    const h = makeHarness();
    const spy = vi.fn((bytes: Uint8Array) => bytes);
    vi.stubGlobal("crypto", { getRandomValues: spy });
    // A bad workspace reference is rejected before the boundary is touched.
    expect(h.binding.makePreviewRequest("no-prefix", GENUINE_MESSAGE)).toBeNull();
    expect(h.binding.makePreviewRequest(`${GENUINE_WORK_REF}\n`, GENUINE_MESSAGE)).toBeNull();
    expect(spy).not.toHaveBeenCalled();
    // A bad message never yields a request; the unused entropy is discarded.
    expect(h.binding.makePreviewRequest(GENUINE_WORK_REF, "")).toBeNull();
    expect(h.binding.makePreviewRequest(GENUINE_WORK_REF, "   ")).toBeNull();
  });

  it("fails closed when the crypto boundary is absent, throws or misbehaves", () => {
    const h = makeHarness();
    vi.stubGlobal("crypto", undefined);
    expect(h.binding.makePreviewRequest(GENUINE_WORK_REF, GENUINE_MESSAGE)).toBeNull();
    vi.stubGlobal("crypto", {
      getRandomValues(): never {
        throw new Error("crypto denied");
      },
    });
    expect(h.binding.makePreviewRequest(GENUINE_WORK_REF, GENUINE_MESSAGE)).toBeNull();
    vi.stubGlobal("crypto", { getRandomValues: () => null });
    expect(h.binding.makePreviewRequest(GENUINE_WORK_REF, GENUINE_MESSAGE)).toBeNull();
    vi.stubGlobal("crypto", {
      getRandomValues: (bytes: Uint8Array) => bytes.subarray(0, 5),
    });
    expect(h.binding.makePreviewRequest(GENUINE_WORK_REF, GENUINE_MESSAGE)).toBeNull();
  });

  it("never recovers a failed mint with a fallback key", () => {
    const h = makeHarness();
    vi.stubGlobal("crypto", {
      getRandomValues(): never {
        throw new Error("crypto denied");
      },
    });
    expect(h.binding.makePreviewRequest(GENUINE_WORK_REF, GENUINE_MESSAGE)).toBeNull();
    vi.unstubAllGlobals();
    const retry = h.binding.makePreviewRequest(GENUINE_WORK_REF, GENUINE_MESSAGE);
    expect(retry).not.toBeNull();
    expect(retry?.operation_key).toMatch(/^mmos-conversation-create-[0-9a-f]{40}$/);
  });
});

// ── Preview observation ──────────────────────────────────────────────────────

describe("preview", () => {
  it("returns the genuine envelope verbatim with zero store writes and zero creates", async () => {
    stubCanonicalKey();
    const h = makeHarness();
    const signal = new AbortController().signal;
    const request = h.binding.makePreviewRequest(GENUINE_WORK_REF, GENUINE_MESSAGE);
    expect(request).not.toBeNull();
    const raw = await h.binding.preview(request!, signal);
    // Original five-field envelope by identity — never a normalized surrogate.
    expect(raw).toBe(GENUINE_PREVIEW_FRAME);
    expect(h.preview).toHaveBeenCalledTimes(1);
    expect(h.preview.mock.calls[0]?.[0]).toEqual({
      work_ref: GENUINE_WORK_REF,
      operation_key: GENUINE_KEY,
      message: GENUINE_MESSAGE,
    });
    expect(h.preview.mock.calls[0]?.[1]).toBe(signal);
    expect(h.create).not.toHaveBeenCalled();
    expect(await h.store.read(SCOPE)).toBeNull();
  });

  it("refuses closed without owner or availability, before any transport call", async () => {
    stubCanonicalKey();
    const h = makeHarness();
    const request = h.binding.makePreviewRequest(GENUINE_WORK_REF, GENUINE_MESSAGE)!;
    h.setOwner(null);
    await expect(h.binding.preview(request, new AbortController().signal)).rejects.toMatchObject({
      message: FRESH_CONVERSATION_BINDING_CLOSED,
    });
    h.setOwner(makeOwner());
    h.setAvailable(false);
    await expect(h.binding.preview(request, new AbortController().signal)).rejects.toMatchObject({
      message: FRESH_CONVERSATION_BINDING_CLOSED,
    });
    expect(h.preview).not.toHaveBeenCalled();
    expect(h.create).not.toHaveBeenCalled();
  });

  it("withholds the raw envelope when the owner generation moves across the await", async () => {
    stubCanonicalKey();
    const h = makeHarness();
    const request = h.binding.makePreviewRequest(GENUINE_WORK_REF, GENUINE_MESSAGE)!;
    const gate = deferred<unknown>();
    h.preview.mockImplementationOnce(() => gate.promise);
    const pending = h.binding.preview(request, new AbortController().signal);
    await vi.waitFor(() => expect(h.preview).toHaveBeenCalledTimes(1));
    h.bumpGeneration("gen-2");
    gate.resolve(GENUINE_PREVIEW_FRAME);
    await expect(pending).rejects.toMatchObject({
      message: FRESH_CONVERSATION_BINDING_CLOSED,
    });
    expect(h.create).not.toHaveBeenCalled();
  });

  it("reports a closed generic error on a thrown transport, never raw text", async () => {
    stubCanonicalKey();
    const h = makeHarness();
    const request = h.binding.makePreviewRequest(GENUINE_WORK_REF, GENUINE_MESSAGE)!;
    h.preview.mockRejectedValueOnce(new Error("raw transport detail leaked"));
    await expect(h.binding.preview(request, new AbortController().signal)).rejects.toMatchObject({
      message: FRESH_CONVERSATION_BINDING_CLOSED,
    });
  });
});

// ── Create intent ────────────────────────────────────────────────────────────

describe("makeCreateIntent", () => {
  it("builds the exact conversation_create intent from the actual vectors", () => {
    stubCanonicalKey();
    const h = makeHarness();
    const request = h.binding.makePreviewRequest(GENUINE_WORK_REF, GENUINE_MESSAGE)!;
    const intent = h.binding.makeCreateIntent(request, genuinePreviewData());
    expect(intent).not.toBeNull();
    expect(intent?.kind).toBe("conversation_create");
    expect(intent?.targetKey).toBe(GENUINE_WORK_REF);
    expect(Object.keys(intent!.payload).sort()).toEqual(["owner", "request"]);
    expect(intent?.payload.request).toEqual(GENUINE_CREATE_REQUEST);
    expect(intent?.payload.owner).toEqual({ principalScope: SCOPE, generation: "gen-1" });
    expect(Object.keys(intent!.payload.owner as OwnerContext).sort()).toEqual([
      "generation",
      "principalScope",
    ]);
  });

  it("returns null without an owner or create availability", () => {
    stubCanonicalKey();
    const h = makeHarness();
    const request = h.binding.makePreviewRequest(GENUINE_WORK_REF, GENUINE_MESSAGE)!;
    const data = genuinePreviewData();
    expect(h.binding.makeCreateIntent(request, data)).not.toBeNull();
    h.setOwner(null);
    expect(h.binding.makeCreateIntent(request, data)).toBeNull();
    h.setOwner(makeOwner());
    h.setAvailable(false);
    expect(h.binding.makeCreateIntent(request, data)).toBeNull();
  });

  it("rejects surrogates that are not the actual PREVIEW_READY selector", () => {
    stubCanonicalKey();
    const h = makeHarness();
    const request = h.binding.makePreviewRequest(GENUINE_WORK_REF, GENUINE_MESSAGE)!;
    const data = genuinePreviewData();
    const absent = { ...data, state: "ABSENT" } as unknown as FreshConversationData;
    expect(h.binding.makeCreateIntent(request, absent)).toBeNull();
    const foreignSelector = {
      ...data,
      operation_key: OTHER_KEY,
    } as unknown as FreshConversationData;
    expect(h.binding.makeCreateIntent(request, foreignSelector)).toBeNull();
    const noPreview = { ...data, preview: null } as unknown as FreshConversationData;
    expect(h.binding.makeCreateIntent(request, noPreview)).toBeNull();
  });
});

// ── One create, duplicates, and pre-existing pointers ────────────────────────

describe("controller.begin over the actual vectors", () => {
  it("submits exactly one genuine create and publishes accepted with the store cleared", async () => {
    stubCanonicalKey();
    const h = makeHarness();
    const signal = new AbortController().signal;
    const intent = genuineIntent(h.binding);
    const state = await h.binding.controller.begin(intent);
    expect(state).toEqual(ACCEPTED_STATE);
    expect(Object.hasOwn(state, "missionSelection")).toBe(false);
    expect(h.create).toHaveBeenCalledTimes(1);
    expect(h.create.mock.calls[0]?.[0]).toEqual(GENUINE_CREATE_REQUEST);
    // The controller forwards its own live in-flight signal to the transport.
    expect(h.create.mock.calls[0]?.[1]).toBeInstanceOf(AbortSignal);
    expect(await h.store.read(SCOPE)).toBeNull();
  });

  it("refuses a rapid duplicate begin locally and still submits only one create", async () => {
    stubCanonicalKey();
    const h = makeHarness();
    const gate = deferred<unknown>();
    h.create.mockImplementationOnce(() => gate.promise);
    const first = h.binding.controller.begin(genuineIntent(h.binding));
    await vi.waitFor(() => expect(h.create).toHaveBeenCalledTimes(1));
    const second = await h.binding.controller.begin(genuineIntent(h.binding));
    expect(second).toEqual({ status: "refused", pointer: null, reason: "OPERATION_BUSY" });
    gate.resolve(GENUINE_CREATE_FRAME);
    expect(await first).toEqual(ACCEPTED_STATE);
    expect(h.create).toHaveBeenCalledTimes(1);
    expect(await h.store.read(SCOPE)).toBeNull();
  });

  it("routes a begin over an existing pointer to checking without submitting", async () => {
    stubCanonicalKey();
    const h = makeHarness();
    await seedPointer(h.store);
    const state = await h.binding.controller.begin(genuineIntent(h.binding));
    expect(state).toEqual({
      status: "checking",
      pointer: GENUINE_POINTER,
      reason: "PENDING_POINTER",
    });
    expect(h.create).not.toHaveBeenCalled();
  });

  it("stores exactly the three-field pointer — never payload or message", async () => {
    stubCanonicalKey();
    const h = makeHarness();
    const gate = deferred<unknown>();
    h.create.mockImplementationOnce(() => gate.promise);
    const pending = h.binding.controller.begin(genuineIntent(h.binding));
    await vi.waitFor(() => expect(h.create).toHaveBeenCalledTimes(1));
    const stored = await h.store.read(SCOPE);
    expect(stored).toEqual(GENUINE_POINTER);
    expect(Object.keys(stored ?? {}).sort()).toEqual(["kind", "operationKey", "targetKey"]);
    expect(JSON.stringify(stored)).not.toContain("新对话");
    gate.resolve(GENUINE_CREATE_FRAME);
    expect(await pending).toEqual(ACCEPTED_STATE);
  });
});

// ── Unknown and refused create outcomes ──────────────────────────────────────

describe("create receipt classification", () => {
  it.each([
    ["ADMITTED", UNIT_CREATE_ADMITTED],
    ["ABSENT", UNIT_CREATE_ABSENT],
    ["RECONCILIATION_REQUIRED", UNIT_CREATE_RECONCILIATION_REQUIRED],
  ])("retains the pointer on a %s create projection", async (_state, frame) => {
    stubCanonicalKey();
    const h = makeHarness();
    h.create.mockResolvedValueOnce(frame);
    const result = await h.binding.controller.begin(genuineIntent(h.binding));
    expect(result).toEqual(UNKNOWN_STATE);
    expect(h.create).toHaveBeenCalledTimes(1);
    expect(await h.store.read(SCOPE)).toEqual(GENUINE_POINTER);
  });

  it.each([
    ["known public refusal", "invalid_input", { status: "refused", pointer: null, reason: "REFUSED" }],
    ["effect_unknown code", "effect_unknown", UNKNOWN_STATE],
    ["unknown future code", "plausible_future_code", UNKNOWN_STATE],
    ["malformed error frame", null, UNKNOWN_STATE],
  ])("classifies a %s without reading message text", async (label, code, expected) => {
    stubCanonicalKey();
    const h = makeHarness();
    const frame =
      code === null
        ? unitCreateErrorFrame({ code: "refused" })
        : unitCreateErrorFrame({ code, message: `unit ${label} frame` });
    h.create.mockResolvedValueOnce(frame);
    const result = await h.binding.controller.begin(genuineIntent(h.binding));
    expect(result).toEqual(expected);
    if (expected.status === "unknown") {
      expect(await h.store.read(SCOPE)).toEqual(GENUINE_POINTER);
    } else {
      expect(await h.store.read(SCOPE)).toBeNull();
    }
  });

  it.each([
    ["foreign selector", { ...GENUINE_CREATE_FRAME, data: { ...(GENUINE_CREATE_FRAME.data as Record<string, unknown>), operation_key: OTHER_KEY } }],
    ["wrong data schema", { ...GENUINE_CREATE_FRAME, data: { ...(GENUINE_CREATE_FRAME.data as Record<string, unknown>), schema: "mastermind.executive.fresh_conversation_data.v2" } }],
    ["truncated envelope", { schema: "mastermind.executive.fresh_conversation_result.v1", operation: "create", ok: true, data: GENUINE_CREATE_FRAME.data }],
  ])("holds unknown on a %s frame", async (_label, frame) => {
    stubCanonicalKey();
    const h = makeHarness();
    h.create.mockResolvedValueOnce(frame);
    const result = await h.binding.controller.begin(genuineIntent(h.binding));
    expect(result).toEqual(UNKNOWN_STATE);
    expect(await h.store.read(SCOPE)).toEqual(GENUINE_POINTER);
  });

  it("holds unknown and retains the pointer when create throws", async () => {
    stubCanonicalKey();
    const h = makeHarness();
    h.create.mockRejectedValueOnce(new Error("connection reset before response"));
    const result = await h.binding.controller.begin(genuineIntent(h.binding));
    // A thrown transport is classified as unknown, never refused.
    expect(result).toEqual(UNKNOWN_STATE);
    expect(await h.store.read(SCOPE)).toEqual(GENUINE_POINTER);
  });
});

// ── Authentication fences across the await ────────────────────────────────────

describe("authentication epoch fences", () => {
  it("withholds a create receipt when the generation moves across the await", async () => {
    stubCanonicalKey();
    const h = makeHarness();
    const gate = deferred<unknown>();
    h.create.mockImplementationOnce(() => gate.promise);
    const pending = h.binding.controller.begin(genuineIntent(h.binding));
    await vi.waitFor(() => expect(h.create).toHaveBeenCalledTimes(1));
    h.bumpGeneration("gen-2");
    gate.resolve(GENUINE_CREATE_FRAME);
    expect(await pending).toEqual({ status: "idle", pointer: null, reason: "EPOCH_CHANGED" });
    // The committed effect is never cancelled or published: pointer retained.
    expect(h.create).toHaveBeenCalledTimes(1);
    expect(await h.store.read(SCOPE)).toEqual(GENUINE_POINTER);
  });

  it("withholds and retains when the principal changes across the await", async () => {
    stubCanonicalKey();
    const h = makeHarness();
    const gate = deferred<unknown>();
    h.create.mockImplementationOnce(() => gate.promise);
    const pending = h.binding.controller.begin(genuineIntent(h.binding));
    await vi.waitFor(() => expect(h.create).toHaveBeenCalledTimes(1));
    h.setOwner({ principalScope: `${SCOPE.slice(0, -2)}aa`, generation: "gen-1" });
    gate.resolve(GENUINE_CREATE_FRAME);
    expect(await pending).toEqual({ status: "idle", pointer: null, reason: "EPOCH_CHANGED" });
    expect(await h.store.read(SCOPE)).toEqual(GENUINE_POINTER);
  });

  it("retains the pointer when the owner disappears across a recovery await", async () => {
    const h = makeHarness();
    await seedPointer(h.store);
    const gate = deferred<unknown>();
    h.status.mockImplementationOnce(() => gate.promise);
    const pending = h.binding.controller.recover();
    await vi.waitFor(() => expect(h.status).toHaveBeenCalledTimes(1));
    h.setOwner(null);
    gate.resolve(unitStatusOkFrame());
    // The controller's epoch fence publishes first; the pointer stays anyway.
    expect(await pending).toEqual({ status: "idle", pointer: null, reason: "EPOCH_CHANGED" });
    expect(await h.store.read(SCOPE)).toEqual(GENUINE_POINTER);
  });
});

// ── Recovery over the same original key ──────────────────────────────────────

describe("recovery", () => {
  it("remounts a new binding over the same store and recovers the same key", async () => {
    stubCanonicalKey();
    const lost = makeHarness();
    const intent = genuineIntent(lost.binding);
    lost.create.mockRejectedValueOnce(new Error("connection reset before response"));
    expect(await lost.binding.controller.begin(intent)).toEqual(UNKNOWN_STATE);
    expect(await lost.store.read(SCOPE)).toEqual(GENUINE_POINTER);

    // Remount: brand-new binding + controller over the SAME durable store.
    const remounted = makeHarness(lost.store);
    const recovered = await remounted.binding.controller.recover();
    expect(recovered).toEqual(ACCEPTED_STATE);
    expect(remounted.status).toHaveBeenCalledTimes(1);
    expect(remounted.status.mock.calls[0]?.[0]).toEqual({
      work_ref: GENUINE_WORK_REF,
      operation_key: GENUINE_KEY,
    });
    expect(remounted.create).not.toHaveBeenCalled();
    expect(await lost.store.read(SCOPE)).toBeNull();
  });

  it.each([
    ["CREATED", unitStatusOkFrame({ state: "CREATED" }), ACCEPTED_STATE],
    ["SETTLED", unitStatusOkFrame({ state: "SETTLED", session: null }), ACCEPTED_STATE],
    ["ADMITTED", unitStatusOkFrame({ state: "ADMITTED", session: null }), UNKNOWN_STATE],
    ["ABSENT", unitStatusOkFrame({ state: "ABSENT", locator: null, session: null }), UNKNOWN_STATE],
    [
      "RECONCILIATION_REQUIRED",
      unitStatusOkFrame({ state: "RECONCILIATION_REQUIRED", session: null }),
      UNKNOWN_STATE,
    ],
  ])("reads a unit status %s projection", async (_state, frame, expected) => {
    const h = makeHarness();
    await seedPointer(h.store);
    h.status.mockResolvedValueOnce(frame);
    const recovered = await h.binding.controller.recover();
    expect(recovered).toEqual(expected);
    if (expected.status === "unknown") {
      expect(await h.store.read(SCOPE)).toEqual(GENUINE_POINTER);
    } else {
      expect(await h.store.read(SCOPE)).toBeNull();
    }
    expect(h.status).toHaveBeenCalledTimes(1);
    expect(h.create).not.toHaveBeenCalled();
  });

  it("treats a status error, malformed status frame, or throw as a hold — never clearance", async () => {
    const errorHarness = makeHarness();
    await seedPointer(errorHarness.store);
    errorHarness.status.mockResolvedValueOnce(
      unitStatusErrorFrame({ code: "refused", message: "unit status refusal" }),
    );
    expect(await errorHarness.binding.controller.recover()).toEqual(UNKNOWN_STATE);
    expect(await errorHarness.store.read(SCOPE)).toEqual(GENUINE_POINTER);

    const malformedHarness = makeHarness();
    await seedPointer(malformedHarness.store);
    const truncated = unitStatusOkFrame();
    delete truncated.error;
    malformedHarness.status.mockResolvedValueOnce(truncated);
    expect(await malformedHarness.binding.controller.recover()).toEqual(UNKNOWN_STATE);
    expect(await malformedHarness.store.read(SCOPE)).toEqual(GENUINE_POINTER);

    const thrownHarness = makeHarness();
    await seedPointer(thrownHarness.store);
    thrownHarness.status.mockRejectedValueOnce(new Error("status unreachable"));
    expect(await thrownHarness.binding.controller.recover()).toEqual(UNKNOWN_STATE);
    expect(await thrownHarness.store.read(SCOPE)).toEqual(GENUINE_POINTER);
  });

  it("keeps default and explicit-source recovery on the original status read", async () => {
    const h = makeHarness();
    await seedPointer(h.store);
    expect(await h.binding.controller.recover({ reconcileSource: true })).toEqual(ACCEPTED_STATE);
    expect(h.status).toHaveBeenCalledTimes(1);
    expect(h.create).not.toHaveBeenCalled();
    expect(await h.store.read(SCOPE)).toBeNull();
  });

  it("prepares nothing when a foreign intent reaches the port", async () => {
    stubCanonicalKey();
    const h = makeHarness();
    const intent = genuineIntent(h.binding);

    const foreignKind = { ...intent, kind: "message" } as CommandIntent;
    expect(await h.binding.controller.begin(foreignKind)).toEqual({
      status: "idle",
      pointer: null,
      reason: "MALFORMED_POINTER",
    });

    const newlineTarget = { ...intent, targetKey: `${GENUINE_WORK_REF}\n` } as CommandIntent;
    expect(await h.binding.controller.begin(newlineTarget)).toEqual({
      status: "idle",
      pointer: null,
      reason: "MALFORMED_POINTER",
    });

    const badPrefixPayload = {
      ...intent,
      payload: {
        ...intent.payload,
        request: {
          ...(intent.payload.request as Record<string, unknown>),
          operation_key: FOREIGN_PREFIX_KEY,
        },
      },
    } as CommandIntent;
    expect(await h.binding.controller.begin(badPrefixPayload)).toEqual({
      status: "idle",
      pointer: null,
      reason: "MALFORMED_POINTER",
    });

    const extraPayloadKey = {
      ...intent,
      payload: { ...intent.payload, session: "surrogate" },
    } as CommandIntent;
    expect(await h.binding.controller.begin(extraPayloadKey)).toEqual({
      status: "idle",
      pointer: null,
      reason: "MALFORMED_POINTER",
    });

    const foreignOwnerPayload = {
      ...intent,
      payload: {
        ...intent.payload,
        owner: { principalScope: SCOPE, generation: "gen-2" },
      },
    } as CommandIntent;
    expect(await h.binding.controller.begin(foreignOwnerPayload)).toEqual({
      status: "idle",
      pointer: null,
      reason: "MALFORMED_POINTER",
    });

    expect(h.create).not.toHaveBeenCalled();
    expect(await h.store.read(SCOPE)).toBeNull();
  });
});

// ── Workspace withdrawal must not block originals ────────────────────────────

describe("create availability independence", () => {
  it("blocks new intents and preview but still allows status and read", async () => {
    stubCanonicalKey();
    const h = makeHarness();
    const request = h.binding.makePreviewRequest(GENUINE_WORK_REF, GENUINE_MESSAGE)!;
    const signal = new AbortController().signal;
    h.setAvailable(false);
    expect(h.binding.makeCreateIntent(request, genuinePreviewData())).toBeNull();
    await expect(h.binding.preview(request, signal)).rejects.toMatchObject({
      message: FRESH_CONVERSATION_BINDING_CLOSED,
    });
    expect(h.preview).not.toHaveBeenCalled();

    // Original observation and recovery are availability-independent.
    const raw = await h.binding.readOriginal(
      { work_ref: GENUINE_WORK_REF, operation_key: GENUINE_KEY },
      signal,
    );
    expect(raw).toBe(GENUINE_READ_FRAME);
    await seedPointer(h.store);
    expect(await h.binding.controller.recover()).toEqual(ACCEPTED_STATE);
    expect(h.status).toHaveBeenCalledTimes(1);
    expect(h.create).not.toHaveBeenCalled();
  });
});

// ── readOriginal ─────────────────────────────────────────────────────────────

describe("readOriginal", () => {
  it("returns the genuine read vector verbatim on the same key without minting", async () => {
    const h = makeHarness();
    const raw = await h.binding.readOriginal(
      { work_ref: GENUINE_WORK_REF, operation_key: GENUINE_KEY },
      new AbortController().signal,
    );
    expect(raw).toBe(GENUINE_READ_FRAME);
    expect(h.read).toHaveBeenCalledTimes(1);
    expect(h.read.mock.calls[0]?.[0]).toEqual({
      work_ref: GENUINE_WORK_REF,
      operation_key: GENUINE_KEY,
    });
    expect(h.create).not.toHaveBeenCalled();
    expect(h.preview).not.toHaveBeenCalled();
  });

  it("the actual read vector still decodes through the parent decoder", () => {
    const decoded = decodeFreshConversationResult(GENUINE_READ_FRAME, "read", {
      work_ref: GENUINE_WORK_REF,
      operation_key: GENUINE_KEY,
    });
    expect(decoded?.ok).toBe(true);
  });

  it("refuses closed without an owner, before any transport call", async () => {
    const h = makeHarness();
    h.setOwner(null);
    await expect(
      h.binding.readOriginal(
        { work_ref: GENUINE_WORK_REF, operation_key: GENUINE_KEY },
        new AbortController().signal,
      ),
    ).rejects.toMatchObject({ message: FRESH_CONVERSATION_BINDING_CLOSED });
    expect(h.read).not.toHaveBeenCalled();
  });

  it("withholds the raw envelope when the owner generation moves across the await", async () => {
    const h = makeHarness();
    const gate = deferred<unknown>();
    h.read.mockImplementationOnce(() => gate.promise);
    const pending = h.binding.readOriginal(
      { work_ref: GENUINE_WORK_REF, operation_key: GENUINE_KEY },
      new AbortController().signal,
    );
    await vi.waitFor(() => expect(h.read).toHaveBeenCalledTimes(1));
    h.bumpGeneration("gen-2");
    gate.resolve(GENUINE_READ_FRAME);
    await expect(pending).rejects.toMatchObject({
      message: FRESH_CONVERSATION_BINDING_CLOSED,
    });
  });

  it("reports a closed generic error on a thrown transport, never raw text", async () => {
    const h = makeHarness();
    h.read.mockRejectedValueOnce(new Error("raw read detail leaked"));
    await expect(
      h.binding.readOriginal(
        { work_ref: GENUINE_WORK_REF, operation_key: GENUINE_KEY },
        new AbortController().signal,
      ),
    ).rejects.toMatchObject({ message: FRESH_CONVERSATION_BINDING_CLOSED });
  });
});

// ── View identity helper ─────────────────────────────────────────────────────

describe("sameConversationOwner", () => {
  it("compares principal scope and generation only", () => {
    const a = makeOwner("gen-1");
    expect(sameConversationOwner(a, makeOwner("gen-1"))).toBe(true);
    expect(sameConversationOwner(a, makeOwner("gen-2"))).toBe(false);
    expect(sameConversationOwner(a, { principalScope: OTHER_SCOPE, generation: "gen-1" })).toBe(
      false,
    );
    expect(sameConversationOwner(a, null)).toBe(false);
    expect(sameConversationOwner(null, a)).toBe(false);
    expect(sameConversationOwner(null, null)).toBe(false);
  });

  it("exposes the incumbent controller and the exact injected store", () => {
    const store = new InMemPendingPointerStore();
    const h = makeHarness(store);
    expect(typeof h.binding.controller.begin).toBe("function");
    expect(typeof h.binding.controller.recover).toBe("function");
    expect(typeof h.binding.controller.invalidate).toBe("function");
    expect(h.binding.store).toBe(store);
    expect(h.binding.context()).toEqual(makeOwner());
  });
});
