// @vitest-environment jsdom
import { StrictMode } from "react";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ProjectConversationAssociation } from "./ProjectConversationAssociation";
import {
  decodeProjectAssociation,
  type ProjectAssociationRead,
  type ProjectAssociationSelection,
  type ProjectAssociationState,
} from "./project-association";

const SELECTION: ProjectAssociationSelection = { workRef: "WS:ALPHA01", rootJobId: "JOB-7" };
type AssociationPort = ProjectAssociationRead;
type AssociationRequest = ProjectAssociationSelection & { signal: AbortSignal };

function hex64(seed: string): string {
  return (seed + "0".repeat(64)).slice(0, 64);
}

function projectSource(selection: ProjectAssociationSelection): Record<string, unknown> {
  return {
    repository: "macro",
    commit: "0123456789abcdef0123456789abcdef01234567",
    path: `agentos/workstreams/${selection.workRef.replace("WS:", "WS-")}.md`,
    content_sha256: hex64("c1"),
    request_sha256: hex64("d2"),
  };
}

function runtimeCreation(): Record<string, unknown> {
  return {
    intent_id: "runtime-intent-1",
    fingerprint: hex64("f1"),
    creation_event_sha256: hex64("e1"),
  };
}

function materialization(): Record<string, unknown> {
  return {
    receipt_sha256: hex64("a3"),
    recorded_at: "2026-11-01T12:00:00.000Z",
    operation_kind: "start_session",
    epoch_sha256: hex64("b4"),
    process_generation_sha256: hex64("c5"),
    provider_session_sha256: hex64("d6"),
    generation_number: 1,
  };
}

function ownerBody(
  state: ProjectAssociationState,
  selection: ProjectAssociationSelection = SELECTION,
): Record<string, unknown> {
  const base: Record<string, unknown> = {
    schema: "mastermind.workspace_project_session_association.v1",
    selection: { work_ref: selection.workRef, root_job_id: selection.rootJobId },
    availability: "AVAILABLE",
    state,
    reason: null,
    observational_only: true,
    can_send: false,
    continuation_target: null,
    project_source: projectSource(selection),
    runtime_creation: runtimeCreation(),
    materialization: materialization(),
  };
  if (state === "RECORDED_MATERIALIZATION") return { ...base, reason: "BROKER_RESTARTED" };
  if (state === "PREPARING") return { ...base, reason: "NOT_MATERIALIZED", materialization: null };
  if (state === "UNAVAILABLE") {
    return {
      ...base,
      availability: "UNAVAILABLE",
      reason: "SOURCE_CHANGED",
      project_source: null,
      runtime_creation: null,
      materialization: null,
    };
  }
  return base;
}

function decodeFixture(state: ProjectAssociationState): NonNullable<ReturnType<typeof decodeProjectAssociation>> {
  const decoded = decodeProjectAssociation(ownerBody(state), SELECTION);
  if (!decoded) throw new Error("test fixture must decode");
  return decoded;
}

function deferred(): {
  promise: Promise<unknown>;
  resolve: (value: unknown) => void;
  reject: (error: unknown) => void;
} {
  let resolve!: (value: unknown) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<unknown>((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}

function tick(): Promise<void> {
  return new Promise(resolve => { setTimeout(resolve, 0); });
}

async function settle(): Promise<void> {
  await act(async () => { await tick(); });
}

function mount(port: AssociationPort, props: Partial<Parameters<typeof ProjectConversationAssociation>[0]> = {}) {
  return render(<ProjectConversationAssociation selection={SELECTION} authGeneration={1}
    hostGeneration="host-gen-1" readAssociation={port} {...props} />);
}

afterEach(cleanup);

describe("ProjectConversationAssociation observation read", () => {
  it("issues exactly one bounded read with the exact frozen selection and signal", async () => {
    const port = vi.fn(() => Promise.resolve(ownerBody("MATERIALIZED_OBSERVATION")));
    mount(port);
    expect(port.mock.calls.length).toBe(1);
    const request = (port.mock.calls[0] as unknown[])[0] as AssociationRequest;
    expect(Object.keys(request).sort()).toEqual(["rootJobId", "signal", "workRef"]);
    expect(Object.isFrozen(request)).toBe(true);
    expect(request.workRef).toBe("WS:ALPHA01");
    expect(request.rootJobId).toBe("JOB-7");
    expect(request.signal instanceof AbortSignal).toBe(true);
    await settle();
    expect(screen.getByText("A managed session was observed.")).toBeTruthy();
    await settle();
    expect(port.mock.calls.length).toBe(1);
    expect(decodeFixture("MATERIALIZED_OBSERVATION").state).toBe("MATERIALIZED_OBSERVATION");
  });

  it("renders a precise local capability note and never reads without selection, host generation or port", async () => {
    const port = vi.fn((_request: AssociationRequest) => Promise.resolve(ownerBody("MATERIALIZED_OBSERVATION")));
    const view = mount(port, { selection: null });
    expect(screen.getByText("No valid workspace selection is available for this evidence read.")).toBeTruthy();
    expect(screen.queryByRole("button")).toBeNull();
    view.rerender(<ProjectConversationAssociation selection={SELECTION} authGeneration={1}
      hostGeneration={null} readAssociation={port} />);
    expect(screen.getByText("No current host generation is available for this evidence read.")).toBeTruthy();
    view.rerender(<ProjectConversationAssociation selection={SELECTION} authGeneration={1}
      hostGeneration="host-gen-1" />);
    expect(screen.getByText("No association observation port is connected for this selection.")).toBeTruthy();
    await settle();
    expect(port.mock.calls.length).toBe(0);
  });

  it("shows the exact owner unavailable reason and never send, continue or resume affordances", async () => {
    const port = vi.fn(() => Promise.resolve(ownerBody("UNAVAILABLE")));
    mount(port);
    await settle();
    expect(screen.getByText("Session information is unavailable here.")).toBeTruthy();
    expect(screen.getByText("SOURCE_CHANGED")).toBeTruthy();
    expect(screen.getByText(/Observation only:/)).toBeTruthy();
    expect(screen.getAllByRole("button").length).toBe(1);
    expect(screen.getByRole("button", { name: "Refresh observation" })).toBeTruthy();
    expect(screen.queryByText("Send")).toBeNull();
    expect(screen.queryByText("Continue")).toBeNull();
    expect(screen.queryByText("Resume")).toBeNull();
    expect(decodeFixture("UNAVAILABLE").reason).toBe("SOURCE_CHANGED");
  });

  it("renders PREPARING without working, starting or conversation-ready claims", async () => {
    const port = vi.fn(() => Promise.resolve(ownerBody("PREPARING")));
    mount(port);
    await settle();
    expect(screen.getByText("The project and its work are recorded. No managed session has been recorded yet.")).toBeTruthy();
    expect(screen.queryByText("The receipt time above is recorded by the owner; it is not a locally observed clock.")).toBeNull();
    expect(screen.getByText("agentos/workstreams/WS-ALPHA01.md")).toBeTruthy();
    expect(screen.getByText("runtime-intent-1")).toBeTruthy();
    expect(screen.queryByText("receipt_sha256")).toBeNull();
    expect(screen.queryByText("Working")).toBeNull();
    expect(screen.queryByText("Starting")).toBeNull();
    expect(screen.queryByText("Conversation ready")).toBeNull();
  });

  it("hides prior data when the auth generation is replaced and rejects the late completion", async () => {
    const pending = deferred();
    const port1 = vi.fn((_request: AssociationRequest) => pending.promise);
    const view = mount(port1);
    expect(screen.getByText("Loading session information…")).toBeTruthy();
    const port2 = vi.fn(() => Promise.resolve(ownerBody("UNAVAILABLE")));
    view.rerender(<ProjectConversationAssociation selection={SELECTION} authGeneration={2}
      hostGeneration="host-gen-1" readAssociation={port2} />);
    expect(port2.mock.calls.length).toBe(1);
    await settle();
    expect(screen.getByText("SOURCE_CHANGED")).toBeTruthy();
    pending.resolve(ownerBody("MATERIALIZED_OBSERVATION"));
    await settle();
    expect(screen.queryByText("A managed session was observed.")).toBeNull();
    expect(screen.queryByText("MATERIALIZED_OBSERVATION")).toBeNull();
    expect(port1.mock.calls.length).toBe(1);
  });

  it("clears and re-reads when the host generation or the port identity is replaced", async () => {
    const port1 = vi.fn(() =>
      port1.mock.calls.length === 1
        ? Promise.resolve(ownerBody("MATERIALIZED_OBSERVATION"))
        : new Promise<unknown>(() => {}));
    const view = mount(port1);
    await settle();
    expect(screen.getByText("A managed session was observed.")).toBeTruthy();
    view.rerender(<ProjectConversationAssociation selection={SELECTION} authGeneration={1}
      hostGeneration="host-gen-2" readAssociation={port1} />);
    expect(screen.getByText("Loading session information…")).toBeTruthy();
    expect(screen.queryByText("A managed session was observed.")).toBeNull();
    const port2 = vi.fn(() => Promise.resolve(ownerBody("RECORDED_MATERIALIZATION")));
    view.rerender(<ProjectConversationAssociation selection={SELECTION} authGeneration={1}
      hostGeneration="host-gen-2" readAssociation={port2} />);
    await settle();
    expect(port1.mock.calls.length).toBe(2);
    expect(port2.mock.calls.length).toBe(1);
    expect(screen.getByText("RECORDED_MATERIALIZATION")).toBeTruthy();
    expect(screen.getByText("AVAILABLE")).toBeTruthy();
    expect(screen.getByText("A saved session record is available. Its current connection is not confirmed. Nothing resumes automatically.")).toBeTruthy();
  });

  it("re-reads every leg of an A-B-A selection change through the fixed port", async () => {
    const port = vi.fn((request: AssociationRequest) =>
      Promise.resolve(ownerBody("MATERIALIZED_OBSERVATION", {
        workRef: request.workRef,
        rootJobId: request.rootJobId,
      })));
    const view = mount(port);
    await settle();
    const beta: ProjectAssociationSelection = { workRef: "WS:BETA02", rootJobId: "JOB-8" };
    view.rerender(<ProjectConversationAssociation selection={beta} authGeneration={1}
      hostGeneration="host-gen-1" readAssociation={port} />);
    await settle();
    expect(screen.getByText("agentos/workstreams/WS-BETA02.md")).toBeTruthy();
    view.rerender(<ProjectConversationAssociation selection={SELECTION} authGeneration={1}
      hostGeneration="host-gen-1" readAssociation={port} />);
    await settle();
    expect(port.mock.calls.length).toBe(3);
    expect(port.mock.calls.map(call => (call[0] as AssociationRequest).workRef))
      .toEqual(["WS:ALPHA01", "WS:BETA02", "WS:ALPHA01"]);
    expect(screen.getByText("agentos/workstreams/WS-ALPHA01.md")).toBeTruthy();
  });

  it("performs exactly one read per explicit refresh, reports the owner error and keeps no stale success", async () => {
    const responses: unknown[] = [ownerBody("MATERIALIZED_OBSERVATION"), ownerBody("UNAVAILABLE")];
    const port = vi.fn(() => Promise.resolve(responses.shift() as unknown));
    mount(port);
    await settle();
    expect(screen.getByText("A managed session was observed.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Refresh observation" }));
    await settle();
    expect(port.mock.calls.length).toBe(2);
    expect(screen.getByText("SOURCE_CHANGED")).toBeTruthy();
    expect(screen.queryByText("A managed session was observed.")).toBeNull();
    await settle();
    expect(port.mock.calls.length).toBe(2);
  });

  it("resolves under StrictMode without a stuck busy state and never paints after unmount", async () => {
    const port = vi.fn(() => Promise.resolve(ownerBody("MATERIALIZED_OBSERVATION")));
    const strictView = render(<StrictMode><ProjectConversationAssociation selection={SELECTION}
      authGeneration={1} hostGeneration="host-gen-1" readAssociation={port} /></StrictMode>);
    await settle();
    expect(screen.getByText("A managed session was observed.")).toBeTruthy();
    const button = screen.getByRole("button", { name: "Refresh observation" }) as HTMLButtonElement;
    expect(button.disabled).toBe(false);
    strictView.unmount();

    const pending = deferred();
    const late = vi.fn((_request: AssociationRequest) => pending.promise);
    const view = mount(late);
    view.unmount();
    pending.resolve(ownerBody("MATERIALIZED_OBSERVATION"));
    await settle();
    expect(document.body.querySelector("section")).toBeNull();
  });

  it("keeps a local read failure and a local decode result distinct from any owner reason", async () => {
    const failing = vi.fn(() => Promise.reject(new Error("local transport down")));
    const failingView = mount(failing);
    await settle();
    expect(screen.getByText("The observation read failed locally before an owner response was decoded. This is not an owner-reported reason.")).toBeTruthy();
    expect(screen.queryByText("SOURCE_CHANGED")).toBeNull();
    failingView.unmount();

    const malformed = vi.fn(() => Promise.resolve({ unexpected: true }));
    const view = mount(malformed);
    await settle();
    expect(screen.getByText("The response could not be decoded as an owner association document. This is a local decoding result, not an owner-reported reason.")).toBeTruthy();
    expect(screen.queryByText("SOURCE_CHANGED")).toBeNull();
    view.unmount();
  });

  it("renders the zh-CN static copy while preserving raw identifiers, hashes and clocks", async () => {
    const port = vi.fn(() => Promise.resolve(JSON.stringify(ownerBody("MATERIALIZED_OBSERVATION"))));
    mount(port, { locale: "zh-CN" });
    await settle();
    expect(screen.getByText("会话记录")).toBeTruthy();
    expect(screen.getByText("已观测到托管会话。")).toBeTruthy();
    expect(screen.getByText(/仅观测：/)).toBeTruthy();
    expect(screen.getByText("WS:ALPHA01")).toBeTruthy();
    expect(screen.getByText("JOB-7")).toBeTruthy();
    expect(screen.getByText("agentos/workstreams/WS-ALPHA01.md")).toBeTruthy();
    expect(screen.getByText(hex64("a3"))).toBeTruthy();
    expect(screen.getByText("2026-11-01T12:00:00.000Z")).toBeTruthy();
    expect(screen.getByText("所有者凭据记录时间")).toBeTruthy();
    expect(screen.getByText("上方的凭据时间由所有者记录，不是本地观测时钟。")).toBeTruthy();
    expect(screen.getByRole("button", { name: "刷新观测" })).toBeTruthy();
  });
  it("keeps background and explicit refresh completion from taking keyboard focus", async () => {
    const initial = deferred(), refreshed = deferred();
    const port = vi.fn<AssociationPort>()
      .mockImplementationOnce(() => initial.promise).mockImplementationOnce(() => refreshed.promise);
    render(<><input aria-label="Other project input" /><ProjectConversationAssociation selection={SELECTION}
      authGeneration={1} hostGeneration="host-gen-1" readAssociation={port} /></>);
    const outside = screen.getByRole("textbox", {name: "Other project input"});
    outside.focus();
    initial.resolve(ownerBody("MATERIALIZED_OBSERVATION")); await settle();
    expect(document.activeElement).toBe(outside);
    const refresh = screen.getByRole("button", {name: "Refresh observation"});
    refresh.focus(); fireEvent.click(refresh);
    refreshed.resolve(ownerBody("UNAVAILABLE")); await settle();
    expect(document.activeElement).toBe(refresh);
    expect(port).toHaveBeenCalledTimes(2);
  });

  it("keeps plain public states separate from closed raw evidence details", async () => {
    const port = vi.fn(() => Promise.resolve(ownerBody("MATERIALIZED_OBSERVATION")));
    mount(port); await settle();
    expect(screen.getByRole("heading", {level: 2}).textContent).toBe("Session evidence");
    const status = screen.getByRole("status");
    expect(status.textContent).toBe("A managed session was observed.");
    const details = screen.getByText("Evidence details").closest("details")!;
    expect(details.open).toBe(false);
    for (const raw of ["AVAILABLE", "MATERIALIZED_OBSERVATION", SELECTION.workRef, SELECTION.rootJobId]) {
      expect(screen.getByText(raw).closest("details")).toBe(details);
      expect(status.textContent).not.toContain(raw);
    }
  });

});
