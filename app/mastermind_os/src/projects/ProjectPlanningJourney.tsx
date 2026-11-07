/**
 * ProjectPlanningJourney — the one explicit new-project journey in the existing
 * {@link NewProjectDraft} shell: goal → source options → profile choice →
 * verified preview → explicit publish → observed source record → explicit
 * initial planning → read result → explicit keep → separately publish its
 * qualified planning proposal → current Plan/Compare.
 *
 * OWNERSHIP. The parent owns the backend, the mount point, App selection and
 * URL navigation. This module owns only the composition of existing pieces:
 * the shell, the incumbent {@link OperationController} plus the supplied
 * {@link PendingPointerStore}, the real {@link ProjectPlanningCommandPort},
 * the incumbent {@link DirectNativeCommandPort} consume wrapper and the fixed
 * source-operation transport reached through `host.sourceOperations`.
 *
 * AUTHORITY. Options, previews and statuses are DATA, never write grants. The
 * only effects this module can start are the explicit user gestures (publish
 * the verified preview, dispatch the composed initial planning, keep a read
 * result) plus the explicit observational reconcile behind "Check
 * publication". Reads never reconcile, never publish and never consume.
 * The separately composed proposal workflow uses the fixed SAME-S19 preparation
 * action and distinct Workspace source-write owner; it never consumes/adopts
 * automatically. Nothing runs on mount: every effect is behind a clicked button, and
 * `onSelection` is called synchronously BEFORE any async prepare or planning
 * dispatch, never from a private prompt.
 *
 * IDENTITY. `createRequestId` is minted once per explicit preview gesture with
 * `crypto.getRandomValues` in the exact `publish_project_proposal` id grammar.
 * An existing selection is never replaced by an error, an unknown outcome or a
 * late receipt: only verified decoded facts move it, and the planning key is
 * recorded before dispatch while the job is recorded after acceptance.
 *
 * PRIVACY. The pending pointers persist only safe identifiers. The CREATE
 * pointer target is `{request_id, work_ref}`; the witness, the private goal
 * and the planning request text stay in the intent payload, which the
 * incumbent controller never persists.
 *
 * HONESTY. Source publication, planning admission and terminal result are
 * separate observed facts. The existing shell footer carries the actual
 * preview/publish action and an explicit phase note, never a conversation claim.
 */

import {ProjectPlanProposalWorkflow} from "../planning/ProjectPlanProposalWorkflow";
import type {PlanProposalOriginal} from "../planning/project-plan-proposal";
import { decodeSourceOperationContext } from "../source-operations/context";
import { useEffect, useLayoutEffect, useId, useRef, useState, type ReactNode } from "react";
import { NewProjectDraft } from "./NewProjectDraft";
import {useProjectDraftFiles,type ProjectDraftFile,type ProjectDraftFileLookup} from "./useProjectDraftFiles";
import type { MissionHost } from "../host";
import {
  makePlanningIntent,
  planningOperationKey,
  planningTargetKey,
  ProjectPlanningCommandPort,
  type PlanningSubmitInput,
} from "../planning/project-planning-command-port";
import {
  planningArguments,
  type PlanningOperation,
  type ProjectPlanningTransport,
} from "../planning/project-planning-transport";
import {
  decodeSourceOperationStatus,
  ORIGINAL_OPERATION_ID_PREFIXES,
  type SourceOperationAction,
  type SourceOperationStatus,
} from "../planning/plan-adoption-status";
import { DirectNativeCommandPort } from "../orchestration/direct-native-command-port";
import {
  decodeDirectNativeResult,
  parseDirectNativeJson,
  type DirectNativeTransport,
  type DirectResult,
  type DirectTerminalSelection,
} from "../direct-native-result";
import {
  OperationController,
  type CommandIntent,
  type EffectReceipt,
  type FiniteCommandPort,
  type OperationPointer,
  type OperationState,
  type OwnerContext,
  type PendingPointerStore,
} from "../orchestration/operation-controller";
import { canonicalJson, sha256Hex } from "../orchestration/operation-key";
import {
  SOURCE_OPERATION_CAP,
  type BasicSourceLookup,
  type SourceOperationTransport,
} from "../source-operations/transport";

// ── Public safe selection routed through the existing App selection owner ────

/** Exact safe identifiers only; route data, never authority. */
export interface ProjectJourneySelection {
  /** Original CREATE request id; the only identity this module mints. */
  readonly createRequestId: string;
  /** Workspace reference named by an observed source status; null before. */
  readonly workRef: string | null;
  /** Operation key of the dispatched initial planning, recorded before submit. */
  readonly planningOperationKey: string | null;
  /** Root job of an accepted initial planning receipt. */
  readonly jobId: string | null;
}

export interface ProjectPlanningJourneyProps {
  /** App supplies exact live global Host/auth identity, including no-render replacement. */
  readonly isHostCurrent?: () => boolean;
  locale?: "en" | "zh-CN";
  host: MissionHost | null;
  /** Genuine current owner identity from the existing command binding. */
  executiveOwner: () => OwnerContext | null;
  /** The existing durable pending-pointer store; shared by the existing effects. */
  store: PendingPointerStore;
  onSelection: (value: ProjectJourneySelection) => void;
  /** Accepted creation supplies only a navigation hint. App must re-read its
   * current catalogue; this exact source witness must remain current. */
  onOpenProject?: (workRef: string, current: () => boolean) => Promise<boolean>;
  selection: ProjectJourneySelection | null;
  goal: string;
  onGoalChange: (value: string) => void;
  goalReadOnly?: boolean;
  onGoalFocus?: () => void;
  /** App-owned ephemeral actual File draft; no body enters URL/storage. */
  draftFiles?:readonly ProjectDraftFile[];
  onDraftFilesChange?:(files:readonly ProjectDraftFile[])=>void;
  originalFileLookup?:ProjectDraftFileLookup|null;
  onOriginalFileLookupChange?:(value:ProjectDraftFileLookup|null)=>void;
  proposalOriginal?: PlanProposalOriginal|null;
  currentProposalOriginal?: ()=>PlanProposalOriginal|null;
  onProposalOriginalChange?: (original:PlanProposalOriginal)=>void;
  /** Parent-qualified proposal controls; rendered only for a readable project. */
  proposalControls?: ReactNode;
  /** Parent-qualified compare panel; rendered only for a readable project. */
  comparePanel?: ReactNode;
}

// ── Closed grammars ──────────────────────────────────────────────────────────

const OPTIONS_SCHEMA = "mastermind.project_creation_options.v1";
const REQUEST_SCHEMA = "mastermind.project_profile_selection.v1";
const PREVIEW_SCHEMA = "mastermind.workspace_source_operation_preview.v1";
const PREVIEW_DOCUMENT_SCHEMA = "mastermind.project_creation_preview.v1";
const WITNESS_REFERENCE_SCHEMA = "mastermind.terminal_original_input_reference.v1";
const PLANNING_RESULT_SCHEMA = "mastermind.project_initial_planning.private_result.v1";
const DIRECT_RECEIPT_SCHEMA = "mastermind.ceo_direct_native_receipt.v1";
const LOOKUP_SCHEMA = "mastermind.workspace_source_operation_lookup.v1";
const CREATE_ACTION = "publish_project_proposal" as const;
const CREATE_KIND = "project_create" as const;
const CREATE_REQUEST_PREFIX = ORIGINAL_OPERATION_ID_PREFIXES.publish_project_proposal;
/** The planning submit contract fixes the canonical project source path. */
const SOURCE_PATH_PREFIX = "agentos/workstreams/WS-";

const HEX64 = /^[0-9a-f]{64}$/;
const HEX40 = /^[0-9a-f]{40}$/;
const IDENTIFIER = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;
const WORK_REF = /^WS:[A-Z0-9]+(?:-[A-Z0-9]+)*$/;

function isCreateRequestId(value: unknown): value is string {
  return (
    typeof value === "string" &&
    value.startsWith(CREATE_REQUEST_PREFIX) &&
    HEX40.test(value.slice(CREATE_REQUEST_PREFIX.length))
  );
}

function isRecord(value: unknown): value is Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return false;
  const proto = Object.getPrototypeOf(value);
  return proto === Object.prototype || proto === null;
}

/**
 * Exact closed key set read from own data descriptors only. Getters, setters,
 * symbols and wrong arity are rejected, so no hostile accessor ever runs and
 * no extra field survives.
 */
function fields(value: unknown, keys: readonly string[]): Record<string, unknown> | null {
  if (!isRecord(value)) return null;
  if (Object.getOwnPropertySymbols(value).length !== 0) return null;
  const own = Object.getOwnPropertyDescriptors(value);
  if (Object.keys(own).length !== keys.length) return null;
  const out: Record<string, unknown> = {};
  for (const key of keys) {
    const descriptor = own[key];
    if (!descriptor || !("value" in descriptor)) return null;
    if (descriptor.get !== undefined || descriptor.set !== undefined) return null;
    out[key] = descriptor.value;
  }
  return out;
}

function hex(value: unknown, pattern: RegExp): value is string {
  return typeof value === "string" && pattern.test(value);
}

/** Bounded well-formed text; control characters are rejected except tab/newline. */
function bounded(value: unknown, maxCodePoints: number, allowEmpty = false): string | null {
  if (typeof value !== "string") return null;
  if (!allowEmpty && value.length === 0) return null;
  const points = [...value];
  if (points.length > maxCodePoints) return null;
  for (const point of points) {
    const code = point.codePointAt(0) as number;
    if (code === 127 || (code >= 0xd800 && code <= 0xdfff)) return null;
    if (code < 32 && code !== 9 && code !== 10) return null;
  }
  return value;
}

function identifiers(value: unknown, max: number): readonly string[] | null {
  if (!Array.isArray(value) || value.length > max) return null;
  const out: string[] = [];
  for (const item of value) {
    const text = bounded(item, 128);
    if (text === null) return null;
    out.push(text);
  }
  return out;
}

/** Bounded closed JSON: strings, safe integers, null, small arrays and records. */


function withinBudget(value: unknown, bytes: number): boolean {
  try {
    return new TextEncoder().encode(canonicalJson(value)).length <= bytes;
  } catch {
    return false;
  }
}

/** Deeply detached plain-JSON copy of an already validated closed value. */
function detached<T>(value: T): T {
  return JSON.parse(canonicalJson(value)) as T;
}

// ── Creation options (DATA) ──────────────────────────────────────────────────

export interface JourneyProfileChoice {
  readonly id: string;
  readonly revision: string;
  readonly labelEn: string;
  readonly labelZh: string;
  readonly summaryEn: string;
  readonly summaryZh: string;
  readonly owner: string;
  readonly program: string;
  readonly repos: readonly string[];
  readonly classification: string;
  readonly blastRadius: string;
  readonly ambiguity: string;
  /** Detached exact supplied profile record; hashed for the request CAS. */
  readonly source: Record<string, unknown>;
}

export interface JourneyOptions {
  readonly expectedMacroSha: string;
  readonly ownerScope: string;
  readonly profiles: readonly JourneyProfileChoice[];
  /** Optional closed planning grounding DATA; its absence blocks planning. */
  readonly grounding: Readonly<{ mastermindSha: string; macroSha: string }> | null;
}

function decodeProfileChoice(value: unknown): JourneyProfileChoice | null {
  const record = fields(value, [
    "ambiguity",
    "blastRadius",
    "classification",
    "id",
    "label",
    "owner",
    "program",
    "repos",
    "revision",
    "summary",
  ]);
  if (!record) return null;
  const id = bounded(record.id, 128);
  if (id === null || !IDENTIFIER.test(id)) return null;
  if (!hex(record.revision, HEX64)) return null;
  const label = fields(record.label, ["en", "zhCN"]);
  const summary = fields(record.summary, ["en", "zhCN"]);
  if (!label || !summary) return null;
  const labelEn = bounded(label.en, 200);
  const labelZh = bounded(label.zhCN, 200);
  const summaryEn = bounded(summary.en, 1000);
  const summaryZh = bounded(summary.zhCN, 1000);
  if (labelEn === null || labelZh === null || summaryEn === null || summaryZh === null) return null;
  const owner = bounded(record.owner, 200);
  const program = bounded(record.program, 200);
  const classification = bounded(record.classification, 64);
  const blastRadius = bounded(record.blastRadius, 64);
  const ambiguity = bounded(record.ambiguity, 64);
  const repos = identifiers(record.repos, 16);
  if (
    owner === null || program === null || classification === null ||
    blastRadius === null || ambiguity === null || repos === null
  ) {
    return null;
  }
  return {
    id,
    revision: record.revision,
    labelEn,
    labelZh,
    summaryEn,
    summaryZh,
    owner,
    program,
    repos,
    classification,
    blastRadius,
    ambiguity,
    source: detached(record),
  };
}

function decodeCreationOptions(value: unknown): JourneyOptions | null {
  const withGrounding = fields(value, [
    "expected_macro_sha",
    "grounding",
    "owner_context",
    "profiles",
    "schema",
  ]);
  const record = withGrounding;
  if (!record || record.schema !== OPTIONS_SCHEMA) return null;
  if (!hex(record.expected_macro_sha, HEX40)) return null;
  const ownerContext = fields(record.owner_context, ["principal_scope"]);
  if (!ownerContext || !hex(ownerContext.principal_scope, HEX64)) return null;
  if (!Array.isArray(record.profiles) || record.profiles.length === 0 || record.profiles.length > 8) {
    return null;
  }
  const profiles: JourneyProfileChoice[] = [];
  for (const profile of record.profiles) {
    const decoded = decodeProfileChoice(profile);
    if (!decoded || profiles.some(item => item.id === decoded.id)) return null;
    profiles.push(decoded);
  }
  let grounding: JourneyOptions["grounding"] = null;
  if (withGrounding) {
    const supplied = fields(record.grounding, ["macro_sha", "mastermind_sha"]);
    if (!supplied || !hex(supplied.mastermind_sha, HEX40) || !hex(supplied.macro_sha, HEX40) || supplied.macro_sha !== record.expected_macro_sha) return null;
    grounding = {
      mastermindSha: supplied.mastermind_sha,
      macroSha: supplied.macro_sha,
    };
  }
  if (!withinBudget(value, SOURCE_OPERATION_CAP)) return null;
  return {
    expectedMacroSha: record.expected_macro_sha,
    ownerScope: ownerContext.principal_scope,
    profiles,
    grounding,
  };
}

/** Presentation classification only, never a plan/publication/adoption proof.
 * Ordinary prose and malformed/foreign declarations stay readable as returned.
 * Exact raw declaration remains available in the existing closed Source details.
 */
function isExplicitPlanDeclaration(text: string, workRef: string): boolean {
  if (text.length > 4096) return false;
  try {
    const value=fields(parseDirectNativeJson(text),["schema","work_ref","base_source","base_adoption","plan","rationale","evidence"]);
    if(!value || value.schema!=="mastermind.project_plan_candidate.v1" || value.work_ref!==workRef) return false;
    const source=fields(value.base_source,["repository","commit","path","content_sha256"]);
    const plan=fields(value.plan,["objective","waves","next_action","body"]);
    return Boolean(source && source.repository==="mastermindx-market-intelligence/macro" && hex(source.commit,HEX40) &&
      bounded(source.path,512)!==null && hex(source.content_sha256,HEX64) &&
      (value.base_adoption===null || typeof value.base_adoption==="string" && /^DEC:[A-Z0-9]+(?:-[A-Z0-9]+)*$/.test(value.base_adoption)) &&
      bounded(value.rationale,4096)!==null && Array.isArray(value.evidence) && value.evidence.length<=32 && plan &&
      bounded(plan.objective,4096)!==null && bounded(plan.next_action,4096)!==null && bounded(plan.body,4096)!==null &&
      Array.isArray(plan.waves) && plan.waves.length<=32 && plan.waves.every(wave=>{
        const row=fields(wave,["id","title","status"]);
        return row!==null && bounded(row.id,128)!==null && bounded(row.title,1024)!==null && bounded(row.status,64)!==null;
      }));
  } catch {return false;}
}

// ── Source identity context (scope binding) ──────────────────────────────────

/**
 * The actor scope comes only from the source context response. The exact DTO
 * belongs to its own decoder, so this reads only the closed owner-context
 * shapes this journey can act on and refuses anything else.
 */
function contextScope(value: unknown): string | null {
  try {
    return decodeSourceOperationContext(value, {action: CREATE_ACTION, workRef: null}).owner_context.principal_scope;
  } catch { return null; }
}

// ── Creation preview (DATA, verified before any offer) ───────────────────────

interface PreviewExpectation {
  readonly requestId: string;
  readonly scope: string;
  /** Exact public request object that was sent; its canonical hash is checked. */
  readonly request: Readonly<Record<string, unknown>>;
  readonly goal: string;
  readonly profileId: string;
  readonly profileRevision: string;
  readonly expectedMacroSha: string;
}

export interface JourneyPreview {
  readonly requestId: string;
  readonly scope: string;
  readonly goal: string;
  readonly workRef: string;
  readonly sourceCommit: string;
  readonly canonicalPath: string;
  readonly contentSha256: string;
  readonly profileId: string;
  readonly profileRevision: string;
  readonly requestSha256: string;
  readonly recipeFingerprintSha256: string;
  /** Detached exact witness, replayed verbatim by the explicit publish. */
  readonly witness: Record<string, unknown>;
}

function decodeCreationPreview(value: unknown, expected: PreviewExpectation): JourneyPreview | null {
  const envelope = fields(value, [
    "owner_context",
    "preview",
    "preview_witness",
    "recipe_fingerprint_sha256",
    "request_sha256",
    "schema",
    "selection",
  ]);
  if (!envelope || envelope.schema !== PREVIEW_SCHEMA) return null;
  if (!withinBudget(value, SOURCE_OPERATION_CAP)) return null;
  const selection = fields(envelope.selection, ["action", "request_id", "work_ref"]);
  if (!selection) return null;
  if (selection.action !== CREATE_ACTION || selection.request_id !== expected.requestId) return null;
  if (selection.work_ref !== null && !(typeof selection.work_ref === "string" && WORK_REF.test(selection.work_ref))) {
    return null;
  }
  const ownerContext = fields(envelope.owner_context, ["principal_scope"]);
  if (!ownerContext || ownerContext.principal_scope !== expected.scope) return null;
  // The real backend hash of the exact public request bytes.
  const requestSha = sha256Hex(canonicalJson(expected.request));
  if (envelope.request_sha256 !== requestSha) return null;
  if (!hex(envelope.recipe_fingerprint_sha256, HEX64)) return null;

  const witness = fields(envelope.preview_witness, ["original_input", "recipe_fingerprint_sha256"]);
  if (!witness || witness.recipe_fingerprint_sha256 !== envelope.recipe_fingerprint_sha256) return null;
  const reference = fields(witness.original_input, [
    "artifact_sha256",
    "input_ref",
    "payload_sha256",
    "schema",
  ]);
  if (
    !reference || reference.schema !== WITNESS_REFERENCE_SCHEMA ||
    typeof reference.input_ref !== "string" ||
    !reference.input_ref.startsWith("terminal-input:") ||
    !HEX64.test(reference.input_ref.slice("terminal-input:".length)) ||
    !hex(reference.artifact_sha256, HEX64) ||
    !hex(reference.payload_sha256, HEX64)
  ) {
    return null;
  }

  const document = fields(envelope.preview, [
    "canonical_path",
    "content_sha256",
    "goal",
    "profile",
    "schema",
    "source_commit",
    "state",
    "work_ref",
  ]);
  if (!document || document.schema !== PREVIEW_DOCUMENT_SCHEMA || document.state !== "DRAFT_ONLY") {
    return null;
  }
  const workRef = document.work_ref;
  if (typeof workRef !== "string" || !WORK_REF.test(workRef)) return null;
  // The envelope selection is either the same reference or the pre-derivation null.
  if (selection.work_ref !== null && selection.work_ref !== workRef) return null;
  // Compare-and-set: the preview must be computed against the loaded macro.
  if (document.source_commit !== expected.expectedMacroSha) return null;
  const canonicalPath = bounded(document.canonical_path, 512);
  if (canonicalPath === null || canonicalPath.startsWith("/")) return null;
  if (!hex(document.content_sha256, HEX64)) return null;
  if (document.goal !== expected.goal) return null;
  const profile = fields(document.profile, [
    "ambiguity",
    "blast_radius",
    "classification",
    "id",
    "next_action",
    "owner",
    "program",
    "repos",
    "revision",
    "title",
    "waves",
  ]);
  if (!profile || profile.id !== expected.profileId || profile.revision !== expected.profileRevision) {
    return null;
  }
  const title = bounded(profile.title, 200);
  const owner = bounded(profile.owner, 200);
  const program = bounded(profile.program, 200);
  const classification = bounded(profile.classification, 64);
  const blastRadius = bounded(profile.blast_radius, 64);
  const ambiguity = bounded(profile.ambiguity, 64);
  const nextAction = bounded(profile.next_action, 500);
  const repos = identifiers(profile.repos, 16);
  if (
    title === null || owner === null || program === null || classification === null ||
    blastRadius === null || ambiguity === null || nextAction === null || repos === null
  ) {
    return null;
  }
  if (
    !Array.isArray(profile.waves) ||
    profile.waves.length > 16 ||
    !profile.waves.every((wave) => {
      const row=fields(wave,["id","title","status"]);
      return row !== null && bounded(row.id,128) !== null && bounded(row.title,200) !== null && bounded(row.status,64) !== null;
    })
  ) {
    return null;
  }
  return {
    requestId: expected.requestId,
    scope: expected.scope,
    goal: expected.goal,
    workRef,
    sourceCommit: document.source_commit,
    canonicalPath,
    contentSha256: document.content_sha256,
    profileId: profile.id,
    profileRevision: profile.revision,
    requestSha256: envelope.request_sha256,
    recipeFingerprintSha256: envelope.recipe_fingerprint_sha256,
    witness: detached(witness),
  };
}

// ── Observed status → receipt, publication and project source ────────────────

interface CreateExpectation {
  readonly requestId: string;
  readonly workRef: string | null;
  readonly scope: string;
}

function unknownReceipt(pointer: OperationPointer, reason: string): EffectReceipt {
  return { ...pointer, disposition: "unknown", reason };
}

function createReceipt(
  pointer: OperationPointer,
  status: SourceOperationStatus,
  expected: CreateExpectation,
): EffectReceipt {
  if (status.selection.action !== CREATE_ACTION) return unknownReceipt(pointer, "RECEIPT_MISMATCH");
  if (status.selection.request_id !== expected.requestId) return unknownReceipt(pointer, "RECEIPT_MISMATCH");
  if (status.owner_context.principal_scope !== expected.scope) return unknownReceipt(pointer, "RECEIPT_MISMATCH");
  if (expected.workRef !== null && status.selection.work_ref !== expected.workRef) {
    return unknownReceipt(pointer, "RECEIPT_MISMATCH");
  }
  if (!WORK_REF.test(status.selection.work_ref)) return unknownReceipt(pointer, "MALFORMED_RECEIPT");
  if (status.disposition === "accepted") {
    const receipt = status.receipt;
    if (!receipt || receipt.kind !== "SOURCE_OBSERVED" || receipt.sources.length !== 1) {
      return unknownReceipt(pointer, "MALFORMED_RECEIPT");
    }
    if (receipt.sources[0].path !== `${SOURCE_PATH_PREFIX}${status.selection.work_ref.slice(3)}.md`) return unknownReceipt(pointer, "MALFORMED_RECEIPT");
    return { ...pointer, disposition: "accepted" };
  }
  if (status.disposition === "refused") {
    return { ...pointer, disposition: "refused", reason: "REFUSED" };
  }
  return unknownReceipt(pointer, "UNKNOWN_RECEIPT");
}

/** Qualified publication reference of an accepted source observation. */
interface JourneyPublication {
  readonly requestId: string;
  readonly principalScope: string;
  readonly eventId: number;
  readonly receiptSha256: string;
}

function publicationOf(status: SourceOperationStatus): JourneyPublication | null {
  if (status.disposition !== "accepted") return null;
  const receipt = status.receipt;
  if (!receipt || receipt.kind !== "SOURCE_OBSERVED" || receipt.sources.length !== 1) return null;
  if (typeof status.recipe_fingerprint_sha256 !== "string" || !HEX64.test(status.recipe_fingerprint_sha256)) {
    return null;
  }
  return {
    requestId: status.selection.request_id,
    principalScope: status.owner_context.principal_scope,
    eventId: receipt.event_id,
    receiptSha256: receipt.receipt_sha256,
  };
}

/** The exact planning project source: observed macro plus the real request digest. */
function projectSourceOf(status: SourceOperationStatus): Record<string, unknown> | null {
  if (status.disposition !== "accepted") return null;
  const receipt = status.receipt;
  if (!receipt || receipt.kind !== "SOURCE_OBSERVED" || receipt.sources.length !== 1) return null;
  const source = receipt.sources[0];
  if (typeof status.recipe_fingerprint_sha256 !== "string") return null;
  return {
    repository: source.repository,
    commit: source.commit,
    path: source.path,
    content_sha256: source.content_sha256,
    request_sha256: status.recipe_fingerprint_sha256,
  };
}

// ── CREATE pointers (opaque safe target only) ────────────────────────────────

function createTargetKey(requestId: string, workRef: string | null): string {
  return canonicalJson({ request_id: requestId, work_ref: workRef });
}

function parseCreateTarget(targetKey: string | null): { request_id: string; work_ref: string | null } | null {
  if (typeof targetKey !== "string") return null;
  let parsed: unknown;
  try {
    parsed = JSON.parse(targetKey);
  } catch {
    return null;
  }
  const record = fields(parsed, ["request_id", "work_ref"]);
  if (!record || !isCreateRequestId(record.request_id)) return null;
  if (record.work_ref !== null && !(typeof record.work_ref === "string" && WORK_REF.test(record.work_ref))) {
    return null;
  }
  if (canonicalJson(parsed) !== targetKey) return null;
  return { request_id: record.request_id, work_ref: record.work_ref as string | null };
}

/**
 * The exact original keep target: the same closed selection and digest the
 * incumbent consume helper wrote, read back without guessing any field.
 */
function parseConsumeTarget(targetKey: string | null): {
  work_ref: string;
  job_id: string;
  attempt_id: string;
  result_digest: string;
} | null {
  if (typeof targetKey !== "string") return null;
  let parsed: unknown;
  try {
    parsed = JSON.parse(targetKey);
  } catch {
    return null;
  }
  const record = fields(parsed, ["attempt_id", "job_id", "result_digest", "work_ref"]);
  if (!record) return null;
  if (
    typeof record.work_ref !== "string" ||
    typeof record.job_id !== "string" ||
    typeof record.attempt_id !== "string" ||
    !hex(record.result_digest, HEX64) ||
    canonicalJson(parsed) !== targetKey
  ) {
    return null;
  }
  return {
    work_ref: record.work_ref,
    job_id: record.job_id,
    attempt_id: record.attempt_id,
    result_digest: record.result_digest,
  };
}

function createPointerKey(scope: string, requestId: string, workRef: string | null): string {
  return `mmos-journey-create-${sha256Hex(
    canonicalJson({ v: 1, principalScope: scope, request_id: requestId, work_ref: workRef }),
  ).slice(0, 40)}`;
}

function mintCreateRequestId(): string {
  const bytes = new Uint8Array(20);
  globalThis.crypto.getRandomValues(bytes);
  let text = "";
  for (const byte of bytes) text += byte.toString(16).padStart(2, "0");
  return CREATE_REQUEST_PREFIX + text;
}

// ── Internal finite CREATE port over the fixed source transport ──────────────

/**
 * The module-local `project_create` port. It holds no store and no lifecycle:
 * the incumbent controller reserves the supplied pointer store BEFORE this
 * port submits. Statuses come only from the fixed transport's submit, read and
 * explicit reconcile, each fenced by the owner epoch captured at dispatch.
 */
class CreateProjectSourcePort implements FiniteCommandPort {
  constructor(
    private readonly _owner: () => OwnerContext | null,
    private readonly _source: () => SourceOperationTransport | null,
    private readonly _record: { createStatus: SourceOperationStatus | null },
  ) {}

  context(): OwnerContext | null {
    return this._owner();
  }

  prepare(intent: CommandIntent): OperationPointer {
    if (intent.kind !== CREATE_KIND) throw new Error("INVALID_KIND");
    const payload = fields(intent.payload, ["action", "preview_witness", "request_id", "work_ref"]);
    if (!payload || payload.action !== CREATE_ACTION) throw new Error("INVALID_PAYLOAD");
    if (!isCreateRequestId(payload.request_id)) throw new Error("INVALID_PAYLOAD");
    if (typeof payload.work_ref !== "string" || !WORK_REF.test(payload.work_ref)) {
      throw new Error("INVALID_PAYLOAD");
    }
    const witness = fields(payload.preview_witness, ["original_input", "recipe_fingerprint_sha256"]);
    const reference = witness
      ? fields(witness.original_input, ["artifact_sha256", "input_ref", "payload_sha256", "schema"])
      : null;
    if (
      !witness || !reference ||
      !hex(witness.recipe_fingerprint_sha256, HEX64) ||
      reference.schema !== WITNESS_REFERENCE_SCHEMA ||
      typeof reference.input_ref !== "string" ||
      !reference.input_ref.startsWith("terminal-input:") ||
      !HEX64.test(reference.input_ref.slice("terminal-input:".length)) ||
      !hex(reference.artifact_sha256, HEX64) ||
      !hex(reference.payload_sha256, HEX64)
    ) {
      throw new Error("INVALID_PAYLOAD");
    }
    const owner = this._owner();
    if (!owner) throw new Error("OWNER_ABSENT");
    const requestId = payload.request_id;
    const targetKey = createTargetKey(requestId, payload.work_ref);
    if (intent.targetKey !== targetKey) throw new Error("INVALID_TARGET");
    return {
      operationKey: createPointerKey(owner.principalScope, requestId, payload.work_ref),
      kind: CREATE_KIND,
      targetKey,
    };
  }

  async submit(pointer: OperationPointer, intent: CommandIntent, signal: AbortSignal): Promise<EffectReceipt> {
    const before = this._owner();
    if (!before) return unknownReceipt(pointer, "OWNER_ABSENT");
    let expected: OperationPointer;
    try {
      expected = this.prepare(intent);
    } catch {
      return unknownReceipt(pointer, "MALFORMED_POINTER");
    }
    if (
      expected.operationKey !== pointer.operationKey ||
      expected.kind !== pointer.kind ||
      expected.targetKey !== pointer.targetKey
    ) {
      return unknownReceipt(pointer, "RECEIPT_MISMATCH");
    }
    const source = this._source();
    if (!source) return unknownReceipt(pointer, "LOCAL_UNAVAILABLE");
    if (signal.aborted) return unknownReceipt(pointer, "TRANSPORT_ERROR");
    const payload = intent.payload as { request_id: string; work_ref: string; preview_witness: unknown };
    let raw: unknown;
    try {
      raw = await source.submitSourceOperation({
        action: CREATE_ACTION,
        request_id: payload.request_id,
        work_ref: payload.work_ref,
        preview_witness: payload.preview_witness,
      }, signal);
    } catch {
      return unknownReceipt(pointer, "TRANSPORT_ERROR");
    }
    if (signal.aborted) return unknownReceipt(pointer, "TRANSPORT_ERROR");
    const after = this._owner();
    if (!after || after.principalScope !== before.principalScope || after.generation !== before.generation) {
      // A lost or late receipt never erases the owner's submit; it stays
      // unknown under the original pointer for a later recover.
      return unknownReceipt(pointer, "EPOCH_CHANGED");
    }
    return this._status(pointer, raw, {
      requestId: payload.request_id,
      workRef: payload.work_ref,
      scope: before.principalScope,
    });
  }

  async readOperation(pointer: OperationPointer, signal: AbortSignal): Promise<EffectReceipt> {
    const owner = this._owner();
    const target = parseCreateTarget(pointer.targetKey);
    if (!owner || !target || pointer.kind !== CREATE_KIND) return unknownReceipt(pointer, "MALFORMED_POINTER");
    const source = this._source();
    if (!source) return unknownReceipt(pointer, "LOCAL_UNAVAILABLE");
    if (signal.aborted) return unknownReceipt(pointer, "TRANSPORT_ERROR");
    try {
      const raw = await source.readSourceOperation(this._lookup(target), signal);
      if (signal.aborted) return unknownReceipt(pointer, "TRANSPORT_ERROR");
      const current = this._owner();
      if (!current || current.principalScope !== owner.principalScope || current.generation !== owner.generation) {
        return unknownReceipt(pointer, "EPOCH_CHANGED");
      }
      return this._status(pointer, raw, {
        requestId: target.request_id,
        workRef: target.work_ref,
        scope: owner.principalScope,
      });
    } catch {
      return unknownReceipt(pointer, "RECOVER_FAILED");
    }
  }

  /**
   * Explicit observational reconcile of the SAME original operation. It never
   * runs implicitly and only with the exact non-null workspace reference.
   */
  async reconcileOperation(pointer: OperationPointer, signal: AbortSignal): Promise<EffectReceipt> {
    const owner = this._owner();
    const target = parseCreateTarget(pointer.targetKey);
    if (!owner || !target || pointer.kind !== CREATE_KIND || typeof target.work_ref !== "string") {
      return unknownReceipt(pointer, "MALFORMED_POINTER");
    }
    const source = this._source();
    if (!source) return unknownReceipt(pointer, "LOCAL_UNAVAILABLE");
    if (signal.aborted) return unknownReceipt(pointer, "TRANSPORT_ERROR");
    try {
      const raw = await source.reconcileSourceOperation(this._lookup(target), signal);
      if (signal.aborted) return unknownReceipt(pointer, "TRANSPORT_ERROR");
      const current = this._owner();
      if (!current || current.principalScope !== owner.principalScope || current.generation !== owner.generation) {
        return unknownReceipt(pointer, "EPOCH_CHANGED");
      }
      return this._status(pointer, raw, {
        requestId: target.request_id,
        workRef: target.work_ref,
        scope: owner.principalScope,
      });
    } catch {
      return unknownReceipt(pointer, "RECOVER_FAILED");
    }
  }

  /** CREATE-only null lookup lets the server derive the original workspace. */
  private _lookup(target: { request_id: string; work_ref: string | null }): BasicSourceLookup {
    return {
      schema: LOOKUP_SCHEMA,
      action: CREATE_ACTION,
      request_id: target.request_id,
      work_ref: target.work_ref,
    };
  }

  private _status(pointer: OperationPointer, raw: unknown, expected: CreateExpectation): EffectReceipt {
    let status: SourceOperationStatus;
    try {
      status = decodeSourceOperationStatus(raw);
    } catch {
      this._record.createStatus = null;
      return unknownReceipt(pointer, "MALFORMED_RECEIPT");
    }
    const receipt = createReceipt(pointer, status, expected);
    if (receipt.disposition === "unknown" && receipt.reason !== "UNKNOWN_RECEIPT") {
      this._record.createStatus = null;
    } else {
      this._record.createStatus = status;
    }
    return receipt;
  }
}

// ── Executive routing: CREATE remains in its separate Workspace scope ──────

/** Routes only the two Executive operation kinds through their existing ports. */
class JourneyCommandPort implements FiniteCommandPort {
  constructor(
    private readonly _owner: () => OwnerContext | null,
    private readonly _planning: ProjectPlanningCommandPort,
    private readonly _consume: DirectNativeCommandPort,
  ) {}

  context(): OwnerContext | null {
    return this._owner();
  }

  prepare(intent: CommandIntent): OperationPointer {
    if (intent.kind === "launch") return this._planning.prepare(intent);
    if (intent.kind === "consume") return this._consume.prepare(intent);
    throw new Error("INVALID_KIND");
  }

  submit(pointer: OperationPointer, intent: CommandIntent, signal: AbortSignal): Promise<EffectReceipt> {
    if (pointer.kind === "launch" && intent.kind === "launch") {
      return this._planning.submit(pointer, intent, signal);
    }
    if (pointer.kind === "consume" && intent.kind === "consume") {
      return this._consume.submit(pointer, intent, signal);
    }
    return Promise.resolve(unknownReceipt(pointer, "KIND_MISMATCH"));
  }

  readOperation(pointer: OperationPointer, signal: AbortSignal): Promise<EffectReceipt> {
    if (pointer.kind === "launch") return this._planning.readOperation(pointer, signal);
    if (pointer.kind === "consume") return this._consume.readOperation(pointer, signal);
    return Promise.resolve(unknownReceipt(pointer, "KIND_MISMATCH"));
  }

}

// ── Planning envelope (closed unwrap; no raw fallback) ───────────────────────

/**
 * Unwraps ONLY the matching closed planning envelope. A raw receipt, a foreign
 * schema, a mismatched operation or a non-true `ok` is never accepted as data.
 */
async function unwrapPlanningEnvelope(
  pending: Promise<unknown>,
  operation: PlanningOperation,
): Promise<unknown> {
  const value = await pending;
  const envelope = fields(value, ["data", "error", "ok", "operation", "schema"]);
  if (!envelope) throw new Error("PROJECT_PLANNING_ENVELOPE_INVALID");
  if (envelope.schema !== PLANNING_RESULT_SCHEMA) throw new Error("PROJECT_PLANNING_ENVELOPE_INVALID");
  if (envelope.operation !== operation) throw new Error("PROJECT_PLANNING_ENVELOPE_INVALID");
  if (envelope.ok !== true || envelope.error !== null) throw new Error("PROJECT_PLANNING_ENVELOPE_INVALID");
  return envelope.data;
}

/** The optional parent-bound planning transport, read structurally. */
function planningTransportOf(host: MissionHost | null): ProjectPlanningTransport | null {
  if (!host) return null;
  const candidate = (host as unknown as { readonly projectPlanning?: unknown }).projectPlanning;
  if (typeof candidate !== "object" || candidate === null) return null;
  const request = (candidate as { request?: unknown }).request;
  return typeof request === "function" ? (candidate as unknown as ProjectPlanningTransport) : null;
}

// ── Closed copy ──────────────────────────────────────────────────────────────

type Notice =
  | "AUTH"
  | "CONTEXT"
  | "OPTIONS"
  | "SCOPE_MISMATCH"
  | "PROFILE_REQUIRED"
  | "GOAL_REQUIRED"
  | "PREVIEW_UNAVAILABLE"
  | "PREVIEW_STALE"
  | "CREATE_BUSY"
  | "SOURCE_READ_UNAVAILABLE"
  | "OPEN_PROJECT_UNAVAILABLE"
  | "PUBLICATION_RECONCILE_UNAVAILABLE"
  | "PLANNING_UNAVAILABLE_HOST"
  | "PLANNING_UNAVAILABLE_GROUNDING"
  | "PLANNING_UNAVAILABLE_SOURCE"
  | "PLANNING_FILES_PENDING"
  | "PLANNING_ALREADY_DISPATCHED"
  | "PLANNING_REQUEST_REQUIRED"
  | "PLANNING_READ_UNAVAILABLE"
  | "RESULT_UNAVAILABLE"
  | "RESULT_NEEDS_JOB"
  | "OWNER_ABSENT";

/** Every string this module shows, as an exact [English, Chinese] pair. */
const NOTICE_COPY: Record<Notice, readonly [string, string]> = {
  PLANNING_FILES_PENDING: ["Add all selected files to the project, or remove unsent files, before initial planning.", "请先将所有所选文件添加到项目，或移除尚未发送的文件，然后再进行初始规划。"],
  AUTH: ["Sign in with acquisition to continue this journey.", "登录并获得访问权后才能继续。"],
  CONTEXT: ["The source identity context is unavailable, so no scope was bound.", "来源身份上下文不可用，因此未绑定范围。"],
  OPTIONS: ["The supplied project options are unavailable right now.", "暂时无法载入提供的项目选项。"],
  SCOPE_MISMATCH: ["The options belong to a different source scope, so nothing was bound.", "选项属于其他来源范围，因此未绑定。"],
  PROFILE_REQUIRED: ["Choose one profile first.", "请先选择一个配置。"],
  GOAL_REQUIRED: ["Write a goal first.", "请先填写目标。"],
  PREVIEW_UNAVAILABLE: ["The source preview could not be verified, so nothing was offered.", "无法核对来源预览，因此未提供任何操作。"],
  PREVIEW_STALE: ["This preview no longer matches the goal or the profile. Prepare it again.", "预览与目标或配置不再一致，请重新准备。"],
  CREATE_BUSY: ["A source publication is already being observed. Nothing was started twice.", "正在观察一次来源发布，没有重复启动。"],
  SOURCE_READ_UNAVAILABLE: ["The source status read is unavailable right now.", "暂时无法读取来源状态。"],
  OPEN_PROJECT_UNAVAILABLE: ["The created project is unavailable in the current project list. Try Open project again.", "当前项目列表中无法打开此项目。请再次选择“打开项目”。"],
  PUBLICATION_RECONCILE_UNAVAILABLE: [
    "An explicit publication check needs the workspace reference of the pending publication.",
    "显式发布检查需要待发布记录的工作区引用。",
  ],
  PLANNING_UNAVAILABLE_HOST: ["Initial planning is not available from this host.", "此主机不提供初始规划。"],
  PLANNING_UNAVAILABLE_GROUNDING: [
    "The loaded options do not carry planning grounding, so planning stays unavailable.",
    "载入的选项不包含规划依据，因此规划不可用。",
  ],
  PLANNING_UNAVAILABLE_SOURCE: [
    "The observed source record does not match the planning contract.",
    "观测到的来源记录与规划契约不一致。",
  ],
  PLANNING_ALREADY_DISPATCHED: [
    "The initial planning request was already dispatched. Check its status instead.",
    "初始规划请求已发出，请改为查询其状态。",
  ],
  PLANNING_REQUEST_REQUIRED: ["Write the initial request and choose clarify or plan.", "请填写初始请求并选择澄清或规划。"],
  PLANNING_READ_UNAVAILABLE: [
    "Planning status can only be re-read on the originally dispatched request.",
    "只能重新查询已发出的原始规划请求。",
  ],
  RESULT_UNAVAILABLE: ["The planning result is not readable yet.", "规划结果暂不可读。"],
  RESULT_NEEDS_JOB: ["Read the accepted planning status before the result.", "读取结果前请先查询已接受的规划状态。"],
  OWNER_ABSENT: ["The owner identity is unavailable.", "所有者身份不可用。"],
};

// ── Component ────────────────────────────────────────────────────────────────

type BusyAction =
  | "options"
  | "preview"
  | "publish"
  | "source-read"
  | "publication"
  | "plan"
  | "plan-read"
  | "result"
  | "keep"
  | "keep-read"
  | "open-project";

interface JourneyRecord {
  createStatus: SourceOperationStatus | null;
  planningKey: string | null;
  planningJob: { jobId: string; jobStatus: string } | null;
  keptDigest: string | null;
}

export function ProjectPlanningJourney(props: ProjectPlanningJourneyProps) {
  const { locale = "en", goal, onGoalChange, selection, proposalControls, comparePanel } = props;
  const zh = locale === "zh-CN";
  const copy = (pair: readonly [string, string]) => (zh ? pair[1] : pair[0]);

  const live = useRef(props);
  live.current = props;

  const callerCurrent = () => {
    try { const check=live.current.isHostCurrent; return check === undefined || check() === true; } catch { return false; }
  };

  const radioName = useId();
  const requestIdLabel = useId();

  const selectedIdentity = (value: ProjectJourneySelection | null) => value === null ? "null" : canonicalJson(value);
  const expectedSelection = useRef(selectedIdentity(selection));
  const emitSelection = (value: ProjectJourneySelection) => {
    expectedSelection.current=selectedIdentity(value);
    live.current.onSelection(value);
  };
  const boundHost = useRef(props.host);
  const sourceIdentity = useRef<{
    host: MissionHost; generation: number; source: SourceOperationTransport;
    readContext: NonNullable<MissionHost["readSourceOperationContext"]>; scope: string;
  } | null>(null);
  const sourceOwner = (): OwnerContext | null => {
    const saved=sourceIdentity.current,host=live.current.host;
    if (!callerCurrent()) return null;
    if (!saved || !host || saved.host!==host || saved.source!==host.sourceOperations ||
        saved.readContext!==host.readSourceOperationContext || saved.generation!==host.invalidationGeneration?.()) return null;
    const auth=host.auth?.getState();
    if (!auth || auth.status!=="signed_in" || !auth.acquisition) return null;
    return {principalScope:saved.scope,generation:`workspace:${saved.generation}`};
  };
  const record = useRef<JourneyRecord>({
    createStatus: null,
    planningKey: null,
    planningJob: null,
    keptDigest: null,
  });
  const abort = useRef<AbortController | null>(null);
  const busyRef = useRef<BusyAction | null>(null);
  const sequence = useRef(0);

  const [options, setOptions] = useState<JourneyOptions | null>(null);
  const [profileId, setProfileId] = useState<string | null>(null);
  const [preview, setPreview] = useState<JourneyPreview | null>(null);
  const [createDispatched, setCreateDispatched] = useState(false);
  const [previewUnknown, setPreviewUnknown] = useState(selection !== null);
  const [status, setStatus] = useState<SourceOperationStatus | null>(null);
  const [control, setControl] = useState<OperationState>({ status: "idle", pointer: null, reason: "IDLE" });
  const [notice, setNotice] = useState<Notice | null>(null);
  const [busy, setBusy] = useState<BusyAction | null>(null);
  const [planStage, setPlanStage] = useState<"clarify" | "plan" | null>(null);
  const [planRequest, setPlanRequest] = useState<string | null>(null);
  const [result, setResult] = useState<DirectResult | null>(null);

  const fileDraft=useProjectDraftFiles({locale,host:props.host,store:props.store,
    isCurrent:()=>callerCurrent()&&live.current.onDraftFilesChange!==undefined&&live.current.onOriginalFileLookupChange!==undefined,
    interactionBlocked:()=>busyRef.current!==null,workRef:selection?.workRef??null,created:status?.disposition==='accepted'&&status.receipt?.kind==='SOURCE_OBSERVED'&&status.selection.request_id===selection?.createRequestId&&status.owner_context.principal_scope===sourceOwner()?.principalScope,
    planningStarted:selection?.planningOperationKey!=null,files:props.draftFiles??[],
    onFilesChange:value=>live.current.onDraftFilesChange?.(value),original:props.originalFileLookup??null,
    onOriginalChange:value=>live.current.onOriginalFileLookupChange?.(value)});

  // Resource-specific controllers share the incumbent atomic store. The UI
  // gesture fence permits one effect at a time; Workspace and Executive scopes
  // remain distinct and private payloads never enter pending pointers.
  const machine = useRef<{
    controller: OperationController;
    createController: OperationController;
    planning: ProjectPlanningCommandPort;
    consume: DirectNativeCommandPort;
    planningRequest: (
      operation: PlanningOperation,
      args: Readonly<Record<string, unknown>>,
      signal: AbortSignal,
    ) => Promise<unknown>;
  } | null>(null);
  if (machine.current === null) {
    const owner = () => live.current.executiveOwner();
    const source = () => live.current.host?.sourceOperations ?? null;
    const suppliedStore = () => live.current.store;
    const store: PendingPointerStore = {
      read: (scope, signal) => suppliedStore().read(scope, signal),
      reserve: (scope, pointer, signal) => suppliedStore().reserve(scope, pointer, signal),
      clearIfEqual: (scope, pointer, signal) => suppliedStore().clearIfEqual(scope, pointer, signal),
    };
    const planningRequest = (
      operation: PlanningOperation,
      args: Readonly<Record<string, unknown>>,
      signal: AbortSignal,
    ): Promise<unknown> => {
      const transport = planningTransportOf(live.current.host);
      if (!transport) return Promise.reject(new Error("PROJECT_PLANNING_TRANSPORT_UNAVAILABLE"));
      return transport.request(operation, args, signal);
    };
    const planningKey = () => live.current.selection?.planningOperationKey ?? record.current.planningKey;
    // The real planning port expects raw receipts; the actual transport returns
    // the closed envelope, so exactly the matching envelope is unwrapped here.
    const wrappedPlanning: ProjectPlanningTransport = {
      request: (operation, args, signal) =>
        unwrapPlanningEnvelope(planningRequest(operation, args, signal), operation).then((data) => {
          return data;
        }),
    };
    const consumeTransport: DirectNativeTransport = {
      read: (selected, signal) =>
        unwrapPlanningEnvelope(
          planningRequest("result", planningArguments("result", {
            operation_key: planningKey(),
            work_ref: selected.work_ref,
          }), signal),
          "result",
        ),
      consume: (request, signal) =>
        unwrapPlanningEnvelope(
          planningRequest("consume", planningArguments("consume", {
            operation_key: planningKey(),
            work_ref: request.work_ref,
            attempt_id: request.attempt_id,
            result_digest: request.result_digest,
            consumption_operation_key: request.operation_key,
          }), signal),
          "consume",
        ),
    };
    const createPort = new CreateProjectSourcePort(sourceOwner, source, record.current);
    const planningPort = new ProjectPlanningCommandPort(wrappedPlanning, owner);
    const consumePort = new DirectNativeCommandPort(consumeTransport, owner);
    machine.current = {
      controller: new OperationController(new JourneyCommandPort(owner, planningPort, consumePort), store),
      createController: new OperationController(createPort, store),
      planning: planningPort,
      consume: consumePort,
      planningRequest,
    };
  }
  const controller = machine.current.controller;
  const createController = machine.current.createController;
  const consumePort = machine.current.consume;

  // A different project or host cannot retain the prior private draft/result.
  // Own preview records its new id before navigation, so that one normal
  // null→id transition does not invalidate its in-flight preparation.
  useLayoutEffect(() => {
    const next = selectedIdentity(selection);
    if (expectedSelection.current === next && boundHost.current === props.host) return;
    expectedSelection.current = next; boundHost.current = props.host;
    sourceIdentity.current = null;
    abort.current?.abort(); ++sequence.current; busyRef.current = null;
    controller.invalidate(); createController.invalidate();
    Object.assign(record.current, {createStatus:null, planningKey:null, planningJob:null, keptDigest:null});
    setOptions(null); setProfileId(null); setPreview(null); setStatus(null);
    setResult(null); setPlanRequest(null); setPlanStage(null); setBusy(null);
    setCreateDispatched(false); setPreviewUnknown(selection !== null); setNotice(null);
    setControl({status:"idle", pointer:null, reason:"IDLE"});
  }, [selection?.createRequestId, selection?.workRef, selection?.planningOperationKey, selection?.jobId, props.host]);

  // Unmount only: no read, no write and no navigation happens on mount.
  useEffect(() => () => {
    abort.current?.abort();
    machine.current?.controller.invalidate();
    machine.current?.createController.invalidate();
  }, []);
  useEffect(() => props.host?.auth?.subscribe(() => {
    sourceIdentity.current=null;
    abort.current?.abort(); ++sequence.current; busyRef.current=null; setBusy(null);
    machine.current?.controller.invalidate();
    machine.current?.createController.invalidate();
    record.current.createStatus=null;record.current.planningKey=null;record.current.planningJob=null;record.current.keptDigest=null;
    setOptions(null);setPreview(null);setStatus(null);setResult(null);setPlanRequest(null);setPlanStage(null);
    setControl({status:"idle",pointer:null,reason:"IDLE"});
  }), [props.host]);

  // ── session fence: auth state, generation and transport identity ──────────
  const fence = () => {
    const host = live.current.host;
    if (!host || !callerCurrent()) return null;
    const auth = host.auth?.getState();
    if (!auth || auth.status !== "signed_in" || !auth.acquisition) return null;
    const generation = host.invalidationGeneration?.();
    const source = host.sourceOperations;
    const readContext = host.readSourceOperationContext;
    if (typeof generation !== "number" || !source) return null;
    return { host, generation, source, readContext: readContext ?? null, planning: planningTransportOf(host) };
  };
  const stillFenced = (
    captured: Exclude<ReturnType<typeof fence>, null>,
    signal: AbortSignal,
  ): boolean => {
    const host = live.current.host;
    if (!host || !callerCurrent() || host !== captured.host || signal.aborted) return false;
    const auth = host.auth?.getState();
    if (!auth || auth.status !== "signed_in" || !auth.acquisition) return false;
    if (host.invalidationGeneration?.() !== captured.generation) return false;
    if (host.sourceOperations !== captured.source || planningTransportOf(host) !== captured.planning) return false;
    if (captured.readContext !== null && host.readSourceOperationContext !== captured.readContext) return false;
    return true;
  };

  const bindSourceIdentity = async (captured: Exclude<ReturnType<typeof fence>, null>, signal: AbortSignal) => {
    if (!captured.readContext) throw new Error("SOURCE_OPERATION_CONTEXT_INVALID");
    const raw=await captured.readContext.call(captured.host,{action:CREATE_ACTION,workRef:null,signal});
    if (!stillFenced(captured,signal)) throw new Error("READ_CANCELLED");
    const scope=contextScope(raw);
    if (scope===null) throw new Error("SOURCE_OPERATION_CONTEXT_INVALID");
    sourceIdentity.current={...captured,readContext:captured.readContext,scope};
    return scope;
  };

  const run = (name: BusyAction, body: (signal: AbortSignal) => Promise<void>) => {
    if (busyRef.current !== null || fileDraft.isBusy()) return;
    const started = new AbortController();
    const ticket = ++sequence.current;
    busyRef.current = name;
    setBusy(name);
    abort.current = started;
    void body(started.signal).catch(() => {
      if (!started.signal.aborted && sequence.current === ticket) setNotice("RESULT_UNAVAILABLE");
    }).finally(() => {
      if (sequence.current === ticket) {
        busyRef.current = null;
        setBusy(null);
        if (abort.current === started) abort.current = null;
      }
    });
  };

  const pointerOf = (state: OperationState): OperationPointer | null =>
    state.status === "submitting" || state.status === "checking" || state.status === "unknown"
      ? state.pointer
      : null;

  /** Only verified facts move the parent selection; unknown never rewrites it. */
  const syncCreate = () => {
    const observed = record.current.createStatus;
    if (!observed) return;
    const current = live.current.selection;
    if (!current || observed.selection.request_id !== current.createRequestId ||
        observed.owner_context.principal_scope !== sourceOwner()?.principalScope ||
        (current.workRef !== null && observed.selection.work_ref !== current.workRef)) return;
    setStatus(observed);
    if (observed.disposition !== "accepted") return;
    setPreviewUnknown(false);
    const workRef = observed.selection.work_ref;
    if (!WORK_REF.test(workRef) || current.workRef === workRef) return;
    emitSelection({ ...current, workRef });
  };

  const syncPlanning = (state: OperationState) => {
    if (state.status !== "accepted" || !state.missionSelection) return;
    const current = live.current.selection;
    if (!current) return;
    const { workRef, rootJobId } = state.missionSelection;
    if (workRef !== current.workRef) return;
    record.current.planningJob = { jobId: rootJobId, jobStatus: "ACCEPTED" };
    if (current.jobId === rootJobId) return;
    emitSelection({ ...current, jobId: rootJobId });
  };

  // ── explicit actions ──────────────────────────────────────────────────────

  const loadOptions = () => {
    const captured = fence();
    if (!captured) {
      setNotice("AUTH");
      return;
    }
    const readOptions = captured.source.readProjectCreationOptions;
    if (typeof readOptions !== "function") {
      setNotice("OPTIONS");
      return;
    }
    run("options", async (signal) => {
      let scope: string;
      try { scope = await bindSourceIdentity(captured,signal); }
      catch { if (!signal.aborted && stillFenced(captured,signal)) setNotice("CONTEXT"); return; }
      try {
        const raw = await readOptions.call(captured.source, signal);
        if (!stillFenced(captured, signal)) return;
        const decoded = decodeCreationOptions(raw);
        if (!decoded) {
          setNotice("OPTIONS");
          return;
        }
        if (decoded.ownerScope !== scope) {
          setNotice("SCOPE_MISMATCH");
          return;
        }
        setOptions(decoded);
        setPreview(null);
        setNotice(null);
      } catch {
        if (!signal.aborted && stillFenced(captured, signal)) setNotice("OPTIONS");
      }
    });
  };

  const chooseProfile = (id: string) => {
    setProfileId(id);
    setPreview(null);
    setNotice(null);
  };

  const preparePreview = () => {
    if (!authorized) {
      setNotice("AUTH");
      return;
    }
    if (options === null) {
      setNotice("OPTIONS");
      return;
    }
    if (!goal.trim()) {
      setNotice("GOAL_REQUIRED");
      return;
    }
    const choice = options.profiles.find((profile) => profile.id === profileId);
    if (!choice) {
      setNotice("PROFILE_REQUIRED");
      return;
    }
    const pending = pointerOf(control);
    if (previewUnknown || createDispatched || (pending !== null && pending.kind === CREATE_KIND)) {
      setNotice("CREATE_BUSY");
      return;
    }
    const captured = fence();
    if (!captured) {
      setNotice("AUTH");
      return;
    }
    // Identity is minted once per explicit gesture, synchronously before the
    // prepare effect, and the parent selection is told first.
    const requestId = mintCreateRequestId();
    setPreviewUnknown(true);
    emitSelection({
      createRequestId: requestId,
      workRef: null,
      planningOperationKey: null,
      jobId: null,
    });
    setCreateDispatched(false);
    setPreview(null);
    record.current.createStatus = null;
    record.current.planningKey = null;
    record.current.planningJob = null;
    record.current.keptDigest = null;
    setStatus(null);
    setResult(null);
    const request = {
      schema: REQUEST_SCHEMA,
      request_id: requestId,
      goal,
      expected_macro_sha: options.expectedMacroSha,
      profile_id: choice.id,
      profile_sha256: choice.revision,
    };
    run("preview", async (signal) => {
      try {
        const raw = await captured.source.prepareSourceOperation({ action: CREATE_ACTION, request }, signal);
        if (!stillFenced(captured, signal)) return;
        const verified = decodeCreationPreview(raw, {
          requestId,
          scope: options.ownerScope,
          request,
          goal,
          profileId: choice.id,
          profileRevision: choice.revision,
          expectedMacroSha: options.expectedMacroSha,
        });
        if (!verified) {
          setNotice("PREVIEW_UNAVAILABLE");
          return;
        }
        setPreviewUnknown(false);
        setPreview(verified);
        setNotice(null);
      } catch {
        if (!signal.aborted && stillFenced(captured, signal)) setNotice("PREVIEW_UNAVAILABLE");
      }
    });
  };

  const publish = () => {
    const current = live.current.selection;
    const verified = preview;
    if (
      !verified ||
      !current ||
      current.createRequestId !== verified.requestId ||
      verified.goal !== goal ||
      verified.profileId !== profileId
    ) {
      setNotice("PREVIEW_STALE");
      return;
    }
    if (verified.scope !== sourceOwner()?.principalScope) {
      setNotice("CONTEXT");
      return;
    }
    const intent: CommandIntent = {
      kind: CREATE_KIND,
      targetKey: createTargetKey(verified.requestId, verified.workRef),
      payload: {
        action: CREATE_ACTION,
        request_id: verified.requestId,
        work_ref: verified.workRef,
        preview_witness: verified.witness,
      },
    };
    setCreateDispatched(true);
    run("publish", async () => {
      const state = await createController.begin(intent);
      setControl(state);
      syncCreate();
    });
  };

  const checkSource = () => {
    const current = live.current.selection;
    if (!current) {
      setNotice("SOURCE_READ_UNAVAILABLE");
      return;
    }
    run("source-read", async (signal) => {
      const captured = fence();
      if (!captured) {setNotice("AUTH");return;}
      try {await bindSourceIdentity(captured,signal);} catch {setNotice("CONTEXT");return;}
      const state = await createController.recover();
      setControl(state);
      syncCreate();
      if (state.status !== "idle" || state.reason !== "RECOVER_NO_POINTER") return;
      // Fresh reopen without a stored hint: one exact read-only lookup, with a
      // null work reference when none is known, so the backend derives the
      // actual workspace from the verified principal and the original id.
      try {
        const lookup = {
          schema: LOOKUP_SCHEMA,
          action: CREATE_ACTION,
          request_id: current.createRequestId,
          work_ref: current.workRef,
        } as unknown as BasicSourceLookup;
        const raw = await captured.source.readSourceOperation(lookup, signal);
        if (!stillFenced(captured, signal)) return;
        const observed = decodeSourceOperationStatus(raw);
        const acting = sourceOwner();
        if (
          observed.selection.action !== CREATE_ACTION ||
          observed.selection.request_id !== current.createRequestId ||
          (options !== null && observed.owner_context.principal_scope !== options.ownerScope) ||
          !acting ||
          observed.owner_context.principal_scope !== acting.principalScope
        ) {
          // A foreign original request, or a status owned by another principal,
          // is never this operation whatever its disposition claims.
          setNotice("SOURCE_READ_UNAVAILABLE");
          return;
        }
        const receipt = createReceipt({kind:CREATE_KIND,operationKey:current.createRequestId,
          targetKey:createTargetKey(current.createRequestId,current.workRef)}, observed,
          {requestId:current.createRequestId,workRef:current.workRef,scope:acting.principalScope});
        if (receipt.disposition === "unknown" && receipt.reason !== "UNKNOWN_RECEIPT") {
          setNotice("SOURCE_READ_UNAVAILABLE"); return;
        }
        record.current.createStatus = observed;
        syncCreate();
      } catch {
        if (!signal.aborted && stillFenced(captured, signal)) setNotice("SOURCE_READ_UNAVAILABLE");
      }
    });
  };

  const checkPublication = () => {
    const pending = pointerOf(control);
    const target = pending !== null && pending.kind === CREATE_KIND ? parseCreateTarget(pending.targetKey) : null;
    if (!target || typeof target.work_ref !== "string") {
      setNotice("PUBLICATION_RECONCILE_UNAVAILABLE");
      return;
    }
    run("publication", async () => {
      const state = await createController.recover({ reconcileSource: true });
      setControl(state);
      syncCreate();
    });
  };

  const composePlanning = (
    owner: OwnerContext,
    current: ProjectJourneySelection,
  ): { ok: true; intent: CommandIntent; operationKey: string } | { ok: false; reason: Notice } => {
    if (fileDraft.blocksPlanning()) return {ok:false,reason:"PLANNING_FILES_PENDING"};
    if (current.planningOperationKey !== null) return { ok: false, reason: "PLANNING_ALREADY_DISPATCHED" };
    if (!current.workRef) return { ok: false, reason: "PLANNING_UNAVAILABLE_SOURCE" };
    const observed = record.current.createStatus;
    if (!observed || observed.selection.request_id !== current.createRequestId) {
      return { ok: false, reason: "PLANNING_UNAVAILABLE_SOURCE" };
    }
    const publication = publicationOf(observed);
    const source = projectSourceOf(observed);
    if (!publication || !source) return { ok: false, reason: "PLANNING_UNAVAILABLE_SOURCE" };
    if (!options?.grounding) return { ok: false, reason: "PLANNING_UNAVAILABLE_GROUNDING" };
    if (!hex(options.grounding.mastermindSha, HEX40)) return { ok: false, reason: "PLANNING_UNAVAILABLE_GROUNDING" };
    // The planning macro grounding is the actual observed CREATE commit, never
    // the option's expected value and never a derived or fixture value.
    const commit = fileDraft.currentPlanningCommit() ?? source.commit;
    if (typeof commit !== "string" || !hex(commit, HEX40)) return { ok: false, reason: "PLANNING_UNAVAILABLE_SOURCE" };
    if (source.path !== `${SOURCE_PATH_PREFIX}${current.workRef.slice(3)}.md`) {
      return { ok: false, reason: "PLANNING_UNAVAILABLE_SOURCE" };
    }
    if (publication.principalScope !== sourceOwner()?.principalScope) {
      return { ok: false, reason: "PLANNING_UNAVAILABLE_SOURCE" };
    }
    const request = planRequest ?? goal;
    if (!request.trim() || new TextEncoder().encode(request).length > 32768) {
      return { ok: false, reason: "PLANNING_REQUEST_REQUIRED" };
    }
    if (planStage === null) return { ok: false, reason: "PLANNING_REQUEST_REQUIRED" };
    const grounding = {
      mastermind_sha: options.grounding.mastermindSha,
      macro_sha: commit,
    };
    const input: PlanningSubmitInput = {
      stage: planStage,
      work_ref: current.workRef,
      project_source: source,
      publication: {
        request_id: publication.requestId,
        principal_scope: publication.principalScope,
        event_id: publication.eventId,
        receipt_sha256: publication.receiptSha256,
      },
      grounding,
      private_request: request,
    };
    const intent = makePlanningIntent(owner, input, grounding);
    if (!intent) return { ok: false, reason: "PLANNING_UNAVAILABLE_SOURCE" };
    return { ok: true, intent, operationKey: planningOperationKey(owner, input) };
  };

  const sendPlanning = () => {
    const current = live.current.selection;
    const owner = live.current.executiveOwner();
    if (!current || !owner) {
      setNotice(current === null ? "PLANNING_UNAVAILABLE_SOURCE" : "OWNER_ABSENT");
      return;
    }
    const composed = composePlanning(owner, current);
    if (!composed.ok) {
      setNotice(composed.reason);
      return;
    }
    // The planning key is recorded on the shared selection BEFORE dispatch.
    emitSelection({ ...current, planningOperationKey: composed.operationKey });
    record.current.planningKey = composed.operationKey;
    run("plan", async () => {
      const state = await controller.begin(composed.intent);
      setControl(state);
      syncPlanning(state);
    });
  };

  const checkPlanning = () => {
    const current = live.current.selection;
    if (!current?.workRef || !current.planningOperationKey) {
      setNotice("PLANNING_READ_UNAVAILABLE"); return;
    }
    const captured = fence();
    if (!captured) { setNotice("AUTH"); return; }
    run("plan-read", async (signal) => {
      const recovered = await controller.recover();
      if (!stillFenced(captured, signal)) return;
      setControl(recovered); syncPlanning(recovered);
      if (recovered.status !== "idle" || recovered.reason !== "RECOVER_NO_POINTER") return;
      // A safe route can outlive a cleared local hint. Read the original key
      // through the closed port; never submit a replacement.
      const receipt = await machine.current!.planning.readOperation({
        kind: "launch", operationKey: current.planningOperationKey!,
        targetKey: planningTargetKey(current.workRef!),
      }, signal);
      if (!stillFenced(captured, signal)) return;
      if (receipt.disposition === "accepted" && receipt.missionSelection) {
        const accepted: OperationState = {status:"accepted", pointer:null, reason:"ACCEPTED", missionSelection:receipt.missionSelection};
        setControl(accepted); syncPlanning(accepted);
      } else setNotice("PLANNING_READ_UNAVAILABLE");
    });
  };

  const readResult = () => {
    const current = live.current.selection;
    const key = current?.planningOperationKey ?? record.current.planningKey;
    const jobId = current?.jobId ?? record.current.planningJob?.jobId ?? null;
    if (!current?.workRef || !key) {
      setNotice("RESULT_UNAVAILABLE");
      return;
    }
    if (!jobId) {
      setNotice("RESULT_NEEDS_JOB");
      return;
    }
    const captured = fence();
    if (!captured) {
      setNotice("AUTH");
      return;
    }
    const workRef = current.workRef;
    run("result", async (signal) => {
      try {
        const args = planningArguments("result", { operation_key: key, work_ref: workRef });
        const data = await unwrapPlanningEnvelope(machine.current!.planningRequest("result", args, signal), "result");
        if (!stillFenced(captured, signal)) return;
        // The job comes from the accepted planning status; a null attempt is
        // permitted so the response can carry the actual attempt.
        const decoded = decodeDirectNativeResult(data, { work_ref: workRef, job_id: jobId, attempt_id: null });
        if (!decoded) {
          setNotice("RESULT_UNAVAILABLE");
          return;
        }
        setResult(decoded);
        setNotice(null);
      } catch {
        if (!signal.aborted && stillFenced(captured, signal)) setNotice("RESULT_UNAVAILABLE");
      }
    });
  };

  /** Read-only recovery of a pending keep on the SAME original pointer/digest. */
  const checkKeep = () => {
    const pending = pointerOf(control);
    if (!pending || pending.kind !== "consume") {
      setNotice("RESULT_UNAVAILABLE");
      return;
    }
    run("keep-read", async () => {
      const state = await controller.recover();
      setControl(state);
      if (state.status === "accepted") {
        const target = parseConsumeTarget(pending.targetKey);
        if (target) record.current.keptDigest = target.result_digest;
      }
    });
  };

  const keepResult = () => {
    const current = live.current.selection;
    const decoded = result;
    if (!decoded?.result || !current?.workRef || !decoded.selection.attempt_id) {
      setNotice("RESULT_UNAVAILABLE");
      return;
    }
    const digest = decoded.result.result_digest;
    const intent = consumePort.makeConsumeIntent({
      work_ref: current.workRef,
      job_id: decoded.selection.job_id,
      attempt_id: decoded.selection.attempt_id,
    }, digest);
    if (!intent) {
      setNotice("RESULT_UNAVAILABLE");
      return;
    }
    run("keep", async () => {
      const state = await controller.begin(intent);
      setControl(state);
      if (state.status === "accepted") record.current.keptDigest = digest;
    });
  };

  // ── derived display ───────────────────────────────────────────────────────

  const authorized = (() => {
    const auth = props.host?.auth?.getState();
    return Boolean(callerCurrent() && auth && auth.status === "signed_in" && auth.acquisition);
  })();
  const planningAvailable = planningTransportOf(props.host) !== null;
  const observed =
    status !== null && status.selection.request_id === selection?.createRequestId &&
    status.owner_context.principal_scope === sourceOwner()?.principalScope &&
    status.selection.work_ref === selection?.workRef && status.disposition === "accepted" && status.receipt?.kind === "SOURCE_OBSERVED"
      ? status
      : null;
  const openCreatedProject = () => {
    const accepted = observed, captured = fence(), owner = sourceOwner();
    const open = live.current.onOpenProject;
    if (!accepted || !captured || !owner || !open || record.current.createStatus !== accepted) return;
    const identity = selectedIdentity(live.current.selection), workRef = accepted.selection.work_ref;
    run("open-project", async signal => {
      setNotice(null);
      const current = () => stillFenced(captured, signal) &&
        record.current.createStatus === accepted && selectedIdentity(live.current.selection) === identity &&
        sourceOwner()?.principalScope === owner.principalScope;
      let opened = false;
      try { if (current()) opened = await open(workRef, current); } catch { /* Read-only failure remains retryable. */ }
      if (!opened && current()) setNotice("OPEN_PROJECT_UNAVAILABLE");
    });
  };
  const proposal =
    status !== null && status.disposition === "unknown" && status.receipt !== null ? status : null;
  const publication = observed === null ? null : publicationOf(observed);
  const sourceRecord = observed === null ? null : projectSourceOf(observed);
  const previewLive =
    preview !== null &&
    preview.goal === goal &&
    preview.profileId === profileId &&
    preview.scope === sourceOwner()?.principalScope &&
    selection?.createRequestId === preview.requestId
      ? preview
      : null;
  const readable = Boolean(observed !== null && selection?.workRef !== null);
  const kept = record.current.keptDigest !== null;
  const pendingPointer = pointerOf(control);
  const createPending = pendingPointer !== null && pendingPointer.kind === CREATE_KIND ? pendingPointer : null;
  const createReconcilable =
    createPending !== null && typeof parseCreateTarget(createPending.targetKey)?.work_ref === "string";
  const consumePending = pendingPointer !== null && pendingPointer.kind === "consume" ? pendingPointer : null;
  const observedJobId = selection?.jobId ?? record.current.planningJob?.jobId ?? null;
  const requestText = planRequest ?? goal;
  const returnedDeclaration=authorized && result?.result && result.selection.work_ref===selection?.workRef &&
    result.selection.job_id===observedJobId && isExplicitPlanDeclaration(result.result.current_state,result.selection.work_ref)
      ? result.result.current_state : null;

  const planningBlock: Notice | null = (() => {
    if (!readable) return "PLANNING_UNAVAILABLE_SOURCE";
    if (fileDraft.blocksPlanning()) return "PLANNING_FILES_PENDING";
    if (!planningAvailable) return "PLANNING_UNAVAILABLE_HOST";
    if (!options?.grounding) return "PLANNING_UNAVAILABLE_GROUNDING";
    if (publication === null || sourceRecord === null) return "PLANNING_UNAVAILABLE_SOURCE";
    const workRef = selection?.workRef;
    if (!workRef || sourceRecord.path !== `${SOURCE_PATH_PREFIX}${workRef.slice(3)}.md`) {
      return "PLANNING_UNAVAILABLE_SOURCE";
    }
    const owner = live.current.executiveOwner();
    if (!owner) return "OWNER_ABSENT";
    if (publication.principalScope !== sourceOwner()?.principalScope) return "PLANNING_UNAVAILABLE_SOURCE";
    return null;
  })();

  const planningRecovery=selection?.planningOperationKey != null && result===null &&
    (observed===null || control.status==="unknown" || control.status==="checking");
  const stateLine: readonly [string, string] = (() => {
    const pair = (en: string, cn: string): readonly [string, string] => [en, cn];
    if (!authorized) return NOTICE_COPY.AUTH;
    if (control.status === "submitting") return pair("Sending request…", "正在发送请求…");
    if (control.status === "checking") return pair("Checking the recorded state…", "正在查询记录的状态…");
    if (control.status === "refused") return pair("The source refused this request.", "来源拒绝了此请求。");
    if (planningRecovery) return pair("Check the original planning request. Do not send it again.", "请查询原始规划请求，不要重新发送。");
    if (control.status === "unknown") {
      return pair(
        "The outcome is not known yet. The original record is kept for a later check.",
        "结果尚不可知。原始记录已保留，稍后可再次查询。",
      );
    }
    if (observed !== null) {
      if (kept) return pair("Planning result kept.", "规划结果已保留。");
      if (result?.result !== undefined && result.result !== null) {
        return pair("Planning result read. It is kept only when you keep it.", "规划结果已读取。只有选择保留才会保留。");
      }
      if (observedJobId !== null) {
        return pair("Planning request accepted.", "规划请求已接受。");
      }
      return pair("Project created.", "项目已创建。");
    }
    if (proposal !== null) {
      return pair("Project creation is still pending. Check the original request.", "项目仍在创建中。请查询原始请求。");
    }
    if (previewLive !== null) {
      return pair("Preview ready. Create this project to continue.", "预览已准备好。创建项目后继续。");
    }
    if (previewUnknown && selection !== null) return pair("Check the original project request before continuing.", "继续前请查询原始项目请求。");
    if (options !== null) return pair("Choose a project profile.", "请选择项目配置。");
    return pair("Choose a project profile in Options to continue.", "请在“选项”中选择项目配置后继续。");
  })();

  const disabled = busy !== null || fileDraft.isBusy();

  const optionsPanel = (
    <div role="group" aria-label={copy(["Project profile", "项目配置"])}>
      {!authorized ? (
        <p>{copy(NOTICE_COPY.AUTH)}</p>
      ) : options === null ? (
        <>
          <p>{copy(["Load the supplied project options to choose a profile.", "载入提供的项目选项以选择配置。"])}</p>
          <button type="button" onClick={loadOptions} disabled={disabled}>
            {busy === "options" ? copy(["Loading…", "载入中…"]) : copy(["Load project options", "载入项目选项"])}
          </button>
        </>
      ) : (
        <div role="radiogroup" aria-label={copy(["Project profile", "项目配置"])}>
          {options.profiles.map((profile) => (
            <div key={profile.id}>
              <label>
                <input
                  type="radio"
                  name={radioName}
                  value={profile.id}
                  checked={profileId === profile.id}
                  onChange={() => chooseProfile(profile.id)}
                />
                <span> {zh ? profile.labelZh : profile.labelEn}</span>
              </label>
              <p>{zh ? profile.summaryZh : profile.summaryEn}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );

  const feedback = (
    <div>

      {previewLive !== null && createDispatched && (
        <p>{copy(["Use the original project request below.", "请使用下方原始项目请求。"])}</p>
      )}
      <p>
        {selection !== null && (
          <>
            {" "}
            {!previewUnknown && <button type="button" onClick={checkSource} disabled={disabled}>
              {busy === "source-read" ? copy(["Checking…", "查询中…"]) : copy(["Check original project request", "查询原始项目请求"])}
            </button>}
            {createPending !== null && (
              <>
                {" "}
                <button type="button" onClick={checkPublication} disabled={disabled || !createReconcilable}>
                  {busy === "publication" ? copy(["Checking…", "查询中…"]) : copy(["Check project creation", "查询项目创建状态"])}
                </button>
              </>
            )}
          </>
        )}
      </p>
      {(readable || (selection?.workRef != null && selection.planningOperationKey !== null)) && (
        <section aria-label={copy(["Initial planning", "初始规划"])}>
          <h3>{copy(["Initial planning", "初始规划"])}</h3>
          {planningRecovery && previewUnknown && <p>
            <button type="button" onClick={checkSource} disabled={disabled || !authorized}>
              {copy(["Check original project request", "查询原始项目请求"])}</button>
          </p>}
          {selection?.planningOperationKey != null ? (
            <p>{copy(["Use the original planning request below.", "请使用下方原始规划请求。"] )}</p>
          ) : planningBlock !== null ? (
            <p>{copy(NOTICE_COPY[planningBlock])}</p>
          ) : (
            <>
              <div role="radiogroup" aria-label={copy(["Planning stage", "规划阶段"])}>
                <label>
                  <input
                    type="radio"
                    name={`${radioName}-stage`}
                    value="clarify"
                    checked={planStage === "clarify"}
                    onChange={() => setPlanStage("clarify")}
                  />
                  <span> {copy(["Clarify", "澄清"])}</span>
                </label>
                <label>
                  <input
                    type="radio"
                    name={`${radioName}-stage`}
                    value="plan"
                    checked={planStage === "plan"}
                    onChange={() => setPlanStage("plan")}
                  />
                  <span> {copy(["Plan", "规划"])}</span>
                </label>
              </div>
              <div className="form-field">
                <label htmlFor={requestIdLabel}>{copy(["Initial request", "初始请求"])}</label>
                <textarea
                  id={requestIdLabel}
                  value={requestText}
                  onChange={(event) => setPlanRequest(event.target.value)}
                  rows={4}
                />
              </div>
              <p>
                <button type="button" onClick={sendPlanning} disabled={disabled}>
                  {busy === "plan" ? copy(["Sending…", "发送中…"]) : copy(["Send initial planning request", "发送初始规划请求"])}
                </button>
              </p>
            </>
          )}
          {selection?.planningOperationKey != null && (
            <p>
              <button type="button" onClick={checkPlanning} disabled={disabled}>
                {busy === "plan-read" ? copy(["Checking…", "查询中…"]) : copy(["Check planning status", "查询规划状态"])}
              </button>
            </p>
          )}
          {observedJobId !== null && (
            <p>
              <button type="button" onClick={readResult} disabled={disabled}>
                {busy === "result" ? copy(["Reading…", "读取中…"]) : copy(["Read planning result", "读取规划结果"])}
              </button>
            </p>
          )}
        </section>
      )}
      {authorized && result !== null && result.selection.work_ref === selection?.workRef && result.selection.job_id === observedJobId && result.result !== null && (
        <section aria-label={copy(["Planning result", "规划结果"])}>
          <h3>{copy(["Planning result", "规划结果"])}</h3>
          <p>{result.result.summary}</p>
          {returnedDeclaration === null ? <p>{result.result.current_state}</p> :
            <p>{copy(["This result includes a suggested plan declaration. Publication and adoption are not confirmed here. See Source details.",
              "此结果包含建议计划声明。此处尚未确认发布或采纳；原始声明位于来源详情。"] )}</p>}
          {result.result.completed_steps.length > 0 && (
            <section><h4>{copy(["Completed steps", "已完成的步骤"])}</h4><ul>
              {result.result.completed_steps.map((step, index) => <li key={index}>{step}</li>)}
            </ul></section>
          )}
          {result.result.next_actions.length > 0 && (
            <section><h4>{copy(["Suggested next actions", "建议的后续行动"])}</h4><ul>
              {result.result.next_actions.map((action, index) => <li key={index}>{action}</li>)}
            </ul></section>
          )}
          <p>
            {result.consumption?.state === "CONSUMED" || kept ? (
              copy(["This result is kept.", "此结果已保留。"])
            ) : (
              <button type="button" onClick={keepResult} disabled={disabled}>
                {busy === "keep" ? copy(["Keeping…", "保留中…"]) : copy(["Keep result", "保留结果"])}
              </button>
            )}
          </p>
          {consumePending !== null && (
            <p>
              {copy(["The keep of this exact result is being observed.", "正在观察此结果的保留。"])}{" "}
              <button type="button" onClick={checkKeep} disabled={disabled}>
                {busy === "keep-read" ? copy(["Checking…", "查询中…"]) : copy(["Check keep status", "查询保留状态"])}
              </button>
            </p>
          )}
        </section>
      )}
      {authorized && result !== null && result.selection.work_ref === selection?.workRef && result.selection.job_id === observedJobId && result.result === null && <p>{copy(NOTICE_COPY.RESULT_UNAVAILABLE)}</p>}
      {authorized && selection?.workRef && selection.planningOperationKey && props.onProposalOriginalChange &&
        props.currentProposalOriginal && (returnedDeclaration !== null || props.proposalOriginal) && <ProjectPlanProposalWorkflow
          key={`proposal:${selection.workRef}:${selection.planningOperationKey}`}
          host={props.host} store={props.store} workRef={selection.workRef}
          planningOperationKey={selection.planningOperationKey} result={result}
          consumed={!!result?.result && (record.current.keptDigest === result.result.result_digest || result.consumption?.state === "CONSUMED")}
          hasDeclaration={returnedDeclaration !== null} executiveOwner={props.executiveOwner}
          isCurrent={callerCurrent} original={props.proposalOriginal ?? null}
          onOriginalChange={props.onProposalOriginalChange} currentOriginal={props.currentProposalOriginal} locale={locale}/>}
      {proposal !== null && <p>{copy(["Project creation is still pending. Check the original request.", "项目仍在创建中。请查询原始请求。"])}</p>}
      {readable && (proposalControls !== undefined || comparePanel !== undefined) && (
        <>
          {proposalControls}
          {comparePanel}
        </>
      )}
      <details>
        <summary>{copy(["Source details", "来源详情"])}</summary>
        {returnedDeclaration !== null && <section>
          <h4>{copy(["Suggested plan declaration · Publication and adoption are not confirmed here.", "建议的计划声明 · 此处尚未确认发布或采纳。"])}</h4>
          <pre>{returnedDeclaration}</pre>
        </section>}
        <dl>
          {selection !== null && (
            <>
              <dt>{copy(["Request", "请求"])}</dt>
              <dd>{selection.createRequestId}</dd>
              {selection.workRef !== null && (
                <>
                  <dt>{copy(["Workspace", "工作区"])}</dt>
                  <dd>{selection.workRef}</dd>
                </>
              )}
              {selection.planningOperationKey !== null && (
                <>
                  <dt>{copy(["Planning key", "规划键"])}</dt>
                  <dd>{selection.planningOperationKey}</dd>
                </>
              )}
              {selection.jobId !== null && (
                <>
                  <dt>{copy(["Job", "任务"])}</dt>
                  <dd>{selection.jobId}</dd>
                </>
              )}
            </>
          )}
          {previewLive !== null && (
            <>
              <dt>{copy(["Draft reference", "草稿引用"])}</dt>
              <dd>{previewLive.workRef}</dd>
              <dt>{copy(["Source commit", "来源提交"])}</dt>
              <dd>{previewLive.sourceCommit}</dd>
              <dt>{copy(["Content digest", "内容摘要"])}</dt>
              <dd>{previewLive.contentSha256}</dd>
              <dt>{copy(["Request digest", "请求摘要"])}</dt>
              <dd>{previewLive.requestSha256}</dd>
            </>
          )}
          {observed !== null && observed.receipt !== null && (
            <>
              <dt>{copy(["Publication event", "发布事件"])}</dt>
              <dd>{observed.receipt.event_id}</dd>
              <dt>{copy(["Receipt digest", "回执摘要"])}</dt>
              <dd>{observed.receipt.receipt_sha256}</dd>
              <dt>{copy(["Source commit", "来源提交"])}</dt>
              <dd>{observed.receipt.sources[0]?.commit}</dd>
            </>
          )}
          {record.current.planningJob !== null && (
            <>
              <dt>{copy(["Planning job", "规划任务"])}</dt>
              <dd>{record.current.planningJob.jobId}</dd>
              <dt>{copy(["Planning state", "规划状态"])}</dt>
              <dd>{record.current.planningJob.jobStatus}</dd>
            </>
          )}
          <dt>{copy(["Controller state", "控制器状态"])}</dt>
          <dd>{`${control.status} ${control.reason}`}</dd>
        </dl>
      </details>
    </div>
  );

  return (
    <NewProjectDraft
      headingLevel={1}
      locale={locale}
      goal={goal}
      goalReadOnly={props.goalReadOnly} onGoalFocus={props.onGoalFocus}
      onGoalChange={onGoalChange}
      attachmentsControl={fileDraft.control}
      attachmentsPanel={fileDraft.panel}
      primarySummary={<><p role="status">{copy(stateLine)}</p>{notice!==null&&<p role="status">{copy(NOTICE_COPY[notice])}</p>}
      {observed !== null && props.onOpenProject && <button type="button" className="primary"
        onClick={openCreatedProject} disabled={disabled || !authorized} aria-busy={busy === "open-project"}>
        {busy === "open-project" ? copy(["Opening project…", "正在打开项目…"]) : copy(["Open project", "打开项目"])}
      </button>}
      {previewLive !== null && options !== null && (() => {
        const chosen=options.profiles.find(row=>row.id===previewLive.profileId);
        return chosen ? <div><h3>{zh?chosen.labelZh:chosen.labelEn}</h3>
          <p>{zh?chosen.summaryZh:chosen.summaryEn}</p></div> : null;
      })()}
</>}
      optionsPanel={optionsPanel}
      feedbackPanel={feedback}
      startControl={planningRecovery ? <button type="button" className="primary" onClick={checkPlanning} disabled={disabled || !authorized}>
        {copy(["Check original planning request", "查询原始规划请求"])}</button> : observed !== null ? <span>{copy(["Project created.", "项目已创建。"])}</span> :
        createDispatched ? <span>{copy(["Check project creation below", "请在下方查询项目创建状态"])}</span> :
        previewUnknown ? <button type="button" className="primary" onClick={checkSource} disabled={disabled || !authorized}>{copy(["Check original project request", "查询原始项目请求"])}</button> :
        previewLive !== null ? <button type="button" className="primary" onClick={publish} disabled={disabled}>
          {busy === "publish" ? copy(["Creating project…", "正在创建项目…"]) : copy(["Create project", "创建项目"])}</button> :
        <button type="button" className="primary" onClick={preparePreview} disabled={disabled || !authorized || options === null}>
          {busy === "preview" ? copy(["Preparing…", "准备中…"]) : copy(["Prepare preview", "准备预览"])}</button>}
      startNote={copy(planningRecovery ? ["Check the original planning request. Do not send it again.", "请查询原始规划请求，不要重新发送。"] : observed !== null ? ["Initial planning is a separate action below.", "初始规划是下方独立的操作。"] :
        createDispatched ? ["The original project request is retained for checking.", "原始项目请求已保留，可供查询。"] :
        previewUnknown ? ["Keep the original request identity while its response is unavailable.", "响应不可用时，请保留原始请求标识。"] :
        previewLive !== null ? ["Creates the project. Planning is a separate step.", "创建项目；规划是独立的后续步骤。"] :
        ["Choose the supplied profile and check a preview before creating the project.", "请选择提供的配置，并在创建项目前核对预览。"]) }
    />
  );
}
