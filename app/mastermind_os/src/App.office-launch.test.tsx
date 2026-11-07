// @vitest-environment jsdom
import { act, cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";
import type { AuthState } from "./host";
import { BYOK_ROLES_SCHEMA, type ByokRolesRead } from "./meta-ceo/byok-roles-read";
import { controlRoomFixture, missionFixture } from "./test-fixtures";
import type {
  CommandIntent,
  EffectReceipt,
  OperationPointer,
  OwnerContext,
  PendingPointerStore,
} from "./orchestration/operation-controller";
import type { OrchestratorCommandBinding } from "./orchestration/host-command-bindings";
import { createExecutiveLaunchBinding, type LaunchConfiguration } from "./orchestration/executive-launch-command-port";
import { decodeLaunchBindingConfig } from "./launch-config";

const invoke = vi.fn().mockResolvedValue({
  version: "0.1.0",
  source_revision: "a".repeat(40),
  build_identity: "test-build",
  transport: "UNCONFIGURED",
  state: "BUILT_NOT_PROVEN",
});
vi.mock("@tauri-apps/api/core", () => ({ isTauri: () => false, invoke: (...args: unknown[]) => invoke(...args) }));

const DIRECTION = "Ship the bounded launch slice.";
const MANIFEST = {
  v: 1,
  workstream: "WS:ALPHA",
  priority: 0,
  projects: [{ ref: "alpha-project", label: "Alpha project" }],
  profiles: [{ ref: "research_only", label: "Research only" }],
};

function installHost(options: {
  launchConfig?: LaunchConfiguration;
  selection?: { workRef: string; rootJobId: string };
  ctx?: OwnerContext | null;
  projects?: { ref: string; label: string }[];
  profiles?: { ref: string; label: string }[];
  submit?: (pointer: OperationPointer, intent: CommandIntent) => Promise<EffectReceipt>;
} = {}) {
  let ctx: OwnerContext | null = options.ctx ?? { principalScope: "owner-a", generation: "gen-1" };
  let auth: AuthState = { status: "signed_in", reason: null, acquisition: true, content: true };
  let listener = (_state: AuthState) => {};
  const data = new Map<string, OperationPointer>();
  const store: PendingPointerStore = {
    read: scope => data.get(scope) ?? null,
    reserve: (scope, value) => {
      const saved = data.get(scope);
      if (saved) return { reserved: false, pointer: saved };
      data.set(scope, value);
      return { reserved: true };
    },
    clearIfEqual: (scope, value) => {
      const saved = data.get(scope);
      if (!saved || saved.operationKey !== value.operationKey ||
          saved.kind !== value.kind || saved.targetKey !== value.targetKey) return false;
      data.delete(scope);
      return true;
    },
  };
  const actual = options.launchConfig ? createExecutiveLaunchBinding(options.launchConfig,
    { callTool: async () => { throw new Error("Unexpected transport"); } },
    { context: () => ctx, store, getSession: () => null, subscribe: () => () => {} }) : null;
  const prepare = vi.fn((intent: CommandIntent): OperationPointer => actual ? actual.port.prepare(intent) : ({
    operationKey: `op-${prepare.mock.calls.length + 1}`,
    kind: intent.kind,
    targetKey: intent.targetKey,
  }));
  const submit = vi.fn(options.submit ?? (async (pointer: OperationPointer): Promise<EffectReceipt> => ({
    ...pointer,
    disposition: "accepted",
  })));
  const readOperation = vi.fn(async (pointer: OperationPointer): Promise<EffectReceipt> => ({
    ...pointer,
    disposition: "accepted",
  }));
  const binding: OrchestratorCommandBinding = {
    port: { context: () => ctx, prepare, submit, readOperation },
    store,
    getView: () => actual ? actual.getView() : ({
      projects: options.projects ?? [{ ref: "alpha-project", label: "Alpha project" }],
      profiles: options.profiles ?? [{ ref: "research_only", label: "Research only" }],
      session: null,
    }),
    subscribe: () => () => {},
    // The existing owner maps the launch form onto its own payload. It never
    // carries a session reference and never derives one from the form.
    makeLaunchIntent: form => actual ? actual.makeLaunchIntent(form) : ({
      kind: "launch",
      targetKey: "WS:ALPHA",
      payload: {
        objective: form.goal,
        department: form.projectRef,
        execution_profile: form.profileRef,
        workstream: "WS:ALPHA",
        ...(form.frontierModelAlias !== undefined
          ? { frontier_model_alias: form.frontierModelAlias }
          : {}),
      },
    }),
    makeMessageIntent: () => null,
    makeStopIntent: () => null,
  };
  window.MastermindMissionHost = {
    selection: options.selection ?? { workRef: "WS:ALPHA", rootJobId: "JOB-A" },
    readPrograms: async () => {
      const document = controlRoomFixture();
      if (options.selection) {
        const { workRef, rootJobId } = options.selection;
        const work = document.work[0], responsibility = document.autonomy.responsibilities[0];
        work.work_ref = workRef; work.agent_os.workstream = workRef.slice(3);
        work.executive.jobs[0].workstream = workRef; work.executive.jobs[0].job_id = rootJobId;
        for (const binding of work.bindings) binding.work_ref = workRef;
        responsibility.responsibility_ref = workRef; responsibility.root_job_id = rootJobId;
        responsibility.root_job_candidates = [rootJobId];
        responsibility.dispatch.responsibility_ref = workRef;
        responsibility.dispatch.root_job_id = rootJobId;
        responsibility.dispatch.evidence.responsibility_ref = workRef;
        responsibility.dispatch.evidence.root_job_id = rootJobId;
      }
      return document;
    },
    readMission: async ({ workRef, rootJobId }) => missionFixture(workRef, rootJobId),
    commandBinding: binding,
    auth: {
      getState: () => auth,
      subscribe: fn => { listener = fn; return () => {}; },
      signIn: async () => {},
      signOut: async () => {},
    },
  };
  return {
    binding,
    prepare,
    submit,
    readOperation,
    store,
    notify: (state: AuthState) => { auth = state; listener(state); },
    setCtx: (next: OwnerContext | null) => { ctx = next; },
  };
}

beforeEach(() => {
  history.replaceState(null, "", "/os/");
  delete window.MastermindMissionHost;
  vi.stubEnv("VITE_MM_LAUNCH_CONFIG", JSON.stringify(MANIFEST));
});
afterEach(() => {
  cleanup();
  delete window.MastermindMissionHost;
  vi.unstubAllEnvs();
  vi.restoreAllMocks();
});

/** The Meta-CEO route, with its own source reads already settled. */
async function openOffice(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole("button", { name: "Meta-CEO" }));
  await screen.findByRole("region", { name: "Meta-CEO office" });
  await waitFor(() => {
    const sources = screen.getByRole("region", { name: "Source qualification" });
    // The Mission read has landed; the frozen preview must not be raced by a
    // source revision that arrives after it.
    expect(sources.textContent).not.toContain("MissionUNAVAILABLE");
  });
}

/** One frozen direction preview on the Office, ready for the handoff. */
async function freezeDirection(user: ReturnType<typeof userEvent.setup>, paste = false) {
  // These owner-lifecycle cases may use one real focused paste gesture. They
  // do not assert keyboard-per-character behavior or bypass the input owner.
  if (paste) {
    await user.click(screen.getByLabelText("Direction to Meta-CEO"));
    await user.paste(DIRECTION);
  } else await user.type(screen.getByLabelText("Direction to Meta-CEO"), DIRECTION);
  await user.click(screen.getByRole("button", { name: "Review direction preview" }));
  const preview = await screen.findByRole("region", { name: "Direction preview" });
  expect(preview.textContent).toContain(DIRECTION);
  return preview;
}

/** The handoff refusal inside the frozen preview, not anywhere else on the page. */
function previewRefusal() {
  const preview = screen.getByRole("region", { name: "Direction preview" });
  return within(preview).getByRole("alert");
}

describe("Office direction handoff into the existing launch owner", () => {
  it("opens the existing launch form with the exact frozen direction and the configured choices, and prepares nothing before an explicit launch", async () => {
    const made = installHost();
    const user = userEvent.setup();
    render(<App />);
    await openOffice(user);
    await freezeDirection(user);
    expect(screen.queryByLabelText("Goal")).toBeNull();
    await user.click(screen.getByRole("button", { name: "Start new work" }));
    const goal = await screen.findByLabelText("Goal");
    expect((goal as HTMLTextAreaElement).value).toBe(DIRECTION);
    expect((screen.getByLabelText("Project") as HTMLSelectElement).value).toBe("alpha-project");
    expect((screen.getByLabelText("Profile") as HTMLSelectElement).value).toBe("research_only");
    expect(made.prepare).not.toHaveBeenCalled();
    expect(made.submit).not.toHaveBeenCalled();
    // The Office direction itself is untouched by the handoff.
    expect((screen.getByLabelText("Direction to Meta-CEO") as HTMLTextAreaElement).value).toBe(DIRECTION);
  });

  it("launches the exact frozen direction through the existing owner with no session reference in the payload", async () => {
    const made = installHost();
    const user = userEvent.setup();
    render(<App />);
    await openOffice(user);
    await freezeDirection(user);
    await user.click(screen.getByRole("button", { name: "Start new work" }));
    await user.click(await screen.findByRole("button", { name: "Launch" }));
    await waitFor(() => expect(made.submit).toHaveBeenCalledTimes(1));
    expect(made.prepare).toHaveBeenCalledTimes(1);
    const payload = made.prepare.mock.calls[0][0].payload as Record<string, unknown>;
    expect(payload.objective).toBe(DIRECTION);
    expect(payload.department).toBe("alpha-project");
    expect(payload.execution_profile).toBe("research_only");
    expect(payload.workstream).toBe("WS:ALPHA");
    expect(JSON.stringify(payload)).not.toContain("session");
    // A submission receipt is not a worker result and not acceptance.
    expect(made.submit.mock.calls[0][1].payload).not.toHaveProperty("sessionRef");
  });

  it("consumes only the submitted launch draft on acceptance and keeps the Office direction", async () => {
    const made = installHost({
      submit: async pointer => ({
        ...pointer,
        disposition: "accepted" as const,
        missionSelection: { workRef: "WS:LAUNCH", rootJobId: "JOB-L" },
      }),
    });
    const user = userEvent.setup();
    render(<App />);
    await openOffice(user);
    await freezeDirection(user, true);
    await user.click(screen.getByRole("button", { name: "Start new work" }));
    await user.click(await screen.findByRole("button", { name: "Launch" }));
    await waitFor(() => expect(made.submit).toHaveBeenCalledTimes(1));
    // The accepted effect cleared its own pointer and nothing else.
    await waitFor(() => expect(made.store.read("owner-a")).toBeNull());
    expect(made.prepare).toHaveBeenCalledTimes(1);
    // The submitted launch draft is consumed; the Office direction survives.
    await user.click(await screen.findByRole("button", { name: "Work queue" }));
    expect((await screen.findByLabelText("Goal") as HTMLTextAreaElement).value).toBe("");
    // The settled Office handoff cannot fence a later independent launch.
    await user.click(screen.getByLabelText("Goal"));
    await user.paste("A new launch after the first receipt.");
    await user.click(screen.getByRole("button", { name: "Launch" }));
    await waitFor(() => expect(made.submit).toHaveBeenCalledTimes(2));
    expect(made.prepare.mock.calls[1][0].payload).toHaveProperty(
      "objective", "A new launch after the first receipt.");
  });

  it("keeps the launch goal and the Office direction when the existing owner refuses the launch", async () => {
    const made = installHost({
      submit: async pointer => ({ ...pointer, disposition: "refused" as const }),
    });
    const user = userEvent.setup();
    render(<App />);
    await openOffice(user);
    await freezeDirection(user);
    await user.click(screen.getByRole("button", { name: "Start new work" }));
    await user.click(await screen.findByRole("button", { name: "Launch" }));
    await waitFor(() => expect(made.submit).toHaveBeenCalledTimes(1));
    expect(await screen.findByText("REFUSED")).toBeTruthy();
    expect((screen.getByLabelText("Goal") as HTMLTextAreaElement).value).toBe(DIRECTION);
    expect((screen.getByLabelText("Direction to Meta-CEO") as HTMLTextAreaElement).value).toBe(DIRECTION);
  });

  it("cannot launch twice from one handoff and a cancel keeps the Office direction", async () => {
    let release!: (value: EffectReceipt) => void;
    const held = new Promise<EffectReceipt>(resolve => { release = resolve; });
    const made = installHost({ submit: async pointer => held });
    const user = userEvent.setup();
    render(<App />);
    await openOffice(user);
    await freezeDirection(user);
    await user.click(screen.getByRole("button", { name: "Start new work" }));
    const launch = await screen.findByRole("button", { name: "Launch" });
    await user.click(launch);
    await waitFor(() => expect(made.prepare).toHaveBeenCalledTimes(1));
    await user.click(screen.getByRole("button", { name: "Launching…" }));
    expect(made.prepare).toHaveBeenCalledTimes(1);
    expect(made.submit).toHaveBeenCalledTimes(1);
    await act(async () => { release({ operationKey: "op-1", kind: "launch", targetKey: "WS:ALPHA", disposition: "accepted" }); });
  });

  it("cancels the handoff without clearing the Office direction and without any effect", async () => {
    const made = installHost();
    const user = userEvent.setup();
    render(<App />);
    await openOffice(user);
    await freezeDirection(user);
    await user.click(screen.getByRole("button", { name: "Start new work" }));
    await user.click(await screen.findByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(screen.queryByLabelText("Goal")).toBeNull());
    expect(made.prepare).not.toHaveBeenCalled();
    expect(made.submit).not.toHaveBeenCalled();
    // The Office direction and its frozen preview survive the cancel.
    expect((screen.getByLabelText("Direction to Meta-CEO") as HTMLTextAreaElement).value).toBe(DIRECTION);
    expect(screen.getByRole("region", { name: "Direction preview" }).textContent).toContain(DIRECTION);
  });

  it("refuses the handoff when the launch owner is no longer the bound one, with zero effect", async () => {
    const made = installHost();
    const user = userEvent.setup();
    render(<App />);
    await openOffice(user);
    await freezeDirection(user);
    // The bound owner is replaced between the render and the click.
    window.MastermindMissionHost!.commandBinding = { ...made.binding };
    await user.click(screen.getByRole("button", { name: "Start new work" }));
    expect(previewRefusal()).toHaveProperty(
      "textContent",
      expect.stringContaining("cannot offer a handoff"),
    );
    expect(screen.queryByLabelText("Goal")).toBeNull();
    expect(made.prepare).not.toHaveBeenCalled();
    expect(made.submit).not.toHaveBeenCalled();
  });

  it("refuses the handoff when the selected workstream is not the configured launch workstream", async () => {
    vi.stubEnv("VITE_MM_LAUNCH_CONFIG", JSON.stringify({ ...MANIFEST, workstream: "WS:OTHER" }));
    const made = installHost();
    const user = userEvent.setup();
    render(<App />);
    await openOffice(user);
    await freezeDirection(user);
    await user.click(screen.getByRole("button", { name: "Start new work" }));
    expect(previewRefusal()).toHaveProperty(
      "textContent",
      // An exact lookup with no enrollment cannot offer a launch handoff.
      expect.stringContaining("cannot offer a handoff"),
    );
    expect(screen.queryByLabelText("Goal")).toBeNull();
    expect(made.prepare).not.toHaveBeenCalled();
    expect(made.submit).not.toHaveBeenCalled();
  });

  it("refuses an Office handoff when the launch workstream cannot be established", async () => {
    vi.stubEnv("VITE_MM_LAUNCH_CONFIG", "");
    const made = installHost();
    const user = userEvent.setup();
    render(<App />);
    await openOffice(user);
    await freezeDirection(user);
    await user.click(screen.getByRole("button", { name: "Start new work" }));
    expect(previewRefusal().textContent).toContain("cannot offer a handoff");
    expect(screen.queryByLabelText("Goal")).toBeNull();
    expect(made.prepare).not.toHaveBeenCalled();
    expect(made.submit).not.toHaveBeenCalled();
    expect((screen.getByLabelText("Direction to Meta-CEO") as HTMLTextAreaElement).value).toBe(DIRECTION);
  });

  it("keeps an existing unsent launch goal and refuses to replace it", async () => {
    const made = installHost();
    const user = userEvent.setup();
    render(<App />);
    await user.click(await screen.findByRole("button", { name: "Work queue" }));
    await user.type(await screen.findByLabelText("Goal"), "An earlier unsent goal.");
    await openOffice(user);
    await freezeDirection(user);
    await user.click(screen.getByRole("button", { name: "Start new work" }));
    expect(previewRefusal()).toHaveProperty(
      "textContent",
      expect.stringContaining("unsent launch goal"),
    );
    expect(screen.queryByLabelText("Goal")).toBeNull();
    expect(made.prepare).not.toHaveBeenCalled();
    // The earlier goal is still exactly where it was.
    await user.click(screen.getByRole("button", { name: "Work queue" }));
    expect((await screen.findByLabelText("Goal") as HTMLTextAreaElement).value).toBe("An earlier unsent goal.");
  });

  it("refuses the handoff while an original launch command is held on its own pointer", async () => {
    let release!: (value: EffectReceipt) => void;
    const held = new Promise<EffectReceipt>(resolve => { release = resolve; });
    const made = installHost({ submit: async pointer => held });
    const user = userEvent.setup();
    render(<App />);
    await user.click(await screen.findByRole("button", { name: "Work queue" }));
    await user.click(await screen.findByLabelText("Goal"));
    await user.paste("An earlier unsent goal.");
    await user.click(screen.getByRole("button", { name: "Launch" }));
    await waitFor(() => expect(made.prepare).toHaveBeenCalledTimes(1));
    await openOffice(user);
    await freezeDirection(user, true);
    await user.click(screen.getByRole("button", { name: "Start new work" }));
    expect(previewRefusal()).toHaveProperty(
      "textContent",
      expect.stringContaining("still held"),
    );
    expect(made.prepare).toHaveBeenCalledTimes(1);
    expect(made.submit).toHaveBeenCalledTimes(1);
    await act(async () => { release({ operationKey: "op-1", kind: "launch", targetKey: "WS:ALPHA", disposition: "accepted" }); });
  });

  it("refuses a submission whose frozen preview is no longer current, with zero effect", async () => {
    const made = installHost();
    const user = userEvent.setup();
    render(<App />);
    await openOffice(user);
    await freezeDirection(user);
    await user.click(screen.getByRole("button", { name: "Start new work" }));
    await screen.findByLabelText("Goal");
    // The auth epoch moves while the handoff is open. The user stays signed
    // in, so only the captured preview can refuse the submission.
    act(() => {
      made.notify({ status: "signed_in", reason: null, acquisition: true, content: false });
    });
    await user.click(screen.getByRole("button", { name: "Launch" }));
    await waitFor(() => expect(screen.getByText(/no longer current/)).toBeTruthy());
    expect(made.prepare).not.toHaveBeenCalled();
    expect(made.submit).not.toHaveBeenCalled();
    // The Office direction is retained through the refusal.
    expect((screen.getByLabelText("Direction to Meta-CEO") as HTMLTextAreaElement).value).toBe(DIRECTION);
  });

  it("refuses a submission whose launch owner was replaced after the handoff opened", async () => {
  const made = installHost();
  const user = userEvent.setup();
  render(<App />);
  await openOffice(user);
  await freezeDirection(user);
  await user.click(screen.getByRole("button", { name: "Start new work" }));
  await screen.findByLabelText("Goal");
  // The bound owner is replaced after the handoff opened.
  window.MastermindMissionHost!.commandBinding = { ...made.binding };
  await user.click(screen.getByRole("button", { name: "Launch" }));
  await waitFor(() => expect(screen.getByRole("button", { name: "Launch" })).toBeTruthy());
  expect(made.prepare).not.toHaveBeenCalled();
  expect(made.submit).not.toHaveBeenCalled();
  // The launch goal is retained for an explicit retry, and the Office
  // direction is untouched.
  expect((screen.getByLabelText("Goal") as HTMLTextAreaElement).value).toBe(DIRECTION);
  expect((screen.getByLabelText("Direction to Meta-CEO") as HTMLTextAreaElement).value).toBe(DIRECTION);
});

it("revisits an open handoff without a second launch owner", async () => {
  const made = installHost();
  const user = userEvent.setup();
  render(<App />);
  await openOffice(user);
  await freezeDirection(user);
  await user.click(screen.getByRole("button", { name: "Start new work" }));
  await screen.findByLabelText("Goal");
  expect(screen.getAllByLabelText("Goal")).toHaveLength(1);
  // Close the frozen preview and review it again.
  await user.click(screen.getByRole("button", { name: "Close preview" }));
  await user.click(screen.getByRole("button", { name: "Review direction preview" }));
  await user.click(screen.getByRole("button", { name: "Start new work" }));
  expect(screen.getAllByLabelText("Goal")).toHaveLength(1);
  expect((screen.getByLabelText("Goal") as HTMLTextAreaElement).value).toBe(DIRECTION);
  expect(made.prepare).not.toHaveBeenCalled();
  expect(made.submit).not.toHaveBeenCalled();
});

it("keeps the Office direction and the frozen preview text out of the session namespace", async () => {
    const made = installHost();
    const user = userEvent.setup();
    render(<App />);
    await openOffice(user);
    await freezeDirection(user);
    await user.click(screen.getByRole("button", { name: "Start new work" }));
    await user.click(await screen.findByRole("button", { name: "Launch" }));
    await waitFor(() => expect(made.submit).toHaveBeenCalledTimes(1));
    const pointer = await made.store.read("owner-a");
    expect(pointer?.targetKey).toBe("WS:ALPHA");
    expect(JSON.stringify(pointer)).not.toContain("session");
  });
});


const EEC = "WS:EXECUTIVE-ECOSYSTEM-COMPLETION";
const CCR = "WS:CHAIRMAN-CONTROL-ROOM";
function multiManifest(includeOffice = true) {
  const { v: _v, ...leaf } = MANIFEST;
  return { v: 2, defaultWorkstream: EEC, bindings: [
    { ...leaf, label: "Executive Ecosystem", workstream: EEC, attemptLimit: 1,
      profiles: [...leaf.profiles, { ref: "native_research_only", label: "Native research only" }] },
    ...(includeOffice ? [{ ...leaf, label: "Meta-CEO Office", workstream: CCR, attemptLimit: 1 }] : []),
  ] };
}
function installMultiHost(includeOffice = true) {
  const manifest = multiManifest(includeOffice);
  vi.stubEnv("VITE_MM_LAUNCH_CONFIG", JSON.stringify(manifest));
  return installHost({ launchConfig: decodeLaunchBindingConfig(JSON.stringify(manifest))!,
    selection: { workRef: CCR, rootJobId: "JOB-OFFICE" } });
}

describe("Office uses its exact enrolled workstream through the existing owner", () => {
  it("opens and launches CCR while preserving the default Ecosystem enrollment", async () => {
    const made = installMultiHost();
    const originalBinding = window.MastermindMissionHost!.commandBinding;
    const user = userEvent.setup();
    render(<App />);
    await openOffice(user);
    await freezeDirection(user);
    await user.click(screen.getByRole("button", { name: "Start new work" }));
    const selector = await screen.findByLabelText("Workstream") as HTMLSelectElement;
    expect(selector.value).toBe(CCR);
    expect(selector.disabled).toBe(true);
    expect([...selector.options].map(option => option.value)).toEqual([EEC, CCR]);
    expect(made.prepare).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: /^Launch$/ }));
    await waitFor(() => expect(made.submit).toHaveBeenCalledTimes(1));
    expect(made.prepare.mock.calls[0][0]).toMatchObject({
      targetKey: CCR, payload: { workstream: CCR, objective: DIRECTION,
        department: "alpha-project", execution_profile: "research_only", attempt_limit: 1 } });
    expect(window.MastermindMissionHost!.commandBinding).toBe(originalBinding);
  });

  it("keeps an unenrolled Office direction without falling back to Ecosystem", async () => {
    const made = installMultiHost(false);
    const user = userEvent.setup();
    render(<App />);
    await openOffice(user);
    await freezeDirection(user);
    await user.click(screen.getByRole("button", { name: "Start new work" }));
    expect(previewRefusal().textContent).toContain("cannot offer a handoff");
    expect(screen.queryByLabelText("Goal")).toBeNull();
    expect((screen.getByLabelText("Direction to Meta-CEO") as HTMLTextAreaElement).value).toBe(DIRECTION);
    expect(made.prepare).not.toHaveBeenCalled();
    expect(made.submit).not.toHaveBeenCalled();
  });

  it("retains the selected workstream with its unsent goal across view changes", async () => {
    const made = installMultiHost();
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getByRole("button", { name: "Work queue" }));
    await user.selectOptions(await screen.findByLabelText("Workstream"), CCR);
    await user.type(screen.getByLabelText("Goal"), DIRECTION);
    await openOffice(user);
    await user.click(screen.getByRole("button", { name: "Work queue" }));
    expect((await screen.findByLabelText("Goal") as HTMLTextAreaElement).value).toBe(DIRECTION);
    expect((screen.getByLabelText("Workstream") as HTMLSelectElement).value).toBe(CCR);
    expect(made.prepare).not.toHaveBeenCalled();
    expect(made.submit).not.toHaveBeenCalled();
  });
});

describe("Office BYOK observation integration", () => {
  it("reads and refreshes the role source without changing the frozen direction or preparing work", async () => {
    const made = installHost();
    const observed = (): ByokRolesRead => ({
      schema: BYOK_ROLES_SCHEMA, state: "OBSERVED", reason_code: "OBSERVED",
      roles: [
        { role: "mmmeta", state: "CONFIGURATION_OBSERVED", requested_provider: "zai", requested_model: "glm-5.3" },
        { role: "mmsecretary", state: "ABSENT", requested_provider: null, requested_model: null },
      ],
      source_observation: {
        host_binding_sha256: "a".repeat(64),
        host_boot_id: "12345678-1234-1234-1234-123456789abc",
        implementation_sha: "b".repeat(40), metadata_sha256: "c".repeat(64),
        observed_at_ms: Date.now(),
      },
      proof: { credentials_read: false, provider_called: false, service_observed: false,
        served_model_verified: false, credential_enrollment: "UNVERIFIED" },
    });
    const read = vi.fn(async () => observed());
    window.MastermindMissionHost!.readByokRoles = read;
    window.MastermindMissionHost!.invalidationGeneration = () => 1;
    const user = userEvent.setup();
    render(<App />);
    expect(read).not.toHaveBeenCalled();
    await openOffice(user);
    await screen.findByText("Configuration observed");
    expect(read).toHaveBeenCalledTimes(1);
    await freezeDirection(user);
    await user.click(screen.getByRole("button", { name: "Refresh configuration" }));
    await waitFor(() => expect(read).toHaveBeenCalledTimes(2));
    await screen.findByText("Configuration observed");
    expect((screen.getByLabelText("Direction to Meta-CEO") as HTMLTextAreaElement).value).toBe(DIRECTION);
    expect(screen.getByRole("region", { name: "Direction preview" }).textContent).toContain(DIRECTION);
    await user.click(screen.getByRole("button", { name: "Review connection · Meta-CEO" }));
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByText("zai")).toBeTruthy();
    expect(within(dialog).getByText("glm-5.3")).toBeTruthy();
    expect(within(dialog).getByText("Not verified")).toBeTruthy();
    expect(within(dialog).getByText("Unverified")).toBeTruthy();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(made.prepare).not.toHaveBeenCalled();
    expect(made.submit).not.toHaveBeenCalled();
    expect(made.readOperation).not.toHaveBeenCalled();
    expect(made.store.read("owner-a")).toBeNull();
    await user.click(screen.getByRole("button", { name: "Start new work" }));
    expect((await screen.findByLabelText("Goal") as HTMLTextAreaElement).value).toBe(DIRECTION);
    expect(made.prepare).not.toHaveBeenCalled();
  });
});
