// @vitest-environment jsdom
// Synthetic App routing/consumer proof only. Producer, permissions and actual
// authenticated runtime acceptance remain separate checks.
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
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
  history.replaceState(null, "", "/os/?work_ref=WS%3ADESIGN&root_job_id=JOB-001");
  delete (window as any).__TAURI_INTERNALS__;
  delete window.MastermindMissionHost;
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  delete window.MastermindMissionHost;
});

it("opens exact retained content without a CURRENT Mission or Mission result links", async () => {
  const user = userEvent.setup();
  const result = structuredClone(resultFixture);
  const selected = result.selection;
  const room: any = controlRoomFixture();
  room.work[0].work_ref = selected.work_ref;
  room.work[0].agent_os.workstream = selected.work_ref.slice(3);
  room.work[0].agent_os.title = "Retained-result project";
  Object.assign(room.autonomy.responsibilities[0], {
    responsibility_ref: selected.work_ref,
    root_job_id: selected.root_job_id,
    root_job_candidates: [selected.root_job_id],
    root_job_ambiguous: false,
    runtime_root_state: "RESOLVED",
  });
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
    readProgramsObservation: async () => decodeProgramsObservation({ ...structuredClone(programsFixture), control_room: room }),
    readMissionV3: vi.fn(async () => { throw new Error("SOURCE_UNAVAILABLE"); }),
    readResultReferences: list,
    readResult: read,
    invalidationGeneration: () => 1,
    auth: { getState: () => signed, subscribe: () => () => {}, signIn: async () => {}, signOut: async () => {} },
  };
  render(<App />);
  await user.click(screen.getByRole("button", { name: "Projects" }));
  const project = await screen.findByRole("button", { name: /Retained-result project/ });
  await user.click(project);
  const title = await screen.findByText("Retained results", { exact: true });
  const section = title.closest("section") ?? title.parentElement!;
  const trigger = title.closest("button,summary");
  if (trigger) await user.click(trigger);
  else {
    const open = within(section).queryByRole("button", { name: /retained|read|show/i });
    if (open) await user.click(open);
  }
  await waitFor(() => expect(list).toHaveBeenCalledTimes(1));
  expect(read).not.toHaveBeenCalled();
  expect(section.textContent).toContain("2026-10-21");
  expect(section.textContent?.toUpperCase()).toContain("STALE");
  await user.click(within(section).getByRole("button", { name: new RegExp(selected.job_id) }));
  await waitFor(() => expect(read).toHaveBeenCalledTimes(1));
  expect(read.mock.calls[0][0]).toMatchObject({
    workRef: selected.work_ref, rootJobId: selected.root_job_id, jobId: selected.job_id,
    attemptId: selected.attempt_id, resultEnvelopeDigest: selected.result_envelope_digest,
  });
  expect(await screen.findByRole("heading", { name: "Result detail" })).toBeTruthy();
  expect(window.MastermindMissionHost.readMissionV3).toHaveBeenCalled();
});
