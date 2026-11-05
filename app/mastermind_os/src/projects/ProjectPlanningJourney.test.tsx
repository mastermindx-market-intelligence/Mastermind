// @vitest-environment jsdom
/**
 * ProjectPlanningJourney acceptance tests.
 *
 * Every test drives the real component over a genuine controller, an in-memory
 * durable-shaped pointer store and external transport fixtures only: the fixed
 * source-operation transport, the fixed source identity context read and the
 * closed planning envelope. No browser, no live host and no backend is
 * implied; assertions cover observable UI, the exact frames the module sends,
 * selection movement and the store lifecycle.
 *
 * SCOPE MODEL. The Workspace source scope and the Executive owner scope are
 * genuinely DISTINCT opaque values. Every source DTO — the identity context,
 * the creation options, the verified preview and the observed status — carries
 * the Workspace scope; the executive owner context, the planning admission
 * identity and the launch/consume pointer scope carry the Executive scope. No
 * test equates or derives one from the other, and no test demands that the
 * module use a single conflated scope or a single controller: only the
 * resource-specific store placement of each pending pointer and the observable
 * frames are asserted.
 */

import { useState } from "react";
import sourceIssued from "../fixtures/project-journey-source-issued-388205.json";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { RenderResult } from "@testing-library/react";
import { ProjectPlanningJourney, type ProjectJourneySelection } from "./ProjectPlanningJourney";
import { canonicalJson, sha256Hex } from "../orchestration/operation-key";
import { planningIntentId, planningOperationKey } from "../planning/project-planning-command-port";
import type { MissionHost } from "../host";
import type { OwnerContext, OperationPointer, PendingPointerStore } from "../orchestration/operation-controller";

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

// ── stable fixture identity ──────────────────────────────────────────────────

/** Workspace source scope bound by the fixed source identity context DTO. */
const WS_SCOPE = "a".repeat(64);
/** The workspace of a DIFFERENT principal; never equal or derived from WS_SCOPE. */
const WS_SCOPE_B = "b".repeat(64);
/** Executive owner scope of the acting principal; distinct opaque value. */
const EXEC_SCOPE = "c".repeat(64);
/** Executive owner scope of a foreign principal. */
const EXEC_SCOPE_B = "d".repeat(64);
const MACRO = "1".repeat(40);
const MASTERMIND = "2".repeat(40);
const COMMIT = "3".repeat(40);
const CONTENT = "4".repeat(64);
const REQUEST_SHA = "5".repeat(64);
const RECIPE = "6".repeat(64);
const CONSUME_RECEIPT = "7".repeat(64);
const POLICY = "8".repeat(64);
const FINGERPRINT = "9".repeat(64);
const PROFILE_REVISION = "aa".repeat(32);
const WORK_REF = "WS:JOURNEY1";
const SOURCE_PATH = "agentos/workstreams/WS-JOURNEY1.md";
const JOB = "JOB-journey-1";
const JOB_OTHER = "JOB-journey-2";
const ATTEMPT = "attempt-1";
const GOAL = "Publish the liquidity review project.\n保持原文";
const REQUEST_TEXT = "Plan the first useful slice of this project.";

const CONTEXT_SCHEMA = "mastermind.workspace_source_operation_context.v1";
const OPTIONS_SCHEMA = "mastermind.project_creation_options.v1";
const REQUEST_SCHEMA = "mastermind.project_profile_selection.v1";
const PREVIEW_SCHEMA = "mastermind.workspace_source_operation_preview.v1";
const PREVIEW_DOCUMENT_SCHEMA = "mastermind.project_creation_preview.v1";
const WITNESS_REFERENCE_SCHEMA = "mastermind.terminal_original_input_reference.v1";
const STATUS_SCHEMA = "mastermind.workspace_source_operation_status.v1";
const PLANNING_RESULT_SCHEMA = "mastermind.project_initial_planning.private_result.v1";
const DIRECT_RECEIPT_SCHEMA = "mastermind.ceo_direct_native_receipt.v1";
const RESULT_SCHEMA = "mastermind.direct_native_result_response.v1";

function hex64(seed: string): string {
  return sha256Hex(seed);
}
const PLAN_DIGEST = hex64("plan");

/** Each executive owns its own workspace; the context read reports it. */
function workspaceOf(executiveScope: string): string {
  return executiveScope === EXEC_SCOPE ? WS_SCOPE : WS_SCOPE_B;
}

// ── closed fixture documents ─────────────────────────────────────────────────

const PROFILE = {
  id: "balanced",
  label: { en: "Balanced", zhCN: "均衡" },
  summary: { en: "Balanced source profile.", zhCN: "均衡的来源配置。" },
  revision: PROFILE_REVISION,
  owner: "Chris",
  program: "Mastermind",
  repos: ["macro"],
  classification: "internal",
  blastRadius: "single_project",
  ambiguity: "low",
};

/** The exact fixed context DTO: envelope only, no flat fallback exists. */
function contextDocument(): Record<string, unknown> {
  return {
    schema: CONTEXT_SCHEMA,
    selection: { action: "publish_project_proposal", work_ref: null },
    owner_context: { principal_scope: workspaceOf(currentExecutive()) },
    can_inspect: true,
  };
}

function optionsDocument() {
  return {
    schema: OPTIONS_SCHEMA,
    expected_macro_sha: MACRO,
    grounding: { mastermind_sha: MASTERMIND, macro_sha: MACRO },
    owner_context: { principal_scope: WS_SCOPE },
    profiles: [PROFILE],
  };
}

function previewRequest(requestId: string) {
  return {
    schema: REQUEST_SCHEMA,
    request_id: requestId,
    goal: GOAL,
    expected_macro_sha: MACRO,
    profile_id: PROFILE.id,
    profile_sha256: PROFILE.revision,
  };
}

function previewDocument(request: Record<string, unknown>) {
  return {
    schema: PREVIEW_SCHEMA,
    selection: {
      action: "publish_project_proposal",
      request_id: request.request_id,
      work_ref: null,
    },
    owner_context: { principal_scope: WS_SCOPE },
    request_sha256: sha256Hex(canonicalJson(request)),
    recipe_fingerprint_sha256: RECIPE,
    preview_witness: {
      original_input: {
        schema: WITNESS_REFERENCE_SCHEMA,
        input_ref: `terminal-input:${hex64("terminal-input")}`,
        artifact_sha256: hex64("artifact"),
        payload_sha256: hex64("payload"),
      },
      recipe_fingerprint_sha256: RECIPE,
    },
    preview: {
      schema: PREVIEW_DOCUMENT_SCHEMA,
      state: "DRAFT_ONLY",
      work_ref: WORK_REF,
      source_commit: MACRO,
      canonical_path: SOURCE_PATH,
      content_sha256: CONTENT,
      goal: request.goal,
      profile: {
        id: PROFILE.id,
        revision: PROFILE_REVISION,
        title: "Balanced",
        owner: PROFILE.owner,
        program: PROFILE.program,
        repos: PROFILE.repos,
        classification: PROFILE.classification,
        blast_radius: PROFILE.blastRadius,
        ambiguity: PROFILE.ambiguity,
        waves: [
          { id: "wave-observe", title: "Observe the source record.", status: "pending" },
          { id: "wave-plan", title: "Request initial planning.", status: "active" },
        ],
        next_action: "Publish the verified draft.",
      },
    },
  };
}

function statusDocument(requestId: string, kind: "PROPOSAL_OBSERVED" | "SOURCE_OBSERVED") {
  const accepted = kind === "SOURCE_OBSERVED";
  return {
    schema: STATUS_SCHEMA,
    selection: { action: "publish_project_proposal", request_id: requestId, work_ref: WORK_REF },
    owner_context: { principal_scope: WS_SCOPE },
    disposition: accepted ? "accepted" : "unknown",
    reason: accepted ? null : "IN_PROGRESS",
    request_sha256: REQUEST_SHA,
    recipe_fingerprint_sha256: RECIPE,
    phase: "PUBLICATION",
    receipt: accepted
      ? {
          kind,
          event_id: 9,
          recorded_at_ms: 4,
          receipt_sha256: hex64("receipt"),
          sources: [
            { repository: "macro", commit: COMMIT, path: SOURCE_PATH, content_sha256: CONTENT },
          ],
          proposal: null,
        }
      : {
          kind,
          event_id: 7,
          recorded_at_ms: 3,
          receipt_sha256: hex64("proposal-receipt"),
          sources: [],
          proposal: {
            number: 12,
            url: "https://github.com/mastermindx-market-intelligence/macro/pull/12",
            head_commit: COMMIT,
            head_branch: "mmos-journey-1",
          },
        },
    advance: null,
  };
}

function planningReceipt(operationKey: string) {
  return {
    schema: DIRECT_RECEIPT_SCHEMA,
    intent_id: planningIntentId(operationKey, EXEC_SCOPE),
    fingerprint: FINGERPRINT,
    job_id: JOB,
    status: "RUNNING",
    accepted: true,
    duplicate: false,
    dispatched: false,
    authority: { requested: ["READ", "RESEARCH"], policy_sha256: POLICY, authority_level: "A0" },
    grounding: { mastermind_sha: MASTERMIND, macro_sha: COMMIT },
    created_at_ms: 5,
    work_ref: WORK_REF,
  };
}

function resultDocument(digest: string, consumed: boolean) {
  return {
    schema: RESULT_SCHEMA,
    selection: { work_ref: WORK_REF, job_id: JOB, attempt_id: ATTEMPT },
    availability: "AVAILABLE",
    reason_codes: [],
    result: {
      result_digest: digest,
      summary: "Initial planning produced a two step plan.",
      current_state: "The plan is ready for review.",
      completed_steps: ["Read the recorded project source.", "Draft the first wave."],
      next_actions: ["Confirm the plan or ask for a clarification pass."],
    },
    consumption: consumed
      ? { state: "CONSUMED", receipt_digest: CONSUME_RECEIPT }
      : { state: "UNCONSUMED", receipt_digest: null },
  };
}

function envelope(operation: string, data: unknown) {
  return { schema: PLANNING_RESULT_SCHEMA, operation, ok: true, data, error: null };
}

// ── store + harness ──────────────────────────────────────────────────────────

function memoryStore() {
  const pointers = new Map<string, OperationPointer>();
  const store: PendingPointerStore = {
    read: (scope) => pointers.get(scope) ?? null,
    reserve: (scope, pointer) => {
      const existing = pointers.get(scope);
      if (existing) return { reserved: false, pointer: existing };
      pointers.set(scope, pointer);
      return { reserved: true };
    },
    clearIfEqual: (scope, pointer) => {
      const existing = pointers.get(scope);
      if (
        !existing ||
        existing.operationKey !== pointer.operationKey ||
        existing.kind !== pointer.kind ||
        existing.targetKey !== pointer.targetKey
      ) {
        return false;
      }
      pointers.delete(scope);
      return true;
    },
  };
  return { store, pointers };
}

type Deferred = { promise: Promise<unknown>; resolve: (value: unknown) => void };

function deferred(value: unknown): Deferred {
  let resolve: (value: unknown) => void = () => undefined;
  const promise = new Promise<unknown>((done) => { resolve = done; });
  void promise.then(() => undefined, () => undefined);
  return { promise, resolve: (unknown) => resolve(unknown ?? value) };
}

/** The single pending create pointer of this journey, wherever it is stored. */
function storedPointer(store: Map<string, OperationPointer>): { scope: string; pointer: OperationPointer } | null {
  for (const scope of [WS_SCOPE, EXEC_SCOPE]) {
    const pointer = store.get(scope);
    if (pointer) return { scope, pointer };
  }
  return null;
}

interface Harness {
  owner: { current: OwnerContext };
  generation: { current: number };
  calls: {
    context: ReturnType<typeof vi.fn>;
    options: ReturnType<typeof vi.fn>;
    prepare: ReturnType<typeof vi.fn>;
    read: ReturnType<typeof vi.fn>;
    submit: ReturnType<typeof vi.fn>;
    reconcile: ReturnType<typeof vi.fn>;
    planning: ReturnType<typeof vi.fn>;
  };
  responses: {
    options: unknown;
    context: unknown;
    prepare: unknown;
    status: unknown;
    planning: Record<string, unknown>;
  };
  selections: Array<ProjectJourneySelection | null>;
  selectionAtEffect: {
    prepare: ProjectJourneySelection | null;
    planning: ProjectJourneySelection | null;
  };
  store: Map<string, OperationPointer>;
  unmount: () => void;
  remount: () => void;
}

let harnessRef: Harness | null = null;

/** The executive owner the harness host currently reports. */
function currentExecutive(): string {
  return harnessRef?.owner.current.principalScope ?? EXEC_SCOPE;
}

function makeHarness(initial?: {
  selection?: ProjectJourneySelection | null;
  goal?: string;
  locale?: "en" | "zh-CN";
}) {
  const ownerRef = { current: { principalScope: EXEC_SCOPE, generation: "1" } as OwnerContext };
  const generationRef = { current: 11 };
  const calls = {
    context: vi.fn(),
    options: vi.fn(),
    prepare: vi.fn(),
    read: vi.fn(),
    submit: vi.fn(),
    reconcile: vi.fn(),
    planning: vi.fn(),
  };
  const responses: Harness["responses"] = {
    options: optionsDocument(),
    context: null,
    prepare: null,
    status: null,
    planning: {},
  };
  const tracked: {
    selections: Array<ProjectJourneySelection | null>;
    latest: ProjectJourneySelection | null;
    goal: string;
    atEffect: { prepare: ProjectJourneySelection | null; planning: ProjectJourneySelection | null };
  } = {
    selections: [],
    latest: initial?.selection ?? null,
    goal: initial?.goal ?? GOAL,
    atEffect: { prepare: null, planning: null },
  };
  // The fixed context read is always served fresh: it reports the workspace of
  // the CURRENT acting executive, which is how a foreign principal is refused.
  const contextResponse = () => responses.context ?? contextDocument();

  const host = {
    auth: {
      getState: () => ({ status: "signed_in", reason: null, acquisition: true, content: true }),
      subscribe: () => () => undefined,
    },
    invalidationGeneration: () => generationRef.current,
    readSourceOperationContext: (request: unknown) => {
      calls.context(request);
      return Promise.resolve(contextResponse());
    },
    sourceOperations: {
      readProjectCreationOptions: (signal: AbortSignal) => {
        calls.options(signal);
        return Promise.resolve(responses.options);
      },
      prepareSourceOperation: (
        input: { action: string; request: Record<string, unknown> },
        signal: AbortSignal,
      ) => {
        calls.prepare(input, signal);
        tracked.atEffect.prepare = tracked.latest;
        const value = responses.prepare;
        if (value instanceof Error) return Promise.reject(value);
        if (value && typeof (value as Deferred).promise === "object") {
          return (value as Deferred).promise;
        }
        return Promise.resolve(value ?? previewDocument(input.request));
      },
      readSourceOperation: (input: unknown, signal: AbortSignal) => {
        calls.read(input, signal);
        const value = responses.status;
        if (value instanceof Error) return Promise.reject(value);
        if (value && typeof (value as Deferred).promise === "object") {
          return (value as Deferred).promise;
        }
        return Promise.resolve(value);
      },
      submitSourceOperation: (input: unknown, signal: AbortSignal) => {
        calls.submit(input, signal);
        const value = responses.status;
        if (value instanceof Error) return Promise.reject(value);
        if (value && typeof (value as Deferred).promise === "object") {
          return (value as Deferred).promise;
        }
        return Promise.resolve(value);
      },
      reconcileSourceOperation: (input: unknown, signal: AbortSignal) => {
        calls.reconcile(input, signal);
        const value = responses.status;
        if (value instanceof Error) return Promise.reject(value);
        if (value && typeof (value as Deferred).promise === "object") {
          return (value as Deferred).promise;
        }
        return Promise.resolve(value);
      },
    },
    projectPlanning: {
      request: (operation: string, args: Record<string, unknown>, signal: AbortSignal) => {
        calls.planning(operation, args, signal);
        if (operation === "submit") tracked.atEffect.planning = tracked.latest;
        const value = responses.planning[operation];
        if (value instanceof Error) return Promise.reject(value);
        if (value && typeof (value as Deferred).promise === "object") {
          return (value as Deferred).promise;
        }
        if (value !== undefined && value !== null) return Promise.resolve(value);
        const data =
          operation === "submit" || operation === "status"
            ? planningReceipt(String(args.operation_key))
            : operation === "result"
              ? resultDocument(PLAN_DIGEST, false)
              : resultDocument(PLAN_DIGEST, true);
        return Promise.resolve(envelope(operation, data));
      },
    },
  };

  const { store, pointers } = memoryStore();

  function View() {
    const [selection, setSelection] = useState<ProjectJourneySelection | null>(() => tracked.latest);
    const [goal, setGoal] = useState<string>(() => tracked.goal);
    tracked.selections.push(selection);
    return (
      <ProjectPlanningJourney
        locale={initial?.locale ?? "en"}
        host={host as unknown as MissionHost}
        executiveOwner={() => ownerRef.current}
        store={store}
        onSelection={(value) => {
          tracked.latest = value;
          setSelection(value);
        }}
        selection={selection}
        goal={goal}
        onGoalChange={(value) => {
          tracked.goal = value;
          setGoal(value);
        }}
      />
    );
  }

  let mounted: RenderResult | null = null;
  const mountNow = () => { mounted = render(<View />); };
  mountNow();

  return {
    owner: ownerRef,
    generation: generationRef,
    calls,
    responses,
    selections: tracked.selections,
    selectionAtEffect: tracked.atEffect,
    store: pointers,
    unmount: () => {
      mounted?.unmount();
      mounted = null;
    },
    remount: () => {
      mounted?.unmount();
      mountNow();
    },
  };
}

// ── step helpers ─────────────────────────────────────────────────────────────

async function loadOptionsAndProfile() {
  fireEvent.click(screen.getByRole("button", { name: "Options" }));
  fireEvent.click(screen.getByRole("button", { name: "Load project options" }));
  const radio = await waitFor(() => screen.getByRole("radio", { name: "Balanced" }));
  expect(screen.getByText("Balanced source profile.")).toBeTruthy();
  fireEvent.click(radio);
}

async function preparePreview() {
  fireEvent.click(screen.getByRole("button", { name: "Prepare preview" }));
  await waitFor(() => screen.getByRole("button", { name: "Create project" }));
}

async function runToReadableProject(): Promise<{ requestId: string; planningKey: string }> {
  const h = harnessRef as Harness;
  await loadOptionsAndProfile();
  await preparePreview();
  const requestId = (h.calls.prepare.mock.calls[0][0] as { request: { request_id: string } }).request.request_id;
  h.responses.status = statusDocument(requestId, "SOURCE_OBSERVED");
  fireEvent.click(screen.getByRole("button", { name: "Create project" }));
  await waitFor(() => expect(screen.getAllByText("Project created.")).toBeTruthy());
  fireEvent.click(screen.getByRole("radio", { name: "Plan" }));
  fireEvent.click(screen.getByRole("button", { name: "Send initial planning request" }));
  await waitFor(() => expect(h.selections.at(-1)?.jobId).toBe(JOB));
  const submitCall = h.calls.planning.mock.calls.find((call) => call[0] === "submit") as unknown as [
    string,
    Record<string, unknown>,
  ];
  return { requestId, planningKey: String(submitCall[1].operation_key) };
}

// ── tests ────────────────────────────────────────────────────────────────────

describe("ProjectPlanningJourney", () => {
  it("mounts with no read, no effect and no invented offer", () => {
    const h = makeHarness();
    harnessRef = h;
    expect(screen.getByLabelText("Your goal")).toBeTruthy();
    expect((screen.getByLabelText("Your goal") as HTMLTextAreaElement).value).toBe(GOAL);
    expect(screen.queryByRole("button", { name: "Create project" })).toBeNull();
    expect(screen.queryByText("Initial planning")).toBeNull();
    expect(h.calls.options).not.toHaveBeenCalled();
    expect(h.calls.context).not.toHaveBeenCalled();
    expect(h.calls.prepare).not.toHaveBeenCalled();
    expect(h.calls.read).not.toHaveBeenCalled();
    expect(h.calls.submit).not.toHaveBeenCalled();
    expect(h.calls.reconcile).not.toHaveBeenCalled();
    expect(h.calls.planning).not.toHaveBeenCalled();
    expect(h.selections.every((entry) => entry === null)).toBe(true);
    expect(h.store.size).toBe(0);
  });

  it("runs the whole explicit journey over distinct workspace and executive scopes", async () => {
    const h = makeHarness();
    harnessRef = h;
    await loadOptionsAndProfile();

    // The context read binds the Workspace scope from the exact fixed DTO; the
    // options are only DATA and never mint a scope of their own.
    expect(h.calls.context).toHaveBeenCalledTimes(1);
    expect(h.calls.context.mock.calls[0][0]).toMatchObject({
      action: "publish_project_proposal",
      workRef: null,
    });
    expect(h.calls.options).toHaveBeenCalledTimes(1);

    await preparePreview();
    expect(h.calls.prepare).toHaveBeenCalledTimes(1);
    const prepareFrame = h.calls.prepare.mock.calls[0][0] as {
      action: string;
      request: Record<string, unknown>;
    };
    expect(prepareFrame.action).toBe("publish_project_proposal");
    expect(prepareFrame.request).toEqual(previewRequest(String(prepareFrame.request.request_id)));
    expect(String(prepareFrame.request.request_id)).toMatch(/^mmos-project-create-[0-9a-f]{40}$/);
    // The minted identity reached the parent selection BEFORE the prepare effect.
    expect(h.selectionAtEffect.prepare).toMatchObject({
      createRequestId: prepareFrame.request.request_id,
      workRef: null,
      planningOperationKey: null,
      jobId: null,
    });
    await waitFor(() =>
      expect(screen.getByText("Preview ready. Create this project to continue.")).toBeTruthy(),
    );

    // Publishing reserves a durable pending hint BEFORE the source submit.
    // The first observation is a pending source proposal, never a started
    // project. The hint sits under exactly one resource-specific scope; the
    // test does not demand which controller topology placed it there, only
    // that it exists once with safe identifiers and is not duplicated.
    h.responses.status = statusDocument(String(prepareFrame.request.request_id), "PROPOSAL_OBSERVED");
    fireEvent.click(screen.getByRole("button", { name: "Create project" }));
    await waitFor(() => expect(h.calls.submit).toHaveBeenCalledTimes(1));
    const submitFrame = h.calls.submit.mock.calls[0][0] as {
      action: string;
      request_id: string;
      work_ref: string;
      preview_witness: Record<string, unknown>;
    };
    expect(submitFrame.action).toBe("publish_project_proposal");
    expect(submitFrame.request_id).toBe(prepareFrame.request.request_id);
    expect(submitFrame.work_ref).toBe(WORK_REF);
    expect(Object.keys(submitFrame.preview_witness).sort()).toEqual([
      "original_input",
      "recipe_fingerprint_sha256",
    ]);
    await waitFor(() => {
      const placed = storedPointer(h.store);
      expect(placed).not.toBeNull();
      expect(placed!.pointer.kind).toBe("project_create");
      expect(JSON.parse(placed!.pointer.targetKey as string)).toEqual({
        request_id: submitFrame.request_id,
        work_ref: WORK_REF,
      });
      return true;
    });
    // No second copy of the hint under the other resource scope.
    const placedScope = storedPointer(h.store)!.scope;
    const otherScope = placedScope === WS_SCOPE ? EXEC_SCOPE : WS_SCOPE;
    expect(h.store.has(otherScope)).toBe(false);
    await waitFor(() =>
      expect(screen.getByText("Project creation is still pending. Check the original request.")).toBeTruthy(),
    );
    expect(h.selections.at(-1)?.workRef).toBeNull();

    // Explicit publication check: reconcile only, on the same original hint.
    h.responses.status = statusDocument(submitFrame.request_id, "SOURCE_OBSERVED");
    fireEvent.click(screen.getByRole("button", { name: "Check project creation" }));
    await waitFor(() => expect(h.calls.reconcile).toHaveBeenCalledTimes(1));
    expect(h.calls.reconcile.mock.calls[0][0]).toEqual({
      schema: "mastermind.workspace_source_operation_lookup.v1",
      action: "publish_project_proposal",
      request_id: submitFrame.request_id,
      work_ref: WORK_REF,
    });
    await waitFor(() => expect(screen.getAllByText("Project created.")).toBeTruthy());
    expect(h.store.size).toBe(0);
    expect(h.selections.at(-1)).toEqual({
      createRequestId: submitFrame.request_id,
      workRef: WORK_REF,
      planningOperationKey: null,
      jobId: null,
    });

    // Initial planning is explicit: stage choice, unsent request text, one
    // admission key bound to the EXECUTIVE owner, with the publication and
    // project source carried from the observed Workspace-scoped status.
    expect(screen.getByText("Initial planning")).toBeTruthy();
    fireEvent.click(screen.getByRole("radio", { name: "Plan" }));
    const request = screen.getByLabelText("Initial request") as HTMLTextAreaElement;
    expect(request.value).toBe(GOAL);
    fireEvent.change(request, { target: { value: REQUEST_TEXT } });
    fireEvent.click(screen.getByRole("button", { name: "Send initial planning request" }));
    await waitFor(() => expect(h.calls.planning).toHaveBeenCalledTimes(1));
    const [operation, args] = h.calls.planning.mock.calls[0];
    expect(operation).toBe("submit");
    expect(Object.keys(args as Record<string, unknown>).sort()).toEqual([
      "grounding",
      "operation_key",
      "private_request",
      "project_source",
      "publication",
      "stage",
      "work_ref",
    ]);
    const submitArgs = args as Record<string, unknown>;
    expect(submitArgs.stage).toBe("plan");
    expect(submitArgs.work_ref).toBe(WORK_REF);
    expect(submitArgs.private_request).toBe(REQUEST_TEXT);
    // Grounding macro is the OBSERVED create commit, never the option value.
    expect(submitArgs.grounding).toEqual({ mastermind_sha: MASTERMIND, macro_sha: COMMIT });
    expect(submitArgs.project_source).toEqual({
      repository: "macro",
      commit: COMMIT,
      path: SOURCE_PATH,
      content_sha256: CONTENT,
      request_sha256: RECIPE,
    });
    // The publication reference keeps the WORKSPACE scope of the observed
    // status; it is never rewritten to the executive owner scope.
    expect(submitArgs.publication).toEqual({
      request_id: submitFrame.request_id,
      principal_scope: WS_SCOPE,
      event_id: 9,
      receipt_sha256: hex64("receipt"),
    });
    const planningKey = planningOperationKey(
      { principalScope: EXEC_SCOPE, generation: "1" },
      {
        stage: "plan",
        work_ref: WORK_REF,
        project_source: submitArgs.project_source as Record<string, unknown>,
        publication: submitArgs.publication as Record<string, unknown>,
        grounding: submitArgs.grounding as Record<string, unknown>,
        private_request: REQUEST_TEXT,
      },
    );
    expect(submitArgs.operation_key).toBe(planningKey);
    // The planning key was recorded on the shared selection BEFORE dispatch.
    expect(h.selectionAtEffect.planning).toMatchObject({
      planningOperationKey: planningKey,
      workRef: WORK_REF,
      jobId: null,
    });
    await waitFor(() => expect(h.selections.at(-1)?.jobId).toBe(JOB));
    expect(h.store.size).toBe(0);

    // Result read only: same admission key and work reference, no attempt guess.
    fireEvent.click(screen.getByRole("button", { name: "Read planning result" }));
    await waitFor(() => expect(h.calls.planning.mock.calls.length).toBeGreaterThanOrEqual(2));
    const resultCall = h.calls.planning.mock.calls.at(-1) as unknown as [string, Record<string, unknown>];
    expect(resultCall[0]).toBe("result");
    expect(resultCall[1]).toEqual({ operation_key: planningKey, work_ref: WORK_REF });
    await waitFor(() => expect(screen.getByText("Initial planning produced a two step plan.")).toBeTruthy());
    expect(screen.getByText("Confirm the plan or ask for a clarification pass.")).toBeTruthy();
    expect(screen.queryByText("This result is kept.")).toBeNull();

    // Explicit keep: the consume transport sends the ORIGINAL planning key in
    // operation_key and a SEPARATE deterministic acknowledgment key in
    // consumption_operation_key; the two are never equal. The keep answer here
    // describes a different digest, so nothing is ever kept.
    h.responses.planning.consume = envelope("consume", resultDocument(hex64("other-plan"), true));
    fireEvent.click(screen.getByRole("button", { name: "Keep result" }));
    await waitFor(() => expect(h.calls.planning.mock.calls.at(-1)?.[0]).toBe("consume"));
    const consumeCall = h.calls.planning.mock.calls.at(-1) as unknown as [string, Record<string, unknown>];
    expect(consumeCall[0]).toBe("consume");
    const consumeArgs = consumeCall[1] as Record<string, unknown>;
    expect(consumeArgs.operation_key).toBe(planningKey);
    expect(String(consumeArgs.consumption_operation_key)).toMatch(/^mmos-consume-[0-9a-f]{40}$/);
    expect(consumeArgs.consumption_operation_key).not.toBe(planningKey);
    expect(consumeArgs).toMatchObject({ work_ref: WORK_REF, attempt_id: ATTEMPT, result_digest: PLAN_DIGEST });
    await waitFor(() => expect(screen.getByText("unknown UNKNOWN_RECEIPT")).toBeTruthy());
    expect(screen.queryByText("This result is kept.")).toBeNull();
    // The exact keep stays pending on the original pointer for recovery, and
    // the pending hint IS the acknowledgment key: deterministic, not reminted.
    const pointer = h.store.get(EXEC_SCOPE) as OperationPointer;
    expect(pointer).not.toBeUndefined();
    expect(pointer.kind).toBe("consume");
    expect(pointer.operationKey).toBe(String(consumeArgs.consumption_operation_key));
    expect(JSON.parse(pointer.targetKey as string)).toEqual({
      work_ref: WORK_REF,
      job_id: JOB,
      attempt_id: ATTEMPT,
      result_digest: PLAN_DIGEST,
    });
    expect(h.selections.at(-1)).toMatchObject({
      createRequestId: submitFrame.request_id,
      workRef: WORK_REF,
      planningOperationKey: planningKey,
      jobId: JOB,
    });
  });

  it("binds the scope only from the fixed context DTO and refuses a flat fallback", async () => {
    const h = makeHarness();
    harnessRef = h;
    // A flat owner-context object is not the fixed envelope: no scope is
    // bound, no options are fetched and nothing else runs.
    h.responses.context = { principal_scope: WS_SCOPE };
    fireEvent.click(screen.getByRole("button", { name: "Options" }));
    fireEvent.click(screen.getByRole("button", { name: "Load project options" }));
    await waitFor(() =>
      expect(screen.getByText("The source identity context is unavailable, so no scope was bound.")).toBeTruthy(),
    );
    expect(h.calls.context).toHaveBeenCalledTimes(1);
    expect(h.calls.options).not.toHaveBeenCalled();
    expect(h.calls.prepare).not.toHaveBeenCalled();
    expect(screen.queryByRole("radio", { name: "Balanced" })).toBeNull();

    // An envelope with a different original selection is equally refused.
    h.responses.context = {
      ...contextDocument(),
      selection: { action: "ADOPT_PLAN", work_ref: WORK_REF },
    };
    fireEvent.click(screen.getByRole("button", { name: "Load project options" }));
    await waitFor(() =>
      expect(screen.getByText("The source identity context is unavailable, so no scope was bound.")).toBeTruthy(),
    );
    expect(h.calls.options).not.toHaveBeenCalled();
    expect(h.store.size).toBe(0);
  });

  it("keeps the selection after a lost preview and reopens by status without a second prepare", async () => {
    const h = makeHarness();
    harnessRef = h;
    h.responses.prepare = new Error("SOURCE_OPERATION_REQUEST_INVALID");
    await loadOptionsAndProfile();
    fireEvent.click(screen.getByRole("button", { name: "Prepare preview" }));
    await waitFor(() =>
      expect(screen.getByText("The source preview could not be verified, so nothing was offered.")).toBeTruthy(),
    );
    const minted = h.selections.at(-1) as ProjectJourneySelection;
    expect(minted.createRequestId).toMatch(/^mmos-project-create-[0-9a-f]{40}$/);
    expect(minted.workRef).toBeNull();
    expect(screen.queryByRole("button", { name: "Create project" })).toBeNull();

    // Status reopen reads the original operation with a null work reference
    // and never prepares the same draft again.
    h.responses.status = statusDocument(minted.createRequestId, "SOURCE_OBSERVED");
    fireEvent.click(screen.getByRole("button", { name: "Check original project request" }));
    await waitFor(() => expect(h.calls.read).toHaveBeenCalledTimes(1));
    expect(h.calls.prepare).toHaveBeenCalledTimes(1);
    expect(h.calls.read.mock.calls[0][0]).toEqual({
      schema: "mastermind.workspace_source_operation_lookup.v1",
      action: "publish_project_proposal",
      request_id: minted.createRequestId,
      work_ref: null,
    });
    await waitFor(() => expect(screen.getAllByText("Project created.")).toBeTruthy());
    expect(h.selections.at(-1)).toMatchObject({
      createRequestId: minted.createRequestId,
      workRef: WORK_REF,
      planningOperationKey: null,
      jobId: null,
    });
    expect(h.store.size).toBe(0);
    // The reopened project is a real readable project for the supplied slots.
    expect(screen.getByText("Initial planning")).toBeTruthy();
  });

  it("suppresses a late receipt after an auth change and recovers under a monotonic epoch", async () => {
    const h = makeHarness();
    harnessRef = h;
    await loadOptionsAndProfile();
    await preparePreview();
    const requestId = (h.calls.prepare.mock.calls[0][0] as { request: { request_id: string } }).request.request_id;

    // Hold the submit open, move the auth epoch, then deliver the receipt.
    const pending = deferred(statusDocument(requestId, "SOURCE_OBSERVED"));
    h.responses.status = pending;
    fireEvent.click(screen.getByRole("button", { name: "Create project" }));
    await waitFor(() => expect(h.calls.submit).toHaveBeenCalledTimes(1));
    expect(storedPointer(h.store)).not.toBeNull();
    const hintScope = storedPointer(h.store)!.scope;
    h.owner.current = { principalScope: EXEC_SCOPE, generation: "2" };
    h.generation.current = 12;
    pending.resolve(statusDocument(requestId, "SOURCE_OBSERVED"));
    await waitFor(() => expect(screen.getByText("idle EPOCH_CHANGED")).toBeTruthy());
    // The late receipt never moved the selection and never claimed a project.
    expect(h.selections.at(-1)?.workRef).toBeNull();
    expect(screen.queryByText("Project created.")).toBeNull();
    // The original hint is still durably held for a later recover.
    expect(h.store.get(hintScope)).not.toBeUndefined();

    // A different executive cannot observe or resolve the original hint: its
    // own workspace is a different opaque scope, and the context read served
    // fresh under it reports that other workspace.
    h.owner.current = { principalScope: EXEC_SCOPE_B, generation: "3" };
    h.generation.current = 13;
    h.responses.status = statusDocument(requestId, "SOURCE_OBSERVED");
    fireEvent.click(screen.getByRole("button", { name: "Check original project request" }));
    await waitFor(() => expect(h.calls.context.mock.calls.length).toBeGreaterThanOrEqual(2));
    await waitFor(() =>
      expect(screen.getByText("The source status read is unavailable right now.")).toBeTruthy(),
    );
    expect(h.selections.at(-1)?.workRef).toBeNull();
    expect(screen.queryByText("Project created.")).toBeNull();
    expect(h.store.get(hintScope)).not.toBeUndefined();

    // The original executive returns on a third generation and resolves it.
    h.owner.current = { principalScope: EXEC_SCOPE, generation: "4" };
    h.generation.current = 14;
    fireEvent.click(screen.getByRole("button", { name: "Check original project request" }));
    await waitFor(() => expect(screen.getAllByText("Project created.")).toBeTruthy());
    expect(h.selections.at(-1)).toMatchObject({ createRequestId: requestId, workRef: WORK_REF });
    expect(h.store.size).toBe(0);
  });

  it("refuses a foreign workspace preview, a foreign status and never conflates the scopes", async () => {
    const h = makeHarness();
    harnessRef = h;
    await loadOptionsAndProfile();

    // A preview bound to another workspace scope is never offered, even
    // though the acting executive owner is present and valid.
    h.responses.prepare = {
      ...previewDocument(previewRequest("mmos-project-create-" + "0".repeat(40))),
      owner_context: { principal_scope: WS_SCOPE_B },
    };
    fireEvent.click(screen.getByRole("button", { name: "Prepare preview" }));
    await waitFor(() => expect(h.calls.prepare).toHaveBeenCalledTimes(1));
    await waitFor(() =>
      expect(screen.getByText("The source preview could not be verified, so nothing was offered.")).toBeTruthy(),
    );
    expect(screen.queryByRole("button", { name: "Create project" })).toBeNull();
    const minted = h.selections.at(-1) as ProjectJourneySelection;

    // A status describing another original request is never this operation.
    h.responses.prepare = null;
    h.responses.status = statusDocument("mmos-project-create-" + "f".repeat(40), "SOURCE_OBSERVED");
    fireEvent.click(screen.getByRole("button", { name: "Check original project request" }));
    await waitFor(() => expect(h.calls.read).toHaveBeenCalledTimes(1));
    await waitFor(() =>
      expect(screen.getByText("The source status read is unavailable right now.")).toBeTruthy(),
    );
    expect(h.selections.at(-1)).toEqual(minted);
    expect(screen.queryByText("Project created.")).toBeNull();
    expect(h.store.size).toBe(0);
  });

  it("reuses the same acknowledgment key on an unknown keep and settles it by the original pointer", async () => {
    const h = makeHarness();
    harnessRef = h;
    const { requestId, planningKey } = await runToReadableProject();
    void requestId;
    fireEvent.click(screen.getByRole("button", { name: "Read planning result" }));
    await waitFor(() => expect(screen.getByText("Initial planning produced a two step plan.")).toBeTruthy());

    // The keep answer describes a different digest: never accepted. The one
    // consume frame still carries the ORIGINAL planning key plus a separate
    // deterministic acknowledgment key.
    h.responses.planning.consume = envelope("consume", resultDocument(hex64("other-plan"), true));
    fireEvent.click(screen.getByRole("button", { name: "Keep result" }));
    await waitFor(() => expect(h.calls.planning.mock.calls.at(-1)?.[0]).toBe("consume"));
    const consumeFrame = h.calls.planning.mock.calls.at(-1) as unknown as [string, Record<string, unknown>];
    const ackKey = String((consumeFrame[1] as Record<string, unknown>).consumption_operation_key);
    expect((consumeFrame[1] as Record<string, unknown>).operation_key).toBe(planningKey);
    expect(ackKey).toMatch(/^mmos-consume-[0-9a-f]{40}$/);
    expect(ackKey).not.toBe(planningKey);
    await waitFor(() => expect(screen.getByText("unknown UNKNOWN_RECEIPT")).toBeTruthy());
    expect(screen.queryByText("This result is kept.")).toBeNull();

    // The exact keep stays pending on the original pointer for recovery, and
    // the pending hint IS the acknowledgment key: deterministic, not reminted.
    const pointer = h.store.get(EXEC_SCOPE) as OperationPointer;
    expect(pointer).not.toBeUndefined();
    expect(pointer.kind).toBe("consume");
    expect(pointer.operationKey).toBe(ackKey);
    expect(JSON.parse(pointer.targetKey as string)).toEqual({
      work_ref: WORK_REF,
      job_id: JOB,
      attempt_id: ATTEMPT,
      result_digest: PLAN_DIGEST,
    });

    // The unknown keep is read on the SAME original pointer and digest with
    // the ORIGINAL planning key; the acknowledgment key is reused untouched.
    delete h.responses.planning.consume;
    h.responses.planning.result = envelope("result", resultDocument(PLAN_DIGEST, true));
    fireEvent.click(screen.getByRole("button", { name: "Check keep status" }));
    await waitFor(() => expect(screen.getByText("This result is kept.")).toBeTruthy());
    expect(h.store.size).toBe(0);
    const recovery = h.calls.planning.mock.calls.at(-1) as unknown as [string, Record<string, unknown>];
    expect(recovery[0]).toBe("result");
    expect(recovery[1]).toEqual({ operation_key: planningKey, work_ref: WORK_REF });
    // Recovery was a read only: no second consume was ever sent.
    expect(h.calls.planning.mock.calls.filter((call) => call[0] === "consume").length).toBe(1);
  });

  it("recovers the original planning job after a lost submit reply across reopen with no second submit", async () => {
    const h = makeHarness();
    harnessRef = h;
    await loadOptionsAndProfile();
    await preparePreview();
    const requestId = (h.calls.prepare.mock.calls[0][0] as { request: { request_id: string } }).request.request_id;
    h.responses.status = statusDocument(requestId, "SOURCE_OBSERVED");
    fireEvent.click(screen.getByRole("button", { name: "Create project" }));
    await waitFor(() => expect(screen.getAllByText("Project created.")).toBeTruthy());
    fireEvent.click(screen.getByRole("radio", { name: "Plan" }));

    // Hold the planning submit reply open so it is lost across the unmount.
    const pending = deferred(null);
    h.responses.planning.submit = pending;
    fireEvent.click(screen.getByRole("button", { name: "Send initial planning request" }));
    await waitFor(() => expect(h.calls.planning.mock.calls.length).toBe(1));
    expect(h.calls.planning.mock.calls[0][0]).toBe("submit");
    const planningKey = String((h.calls.planning.mock.calls[0][1] as Record<string, unknown>).operation_key);
    const selectionBefore = h.selections.at(-1) as ProjectJourneySelection;
    // The admission key was recorded on the shared selection BEFORE dispatch;
    // the job is unknown while the reply is lost.
    expect(selectionBefore).toMatchObject({
      createRequestId: requestId,
      workRef: WORK_REF,
      planningOperationKey: planningKey,
      jobId: null,
    });

    h.unmount();

    // The durable pending admission hint survived the unmount under the
    // executive resource scope, keyed by the ORIGINAL planning key.
    const pointer = h.store.get(EXEC_SCOPE) as OperationPointer;
    expect(pointer).not.toBeUndefined();
    expect(pointer.kind).toBe("launch");
    expect(pointer.operationKey).toBe(planningKey);

    h.remount();

    // Explicit check of the initial request status on reopen recovers the
    // original job: one status read on the same key, never a second submit.
    fireEvent.click(screen.getByRole("button", { name: "Check planning status" }));
    await waitFor(() => expect(h.selections.at(-1)?.jobId).toBe(JOB));
    const statusCalls = h.calls.planning.mock.calls.filter((call) => call[0] === "status");
    expect(statusCalls.length).toBe(1);
    expect(statusCalls[0][1]).toEqual({ operation_key: planningKey, work_ref: WORK_REF });
    expect(h.calls.planning.mock.calls.filter((call) => call[0] === "submit").length).toBe(1);
    // The recovered hint is settled: no pending pointer remains.
    expect(h.store.size).toBe(0);

    // Re-observe the source record so the readable project slots return; the
    // recovered job keeps the honest admission-only line. Then read the
    // result of the ORIGINAL admission key.
    h.responses.status = statusDocument(requestId, "SOURCE_OBSERVED");
    fireEvent.click(screen.getByRole("button", { name: "Check original project request" }));
    await waitFor(() => screen.getByRole("button", { name: "Read planning result" }));
    expect(screen.getByText("Planning request accepted.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Read planning result" }));
    await waitFor(() => expect(screen.getByText("Initial planning produced a two step plan.")).toBeTruthy());
    const resultCalls = h.calls.planning.mock.calls.filter((call) => call[0] === "result");
    expect(resultCalls.length).toBe(1);
    expect(resultCalls[0][1]).toEqual({ operation_key: planningKey, work_ref: WORK_REF });

    // The late lost reply arrives now carrying a different job: it is stale,
    // so the recovered job stands and no further frame is ever sent.
    pending.resolve(envelope("submit", { ...planningReceipt(planningKey), job_id: JOB_OTHER }));
    await new Promise((done) => setTimeout(done, 20));
    expect(h.selections.at(-1)?.jobId).toBe(JOB);
    expect(h.calls.planning.mock.calls.filter((call) => call[0] === "submit").length).toBe(1);
    expect(h.store.size).toBe(0);
  });

  it("renders the same actions in Chinese over the same closed contract", async () => {
    const h = makeHarness({ locale: "zh-CN" });
    harnessRef = h;
    expect(screen.getByLabelText("你的目标")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "选项" }));
    fireEvent.click(screen.getByRole("button", { name: "载入项目选项" }));
    const radio = await waitFor(() => screen.getByRole("radio", { name: "均衡" }));
    fireEvent.click(radio);
    fireEvent.click(screen.getByRole("button", { name: "准备预览" }));
    await waitFor(() => expect(h.calls.prepare).toHaveBeenCalledTimes(1));
    await waitFor(() => screen.getByRole("button", { name: "创建项目" }));
    expect(screen.getByText("预览已准备好。创建项目后继续。")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Create project" })).toBeNull();
    expect(screen.getByText("创建项目；规划是独立的后续步骤。")).toBeTruthy();
  });
});

// Exact immutable operands from the real installed/signature/AF_UNIX recorder.
// Only the Host boundary below is a fixture; raw supplied records stay untouched.
it.each(["en", "zh-CN"] as const)("uses canonical installed profile labels and issued revision in %s", async locale => {
  const h=makeHarness({goal:sourceIssued.consumer_inputs.create_goal,locale});harnessRef=h;
  const options=sourceIssued.samples[1].response;
  h.responses.options=options;h.responses.context=sourceIssued.samples[0].response;
  h.responses.prepare=sourceIssued.samples[2].response;
  vi.spyOn(crypto,"getRandomValues").mockImplementation(array=>{(array as Uint8Array).fill(0xbb);return array;});
  fireEvent.click(screen.getByRole("button",{name:locale==="en"?"Options":"选项"}));
  fireEvent.click(screen.getByRole("button",{name:locale==="en"?"Load project options":"载入项目选项"}));
  const label=locale==="en"?"Mastermind OS delivery":"Mastermind OS 交付";
  const radio=await screen.findByRole("radio",{name:label});fireEvent.click(radio);
  fireEvent.click(screen.getByRole("button",{name:locale==="en"?"Prepare preview":"准备预览"}));
  await screen.findByRole("button",{name:locale==="en"?"Create project":"创建项目"});
  expect(h.calls.prepare.mock.calls[0][0]).toEqual(sourceIssued.samples[2].request);
  expect(h.calls.prepare.mock.calls[0][0].request.profile_sha256).toBe(options.profiles![0].revision);
  expect(h.calls.submit).not.toHaveBeenCalled();
});

it.each(["legacy", "mixed", "extra", "missing", "nontext"])("refuses %s installed profile label shape without prepare", async variant => {
  const h=makeHarness();harnessRef=h;
  const options=structuredClone(sourceIssued.samples[1].response);
  const profile=options.profiles![0] as unknown as Record<string,unknown>;
  const actual=profile.label as Record<string,unknown>;
  profile.label=variant==="legacy"?{en:actual.en,"zh-CN":actual.zhCN}:variant==="mixed"?{...actual,"zh-CN":actual.zhCN}:variant==="extra"?{...actual,other:"x"}:variant==="missing"?{en:actual.en}:{en:actual.en,zhCN:42};
  h.responses.context=sourceIssued.samples[0].response;h.responses.options=options;
  fireEvent.click(screen.getByRole("button",{name:"Options"}));
  fireEvent.click(screen.getByRole("button",{name:"Load project options"}));
  await screen.findByText("The supplied project options are unavailable right now.");
  expect(screen.queryByRole("radio",{name:"Mastermind OS delivery"})).toBeNull();
  expect(h.calls.prepare).not.toHaveBeenCalled();
});

it.each(["en","zh-CN"] as const)("keeps the exact explicit plan declaration in closed Source details in %s",async locale=>{
  const recorded=sourceIssued.samples[8].response;
  const data=recorded.data! as unknown as ReturnType<typeof resultDocument>;
  const h=makeHarness({locale,selection:{createRequestId:sourceIssued.identities.creation_request_id,
    workRef:data.selection.work_ref,jobId:data.selection.job_id,
    planningOperationKey:sourceIssued.identities.planning_operation_key}});
  harnessRef=h;h.responses.planning.result=recorded;
  fireEvent.click(screen.getByRole("button",{name:locale==="en"?"Read planning result":"读取规划结果"}));
  await screen.findByText(data.result!.summary);
  const resultRegion=screen.getByRole("region",{name:locale==="en"?"Planning result":"规划结果"});
  expect(within(resultRegion).queryByText(data.result!.current_state)).toBeNull();
  const raw=screen.getByText(data.result!.current_state,{exact:true});
  const details=raw.closest("details")!;
  expect(details).not.toBeNull();expect(details.open).toBe(false);
  expect(details.querySelector("summary")?.textContent).toBe(locale==="en"?"Source details":"来源详情");
  expect(screen.getByRole("button",{name:locale==="en"?"Keep result":"保留结果"})).toBeTruthy();
  expect(h.calls.planning.mock.calls.map(row=>row[0])).toEqual(["result"]);
});
it.each(["ordinary prose","foreign declaration","malformed declaration","duplicate declaration"])("keeps %s current state readable",async variant=>{
  const recorded=structuredClone(sourceIssued.samples[8].response);
  const data=recorded.data! as unknown as ReturnType<typeof resultDocument>;
  const declaration=JSON.parse(data.result!.current_state);
  const text=variant==="ordinary prose"?"The returned research still needs review.":variant==="foreign declaration"?
    JSON.stringify({...declaration,work_ref:"WS:FOREIGN"}):variant==="duplicate declaration"?
    data.result!.current_state.replace('"work_ref":','"work_ref":"WS:FOREIGN","work_ref":') : "{invalid declaration";
  data.result!.current_state=text;
  const h=makeHarness({selection:{createRequestId:sourceIssued.identities.creation_request_id,
    workRef:data.selection.work_ref,jobId:data.selection.job_id,planningOperationKey:sourceIssued.identities.planning_operation_key}});
  harnessRef=h;h.responses.planning.result=recorded;
  fireEvent.click(screen.getByRole("button",{name:"Read planning result"}));
  const raw=await screen.findByText(text,{exact:true});expect(raw.closest("details")).toBeNull();
  expect(h.calls.planning.mock.calls.map(row=>row[0])).toEqual(["result"]);
});

it("reopens the original planning request with its existing read action first",async()=>{
  const row=sourceIssued.samples[7];
  const h=makeHarness({selection:{createRequestId:sourceIssued.identities.creation_request_id,
    workRef:sourceIssued.identities.work_ref,jobId:null,planningOperationKey:sourceIssued.identities.planning_operation_key}});
  harnessRef=h;h.owner.current={principalScope:sourceIssued.identities.executive_context.principal_scope,generation:"fixture"};
  h.responses.planning.status=row.response;
  expect(h.calls.planning).not.toHaveBeenCalled();
  expect(screen.getAllByText("Check the original planning request. Do not send it again.").length).toBeGreaterThan(0);
  fireEvent.click(screen.getByRole("button",{name:"Check original planning request"}));
  await waitFor(()=>expect(h.calls.planning.mock.calls.map(row=>row[0])).toEqual(["status"]));
  expect(h.calls.planning.mock.calls[0][1]).toEqual(row.request.arguments);
  expect(h.calls.prepare).not.toHaveBeenCalled();expect(h.calls.submit).not.toHaveBeenCalled();
});
