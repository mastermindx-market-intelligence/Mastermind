// @vitest-environment jsdom
// @vitest-environment-options {"url":"https://mcp.mastermind-x.com/os/"}
/**
 * App-mounted New project journey integration acceptance.
 *
 * The REAL App is rendered over a REAL mounted Host: createNativeClient ->
 * composeMissionHost (bindMissionHost) with the genuine ProjectPlanningJourney
 * component, its Journey/Create ports, the incumbent OperationController and
 * the shared durable pending-pointer store (fake-indexeddb). Only the native
 * invoke/listen boundary and the external read DATA are fixtures; Journey,
 * ports, controller, decoders and auth-current guards are never mocked or
 * substituted. Workspace (source) scope and Executive owner scope keep the
 * distinct opaque fixture values; no case equates or derives one from the
 * other, and no case makes the App pass by collapsing them.
 */
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { IDBFactory } from "fake-indexeddb";
import { App } from "./App";
import { createNativeClient } from "./host";
import { composeMissionHost } from "./compose-mission-host";
import { decodeLaunchBindingConfig } from "./launch-config";
import { readOwnerContext } from "./orchestration/host-command-bindings";
import { canonicalJson, intentIdForOperationKey, sha256Hex } from "./orchestration/operation-key";
import programsFixture from "./fixtures/programs-available-workspace-service.json";
import planFixture from "./fixtures/project-plan-canonical-owner.json";
import { controlRoomFixture } from "./test-fixtures";
import {
  planningIntentId,
  planningOperationKey,
  type PlanningSubmitInput,
} from "./planning/project-planning-command-port";

let dispose = () => {};
afterEach(() => {
  cleanup();
  dispose();
  delete window.MastermindMissionHost;
  history.replaceState(null, "", "/os/");
});

// ── accepted fixture identity: distinct Workspace and Executive scopes ──────

const WS_SCOPE = "a".repeat(64);
const EXEC_SCOPE = "c".repeat(64);
const MACRO = "1".repeat(40);
const MASTERMIND = "2".repeat(40);
const COMMIT = "3".repeat(40);
const CONTENT = "4".repeat(64);
const RECIPE = "6".repeat(64);
const POLICY = "8".repeat(64);
const FINGERPRINT = "9".repeat(64);
const PROFILE_REVISION = "aa".repeat(32);
const WORK_REF = "WS:JOURNEY1";
const SOURCE_PATH = "agentos/workstreams/WS-JOURNEY1.md";
const JOB = "JOB-journey-1";
const ATTEMPT = "attempt-1";
const GOAL = "Publish the liquidity review project.\n保持原文";
const REQUEST_TEXT = "Plan the first useful slice of this project.";
const PLAN_DIGEST = sha256Hex("plan");
const PROJECT_TITLE = "Published liquidity review";
const EXECUTION_ROOT = "JOB-731";
const OPEN_FAILURE = "The created project is unavailable in the current project list. Try Open project again.";

function hex64(seed: string): string {
  return sha256Hex(seed);
}

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

function executiveContext(): Record<string, unknown> {
  return {
    schema: "mastermind.os.executive.owner_context.v1",
    principal_scope: EXEC_SCOPE,
    verified_expiry: Math.floor(Date.now() / 1000) + 600,
    profile: { name: "web_ceo_v3", server_version: "1.5.0" },
  };
}

// ── closed fixture documents (verbatim reuse of the accepted journey pins) ──

function contextDocument(): Record<string, unknown> {
  return {
    schema: CONTEXT_SCHEMA,
    selection: { action: "publish_project_proposal", work_ref: null },
    owner_context: { principal_scope: WS_SCOPE },
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

function statusDocument(requestId: string, kind: "SOURCE_OBSERVED") {
  return {
    schema: STATUS_SCHEMA,
    selection: { action: "publish_project_proposal", request_id: requestId, work_ref: WORK_REF },
    owner_context: { principal_scope: WS_SCOPE },
    disposition: "accepted",
    reason: null,
    request_sha256: hex64("request"),
    recipe_fingerprint_sha256: RECIPE,
    phase: "PUBLICATION",
    receipt: {
      kind,
      event_id: 9,
      recorded_at_ms: 4,
      receipt_sha256: hex64("receipt"),
      sources: [
        { repository: "macro", commit: COMMIT, path: SOURCE_PATH, content_sha256: CONTENT },
      ],
      proposal: null,
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
      ? { state: "CONSUMED", receipt_digest: hex64("consume-receipt") }
      : { state: "UNCONSUMED", receipt_digest: null },
  };
}

function envelope(operation: string, data: unknown) {
  return { schema: PLANNING_RESULT_SCHEMA, operation, ok: true, data, error: null };
}

// ── native boundary fixture + real mounted Host ──────────────────────────────

// The joined handoff reuses the existing producer DTOs as inert native read
// DATA. Changed work/title/source values are test coordinates, not proof of an
// installed publication, real provider execution, or newly granted authority.
function programsDocument(created: boolean, title = PROJECT_TITLE) {
  // The envelope fixture deliberately has a minimal control_room for decoder
  // tests. The mounted App's strict domain mapper needs the existing full CCR.
  const room = controlRoomFixture(), original = room.work[0];
  const newRow = structuredClone(original);
  newRow.work_ref = WORK_REF;
  newRow.agent_os.workstream = WORK_REF.slice(3);
  newRow.agent_os.title = title;
  for (const binding of newRow.bindings) binding.work_ref = WORK_REF;
  for (const job of newRow.executive.jobs) job.workstream = WORK_REF;
  room.work = [original, ...(created ? [newRow] : [])];
  // Creation has no Executive root. The actual App must navigate this
  // canonical rootless row without deriving a job from the creation receipt.
  room.autonomy.responsibilities = [];
  return {...structuredClone(programsFixture), control_room: room};
}

function projectPlanDocument() {
  const value = structuredClone(planFixture);
  value.selection.work_ref = WORK_REF;
  value.source.commit = COMMIT;
  value.source.path = SOURCE_PATH;
  value.source.content_sha256 = CONTENT;
  value.plan.version_history.revisions[0].content_sha256 = CONTENT;
  value.plan.title = PROJECT_TITLE;
  value.plan.objective = GOAL;
  return value;
}

// Same closed private preview/receipt shape used by the manifest-free App
// integration. Only this native boundary is inert; its decoder/port are real.
function executionEnvelope(operation: string, request: Record<string, unknown>) {
  const data = operation === "preview" ? {
    schema: "mastermind.project_execution_preview.v1", work_ref: WORK_REF,
    context_sha256: "c".repeat(64), execution_binding_sha256: "d".repeat(64),
    execution_profile_bindings: {research_only: "d".repeat(64)},
    execution_state: "WORK_CAPABLE", continuation_mode: "DURABLE",
    coordinator: {provider: "codex", model: "inert-source-model", effort: "high"},
    execution_scope: {repository: "mastermindx-market-intelligence/Mastermind", commit: MASTERMIND},
    previous_run: null,
    binding: {workstream: WORK_REF, priority: 0, attemptLimit: 1,
      projects: [{ref: "executive-infrastructure", label: "Project team"}],
      profiles: [{ref: "research_only", label: "Research team"}]},
  } : {
    operation_key: request.operation_key, work_ref: WORK_REF, state: "ACCEPTED",
    receipt: {schema: "mastermind.ceo_intent_receipt.v2",
      intent_id: intentIdForOperationKey(String(request.operation_key)),
      fingerprint: FINGERPRINT, job_id: EXECUTION_ROOT, status: "QUEUED",
      accepted: true, dispatched: false, duplicate: operation === "status",
      authority: {requested: ["READ", "RESEARCH"], policy_sha256: POLICY, authority_level: "A0"},
      grounding: {}, created_at_ms: 0},
  };
  return {schema: "mastermind.project_execution_private_result.v1", operation, ok: true, data, error: null};
}

function journeySetup(initialPrograms?: unknown) {
  const responses: { status: unknown; programs: unknown } = { status: null, programs: initialPrograms };
  const invoke = vi.fn(async (command: string, input?: Record<string, unknown>): Promise<unknown> => {
    if (command === "auth_status") {
      return { status: "signed_in", reason: null, acquisition: true, content: true };
    }
    if (command === "executive_auth_status") return { generation: 4, available: true };
    if (command === "executive_context") return executiveContext();
    if (command === "read_programs" && responses.programs !== undefined) {
      if (responses.programs instanceof Error) throw responses.programs;
      return responses.programs;
    }
    if (command === "read_project_plan") return projectPlanDocument();
    if (command === "executive_project_execution") {
      return executionEnvelope(String(input!.operation), input!.arguments as Record<string, unknown>);
    }
    if (command === "read_source_operation_context") return contextDocument();
    if (command === "source_operation_options") return optionsDocument();
    if (command === "source_operation_prepare") {
      return previewDocument((input!.request as { request: Record<string, unknown> }).request);
    }
    if (
      command === "source_operation_submit" ||
      command === "source_operation_read" ||
      command === "source_operation_reconcile"
    ) {
      const value = responses.status;
      if (value instanceof Error) throw value;
      return value;
    }
    if (command === "executive_project_planning") {
      const operation = String(input!.operation);
      const args = (input!.arguments ?? {}) as Record<string, unknown>;
      const data = operation === "result"
        ? resultDocument(PLAN_DIGEST, false)
        : operation === "consume"
          ? resultDocument(PLAN_DIGEST, true)
          : planningReceipt(String(args.operation_key));
      return envelope(operation, data);
    }
    throw new Error(`unexpected fixture effect: ${command}`);
  });
  const events = new Map<string, (event: { payload: unknown }) => void>();
  const listen = vi.fn(async (name: string, callback: (event: { payload: unknown }) => void) => {
    events.set(name, callback);
    return () => {};
  });
  return { responses, invoke, listen, events };
}

async function mountApp(legacyManifest = true, initialPrograms?: unknown) {
  const fixture = journeySetup(initialPrograms);
  const client = await createNativeClient(fixture.invoke as never, fixture.listen as never);
  const config = decodeLaunchBindingConfig(JSON.stringify({
    v: 1, workstream: "WS:JOURNEY-INTEG", priority: 0, attemptLimit: 1,
    projects: [{ ref: "executive-infrastructure", label: "Infrastructure" }],
    profiles: [{ ref: "research_only", label: "Research" },
      { ref: "native_research_only", label: "Native research" }],
  }))!;
  const composed = composeMissionHost(client, legacyManifest ? config : null, new IDBFactory());
  await composed.ready;
  window.MastermindMissionHost = composed.host;
  const page = render(<App />);
  dispose = () => { page.unmount(); composed.dispose(); };
  const calls = (command: string) =>
    fixture.invoke.mock.calls.filter(([name]) => name === command);
  const planningOperations = () =>
    calls("executive_project_planning")
      .map(([, input]) => (input as { operation: string }).operation);
  return { ...fixture, host: composed.host, page, calls, planningOperations };
}

type Mounted = Awaited<ReturnType<typeof mountApp>>;

// ── mounted journey step helpers (public UI only) ────────────────────────────

async function openJourney() {
  fireEvent.click(await screen.findByRole("button", { name: "Projects" }));
  const newProject = await screen.findByRole("button", { name: "New project" });
  expect(newProject.hasAttribute("disabled")).toBe(false);
  fireEvent.click(newProject);
  expect(await screen.findByLabelText("Your goal")).toBeTruthy();
  expect(screen.queryByRole('button',{name:'Back to conversations'})).toBeNull();
}

async function loadOptionsAndProfile() {
  const disclosure = screen.queryByRole("button", { name: "Options" });
  if (disclosure) fireEvent.click(disclosure);
  fireEvent.click(await screen.findByRole("button", { name: "Load project options" }));
  fireEvent.click(await screen.findByRole("radio", { name: "Balanced" }));
  expect(screen.getByText("Balanced source profile.")).toBeTruthy();
}

async function preparePreview() {
  fireEvent.click(screen.getByRole("button", { name: "Prepare preview" }));
  await screen.findByRole("button", { name: "Create project" });
}

async function driveToReadableProject(h: Mounted): Promise<string> {
  await openJourney();
  fireEvent.change(screen.getByLabelText("Your goal"), { target: { value: GOAL } });
  await loadOptionsAndProfile();
  await preparePreview();
  const prepareInput = h.calls("source_operation_prepare")[0][1] as {
    request: { request: { request_id: string } };
  };
  const requestId = prepareInput.request.request.request_id;
  h.responses.status = statusDocument(requestId, "SOURCE_OBSERVED");
  expect(screen.queryByRole("button", { name: "Open project" })).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Create project" }));
  await screen.findAllByText("Project created.");
  return requestId;
}

async function sendInitialPlanning(h: Mounted): Promise<string> {
  fireEvent.click(screen.getByRole("radio", { name: "Plan" }));
  fireEvent.change(screen.getByLabelText("Initial request"), { target: { value: REQUEST_TEXT } });
  fireEvent.click(screen.getByRole("button", { name: "Send initial planning request" }));
  await waitFor(() => expect(h.planningOperations().includes("submit")).toBe(true));
  const submit = h.calls("executive_project_planning")
    .find(([, input]) => (input as { operation: string }).operation === "submit")!;
  return String((submit[1] as { arguments: { operation_key: string } }).arguments.operation_key);
}

/** The exact Executive-owner admission key the real port derives for this input. */
function expectedPlanningKey(h: Mounted, requestId: string): string {
  const owner = readOwnerContext(h.host.commandBinding!.port)!;
  const input: PlanningSubmitInput = {
    stage: "plan",
    work_ref: WORK_REF,
    project_source: {
      repository: "macro", commit: COMMIT, path: SOURCE_PATH,
      content_sha256: CONTENT, request_sha256: RECIPE,
    },
    publication: {
      request_id: requestId, principal_scope: WS_SCOPE,
      event_id: 9, receipt_sha256: hex64("receipt"),
    },
    grounding: { mastermind_sha: MASTERMIND, macro_sha: COMMIT },
    private_request: REQUEST_TEXT,
  };
  return planningOperationKey(owner, input);
}

describe("App project planning journey integration", () => {
  it("opens the observed new project and starts work through manifest-free composition", async () => {
    const h = await mountApp(false, programsDocument(false));
    const requestId = await driveToReadableProject(h);
    const binding = h.host.commandBinding!;
    expect(binding.getView()).toEqual({ projects: [], profiles: [], session: null });
    h.page.rerender(<App locale="zh-CN" />);
    expect(screen.getByRole("button", {name: "打开项目"})).toBeTruthy();
    h.page.rerender(<App locale="en" />);
    const readsBeforeOpen = h.calls("read_programs").length;
    expect(readsBeforeOpen).toBeGreaterThan(0);
    let finishPrograms!: (value: unknown) => void;
    h.responses.programs = new Promise(resolve => { finishPrograms = resolve; });
    const openProject = await screen.findByRole("button", { name: "Open project" });
    fireEvent.click(openProject);
    fireEvent.click(openProject);
    await waitFor(() => expect(h.calls("read_programs")).toHaveLength(readsBeforeOpen + 1));
    expect(screen.getByRole("button", { name: "Opening project…" })).toHaveProperty("disabled", true);
    expect(h.calls("read_project_plan")).toHaveLength(0);
    expect(h.calls("executive_project_execution")).toHaveLength(0);
    expect(screen.queryByRole("heading", { name: PROJECT_TITLE, level: 1 })).toBeNull();

    await act(async () => { finishPrograms(programsDocument(true)); });
    expect(await screen.findByRole("heading", { name: PROJECT_TITLE, level: 1 })).toBeTruthy();
    await waitFor(() => expect(h.calls("read_project_plan")).toHaveLength(1));
    expect(h.calls("read_project_plan")[0][1]).toEqual({ selection: { work_ref: WORK_REF } });
    expect(window.location.search).not.toContain("root_job_id=");
    expect(h.calls("executive_project_execution")).toHaveLength(0);

    await waitFor(() => expect(screen.getByRole("button", {name: "Start work"}))
      .toHaveProperty("disabled", false));
    fireEvent.click(screen.getByRole("button", {name: "Start work"}));
    expect((await screen.findByLabelText("Goal") as HTMLTextAreaElement).value).toBe(GOAL);
    const previews = h.calls("executive_project_execution");
    expect(previews).toHaveLength(1);
    expect(previews[0][1]).toMatchObject({
      operation: "preview", arguments: {work_ref: WORK_REF,
        expected_context: {record_source: projectPlanDocument().source,
          adoption: null, adoption_decision_source: null}},
    });
    const handoff = "Carry the published source into the project team's work.";
    fireEvent.change(screen.getByLabelText("Handoff (optional)"), {target: {value: handoff}});
    const launch = screen.getByRole("button", {name: "Launch"});
    fireEvent.click(launch);
    fireEvent.click(launch);
    await waitFor(() => expect(h.calls("executive_project_execution")
      .filter(([, input]) => input?.operation === "submit")).toHaveLength(1));
    expect(h.calls("executive_project_execution").map(([, input]) => input?.operation))
      .toEqual(["preview", "submit"]);
    const submitted = h.calls("executive_project_execution")[1][1]!;
    expect(submitted.arguments).toMatchObject({
      work_ref: WORK_REF, objective: GOAL, handoff_text: handoff,
      execution_profile: "research_only", execution_binding_sha256: "d".repeat(64),
      continuation_mode: "DURABLE",
    });
    await waitFor(async () => expect(await binding.store.read(EXEC_SCOPE)).toBeNull());
    expect(h.host.commandBinding).toBe(binding);
    expect(binding.getView()).toEqual({projects: [], profiles: [], session: null});
    expect(h.calls("source_operation_prepare")).toHaveLength(1);
    expect(h.calls("source_operation_submit")).toHaveLength(1);
    expect(h.calls("source_operation_read")).toHaveLength(0);
    expect(h.calls("source_operation_reconcile")).toHaveLength(0);
    expect(h.planningOperations()).toEqual([]);
    expect(h.calls("executive_submit")).toHaveLength(0);
    expect((h.calls("source_operation_submit")[0][1]!.request as Record<string, unknown>).request_id)
      .toBe(requestId);
  });

  it.each(["unavailable", "absent"] as const)(
    "retains the created project when the fresh list is %s and retries only that read",
    async failure => {
      // A tempting old row must not substitute for the required new observation.
      const h = await mountApp(false, programsDocument(true, "Cached old project label"));
      const requestId = await driveToReadableProject(h);
      const readsBeforeOpen = h.calls("read_programs").length;
      h.responses.programs = failure === "unavailable"
        ? new Error("inert unavailable current project list") : programsDocument(false);
      fireEvent.click(await screen.findByRole("button", {name: "Open project"}));
      expect(await screen.findByText(OPEN_FAILURE)).toBeTruthy();
      expect((screen.getByLabelText("Your goal") as HTMLTextAreaElement).value).toBe(GOAL);
      expect(h.calls("read_programs")).toHaveLength(readsBeforeOpen + 1);
      expect(h.calls("read_project_plan")).toHaveLength(0);
      expect(screen.queryByRole("heading", {name: PROJECT_TITLE, level: 1})).toBeNull();
      expect(screen.queryByRole("heading", {name: "Cached old project label", level: 1})).toBeNull();
      expect(screen.queryByRole("button", {name: "Start work"})).toBeNull();
      expect(h.calls("executive_project_execution")).toHaveLength(0);
      expect(decodeURIComponent(location.search)).toContain(requestId);

      h.responses.programs = programsDocument(true);
      fireEvent.click(screen.getByRole("button", {name: "Open project"}));
      expect(await screen.findByRole("heading", {name: PROJECT_TITLE, level: 1})).toBeTruthy();
      expect(h.calls("read_programs")).toHaveLength(readsBeforeOpen + 2);
      expect(h.calls("read_project_plan")).toHaveLength(1);
      expect(h.calls("source_operation_prepare")).toHaveLength(1);
      expect(h.calls("source_operation_submit")).toHaveLength(1);
      expect(h.calls("source_operation_read")).toHaveLength(0);
      expect(h.calls("source_operation_reconcile")).toHaveLength(0);
      expect(h.planningOperations()).toEqual([]);
      expect(h.calls("executive_project_execution")).toHaveLength(0);
      expect(h.calls("executive_submit")).toHaveLength(0);
      expect(location.search).not.toContain("root_job_id=");
    },
  );

  it("does not return to the created project after the user leaves while its fresh read waits", async () => {
    const h = await mountApp(false, programsDocument(false));
    await driveToReadableProject(h);
    let finishPrograms!: (value: unknown) => void;
    h.responses.programs = new Promise(resolve => { finishPrograms = resolve; });
    const readsBeforeOpen = h.calls("read_programs").length;
    fireEvent.click(await screen.findByRole("button", {name: "Open project"}));
    await waitFor(() => expect(h.calls("read_programs")).toHaveLength(readsBeforeOpen + 1));

    fireEvent.click(screen.getByRole("button", {name: "Today"}));
    await waitFor(() => expect(document.querySelector(".shell")?.getAttribute("data-active-route")).toBe("Today"));
    const locationAfterLeaving = location.href;
    await act(async () => { finishPrograms(programsDocument(true)); });
    expect(document.querySelector(".shell")?.getAttribute("data-active-route")).toBe("Today");
    expect(location.href).toBe(locationAfterLeaving);
    expect(screen.queryByRole("heading", {name: PROJECT_TITLE, level: 1})).toBeNull();
    expect(screen.queryByRole("button", {name: "Start work"})).toBeNull();
    expect(h.calls("read_project_plan")).toHaveLength(0);
    expect(h.calls("executive_project_execution")).toHaveLength(0);
    expect(h.calls("source_operation_prepare")).toHaveLength(1);
    expect(h.calls("source_operation_submit")).toHaveLength(1);
    expect(h.calls("source_operation_read")).toHaveLength(0);
    expect(h.calls("source_operation_reconcile")).toHaveLength(0);
    expect(h.planningOperations()).toEqual([]);
    expect(h.calls("executive_submit")).toHaveLength(0);
  });

  it("withholds a late created-project read after native auth withdrawal without creation or launch replay", async () => {
    const h = await mountApp(false, programsDocument(false));
    await driveToReadableProject(h);
    let finishPrograms!: (value: unknown) => void;
    h.responses.programs = new Promise(resolve => { finishPrograms = resolve; });
    const readsBeforeOpen = h.calls("read_programs").length;
    fireEvent.click(await screen.findByRole("button", {name: "Open project"}));
    await waitFor(() => expect(h.calls("read_programs")).toHaveLength(readsBeforeOpen + 1));
    await act(async () => {
      h.events.get("mastermind-auth-state")!({payload: {
        status: "signed_out", reason: "USER_SIGNED_OUT", acquisition: false, content: false,
      }});
      finishPrograms(programsDocument(true));
    });
    expect(screen.queryByRole("heading", {name: PROJECT_TITLE, level: 1})).toBeNull();
    expect(screen.queryByRole("button", {name: "Start work"})).toBeNull();
    expect(screen.queryByRole("button", {name: "Open project"})).toBeNull();
    expect(h.calls("read_project_plan")).toHaveLength(0);
    expect(h.calls("executive_project_execution")).toHaveLength(0);
    expect(h.calls("source_operation_prepare")).toHaveLength(1);
    expect(h.calls("source_operation_submit")).toHaveLength(1);
    expect(h.calls("source_operation_read")).toHaveLength(0);
    expect(h.calls("source_operation_reconcile")).toHaveLength(0);
    expect(h.planningOperations()).toEqual([]);
    expect(h.calls("executive_submit")).toHaveLength(0);
    expect(location.search).not.toContain("root_job_id=");
  });
  it('keeps only exact native readiness diagnostic inside closed source details during new-project setup',async()=>{
    let rejectReadiness!:(reason:Error)=>void;
    const readinessCommands:string[]=[];
    Object.defineProperty(window,'__TAURI_INTERNALS__',{configurable:true,value:{invoke:(command:string)=>{
      readinessCommands.push(command);
      if(command==='readiness')return new Promise<never>((_resolve,reject)=>{rejectReadiness=reject;});
      return Promise.reject(Error('inert unsupported native command'));
    }}});
    try{
      const h=await mountApp();await openJourney();
      // Observe the one real readiness edge only after this route exists;
      // unrelated startup Mission notices must not decide test ordering.
      await waitFor(()=>expect(readinessCommands.filter(command=>command==='readiness')).toHaveLength(1));
      await act(async()=>{rejectReadiness(Error('inert readiness boundary'));});
      const diagnostic=await screen.findByText('Native readiness receipt unavailable. No source request was attempted.');
      expect(diagnostic.closest('details.workspace-qualification')).not.toBeNull();
      expect(diagnostic.closest('.notice')).toBeNull();
      expect(document.querySelector('.workspace-header .eyebrow')?.textContent).toBe('New project');
      expect(document.querySelector('.workspace-header .workspace-route h2')?.textContent).toBe('New project');
      expect(document.querySelector('.workspace-header .facts details summary')?.textContent?.trim()).toBe('Sources and access');
      expect(document.querySelector('.workspace-header .facts details')?.textContent).toContain('Workspace project list and existing tasks');
      expect(h.calls('source_operation_prepare')).toHaveLength(0);
      expect(h.calls('source_operation_submit')).toHaveLength(0);
    }finally{delete (window as unknown as Record<string,unknown>).__TAURI_INTERNALS__;}
  });
  it("mounts the real journey: goal → options → verified preview → publication → observed source → planning → result → explicit keep", async () => {
    const h = await mountApp();
    const requestId = await driveToReadableProject(h);

    // The fixed native source frames: the context read binds the Workspace
    // scope once; the options are DATA and never mint a scope.
    expect(requestId).toMatch(/^mmos-project-create-[0-9a-f]{40}$/);
    expect(h.calls("read_source_operation_context")).toEqual([
      ["read_source_operation_context", { selection: { action: "publish_project_proposal", work_ref: null } }],
    ]);
    expect(h.calls("source_operation_options")).toEqual([
      ["source_operation_options", { request: { action: "publish_project_proposal" } }],
    ]);
    expect((h.calls("source_operation_prepare")[0][1] as { request: Record<string, unknown> }).request)
      .toEqual({action:"publish_project_proposal",request:previewRequest(requestId)});

    // Explicit publication: one submit with the verified witness and the
    // preview's workspace reference, and the observed source record.
    const submitFrame = (h.calls("source_operation_submit")[0][1] as {
      request: Record<string, unknown>;
    }).request;
    expect(Object.keys(submitFrame).sort())
      .toEqual(["action", "preview_witness", "request_id", "work_ref"]);
    expect(submitFrame).toMatchObject({
      action: "publish_project_proposal", request_id: requestId, work_ref: WORK_REF,
    });
    await screen.findAllByText("Project created.");

    // The setup URL keeps the original journey identities and is never
    // overwritten by a default Mission selection (no root_job_id param).
    expect(decodeURIComponent(window.location.search)).toContain(requestId);
    expect(window.location.search).not.toContain("root_job_id=");

    // Initial planning is an explicit Executive-scoped dispatch whose
    // publication reference keeps the Workspace scope of the observed status.
    const planningKey = await sendInitialPlanning(h);
    expect(planningKey).toBe(expectedPlanningKey(h, requestId));
    await screen.findByText("Planning request accepted.");

    // Result read on the ORIGINAL admission key, then the explicit keep.
    fireEvent.click(screen.getByRole("button", { name: "Read planning result" }));
    await screen.findByText("Initial planning produced a two step plan.");
    expect(screen.getByText("Confirm the plan or ask for a clarification pass.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Keep result" }));
    await screen.findByText("This result is kept.");

    // One submit/result/consume on the same original admission key; the keep
    // carries a separate deterministic acknowledgment key.
    const frames = h.calls("executive_project_planning")
      .map(([, input]) => input as { operation: string; arguments: Record<string, unknown> });
    expect(frames.map((frame) => frame.operation)).toEqual(["submit", "result", "consume"]);
    const submitArgs = frames[0].arguments;
    expect(Object.keys(submitArgs).sort()).toEqual([
      "grounding", "operation_key", "private_request", "project_source", "publication", "stage", "work_ref",
    ]);
    expect(submitArgs.stage).toBe("plan");
    expect(submitArgs.work_ref).toBe(WORK_REF);
    expect(submitArgs.private_request).toBe(REQUEST_TEXT);
    expect(submitArgs.grounding).toEqual({ mastermind_sha: MASTERMIND, macro_sha: COMMIT });
    expect(submitArgs.project_source).toEqual({
      repository: "macro", commit: COMMIT, path: SOURCE_PATH,
      content_sha256: CONTENT, request_sha256: RECIPE,
    });
    expect(submitArgs.publication).toEqual({
      request_id: requestId, principal_scope: WS_SCOPE,
      event_id: 9, receipt_sha256: hex64("receipt"),
    });
    expect(frames[1].arguments).toEqual({ operation_key: planningKey, work_ref: WORK_REF });
    const consumeArgs = frames[2].arguments;
    expect(consumeArgs.operation_key).toBe(planningKey);
    const ackKey = String(consumeArgs.consumption_operation_key);
    expect(ackKey).toMatch(/^mmos-consume-[0-9a-f]{40}$/);
    expect(ackKey).not.toBe(planningKey);
    expect(consumeArgs).toMatchObject({
      work_ref: WORK_REF, attempt_id: ATTEMPT, result_digest: PLAN_DIGEST,
    });

    // Exact native command counts: one original effect each, no second
    // CREATE, no implicit status/reconcile/consume, and no App launch effect.
    expect(h.calls("source_operation_prepare")).toHaveLength(1);
    expect(h.calls("source_operation_submit")).toHaveLength(1);
    expect(h.calls("source_operation_read")).toHaveLength(0);
    expect(h.calls("source_operation_reconcile")).toHaveLength(0);
    expect(h.calls("executive_project_planning")).toHaveLength(3);
    expect(h.calls("executive_submit")).toHaveLength(0);
    expect(decodeURIComponent(window.location.search)).toContain(requestId);
  });

  it("reopens the same original journey from the setup URL with no second CREATE and no implicit consume", async () => {
    const h = await mountApp();
    const requestId = await driveToReadableProject(h);
    const planningKey = await sendInitialPlanning(h);
    await screen.findByText("Planning request accepted.");
    const setupHref = window.location.href;

    // Re-render the real App over the SAME composed Host and the SAME URL.
    h.page.unmount();
    dispose = () => {};
    history.replaceState(null, "", setupHref);
    window.MastermindMissionHost = h.host;
    const reopened = render(<App />);
    dispose = () => { reopened.unmount(); };

    // The restored selection is not current data: nothing is re-prepared or
    // re-published, and the explicit source check is the only offer.
    expect(await screen.findByLabelText("Your goal")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Create project" })).toBeNull();
    expect(h.calls("source_operation_prepare")).toHaveLength(1);
    expect(h.calls("source_operation_submit")).toHaveLength(1);

    // The explicit source check reads the ORIGINAL operation on its original
    // request identity; no new request id is minted.
    fireEvent.click(screen.getByRole("button", { name: "Check original project request" }));
    await waitFor(() => expect(h.calls("source_operation_read")).toHaveLength(1));
    const lookup = (h.calls("source_operation_read")[0][1] as {
      request: { schema: string; action: string; request_id: string; work_ref: unknown };
    }).request;
    expect(lookup).toMatchObject({
      schema: "mastermind.workspace_source_operation_lookup.v1",
      action: "publish_project_proposal",
      request_id: requestId,
    });
    expect([WORK_REF, null]).toContain(lookup.work_ref);
    // The observed source record (and the accepted planning status when the
    // URL carried the job) is re-established from the ORIGINAL identity.
    await waitFor(() => {
      const text = document.body.textContent ?? "";
      expect(
        text.includes("Project created.") ||
          text.includes("Planning request accepted."),
      ).toBe(true);
    });

    // The ORIGINAL planning key is reused for a status-only read; never a
    // second submit and never an implicit consume.
    fireEvent.click(screen.getByRole("button", { name: "Check planning status" }));
    await waitFor(() => expect(h.planningOperations().includes("status")).toBe(true));
    const statusFrame = h.calls("executive_project_planning")
      .find(([, input]) => (input as { operation: string }).operation === "status")!;
    expect((statusFrame[1] as { arguments: Record<string, unknown> }).arguments)
      .toEqual({ operation_key: planningKey, work_ref: WORK_REF });
    expect(h.planningOperations()).toEqual(["submit", "status"]);
    expect(h.calls("source_operation_prepare")).toHaveLength(1);
    expect(h.calls("source_operation_submit")).toHaveLength(1);
    expect(decodeURIComponent(window.location.search)).toContain(requestId);
  });

  it("refuses journey effects after the mounted Host is replaced, before any native effect", async () => {
    const h = await mountApp();
    await openJourney();
    fireEvent.change(screen.getByLabelText("Your goal"), { target: { value: GOAL } });
    expect(h.calls("read_source_operation_context")).toHaveLength(0);
    expect(h.calls("source_operation_options")).toHaveLength(0);

    // Reveal the existing options action before replacing the Host; opening
    // this local disclosure performs no native read or effect.
    fireEvent.click(screen.getByRole("button", { name: "Options" }));

    // The global Host identity moved without an App render. The mounted
    // journey's original actor refuses BEFORE a new native request and renders
    // its incumbent authorization cue; this is not a fresh signed-out fact.
    window.MastermindMissionHost = { auth: h.host.auth } as never;
    fireEvent.click(screen.getByRole("button", { name: "Load project options" }));
    expect((await screen.findAllByText("Sign in with acquisition to continue this journey.")).length).toBeGreaterThan(0);
    expect(screen.queryByRole("button", { name: "Load project options" })).toBeNull();
    const preview = screen.getByRole("button", {name:"Prepare preview"});
    expect(preview.hasAttribute("disabled")).toBe(true);
    fireEvent.click(preview);

    // The refusal came before every effect: no new native frame of any kind.
    expect(h.calls("read_source_operation_context")).toHaveLength(0);
    expect(h.calls("source_operation_options")).toHaveLength(0);
    expect(h.calls("source_operation_prepare")).toHaveLength(0);
    expect(h.calls("source_operation_submit")).toHaveLength(0);
    expect(h.calls("executive_project_planning")).toHaveLength(0);
  });

  it("refuses the planning dispatch after the executive owner generation moves, before any native effect", async () => {
    const h = await mountApp();
    await driveToReadableProject(h);
    fireEvent.click(screen.getByRole("radio", { name: "Plan" }));
    fireEvent.change(screen.getByLabelText("Initial request"), { target: { value: REQUEST_TEXT } });
    const planningBefore = h.calls("executive_project_planning").length;

    // The Executive owner generation moved under the same signed-in state;
    // the App's captured owner identity is stale for this dispatch.
    h.events.get("mastermind-executive-auth-state")!({
      payload: { generation: 5, available: true },
    });

    fireEvent.click(screen.getByRole("button", { name: "Send initial planning request" }));
    expect(await screen.findByText("The owner identity is unavailable.")).toBeTruthy();
    expect(h.calls("executive_project_planning")).toHaveLength(planningBefore);
    // No admission key was recorded on the shared selection: the original
    // journey stays at the observed source record with no planning owner.
    expect(screen.queryByRole("button", { name: "Check planning status" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Read planning result" })).toBeNull();
    expect(h.calls("source_operation_submit")).toHaveLength(1);
    expect(h.calls("source_operation_prepare")).toHaveLength(1);
  });
});
