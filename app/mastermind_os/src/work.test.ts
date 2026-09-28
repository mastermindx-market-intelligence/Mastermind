import { describe, expect, it } from "vitest";
import { decodeWorkDocument, type WorkDocument } from "./work";

const digest = (c: string) => c.repeat(64);
export function workAvailable(): WorkDocument {
  return {
    schema: "mastermind.workspace_work_queue.v1",
    generated_at: "2026-09-26T07:00:00Z",
    availability: "AVAILABLE",
    lifecycle_source: {
      schema: "mastermind.fabric_job_root_list.v2",
      runtime: {
        root: "/runtime",
        db_present: true,
        identity: null,
        acquisition: {
          schema: "mastermind.fabric_runtime_acquisition.v1",
          query: { kind: "root_discovery" },
          owner: "executive_runtime",
          snapshot_digest: digest("a"),
          budgets: {
            jobs: 17,
            roots: 64,
            attempts_total: 340,
            attempts_per_job: 20,
            creation_events_per_job: 1,
          },
          truncation: {
            jobs: false,
            roots: false,
            projection: false,
            attempt_job_ids: [],
          },
          provenance: { state: "COMPLETE", unjoined_job_ids: [] },
          generation: {
            schema: "mastermind.runtime_read_observation.v1",
            state: "SAME",
            source_identity: digest("b"),
            before: 9,
            after: 9,
          },
        },
      },
      degraded: [],
    },
    effect_exception: {
      value: "NONE",
      scope: "RUNTIME_CURRENT_WORKER",
      observable: false,
      reason: "no_exception_observed",
    },
    coverage: { count: 4, total: 4, truncated: false, completeness: "COMPLETE" },
    groups: {
      EFFECT_EXCEPTION: [],
      NEEDS_SOL: [],
      NEEDS_WORKER: [],
      WAITING_CAPACITY: [],
      RUNNING: [row("JOB-2", "CHECKPOINTED", "RUNNING", true)],
      QUEUED: [row("JOB-1", "QUEUED", "QUEUED", false)],
      COMPLETED_NOT_ACCEPTED: [row("JOB-3", "COMPLETED", "COMPLETED_NOT_ACCEPTED", true)],
      TERMINAL: [row("JOB-4", "CANCELLED", "TERMINAL", true)],
      UNKNOWN: [],
    },
    source_observation: {
      schema: "mastermind.workspace_source_observation.v1",
      state: "SAME",
      selection: null,
      control_room: {
        instance_before: "owner-instance",
        instance_after: "owner-instance",
        publication_before: 3,
        publication_after: 3,
        document_digest: digest("c"),
        source_validity_digest: digest("d"),
        cache_currentness_digest: digest("e"),
      },
      runtime: {
        schema: "mastermind.runtime_read_observation.v1",
        state: "SAME",
        source_identity: digest("b"),
        before: 9,
        after: 9,
        snapshot_digest: digest("a"),
      },
    },
    reason_codes: [],
  };
}

function row(root: string, status: string, group: string, postStart: boolean): any {
  return {
    root_job_id: root,
    lifecycle: {
      status,
      source: "EXECUTIVE_RUNTIME",
      orchestration_role: "aggregation",
      depth: 0,
    },
    next_actor: {
      value: "UNKNOWN",
      source: null,
      reason: "no_producer",
      evidence_ref: null,
      observed_at: null,
    },
    capacity: {
      value: postStart ? "NOT_APPLICABLE" : "UNKNOWN",
      source: postStart ? "EXECUTIVE_RUNTIME" : null,
      reason: postStart ? "post_start_lifecycle" : "no_producer",
      evidence_ref: null,
      observed_at: null,
    },
    effect: {
      value: "UNKNOWN",
      source: null,
      reason: "no_producer",
      evidence_ref: null,
      observed_at: null,
    },
    acceptance: {
      state: "NOT_PROJECTED",
      producer_owner: null,
      reason: "product acceptance has no producer in this projection",
    },
    group,
  };
}

export function workUnavailable(): WorkDocument {
  const value = workAvailable();
  return {
    ...value,
    availability: "UNAVAILABLE",
    lifecycle_source: null,
    coverage: { count: 0, total: null, truncated: false, completeness: "PARTIAL" },
    groups: Object.fromEntries(
      Object.keys(value.groups).map((key) => [key, []]),
    ) as unknown as WorkDocument["groups"],
    effect_exception: {
      value: "UNKNOWN",
      scope: "RUNTIME_CURRENT_WORKER",
      observable: false,
      reason: "read_refused",
    },
    source_observation: {
      schema: "mastermind.workspace_source_observation.v1",
      state: "UNKNOWN",
      selection: null,
      control_room: null,
      runtime: null,
    },
    reason_codes: ["projection_refused"],
  };
}

describe("closed Work document", () => {
  it("accepts an authenticated SAME document and preserves raw lifecycle status", () => {
    const decoded = decodeWorkDocument(workAvailable());
    expect(decoded?.groups.RUNNING[0].lifecycle.status).toBe("CHECKPOINTED");
    expect(decoded?.groups.QUEUED[0].next_actor).toMatchObject({
      value: "UNKNOWN",
      reason: "no_producer",
    });
  });

  it("accepts the typed 503 unavailable body but never turns it into an empty healthy queue", () => {
    const decoded = decodeWorkDocument(workUnavailable());
    expect(decoded).toMatchObject({
      availability: "UNAVAILABLE",
      coverage: { count: 0, total: null, completeness: "PARTIAL" },
      reason_codes: ["projection_refused"],
    });
  });

  it.each([
    ["composer-only observation", (d: any) => (d.source_observation = null)],
    ["unknown top-level key", (d: any) => (d.extra = true)],
    ["unknown group", (d: any) => (d.groups.NEW_GROUP = [])],
    ["group mismatch", (d: any) => (d.groups.QUEUED[0].group = "RUNNING")],
    ["status drift", (d: any) => (d.groups.RUNNING[0].lifecycle.status = "PAUSED")],
    ["acceptance promotion", (d: any) => (d.groups.QUEUED[0].acceptance.state = "ACCEPTED")],
    ["count mismatch", (d: any) => (d.coverage.count = 3)],
    ["runtime drift", (d: any) => (d.source_observation.runtime.after = 10)],
    ["unknown refusal", (d: any) => (d.reason_codes = ["mystery"])],
  ])("refuses %s", (_name, mutate) => {
    const value: any = structuredClone(workAvailable());
    mutate(value);
    expect(decodeWorkDocument(value)).toBeNull();
  });

  it("does not coerce unsupported COO ownership into a Work row", () => {
    const value: any = structuredClone(workAvailable());
    value.groups.QUEUED[0].next_actor.value = "NEEDS_COO";
    expect(decodeWorkDocument(value)).toBeNull();
  });
});
