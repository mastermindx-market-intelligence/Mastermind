/**
 * Closed, pure URL-state adapter for the New project -> initial planning
 * journey of `mastermind_os`.
 *
 * This repairs the missing parent persistence composition: the New-project
 * journey state lives in the URL `search` alone, so a reload or redirect
 * reopens exactly the committed state. The adapter owns exactly five keys
 * (`new_project`, `project_create_request`, `project_create_work_ref`,
 * `project_planning_operation`, `project_planning_job`) and ignores every
 * other input key; it never decodes a goal, profile or prompt payload.
 *
 * Purity and authority:
 *   - no network, storage, DOM, auth, worker, clock or publication effect of
 *     any kind; `commit` runs exactly one caller-supplied `replaceState`.
 *   - a read or committed selection is DATA, never a grant. Decoding or
 *     writing these keys starts, resumes, authorizes or confirms no create,
 *     planning or job operation of any kind.
 *   - written URLs carry only the owned keys. Private inputs (goal, profile,
 *     prompt) and the unrelated legacy Mission identity keys (`work_ref`,
 *     `root_job_id`) are never carried over, and URL credentials are never
 *     propagated; origin (scheme + host + port) and path are preserved.
 *   - every writer rejection throws one constant error; no input value is
 *     ever echoed.
 *
 * Read decision table (total over the owned keys):
 *   - no owned key present                    -> valid, closed, no selection.
 *   - flag `1` without ids (or ids absent)    -> valid, open, blank.
 *   - duplicate owned key, flag value other than `1`, an invalid id, ids
 *     without the CREATE id, planning key without work ref, job id without
 *     planning key                            -> invalid, closed.
 *   - otherwise                               -> valid, open, selection.
 */

import { ORIGINAL_OPERATION_ID_PREFIXES } from "../planning/plan-adoption-status";
import {parseProjectDraftFileLookup,serializeProjectDraftFileLookup,type ProjectDraftFileLookup} from "./project-draft-file-lookup";
import type { ProjectJourneySelection } from "./ProjectPlanningJourney";
import {decodePlanProposalOriginal,parsePlanProposalOriginal,serializePlanProposalOriginal,type PlanProposalOriginal} from "../planning/project-plan-proposal";

/** Single constant rejection message for every invalid selection object. */
export const PROJECT_JOURNEY_SELECTION_INVALID =
  "PROJECT_JOURNEY_SELECTION_INVALID" as const;

/** The journey flag is armed by this exact value; nothing else is accepted. */
export const PROJECT_JOURNEY_FLAG_KEY = "new_project";
export const PROJECT_JOURNEY_FLAG_VALUE = "1";

/** Owned keys, listed in the fixed order the writer emits them. */
export const PROJECT_JOURNEY_CREATE_REQUEST_KEY = "project_create_request";
export const PROJECT_JOURNEY_WORK_REF_KEY = "project_create_work_ref";
export const PROJECT_JOURNEY_PLANNING_OPERATION_KEY = "project_planning_operation";
export const PROJECT_JOURNEY_JOB_KEY = "project_planning_job";
export const PROJECT_JOURNEY_FILE_KEY = "project_file_original";
export const PROJECT_JOURNEY_PLAN_PROPOSAL_KEY = "project_plan_proposal_original";

/** Exact owned key set, in writer emission order. */
export const PROJECT_JOURNEY_KEYS = [
  PROJECT_JOURNEY_FLAG_KEY,
  PROJECT_JOURNEY_CREATE_REQUEST_KEY,
  PROJECT_JOURNEY_WORK_REF_KEY,
  PROJECT_JOURNEY_PLANNING_OPERATION_KEY,
  PROJECT_JOURNEY_JOB_KEY,
  PROJECT_JOURNEY_FILE_KEY,
  PROJECT_JOURNEY_PLAN_PROPOSAL_KEY,
] as const;

/** `<prefix>` + this many lowercase hex characters; never minted here. */
export const CREATE_REQUEST_ID_HEX_CHARS = 40;
export const PLANNING_OPERATION_ID_HEX_CHARS = 40;
export const PLANNING_OPERATION_ID_PREFIX = "mmos-project-planning-";
/** `WS:` suffix bounds, mirroring the producer's work-ref key bounds. */
export const MIN_WORK_REF_KEY_CHARS = 2;
export const MAX_WORK_REF_KEY_CHARS = 64;

const CREATE_REQUEST_PREFIX =
  ORIGINAL_OPERATION_ID_PREFIXES.publish_project_proposal;
const WORK_REF_PREFIX = "WS:";
const CREATE_REQUEST_HEX_RE = new RegExp(
  `^[0-9a-f]{${CREATE_REQUEST_ID_HEX_CHARS}}$`,
);
const PLANNING_OPERATION_ID_RE = new RegExp(
  `^[0-9a-f]{${PLANNING_OPERATION_ID_HEX_CHARS}}$`,
);
const PLANNING_JOB_ID_RE = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;
const WORK_REF_SUFFIX_RE = /^[A-Z0-9]+(?:-[A-Z0-9]+)*$/;
/** Parse-only origin for bare `?...` query strings; never written back. */
const QUERY_ONLY_PARSE_ORIGIN = "http://journey.invalid/";

export interface ProjectJourneyReadResult {
  readonly valid: boolean;
  readonly open: boolean;
  readonly selection: ProjectJourneySelection | null;
  readonly fileLookup?:Readonly<ProjectDraftFileLookup>;
  readonly proposalOriginal?:PlanProposalOriginal;
}

const closedRead = (): ProjectJourneyReadResult => ({
  valid: true,
  open: false,
  selection: null,
});
const openBlankRead = (): ProjectJourneyReadResult => ({
  valid: true,
  open: true,
  selection: null,
});
const invalidRead = (): ProjectJourneyReadResult => ({
  valid: false,
  open: false,
  selection: null,
});

function isCreateRequestId(value: string): boolean {
  if (!value.startsWith(CREATE_REQUEST_PREFIX)) return false;
  return CREATE_REQUEST_HEX_RE.test(value.slice(CREATE_REQUEST_PREFIX.length));
}

function isWorkRef(value: string): boolean {
  if (!value.startsWith(WORK_REF_PREFIX)) return false;
  const suffix = value.slice(WORK_REF_PREFIX.length);
  if (suffix.length < MIN_WORK_REF_KEY_CHARS) return false;
  if (suffix.length > MAX_WORK_REF_KEY_CHARS) return false;
  return WORK_REF_SUFFIX_RE.test(suffix);
}

function isPlanningOperationId(value: string): boolean {
  return value.startsWith(PLANNING_OPERATION_ID_PREFIX) &&
    PLANNING_OPERATION_ID_RE.test(value.slice(PLANNING_OPERATION_ID_PREFIX.length));
}

function isPlanningJobId(value: string): boolean {
  return PLANNING_JOB_ID_RE.test(value);
}

function toReadUrl(input: string | URL): URL {
  if (input instanceof URL) return input;
  try {
    return new URL(input);
  } catch (error) {
    if (input.startsWith("?")) return new URL(input, QUERY_ONLY_PARSE_ORIGIN);
    throw error;
  }
}

function toWriteUrl(input: string | URL): URL {
  try {
    if (input instanceof URL) return input;
    return new URL(input);
  } catch {
    throw new TypeError(PROJECT_JOURNEY_SELECTION_INVALID);
  }
}

/** Validate ids and their dependency chain of an owned-key view. */
function checkIds(
  createRequestId: string | null,
  workRef: string | null,
  planningOperationKey: string | null,
  jobId: string | null,
): boolean {
  if (createRequestId !== null && !isCreateRequestId(createRequestId)) return false;
  if (workRef !== null && !isWorkRef(workRef)) return false;
  if (planningOperationKey !== null && !isPlanningOperationId(planningOperationKey)) {
    return false;
  }
  if (jobId !== null && !isPlanningJobId(jobId)) return false;
  if (planningOperationKey !== null && workRef === null) return false;
  if (jobId !== null && planningOperationKey === null) return false;
  if (createRequestId === null && workRef === null && planningOperationKey === null && jobId === null) {
    return true;
  }
  return createRequestId !== null;
}

/**
 * Read the journey state of a location. Total over all inputs: unrelated
 * keys are ignored, malformed journey state never throws.
 */
export function readProjectJourneyLocation(input: string | URL): ProjectJourneyReadResult {
  let params: URLSearchParams;
  try { params = toReadUrl(input).searchParams; }
  catch { return invalidRead(); }
  const owned = new Map<string, string>();
  for (const key of PROJECT_JOURNEY_KEYS) {
    const values = params.getAll(key);
    if (values.length > 1) return invalidRead();
    if (values.length === 1) owned.set(key, values[0]);
  }
  if (owned.size === 0) return closedRead();
  const flag = owned.get(PROJECT_JOURNEY_FLAG_KEY);
  if (flag !== undefined && flag !== PROJECT_JOURNEY_FLAG_VALUE) return invalidRead();
  const createRequestId = owned.get(PROJECT_JOURNEY_CREATE_REQUEST_KEY) ?? null;
  const workRef = owned.get(PROJECT_JOURNEY_WORK_REF_KEY) ?? null;
  const planningOperationKey = owned.get(PROJECT_JOURNEY_PLANNING_OPERATION_KEY) ?? null;
  const jobId = owned.get(PROJECT_JOURNEY_JOB_KEY) ?? null;
  if (!checkIds(createRequestId, workRef, planningOperationKey, jobId)) return invalidRead();
  let fileLookup:Readonly<ProjectDraftFileLookup>|undefined;
  if(owned.has(PROJECT_JOURNEY_FILE_KEY)){
    if(createRequestId===null||workRef===null)return invalidRead();
    try{fileLookup=parseProjectDraftFileLookup(owned.get(PROJECT_JOURNEY_FILE_KEY)!,workRef);}catch{return invalidRead();}
  }
  let proposalOriginal:PlanProposalOriginal|undefined;
  if(owned.has(PROJECT_JOURNEY_PLAN_PROPOSAL_KEY)){
    if(!createRequestId||!workRef||!planningOperationKey||!jobId)return invalidRead();
    try{proposalOriginal=parsePlanProposalOriginal(owned.get(PROJECT_JOURNEY_PLAN_PROPOSAL_KEY)!,workRef);
      if(proposalOriginal.operation_key!==planningOperationKey||proposalOriginal.proposal_request.selection.job_id!==jobId)return invalidRead();
    }catch{return invalidRead();}
  }
  if (createRequestId === null) return openBlankRead();
  return {
    valid: true,
    open: true,
    selection: { createRequestId, workRef, planningOperationKey, jobId },
    ...(fileLookup?{fileLookup}:{}),
    ...(proposalOriginal?{proposalOriginal}:{}),
  };
}

const SELECTION_KEYS = ["createRequestId", "workRef", "planningOperationKey", "jobId"] as const;
const SELECTION_KEY_SET = new Set<string>(SELECTION_KEYS);

function isPlainRecord(value: unknown): value is Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return false;
  const proto = Object.getPrototypeOf(value);
  return proto === Object.prototype || proto === null;
}

/**
 * Runtime-check a closed, plain selection: exactly the four declared keys as
 * own enumerable data properties, no accessors, no extras, no symbol keys,
 * class instances or arrays; values match the reader's grammar and the same
 * dependency chain. Values are copied into a fresh plain object and never
 * echoed on rejection.
 */
function checkedSelection(selection: ProjectJourneySelection): ProjectJourneySelection {
  if (!isPlainRecord(selection)) throw new Error(PROJECT_JOURNEY_SELECTION_INVALID);
  const names = Reflect.ownKeys(selection);
  if (names.length !== SELECTION_KEYS.length) throw new Error(PROJECT_JOURNEY_SELECTION_INVALID);
  for (const name of names) {
    if (typeof name !== "string" || !SELECTION_KEY_SET.has(name)) {
      throw new Error(PROJECT_JOURNEY_SELECTION_INVALID);
    }
  }
  const descriptors = Object.getOwnPropertyDescriptors(selection);
  for (const key of SELECTION_KEYS) {
    const descriptor = descriptors[key];
    if (descriptor === undefined || descriptor.get !== undefined || descriptor.set !== undefined) {
      throw new Error(PROJECT_JOURNEY_SELECTION_INVALID);
    }
  }
  const createRequestId = selection.createRequestId;
  const workRef = selection.workRef;
  const planningOperationKey = selection.planningOperationKey;
  const jobId = selection.jobId;
  const notId = (value: unknown): boolean =>
    typeof value !== "string" || value === "null";
  if (notId(createRequestId) || !isCreateRequestId(createRequestId)) {
    throw new Error(PROJECT_JOURNEY_SELECTION_INVALID);
  }
  if (
    (workRef !== null && notId(workRef)) ||
    (workRef !== null && !isWorkRef(workRef)) ||
    (planningOperationKey !== null && notId(planningOperationKey)) ||
    (planningOperationKey !== null && !isPlanningOperationId(planningOperationKey)) ||
    (jobId !== null && notId(jobId)) ||
    (jobId !== null && !isPlanningJobId(jobId))
  ) {
    throw new Error(PROJECT_JOURNEY_SELECTION_INVALID);
  }
  if (
    (planningOperationKey !== null && workRef === null) ||
    (jobId !== null && planningOperationKey === null)
  ) {
    throw new Error(PROJECT_JOURNEY_SELECTION_INVALID);
  }
  return { createRequestId, workRef, planningOperationKey, jobId };
}

/**
 * Build the committed URL: origin (scheme + host + port) and path are
 * preserved, prior search and hash are cleared, and only the owned keys are
 * written. A `null` selection commits the clean closed URL; every non-null
 * selection is committed with the flag armed.
 */
function journeyUrl(
  input: string | URL,
  selection: ProjectJourneySelection | null,
  fileLookup?:ProjectDraftFileLookup|null,
  proposalOriginal?:PlanProposalOriginal|null,
): { href: string; committed: ProjectJourneySelection | null } {
  const url = toWriteUrl(input);
  const committed = selection === null ? null : checkedSelection(selection);
  let encodedFile:string|null=null;
  if(fileLookup!==undefined&&fileLookup!==null){
    if(!committed?.workRef)throw Error(PROJECT_JOURNEY_SELECTION_INVALID);
    try{encodedFile=serializeProjectDraftFileLookup(fileLookup,committed.workRef);}catch{throw Error(PROJECT_JOURNEY_SELECTION_INVALID);}
  }
  let encodedProposal:string|null=null;
  if(proposalOriginal!==undefined&&proposalOriginal!==null){
    if(!committed?.workRef||!committed.planningOperationKey||!committed.jobId)throw Error(PROJECT_JOURNEY_SELECTION_INVALID);
    try{const checked=decodePlanProposalOriginal(proposalOriginal,committed.workRef);
      if(checked.operation_key!==committed.planningOperationKey||checked.proposal_request.selection.job_id!==committed.jobId)throw Error();
      encodedProposal=serializePlanProposalOriginal(checked);
    }catch{throw Error(PROJECT_JOURNEY_SELECTION_INVALID);}
  }
  const params = new URLSearchParams();
  if (committed !== null) {
    params.set(PROJECT_JOURNEY_FLAG_KEY, PROJECT_JOURNEY_FLAG_VALUE);
    params.set(PROJECT_JOURNEY_CREATE_REQUEST_KEY, committed.createRequestId);
    if (committed.workRef !== null) {
      params.set(PROJECT_JOURNEY_WORK_REF_KEY, committed.workRef);
    }
    if (committed.planningOperationKey !== null) {
      params.set(PROJECT_JOURNEY_PLANNING_OPERATION_KEY, committed.planningOperationKey);
    }
    if (committed.jobId !== null) {
      params.set(PROJECT_JOURNEY_JOB_KEY, committed.jobId);
    }
  }
  if(encodedFile!==null)params.set(PROJECT_JOURNEY_FILE_KEY,encodedFile);
  if(encodedProposal!==null)params.set(PROJECT_JOURNEY_PLAN_PROPOSAL_KEY,encodedProposal);
  const base = `${url.protocol}//${url.host}${url.pathname}`;
  const search = params.toString();
  return { href: search === "" ? base : `${base}?${search}`, committed };
}

/** Compute the URL that commits `selection` to this location. */
export function projectJourneyUrl(
  input: string | URL,
  selection: ProjectJourneySelection | null,
  fileLookup?:ProjectDraftFileLookup|null,
  proposalOriginal?:PlanProposalOriginal|null,
): string {
  return journeyUrl(input, selection,fileLookup,proposalOriginal).href;
}

/**
 * Commit `selection` to this location: the URL is computed and synchronously
 * written through `history.replaceState(null, "", url)` BEFORE `onCommitted`
 * runs. If `replaceState` throws, `onCommitted` is never called and the error
 * propagates unchanged. No promise, effect or state owner is involved.
 */
export function commitProjectJourneySelection(
  input: string | URL,
  selection: ProjectJourneySelection | null,
  history: Pick<History, "replaceState">,
  onCommitted: (selection: ProjectJourneySelection | null) => void,
  fileLookup?:ProjectDraftFileLookup|null,
  proposalOriginal?:PlanProposalOriginal|null,
): void {
  const { href, committed } = journeyUrl(input, selection,fileLookup,proposalOriginal);
  history.replaceState(null, "", href);
  onCommitted(committed);
}
