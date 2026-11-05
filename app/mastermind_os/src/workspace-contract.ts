/** Validation of authenticated fixed-service responses, never a currentness producer. */
const record = (v: unknown): v is Record<string, unknown> =>
  typeof v === "object" && v !== null && !Array.isArray(v);
const exact = (v: Record<string, unknown>, keys: string[]) =>
  Object.keys(v).length === keys.length &&
  keys.every((k) => Object.hasOwn(v, k));
const text = (v: unknown, max = 256): v is string =>
  typeof v === "string" &&
  v.length > 0 &&
  v.length <= max &&
  !/[\u0000-\u001f\u007f]/.test(v);
// Mission companions reuse the same opaque owner-reference grammar.
export { text as isOwnerObservationReference };
const hash = (v: unknown): v is string =>
  typeof v === "string" && /^[0-9a-f]{64}$/.test(v);
const integer = (v: unknown, min = 0): v is number =>
  Number.isSafeInteger(v) && Number(v) >= min;
const nullable = (v: unknown, check: (v: unknown) => boolean) =>
  v === null || check(v);
const state = (v: unknown) =>
  v === "SAME" || v === "UNKNOWN" || v === "CONFLICT";
type Pair = { work_ref: string; root_job_id: string };
export interface OwnerObservation {
  schema: "mastermind.workspace_source_observation.v1";
  state: "SAME" | "UNKNOWN" | "CONFLICT";
  selection: Pair | null;
  control_room: null | {
    instance_before: string | null;
    instance_after: string | null;
    publication_before: number | null;
    publication_after: number | null;
    document_digest: string | null;
    source_validity_digest: string | null;
    cache_currentness_digest: string | null;
  };
  runtime: null | {
    schema: "mastermind.runtime_read_observation.v1";
    state: "SAME" | "UNKNOWN" | "CONFLICT";
    source_identity: string | null;
    before: number | null;
    after: number | null;
    snapshot_digest: string | null;
  };
}
export function decodeOwnerObservation(
  value: unknown,
  selection: Pair | null,
): OwnerObservation | null {
  if (
    !record(value) ||
    !exact(value, [
      "schema",
      "state",
      "selection",
      "control_room",
      "runtime",
    ]) ||
    value.schema !== "mastermind.workspace_source_observation.v1" ||
    !state(value.state)
  )
    return null;
  if (
    selection === null
      ? value.selection !== null
      : !record(value.selection) ||
        !exact(value.selection, ["work_ref", "root_job_id"]) ||
        value.selection.work_ref !== selection.work_ref ||
        value.selection.root_job_id !== selection.root_job_id
  )
    return null;
  const c = value.control_room;
  if (
    c !== null &&
    (!record(c) ||
      !exact(c, [
        "instance_before",
        "instance_after",
        "publication_before",
        "publication_after",
        "document_digest",
        "source_validity_digest",
        "cache_currentness_digest",
      ]) ||
      !nullable(c.instance_before, text) ||
      !nullable(c.instance_after, text) ||
      !nullable(c.publication_before, (v) => integer(v, 1)) ||
      !nullable(c.publication_after, (v) => integer(v, 1)) ||
      ![
        c.document_digest,
        c.source_validity_digest,
        c.cache_currentness_digest,
      ].every((v) => nullable(v, hash)))
  )
    return null;
  const r = value.runtime;
  if (selection === null) {
    if (r !== null) return null;
  } else if (
    r !== null &&
    (!record(r) ||
      !exact(r, [
        "schema",
        "state",
        "source_identity",
        "before",
        "after",
        "snapshot_digest",
      ]) ||
      r.schema !== "mastermind.runtime_read_observation.v1" ||
      !state(r.state) ||
      !nullable(r.source_identity, text) ||
      !nullable(r.before, integer) ||
      !nullable(r.after, integer) ||
      !nullable(r.snapshot_digest, hash))
  )
    return null;
  if (
    record(r) &&
    r.state === "SAME" &&
    (!text(r.source_identity) ||
      !integer(r.before) ||
      r.before !== r.after ||
      !hash(r.snapshot_digest))
  )
    return null;
  if (
    value.state === "SAME" &&
    (!record(c) ||
      !text(c.instance_before) ||
      c.instance_before !== c.instance_after ||
      !integer(c.publication_before, 1) ||
      c.publication_before !== c.publication_after ||
      ![
        c.document_digest,
        c.source_validity_digest,
        c.cache_currentness_digest,
      ].every(hash) ||
      (selection !== null &&
        (!record(r) ||
          r.state !== "SAME" ||
          !text(r.source_identity) ||
          !integer(r.before) ||
          r.before !== r.after ||
          !hash(r.snapshot_digest))))
  )
    return null;
  return value as unknown as OwnerObservation;
}
export function decodeProgramsEnvelope(value: unknown): unknown {
  if (
    !record(value) ||
    !exact(value, [
      "schema",
      "availability",
      "control_room",
      "source_observation",
      "reason_codes",
    ]) ||
    value.schema !== "mastermind.workspace_programs.v1" ||
    !["AVAILABLE", "UNAVAILABLE"].includes(String(value.availability)) ||
    !Array.isArray(value.reason_codes) ||
    value.reason_codes.length > 64 ||
    !value.reason_codes.every((v) => text(v, 128))
  )
    throw new Error("PROGRAM_RESPONSE_INVALID");
  const observation = decodeOwnerObservation(value.source_observation, null);
  if (!observation) throw new Error("PROGRAM_OBSERVATION_INVALID");
  if (value.availability !== "AVAILABLE")
    throw new Error("PROGRAM_SOURCE_UNAVAILABLE");
  if (
    observation.state !== "SAME" ||
    !record(value.control_room) ||
    value.control_room.schema !== "mastermind.chairman_control_room.v1"
  )
    throw new Error("PROGRAM_SOURCE_UNQUALIFIED");
  return value.control_room;
}
export interface WindowItem {
  id: string;
  source_sequence: number;
  publication_sequence: number;
  state: "partial" | "completed";
  kind: "visible-response" | "withheld";
  text: string | null;
  representation: "VISIBLE_TEXT" | "FILTERED_VISIBLE_TEXT" | "WITHHELD";
  display_sha256: string | null;
}
export interface WindowView {
  schema: "mastermind.workspace.visible_window_candidate.v1";
  source_ref: string;
  scope: "one-managed-turn-window";
  observed_at: string;
  epoch: string;
  terminal: boolean;
  coverage: "OBSERVED_WINDOW" | "READ_LIMIT_REACHED" | "GAP_PRESENT";
  history: "NOT_PROVEN";
  acceptance: "NOT_PROJECTED";
  capabilities: { send: false; provider_control: false; history: false };
  items: WindowItem[];
  gaps: Array<{ first: number; last: number; reason: "SOURCE_REPORTED_GAP" }>;
}
export interface ObservationBinding {
  job_id: string;
  attempt_id: string;
}
interface WindowEnvelope {
  selection_ref: string;
  mode: "observed-turn-window";
  view: WindowView;
}
export interface WindowDocumentV1 extends WindowEnvelope {
  schema: "mastermind.workspace.window_read_candidate.v1";
}
export interface WindowDocumentV2 extends WindowEnvelope {
  schema: "mastermind.workspace.window_read_candidate.v2";
  observation_binding: ObservationBinding;
}
export type WindowDocument = WindowDocumentV1 | WindowDocumentV2;
export interface ObservedMissionAssociation {
  state: "OBSERVED_MISSION_ASSOCIATION";
  job_id: string;
  attempt_id: string;
  window_observed_at: string;
  mission_generated_at: string | null;
}
const JOB_ID = /^JOB-[0-9]{1,9}$/;
const ATTEMPT_ID = /^ATT-[0-9a-f]{32}$/;
function decodeObservationBinding(value: unknown): ObservationBinding | null {
  if (
    !record(value) ||
    !exact(value, ["job_id", "attempt_id"]) ||
    typeof value.job_id !== "string" ||
    typeof value.attempt_id !== "string" ||
    !JOB_ID.test(value.job_id) ||
    !ATTEMPT_ID.test(value.attempt_id)
  )
    return null;
  return { job_id: value.job_id, attempt_id: value.attempt_id };
}
async function digest(value: string) {
  return Array.from(
    new Uint8Array(
      await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value)),
    ),
  )
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}
export async function decodeWindow(
  value: unknown,
): Promise<WindowDocument | null> {
  try {
    value = structuredClone(value);
  } catch {
    return null;
  }
  if (!record(value)) return null;
  const schema = value.schema;
  const v1 = schema === "mastermind.workspace.window_read_candidate.v1";
  const v2 = schema === "mastermind.workspace.window_read_candidate.v2";
  if (
    !(v1
      ? exact(value, ["schema", "selection_ref", "mode", "view"])
      : v2
        ? exact(value, [
            "schema",
            "selection_ref",
            "mode",
            "view",
            "observation_binding",
          ])
        : false) ||
    value.mode !== "observed-turn-window" ||
    typeof value.selection_ref !== "string" ||
    !/^managed-window:[A-Za-z0-9][A-Za-z0-9_.-]{0,95}$/.test(
      value.selection_ref,
    ) ||
    value.selection_ref.includes("..")
  )
    return null;
  const binding = v2 ? decodeObservationBinding(value.observation_binding) : null;
  if (v2 && !binding) return null;
  const v = value.view;
  if (
    !record(v) ||
    !exact(v, [
      "schema",
      "source_ref",
      "scope",
      "observed_at",
      "epoch",
      "terminal",
      "coverage",
      "history",
      "acceptance",
      "capabilities",
      "items",
      "gaps",
    ]) ||
    v.schema !== "mastermind.workspace.visible_window_candidate.v1" ||
    v.source_ref !== value.selection_ref ||
    v.scope !== "one-managed-turn-window" ||
    v.history !== "NOT_PROVEN" ||
    v.acceptance !== "NOT_PROJECTED" ||
    !text(v.observed_at, 50) ||
    !/(Z|[+-]\d\d:\d\d)$/.test(v.observed_at) ||
    !Number.isFinite(Date.parse(v.observed_at)) ||
    !hash(v.epoch) ||
    typeof v.terminal !== "boolean" ||
    !["OBSERVED_WINDOW", "READ_LIMIT_REACHED", "GAP_PRESENT"].includes(
      String(v.coverage),
    ) ||
    !record(v.capabilities) ||
    !exact(v.capabilities, ["send", "provider_control", "history"]) ||
    !Object.values(v.capabilities).every((bit) => bit === false) ||
    !Array.isArray(v.items) ||
    v.items.length > 256 ||
    !Array.isArray(v.gaps) ||
    v.gaps.length > 256
  )
    return null;
  const ids = new Set<string>();
  let total = 0;
  for (const item of v.items) {
    if (
      !record(item) ||
      !exact(item, [
        "id",
        "source_sequence",
        "publication_sequence",
        "state",
        "kind",
        "text",
        "representation",
        "display_sha256",
      ]) ||
      typeof item.id !== "string" ||
      !/^visible:[0-9a-f]{64}$/.test(item.id) ||
      ids.has(item.id) ||
      !integer(item.source_sequence) ||
      !integer(item.publication_sequence, 1) ||
      !["partial", "completed"].includes(String(item.state))
    )
      return null;
    ids.add(item.id);
    if (item.kind === "withheld") {
      if (
        item.text !== null ||
        item.display_sha256 !== null ||
        item.representation !== "WITHHELD"
      )
        return null;
    } else if (item.kind === "visible-response") {
      if (
        typeof item.text !== "string" ||
        !["VISIBLE_TEXT", "FILTERED_VISIBLE_TEXT"].includes(
          String(item.representation),
        ) ||
        !hash(item.display_sha256)
      )
        return null;
      // Reject lone surrogates rather than hashing replacement characters.
      if (
        Array.from(item.text).some((c) => {
          const n = c.codePointAt(0)!;
          return n >= 0xd800 && n <= 0xdfff;
        })
      )
        return null;
      const bytes = new TextEncoder().encode(item.text).length;
      total += bytes;
      if (
        bytes > 16384 ||
        total > 1048576 ||
        (await digest(item.text)) !== item.display_sha256
      )
        return null;
    } else return null;
  }
  if (
    v.gaps.some(
      (g) =>
        !record(g) ||
        !exact(g, ["first", "last", "reason"]) ||
        g.reason !== "SOURCE_REPORTED_GAP" ||
        !integer(g.first) ||
        !integer(g.last) ||
        g.first > g.last,
    ) ||
    (v.gaps.length > 0 && v.coverage !== "GAP_PRESENT")
  )
    return null;
  return structuredClone(value) as unknown as WindowDocument;
}
type AssociationMission = {
  schema: string;
  generated_at: string | null;
  program: { work_ref: string };
  mission: {
    root_job_id: string | null;
    runtime_root_state: string;
    root_job_ambiguous: boolean;
  };
  read_state: { state: string };
  source: {
    owner_observation?: {
      state: string;
      runtime?: { state: string } | null;
    };
  };
  children: {
    state: string;
    coverage: string;
    items: Array<{
      job_id: string;
      status: string | null;
      parent_job_id: string;
      depth: number | null;
      orchestration_role: string | null;
      current_attempt_id: string | null;
      latest_attempt: {
        attempt_id: string | null;
        status: string | null;
      } | null;
    }>;
  };
};
type AssociationSelection = { workRef: string; rootJobId: string };
export function observedMissionAssociation(
  window: WindowDocument | null | undefined,
  mission: AssociationMission | null | undefined,
  selection: AssociationSelection | null | undefined,
): ObservedMissionAssociation | null {
  if (
    !window ||
    window.schema !== "mastermind.workspace.window_read_candidate.v2" ||
    window.view.terminal !== false ||
    window.view.coverage !== "OBSERVED_WINDOW" ||
    !mission ||
    !selection ||
    mission.schema !== "mastermind.mission_workspace.v3"
  )
    return null;
  const binding = window.observation_binding;
  const observation = mission.source.owner_observation;
  const runtime = observation?.runtime;
  if (
    mission.program.work_ref !== selection.workRef ||
    mission.mission.root_job_id !== selection.rootJobId ||
    mission.read_state.state !== "CURRENT" ||
    mission.mission.runtime_root_state !== "RESOLVED" ||
    mission.mission.root_job_ambiguous !== false ||
    observation?.state !== "SAME" ||
    runtime?.state !== "SAME" ||
    mission.children.state !== "AVAILABLE" ||
    mission.children.coverage !== "COMPLETE"
  )
    return null;
  const matches = mission.children.items.filter(
    (row) => row.job_id === binding.job_id,
  );
  if (matches.length !== 1) return null;
  const child = matches[0];
  const live = child.status === "RUNNING" || child.status === "CHECKPOINTED";
  const latest = child.latest_attempt;
  const attemptLive =
    latest?.status === "RUNNING" || latest?.status === "CHECKPOINTED";
  if (
    child.orchestration_role !== "plan" ||
    child.parent_job_id !== selection.rootJobId ||
    child.depth !== 1 ||
    child.current_attempt_id !== binding.attempt_id ||
    !live ||
    !latest ||
    latest.attempt_id !== binding.attempt_id ||
    !attemptLive
  )
    return null;
  return {
    state: "OBSERVED_MISSION_ASSOCIATION",
    job_id: binding.job_id,
    attempt_id: binding.attempt_id,
    window_observed_at: window.view.observed_at,
    mission_generated_at: mission.generated_at,
  };
}
