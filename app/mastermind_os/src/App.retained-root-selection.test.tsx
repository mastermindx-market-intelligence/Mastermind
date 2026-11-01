// @vitest-environment jsdom
// Synthetic App routing/consumer proof only. Producer, permissions and actual
// authenticated runtime acceptance remain separate checks.
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { App } from "./App";
import { controlRoomFixture } from "./test-fixtures";
import { decodeProgramsObservation } from "./programs-observation";
import programsFixture from "./fixtures/programs-available-workspace-service.json";
import { decodeResultReferencesEnvelope } from "./result-references";
import type { ResultSelection } from "./result";
import resultFixture from "./fixtures/result-design-available-at-16384-socket-bytes.json";

beforeEach(() => {
  history.replaceState(null, "", "/os/");
  delete (window as any).__TAURI_INTERNALS__;
  delete window.MastermindMissionHost;
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); delete window.MastermindMissionHost; });

// Explicit synthetic transport fixture; no server/Runtime authority is mocked
// into a claim of actual authenticated product acceptance.
function setup() {
  let notify: (state: any) => void = () => {};
  const result = structuredClone(resultFixture);
  const selected = result.selection;
  const room: any = controlRoomFixture();
  room.work[0].work_ref = selected.work_ref;
  room.work[0].agent_os.workstream = selected.work_ref.slice(3);
  room.work[0].agent_os.title = "Retained-result project";
  Object.assign(room.autonomy.responsibilities[0], {
    responsibility_ref: selected.work_ref,
    root_job_id: null,
    root_job_candidates: [selected.root_job_id, "JOB-999"],
    root_job_ambiguous: true,
    runtime_root_state: "CONFLICT",
    freshness: "stale",
  });
  room.autonomy.responsibilities[0].validity.card.valid_for_ms = null;
  const pair = { work_ref: selected.work_ref, root_job_id: selected.root_job_id };
  const generation = structuredClone(result.source_observation.runtime!);
  const references = {
    schema: "mastermind.workspace_result_references.v1",
    selection: pair,
    availability: "AVAILABLE",
    reason_codes: [],
    catalogue: { generated_at: "2026-10-21T05:28:23Z", freshness: "STALE" },
    index: {
      schema: "mastermind.fabric_result_reference_index.v1",
      root_job_id: selected.root_job_id,
      snapshot_digest: "c".repeat(64),
      generation,
      availability: "AVAILABLE",
      refs: [{ root_job_id: selected.root_job_id, job_id: selected.job_id,
        attempt_id: selected.attempt_id, result_envelope_digest: selected.result_envelope_digest,
        orchestration_role: "review", validation: "UNVALIDATED" }],
      absent_job_ids: [], omitted_job_ids: [], truncated: false,
    },
    source_observation: {
      schema: "mastermind.workspace_source_observation.v1", state: "SAME", selection: pair,
      control_room: structuredClone(result.source_observation.control_room), runtime: generation,
    },
  };
  const referenceDocument = decodeResultReferencesEnvelope(references,
    { workRef: selected.work_ref, rootJobId: selected.root_job_id });
  expect(referenceDocument).not.toBeNull();
  const list = vi.fn(async (_request: { workRef: string; rootJobId: string; signal: AbortSignal }) => referenceDocument!);
  const read = vi.fn(async (_request: ResultSelection & { signal: AbortSignal }) => result);
  const signed = { status: "signed_in" as const, reason: null, acquisition: true, content: false };
  window.MastermindMissionHost = {
    readPrograms: async () => room,
    readProgramsObservation: vi.fn(async () => decodeProgramsObservation({ ...structuredClone(programsFixture), control_room: structuredClone(room) })),
    readMissionV3: vi.fn(async () => { throw new Error("SOURCE_UNAVAILABLE"); }),
    readResultReferences: list,
    readResult: read,
    invalidationGeneration: () => 1,
    auth: { getState: () => signed, subscribe: (cb) => { notify = cb; return () => {}; }, signIn: async () => {}, signOut: async () => {} },
  };

  return { room, result, references, selected, list, read,
    notify: (state: any) => notify(state) };
}
async function choose(user: ReturnType<typeof userEvent.setup>, root: string) {
  const button = screen.getAllByRole("button").find(b =>
    !(b as HTMLButtonElement).disabled && b.textContent?.includes(root));
  expect(button).toBeTruthy();
  await user.click(button!);
}
async function openPrograms(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole("button", { name: "Open Programs" }));
  await screen.findByText(/Root conflict:/);
}
function historyRegion() { return screen.getByRole("region", { name: "Retained results" }); }

it("explicit candidate history never selects a Mission or enables its action path", async () => {
  const f = setup(), user = userEvent.setup();
  render(<App />); await openPrograms(user);
  expect(f.list).not.toHaveBeenCalled();
  const originalLocation = location.search;
  const programme = screen.getByRole("button", { name: /Retained-result project/ }) as HTMLButtonElement;
  expect(programme.disabled).toBe(true);
  await choose(user, f.selected.root_job_id);
  await user.click(within(historyRegion()).getByRole("button", { name: "Show retained results" }));
  await waitFor(() => expect(f.list).toHaveBeenCalledTimes(1));
  expect(f.list.mock.calls[0][0]).toMatchObject({ workRef: f.selected.work_ref, rootJobId: f.selected.root_job_id });
  expect(location.search).toBe(originalLocation);
  expect(window.MastermindMissionHost!.readMissionV3).not.toHaveBeenCalled();
  expect(screen.getByText(/Root conflict:/)).toBeTruthy();
  await user.click(within(historyRegion()).getByRole("button", { name: new RegExp(f.selected.job_id) }));
  await waitFor(() => expect(f.read).toHaveBeenCalledTimes(1));
  expect(f.read.mock.calls[0][0]).toMatchObject({ workRef: f.selected.work_ref,
    rootJobId: f.selected.root_job_id, jobId: f.selected.job_id,
    attemptId: f.selected.attempt_id, resultEnvelopeDigest: f.selected.result_envelope_digest });
  expect(await screen.findByRole("heading", { name: "Result detail" })).toBeTruthy();
});

it("changing selected roots aborts the old history read without reopening Mission", async () => {
  const f = setup(), user = userEvent.setup();
  let resolve!: (x: any) => void;
  f.list.mockImplementationOnce(() => new Promise(r => { resolve = r; }));
  render(<App />); await openPrograms(user); await choose(user, f.selected.root_job_id);
  await user.click(within(historyRegion()).getByRole("button", { name: "Show retained results" }));
  await waitFor(() => expect(f.list).toHaveBeenCalledTimes(1));
  const signal = f.list.mock.calls[0][0].signal;
  await choose(user, "JOB-999");
  expect(signal.aborted).toBe(true);
  await act(async () => resolve(f.references));
  expect(f.read).not.toHaveBeenCalled();
  expect(window.MastermindMissionHost!.readMissionV3).not.toHaveBeenCalled();
});

it("a new paired catalogue read clears the choice even with identical candidates", async () => {
  const f = setup(), user = userEvent.setup();
  render(<App />); await openPrograms(user); await choose(user, f.selected.root_job_id);
  expect(historyRegion()).toBeTruthy();
  await user.click(screen.getByRole("button", { name: "Refresh Projects" }));
  await waitFor(() => expect(screen.queryByRole("region", { name: "Retained results" })).toBeNull());
  expect(f.list).not.toHaveBeenCalled();
});

it("auth revocation aborts and clears selected retained history", async () => {
  const f = setup(), user = userEvent.setup();
  let resolve!: (x: any) => void;
  f.list.mockImplementationOnce(() => new Promise(r => { resolve = r; }));
  render(<App />); await openPrograms(user); await choose(user, f.selected.root_job_id);
  await user.click(within(historyRegion()).getByRole("button", { name: "Show retained results" }));
  await waitFor(() => expect(f.list).toHaveBeenCalledTimes(1));
  const signal = f.list.mock.calls[0][0].signal;
  act(() => f.notify({ status: "signed_out", reason: null, acquisition: false, content: false }));
  await waitFor(() => expect(screen.queryByRole("region", { name: "Retained results" })).toBeNull());
  expect(signal.aborted).toBe(true);
  await act(async () => resolve(f.references));
  expect(f.read).not.toHaveBeenCalled();
});

it("changing the Mission workstream aborts independent retained history", async () => {
  const f = setup(), user = userEvent.setup();
  let resolve!: (x: any) => void;
  f.list.mockImplementationOnce(() => new Promise(r => { resolve = r; }));
  render(<App />); await openPrograms(user); await choose(user, f.selected.root_job_id);
  await user.click(within(historyRegion()).getByRole("button", { name: "Show retained results" }));
  await waitFor(() => expect(f.list).toHaveBeenCalledTimes(1));
  const signal = f.list.mock.calls[0][0].signal;
  act(() => {
    history.pushState(null, "", "/os/?work_ref=WS%3AOTHER&root_job_id=JOB-888");
    fireEvent(window, new PopStateEvent("popstate"));
  });
  await waitFor(() => expect(signal.aborted).toBe(true));
  await act(async () => resolve(f.references));
  expect(f.list).toHaveBeenCalledTimes(1);
  expect(f.read).not.toHaveBeenCalled();
  expect(screen.queryByRole("heading", { name: "Result detail" })).toBeNull();
});
