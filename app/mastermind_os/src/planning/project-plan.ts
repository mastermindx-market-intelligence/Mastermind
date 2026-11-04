/**
 * Pure TypeScript decoder for the canonical Agent OS workspace project-plan
 * READ body (``mastermind.workspace_project_plan.v1``).
 *
 * The fixed HTTP and native transports already return the public BODY.
 * This decoder validates that body, counts its canonical socket envelope
 * plus line delimiter against MAX_RESPONSE_BYTES, and returns detached data.
 * Transport envelopes, strings and byte buffers are not alternate inputs.
 *
 * Ported 1:1 from the authoritative Python side:
 *
 * - ``common/workspace_project_plan_contract.py`` (``validate_body``,
 *   ``validate_selection``, ``validate_source``, ``unavailable``), and
 * - ``control_plane/workspace_project_plan.py`` (``project_workstream_plan``),
 *   whose projection rules the wire body must reproduce exactly -- the
 *   Python ``validate_body`` reconstructs the body through the projector and
 *   rejects any value that is not equal to that reconstruction.  The
 *   reconstruction-vs-body comparison below preserves that guard, which is
 *   why e.g. a wire ``depends_on: null`` or a blank-but-present
 *   ``next_action`` is rejected even though each field looks individually
 *   harmless.
 *
 * Like the Python contract this decoder is PURE: no I/O, no clock, no
 * network, no parser, no transport, no cache, no Git access.  The source
 * identity and the Git record revision history are owner-supplied *facts*
 * that are checked here -- never fetched, never reconstructed, never treated
 * as authorization.  Authored ``done`` status is record state, never
 * acceptance or approval; ``adoption`` stays explicitly unavailable and is
 * never invented.  Authored status vocabularies are producer-owned and are
 * passed through verbatim as bounded nonempty strings; no private enum is
 * added for them.
 *
 * Rejected input is never echoed back: every failure raises the single
 * value-free constant ``PROJECT_PLAN_INVALID``.
 *
 * PR references use the same positive JS-safe integer bound as the owner.
 *
 * Accepted ``committed_at`` forms mirror CPython 3.12
 * ``datetime.fromisoformat`` (probed): extended or basic calendar dates, an
 * optional single separator character, ``HH``, ``HHMM`` or ``HH:MM`` with
 * optional seconds, an optional ``.``/`,` fraction with zero or more digits
 * on the last component, and a required ``Z`` (uppercase only) or
 * ``+HH[:MM[:SS]]`` / ``+HHMM[SS]`` offset whose normalized magnitude is
 * strictly below 24 hours (offset minutes/seconds beyond 59 normalize the
 * same way Python does).  Week dates and ordinal dates are deliberately not
 * accepted.
 */

import { decodeProjectPlanContinuity, type ProjectPlanContinuityRead,
  type ProjectPlanSourceRef, type ProjectPlanAdoptionUnavailableReason } from "./project-plan-continuity";

export const BODY_SCHEMA = "mastermind.workspace_project_plan.v1";
export const BODY_SCHEMA_V2 = "mastermind.workspace_project_plan.v2";
export const FRAME_SCHEMA = "mastermind.workspace_project_plan_read.v1";
export const OPERATION = "project_plan";
export const MAX_RESPONSE_BYTES = 131072;

/** The exact source repository this operation may address. */
export const CANONICAL_REPOSITORY = "mastermindx-market-intelligence/macro";

/** ``WS:`` selector facts, mirroring the producer's ``KEY_RE``. */
export const WORK_REF_PREFIX = "WS:";
export const MIN_WORK_REF_KEY_CHARS = 2;
export const MAX_WORK_REF_KEY_CHARS = 64;

/** Closed typed-unavailability reason codes carried by ``reason_codes``. */
export const REASON_SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE";
export const REASON_SOURCE_CHANGED = "SOURCE_CHANGED";
export const REASON_RECORD_NOT_FOUND = "RECORD_NOT_FOUND";
export const REASON_RECORD_INVALID = "RECORD_INVALID";
export const REASON_CONTENT_OVER_BUDGET = "CONTENT_OVER_BUDGET";
export const REASON_CODES = [
  REASON_SOURCE_UNAVAILABLE,
  REASON_SOURCE_CHANGED,
  REASON_RECORD_NOT_FOUND,
  REASON_RECORD_INVALID,
  REASON_CONTENT_OVER_BUDGET,
] as const;
export type ProjectPlanReasonCode = (typeof REASON_CODES)[number];

export const AVAILABILITY_AVAILABLE = "AVAILABLE";
export const AVAILABILITY_UNAVAILABLE = "UNAVAILABLE";

/** ``adoption`` is never invented: no generic adoption field is authored. */
export const ADOPTION_STATE_UNAVAILABLE = "UNAVAILABLE";
export const ADOPTION_REASON_NOT_DECLARED = "NOT_DECLARED";

/** Owner-supplied Git record history, checked -- never fetched or invented. */
export const VERSION_HISTORY_STATE_UNAVAILABLE = "UNAVAILABLE";
export const VERSION_HISTORY_REASON_NOT_SUPPLIED_BY_OWNER = "NOT_SUPPLIED_BY_OWNER";
export const VERSION_HISTORY_REASON_SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE";

/** Projection bounds mandated by the commissioned read contract. */
export const MAX_TITLE_CHARS = 512;
export const MAX_OBJECTIVE_CHARS = 16384;
export const MAX_OWNER_CHARS = 256;
export const MAX_NEXT_ACTION_CHARS = 16384;
export const MAX_WORKSTREAM_STATUS_CHARS = 64;
export const MAX_WAVES = 64;
export const MAX_WAVE_ID_CHARS = 128;
export const MAX_WAVE_TITLE_CHARS = 1024;
export const MAX_WAVE_STATUS_CHARS = 32;
export const MAX_WAVE_NEXT_ACTION_CHARS = 16384;
export const MAX_DEPENDENCY_ID_CHARS = 128;
export const MAX_PRS_PER_WAVE = 32;
export const MAX_REVISIONS = 8;
export const MAX_COMMITTED_AT_CHARS = 40;

export const BODY_KEYS = [
  "schema",
  "selection",
  "availability",
  "source",
  "plan",
  "reason_codes",
] as const;

/** Strict selection: exactly one ``WS:<KEY>`` work reference. */
export interface ProjectPlanSelection {
  work_ref: string;
}

/** Source identity: addressing and pinning facts, never authorization. */
export interface ProjectPlanSourceIdentity {
  repository: string;
  commit: string;
  path: string;
  content_sha256: string;
}

export interface ProjectPlanAdoptionUnavailable {
  state: typeof ADOPTION_STATE_UNAVAILABLE;
  reason: typeof ADOPTION_REASON_NOT_DECLARED;
}

/** One authentic Git record revision, supplied by the trusted owner. */
export interface ProjectPlanGitRecordRevision {
  commit: string;
  committed_at: string;
  content_sha256: string;
}

export type ProjectPlanVersionHistory =
  | {
      state: typeof VERSION_HISTORY_STATE_UNAVAILABLE;
      reason:
        | typeof VERSION_HISTORY_REASON_NOT_SUPPLIED_BY_OWNER
        | typeof VERSION_HISTORY_REASON_SOURCE_UNAVAILABLE;
    }
  | {
      state: "AVAILABLE";
      kind: "GIT_RECORD_REVISIONS";
      revisions: ProjectPlanGitRecordRevision[];
    };

export interface ProjectPlanWave {
  id: string;
  title: string;
  /** Producer-owned authored status, verbatim and bounded -- no enum here. */
  status: string;
  depends_on: string[];
  next_action: string | null;
  /** Positive safe-integer PR references, authored order preserved. */
  prs: number[];
}

export interface ProjectPlan {
  title: string;
  objective: string;
  /** Authored workstream record state -- never acceptance or adoption. */
  status: string;
  owner: string;
  next_action: string | null;
  waves: ProjectPlanWave[];
  adoption: ProjectPlanAdoptionUnavailable;
  version_history: ProjectPlanVersionHistory;
}

export interface ProjectPlanReadAvailable {
  schema: typeof BODY_SCHEMA;
  selection: ProjectPlanSelection;
  availability: typeof AVAILABILITY_AVAILABLE;
  source: ProjectPlanSourceIdentity;
  plan: ProjectPlan;
  reason_codes: [];
}

export interface ProjectPlanReadUnavailable {
  schema: typeof BODY_SCHEMA;
  selection: ProjectPlanSelection;
  availability: typeof AVAILABILITY_UNAVAILABLE;
  source: null;
  plan: null;
  reason_codes: [ProjectPlanReasonCode];
}

export type ProjectPlanAdoptionSummary =
  | { state: "UNAVAILABLE"; reason: ProjectPlanAdoptionUnavailableReason }
  | { state: "AVAILABLE"; decision_ref: string; adopted_source: ProjectPlanSourceRef;
      display_revision: string | null; matches_authored_record: boolean };
export interface ProjectPlanReadAvailableV2 extends Omit<ProjectPlanReadAvailable, "schema" | "plan"> {
  schema: typeof BODY_SCHEMA_V2;
  plan: Omit<ProjectPlan, "adoption"> & { adoption: ProjectPlanAdoptionSummary };
  continuity: ProjectPlanContinuityRead;
}

/** The closed read body for one workstream plan projection. */
export type ProjectPlanRead = ProjectPlanReadAvailable | ProjectPlanReadAvailableV2 | ProjectPlanReadUnavailable;

const INVALID_MESSAGE = "PROJECT_PLAN_INVALID";

const SELECTION_KEYS = ["work_ref"] as const;
const SOURCE_KEYS = ["repository", "commit", "path", "content_sha256"] as const;
const PLAN_KEYS = [
  "title",
  "objective",
  "status",
  "owner",
  "next_action",
  "waves",
  "adoption",
  "version_history",
] as const;
const WAVE_KEYS = ["id", "title", "status", "depends_on", "next_action", "prs"] as const;
const ADOPTION_KEYS = ["state", "reason"] as const;
const HISTORY_UNAVAILABLE_KEYS = ["state", "reason"] as const;
const HISTORY_AVAILABLE_KEYS = ["state", "kind", "revisions"] as const;
const REVISION_KEYS = ["commit", "committed_at", "content_sha256"] as const;

const WORK_REF_KEY_RE = /^[A-Z0-9]+(?:-[A-Z0-9]+)*$/;
const COMMIT_RE = /^[0-9a-f]{40}$/;
const CONTENT_SHA256_RE = /^[0-9a-f]{64}$/;

const UTF8_ENCODER = new TextEncoder();

/** ``str.isspace()`` code points -- the set Python ``str.strip()`` removes. */
const PYTHON_WHITESPACE = new Set<number>([
  0x09, 0x0a, 0x0b, 0x0c, 0x0d, 0x1c, 0x1d, 0x1e, 0x1f, 0x20, 0x85, 0xa0,
  0x1680, 0x2000, 0x2001, 0x2002, 0x2003, 0x2004, 0x2005, 0x2006, 0x2007,
  0x2008, 0x2009, 0x200a, 0x2028, 0x2029, 0x202f, 0x205f, 0x3000,
]);

const DAYS_IN_MONTH = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];

/**
 * Whole-string match.  JS ``$`` also matches before a trailing newline, so
 * the captured match is compared to the full value: any extra character
 * (including that newline) rejects.
 */
function fullMatch(pattern: RegExp, value: string): boolean {
  const match = pattern.exec(value);
  return match !== null && match[0] === value;
}

/** Python ``len()`` counts code points, not UTF-16 code units. */
function charCount(value: string): number {
  let count = 0;
  let index = 0;
  while (index < value.length) {
    const unit = value.charCodeAt(index);
    index += unit >= 0xd800 && unit < 0xdc00 && index + 1 < value.length &&
        value.charCodeAt(index + 1) >= 0xdc00 && value.charCodeAt(index + 1) < 0xe000
      ? 2
      : 1;
    count += 1;
  }
  return count;
}

function pythonStrip(value: string): string {
  let start = 0;
  let end = value.length;
  while (start < end) {
    const code = value.codePointAt(start) as number;
    if (!PYTHON_WHITESPACE.has(code)) break;
    start += code > 0xffff ? 2 : 1;
  }
  while (end > start) {
    const code = value.codePointAt(end - 1) as number;
    if (!PYTHON_WHITESPACE.has(code)) break;
    end -= code > 0xffff ? 2 : 1;
  }
  return value.slice(start, end);
}

function isBlank(value: string): boolean {
  return pythonStrip(value).length === 0;
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function hasExactKeys(value: object, keys: readonly string[]): boolean {
  const actual = Object.keys(value);
  if (actual.length !== keys.length) return false;
  const expected = new Set<string>(keys);
  for (const key of actual) {
    if (!expected.has(key)) return false;
  }
  return true;
}

function fail(): never {
  throw new Error(INVALID_MESSAGE);
}

/** JSON-equivalent deep equality (Python dict/list equality semantics). */
function deepEqual(left: unknown, right: unknown): boolean {
  if (left === right) return true;
  if (typeof left !== typeof right) return false;
  if (left === null || right === null) return false;
  if (Array.isArray(left) !== Array.isArray(right)) return false;
  if (Array.isArray(left)) {
    const rightList = right as unknown[];
    if (left.length !== rightList.length) return false;
    return left.every((item, index) => deepEqual(item, rightList[index]));
  }
  if (isPlainObject(left) && isPlainObject(right)) {
    const leftKeys = Object.keys(left);
    const rightKeys = new Set(Object.keys(right));
    if (leftKeys.length !== rightKeys.size) return false;
    return leftKeys.every(
      (key) => rightKeys.has(key) && deepEqual(left[key], right[key]),
    );
  }
  return false;
}

/** No lone surrogate can occur on a canonical UTF-8 wire frame. */
function isWellFormedString(value: string): boolean {
  let index = 0;
  while (index < value.length) {
    const unit = value.charCodeAt(index);
    if (unit >= 0xd800 && unit < 0xe000) {
      const isPaired = unit < 0xdc00 && index + 1 < value.length &&
        value.charCodeAt(index + 1) >= 0xdc00 && value.charCodeAt(index + 1) < 0xe000;
      if (!isPaired) return false;
      index += 1;
    }
    index += 1;
  }
  return true;
}

function assertWellFormedStrings(value: unknown): void {
  if (typeof value === "string") {
    if (!isWellFormedString(value)) fail();
    return;
  }
  if (Array.isArray(value)) {
    for (const item of value) assertWellFormedStrings(item);
    return;
  }
  if (isPlainObject(value)) {
    for (const key of Object.keys(value)) {
      if (!isWellFormedString(key)) fail();
      assertWellFormedStrings(value[key]);
    }
  }
}

/**
 * Validate one ``WS:<KEY>`` selector string: strict prefix, 2..64 key
 * characters, single dashes between groups, no path or Job selector shape.
 */
function isValidWorkRef(workRef: string): boolean {
  if (!workRef.startsWith(WORK_REF_PREFIX)) return false;
  const key = workRef.slice(WORK_REF_PREFIX.length);
  const length = charCount(key);
  if (length < MIN_WORK_REF_KEY_CHARS || length > MAX_WORK_REF_KEY_CHARS) return false;
  return fullMatch(WORK_REF_KEY_RE, key);
}

/** Exact canonical Store path for one workstream record. */
export function canonicalRecordPath(key: string): string {
  return `agentos/workstreams/WS-${key}.md`;
}

/**
 * Quiet predicate for the closed selection shape: a mapping carrying EXACTLY
 * ``work_ref`` -- no caller-supplied ``path``, ``commit``, ``job`` or any
 * other selector companion.
 */
export function validProjectPlanSelection(value: unknown): value is ProjectPlanSelection {
  return selectionWorkRef(value) !== null;
}

function selectionWorkRef(value: unknown): string | null {
  if (!isPlainObject(value) || !hasExactKeys(value, SELECTION_KEYS)) return null;
  const workRef = value.work_ref;
  if (typeof workRef !== "string" || !isValidWorkRef(workRef)) return null;
  return workRef;
}

function requireExpectedSelection(expected: unknown): string {
  const workRef = selectionWorkRef(expected);
  if (workRef === null) fail();
  return workRef;
}

function requireBodySelection(value: unknown, expectedWorkRef: string): string {
  if (!isPlainObject(value) || !hasExactKeys(value, SELECTION_KEYS)) fail();
  const workRef = value.work_ref;
  if (typeof workRef !== "string" || !isValidWorkRef(workRef)) fail();
  // Matching the selected work_ref is mandatory: the pinned read is only the
  // selected read.
  if (workRef !== expectedWorkRef) fail();
  return workRef;
}

function requireSourceIdentity(value: unknown, workRef: string): ProjectPlanSourceIdentity {
  const key = workRef.slice(WORK_REF_PREFIX.length);
  if (!isPlainObject(value) || !hasExactKeys(value, SOURCE_KEYS)) fail();
  const repository = value.repository;
  const commit = value.commit;
  const path = value.path;
  const contentSha256 = value.content_sha256;
  if (repository !== CANONICAL_REPOSITORY) fail();
  if (typeof commit !== "string" || !fullMatch(COMMIT_RE, commit)) fail();
  if (typeof path !== "string" || path !== canonicalRecordPath(key)) fail();
  if (typeof contentSha256 !== "string" || !fullMatch(CONTENT_SHA256_RE, contentSha256)) fail();
  return { repository, commit, path, content_sha256: contentSha256 };
}

function requireText(value: unknown, maxChars: number): string {
  if (typeof value !== "string" || isBlank(value) || charCount(value) > maxChars) fail();
  return value;
}

function requireOptionalText(value: unknown, maxChars: number): string | null {
  if (value === null) return null;
  if (typeof value !== "string" || isBlank(value) || charCount(value) > maxChars) fail();
  return value;
}

/**
 * Wire ``prs`` list: positive safe integers only.  A non-integer, boolean,
 * zero, negative or beyond-``Number.MAX_SAFE_INTEGER`` reference is invalid
 * -- the Python int producer normalizes to the JS safe range.
 */
function requirePrs(value: unknown): number[] {
  if (!Array.isArray(value) || value.length > MAX_PRS_PER_WAVE) fail();
  for (const pr of value) {
    if (!Number.isSafeInteger(pr) || pr <= 0) fail();
  }
  return value.slice() as number[];
}

function requireDependencies(value: unknown): string[] {
  if (!Array.isArray(value)) fail();
  const deps: string[] = [];
  for (const dep of value) {
    if (typeof dep !== "string" || dep.length === 0) fail();
    if (charCount(dep) > MAX_DEPENDENCY_ID_CHARS) fail();
    if (deps.includes(dep)) fail();
    deps.push(dep);
  }
  return deps;
}

/**
 * Iterative colouring DFS over the authored order.  Forward dependencies
 * (a wave depending on a later wave) alone are never a cycle; unknown
 * dependencies and duplicates within one wave are rejected before this runs.
 */
function hasDependencyCycle(waves: ProjectPlanWave[]): boolean {
  const graph = new Map<string, readonly string[]>();
  for (const wave of waves) graph.set(wave.id, wave.depends_on);
  const settled = new Set<string>();
  for (const start of graph.keys()) {
    if (settled.has(start)) continue;
    const visiting = new Set<string>([start]);
    const stack: Array<{ node: string; index: number }> = [{ node: start, index: 0 }];
    while (stack.length > 0) {
      const frame = stack[stack.length - 1] as { node: string; index: number };
      const deps = graph.get(frame.node) as readonly string[];
      let advanced = false;
      while (frame.index < deps.length) {
        const dep = deps[frame.index] as string;
        frame.index += 1;
        if (visiting.has(dep)) return true;
        if (!settled.has(dep)) {
          visiting.add(dep);
          stack.push({ node: dep, index: 0 });
          advanced = true;
          break;
        }
      }
      if (!advanced) {
        visiting.delete(frame.node);
        settled.add(frame.node);
        stack.pop();
      }
    }
  }
  return false;
}

function requireWaves(value: unknown): ProjectPlanWave[] {
  if (!Array.isArray(value)) fail();
  if (value.length > MAX_WAVES) fail();
  const waves: ProjectPlanWave[] = [];
  const seenIds = new Set<string>();
  for (const wave of value) {
    if (!isPlainObject(wave) || !hasExactKeys(wave, WAVE_KEYS)) fail();
    const id = wave.id;
    if (
      typeof id !== "string" ||
      charCount(id) === 0 ||
      charCount(id) > MAX_WAVE_ID_CHARS ||
      pythonStrip(id) !== id
    ) {
      fail();
    }
    if (seenIds.has(id)) fail();
    seenIds.add(id);
    const title = requireText(wave.title, MAX_WAVE_TITLE_CHARS);
    const status = requireText(wave.status, MAX_WAVE_STATUS_CHARS);
    const dependsOn = requireDependencies(wave.depends_on);
    const nextAction = requireOptionalText(wave.next_action, MAX_WAVE_NEXT_ACTION_CHARS);
    const prs = requirePrs(wave.prs);
    waves.push({ id, title, status, depends_on: dependsOn, next_action: nextAction, prs });
  }
  for (const wave of waves) {
    for (const dep of wave.depends_on) {
      if (!seenIds.has(dep)) fail();
    }
  }
  if (hasDependencyCycle(waves)) fail();
  return waves;
}

function requireAdoption(value: unknown): ProjectPlanAdoptionUnavailable {
  if (!isPlainObject(value) || !hasExactKeys(value, ADOPTION_KEYS)) fail();
  if (value.state !== ADOPTION_STATE_UNAVAILABLE || value.reason !== ADOPTION_REASON_NOT_DECLARED) {
    fail();
  }
  return { state: ADOPTION_STATE_UNAVAILABLE, reason: ADOPTION_REASON_NOT_DECLARED };
}

function isReasonCode(value: unknown): value is ProjectPlanReasonCode {
  return typeof value === "string" && (REASON_CODES as readonly string[]).includes(value);
}

function isLeapYear(year: number): boolean {
  return year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
}

const COMMITTED_AT_RE = new RegExp(
  "^(?:(\\d{4})-(\\d{2})-(\\d{2})|(\\d{4})(\\d{2})(\\d{2}))" + // 1-3 extended / 4-6 basic date
  "[^]?" +                                                     // optional single separator character
  "(\\d{2})(?::(\\d{2})(?::(\\d{2}))?|(\\d{2})(?:(\\d{2}))?)?" + // 7 HH (optional) + 8,9 basic / 10,11 extended MM,SS
  "(?:[.,]\\d*)?" +                                            // fraction on the last time component
  "(?:Z|[+-](\\d{2})(?::(\\d{2})(?::(\\d{2}))?|(\\d{2})(?:\\d{2})?)?(?:[.,]\\d*)?)$", // 12-16 offset
);

/**
 * ``committed_at`` must parse as a timezone-aware ISO-8601 datetime the way
 * Python ``datetime.fromisoformat`` does, within 40 characters.
 */
function isValidCommittedAt(value: string): boolean {
  if (charCount(value) > MAX_COMMITTED_AT_CHARS) return false;
  const match = COMMITTED_AT_RE.exec(value);
  if (match === null) return false;
  const [
    , yearExtended, monthExtended, dayExtended
    , yearBasic, monthBasic, dayBasic
    , hourText, minuteBasic, secondBasic, minuteExtended, secondExtended
    , offsetHourText, offsetMinuteExtended, offsetSecondExtended, offsetMinuteBasic, offsetSecondBasic,
  ] = match;
  const year = Number(yearExtended ?? yearBasic);
  const month = Number(monthExtended ?? monthBasic);
  const day = Number(dayExtended ?? dayBasic);
  if (year < 1) return false;
  if (month < 1 || month > 12) return false;
  const monthLength =
    month === 2 && isLeapYear(year) ? 29 : DAYS_IN_MONTH[month - 1] as number;
  if (day < 1 || day > monthLength) return false;
  if (Number(hourText) > 23) return false;
  const minute = minuteBasic ?? minuteExtended;
  if (minute !== undefined && Number(minute) > 59) return false;
  const second = secondBasic ?? secondExtended;
  if (second !== undefined && Number(second) > 59) return false;
  if (offsetHourText === undefined) return true; // "Z" -- UTC
  const offsetHours = Number(offsetHourText);
  const offsetMinutes = Number(offsetMinuteExtended ?? offsetMinuteBasic ?? "0");
  const offsetSeconds = Number(offsetSecondExtended ?? offsetSecondBasic ?? "0");
  // Strictly below 24 hours after normalization (Python utcoffset bound).
  return offsetHours * 3600 + offsetMinutes * 60 + offsetSeconds < 86400;
}

function requireVersionHistory(
  value: unknown,
  source: ProjectPlanSourceIdentity,
): ProjectPlanVersionHistory {
  if (!isPlainObject(value)) fail();
  if (value.state === VERSION_HISTORY_STATE_UNAVAILABLE) {
    if (!hasExactKeys(value, HISTORY_UNAVAILABLE_KEYS)) fail();
    const reason = value.reason;
    if (
      reason !== VERSION_HISTORY_REASON_NOT_SUPPLIED_BY_OWNER &&
      reason !== VERSION_HISTORY_REASON_SOURCE_UNAVAILABLE
    ) {
      fail();
    }
    return { state: VERSION_HISTORY_STATE_UNAVAILABLE, reason } as ProjectPlanVersionHistory;
  }
  if (value.state !== "AVAILABLE") fail();
  if (!hasExactKeys(value, HISTORY_AVAILABLE_KEYS)) fail();
  if (value.kind !== "GIT_RECORD_REVISIONS") fail();
  const revisions = value.revisions;
  if (!Array.isArray(revisions) || revisions.length < 1 || revisions.length > MAX_REVISIONS) fail();
  const seenCommits = new Set<string>();
  const projected: ProjectPlanGitRecordRevision[] = [];
  for (const revision of revisions) {
    if (!isPlainObject(revision) || !hasExactKeys(revision, REVISION_KEYS)) fail();
    const commit = revision.commit;
    const committedAt = revision.committed_at;
    const contentSha256 = revision.content_sha256;
    if (typeof commit !== "string" || !fullMatch(COMMIT_RE, commit)) fail();
    if (seenCommits.has(commit)) fail();
    if (typeof contentSha256 !== "string" || !fullMatch(CONTENT_SHA256_RE, contentSha256)) fail();
    if (typeof committedAt !== "string" || !isValidCommittedAt(committedAt)) fail();
    seenCommits.add(commit);
    projected.push({ commit, committed_at: committedAt, content_sha256: contentSha256 });
  }
  // The first revision pins the same bytes as the current source identity.
  if (projected[0]!!.content_sha256 !== source.content_sha256) fail();
  return { state: "AVAILABLE", kind: "GIT_RECORD_REVISIONS", revisions: projected };
}

function requirePlan(value: unknown, source: ProjectPlanSourceIdentity): ProjectPlan {
  if (!isPlainObject(value) || !hasExactKeys(value, PLAN_KEYS)) fail();
  const title = requireText(value.title, MAX_TITLE_CHARS);
  const objective = requireText(value.objective, MAX_OBJECTIVE_CHARS);
  const status = requireText(value.status, MAX_WORKSTREAM_STATUS_CHARS);
  const owner = requireText(value.owner, MAX_OWNER_CHARS);
  const nextAction = requireOptionalText(value.next_action, MAX_NEXT_ACTION_CHARS);
  const waves = requireWaves(value.waves);
  const adoption = requireAdoption(value.adoption);
  const versionHistory = requireVersionHistory(value.version_history, source);
  return {
    title,
    objective,
    status,
    owner,
    next_action: nextAction,
    waves,
    adoption,
    version_history: versionHistory,
  };
}

function unavailableBody(workRef: string, reason: ProjectPlanReasonCode): ProjectPlanReadUnavailable {
  return {
    schema: BODY_SCHEMA,
    selection: { work_ref: workRef },
    availability: AVAILABILITY_UNAVAILABLE,
    source: null,
    plan: null,
    reason_codes: [reason],
  };
}

/** Decode the already-parsed public body from the fixed authenticated transport. */
export function decodeProjectPlan(value: unknown, expected: ProjectPlanSelection): ProjectPlanRead {
  const expectedWorkRef = requireExpectedSelection(expected);
  if (!isPlainObject(value)) fail();
  let canonical: string;
  try {
    canonical = JSON.stringify({ ok: true, result: value });
    assertWellFormedStrings(value);
  } catch {
    fail();
  }
  if (UTF8_ENCODER.encode(canonical).length + 1 > MAX_RESPONSE_BYTES) fail();
  const body = value;
  if (body.schema === BODY_SCHEMA_V2) {
    if (!hasExactKeys(body, [...BODY_KEYS, "continuity"]) || body.availability !== "AVAILABLE" || !isPlainObject(body.plan)) fail();
    const { continuity: rawContinuity, ...baseFields } = body;
    const base = decodeProjectPlan({ ...baseFields, schema: BODY_SCHEMA,
      plan: { ...body.plan, adoption: { state: "UNAVAILABLE", reason: "NOT_DECLARED" } } }, expected);
    if (base.availability !== "AVAILABLE" || base.schema !== BODY_SCHEMA) fail();
    let continuity: ProjectPlanContinuityRead;
    try { continuity = decodeProjectPlanContinuity(rawContinuity, expectedWorkRef); } catch { fail(); }
    const adoption = continuity.adoption;
    const summary: ProjectPlanAdoptionSummary = adoption.state === "AVAILABLE"
      ? { state: "AVAILABLE", decision_ref: adoption.decision_ref,
          adopted_source: adoption.adoption.adopted_source,
          display_revision: adoption.adoption.display_revision,
          // This only checks wire consistency. The sealed owner compared both
          // captured bodies; source hashes never authorize an adoption here.
          matches_authored_record: adoption.adoption.adopted_source.content_sha256 === base.source.content_sha256 }
      : { state: "UNAVAILABLE", reason: adoption.reason };
    if (!deepEqual(body.plan.adoption, summary)) fail();
    const declaration = adoption.state === "AVAILABLE" ? adoption
      : "declared_decision" in adoption ? adoption.declared_decision : undefined;
    if (declaration && declaration.decision_source.commit !== base.source.commit) fail();
    if (continuity.proposals.state === "AVAILABLE") for (const item of continuity.proposals.items) {
      if (item.proposal_source.repository === CANONICAL_REPOSITORY && item.proposal_source.commit !== base.source.commit &&
          (declaration === undefined || !deepEqual(declaration.adoption.proposal_source, item.proposal_source))) fail();
    }
    return { ...base, schema: BODY_SCHEMA_V2, plan: { ...base.plan, adoption: summary }, continuity };
  }
  if (!isPlainObject(body) || !hasExactKeys(body, BODY_KEYS)) fail();
  if (body.schema !== BODY_SCHEMA) fail();
  const workRef = requireBodySelection(body.selection, expectedWorkRef);

  if (body.availability === AVAILABILITY_UNAVAILABLE) {
    const reasonCodes = body.reason_codes;
    if (!Array.isArray(reasonCodes) || reasonCodes.length !== 1) fail();
    const reason = reasonCodes[0];
    if (!isReasonCode(reason)) fail();
    if (body.source !== null || body.plan !== null) fail();
    const reconstructed = unavailableBody(workRef, reason);
    if (!deepEqual(reconstructed, body)) fail();
    return reconstructed;
  }
  if (body.availability !== AVAILABILITY_AVAILABLE) fail();
  const reasonCodes = body.reason_codes;
  if (!Array.isArray(reasonCodes) || reasonCodes.length !== 0) fail();
  const source = requireSourceIdentity(body.source, workRef);
  const plan = requirePlan(body.plan, source);
  const reconstructed: ProjectPlanReadAvailable = {
    schema: BODY_SCHEMA,
    selection: { work_ref: workRef },
    availability: AVAILABILITY_AVAILABLE,
    source,
    plan,
    reason_codes: [],
  };
  // Reproduces Python validate_body: the body must equal what the pure
  // projector would have produced for these exact fields.
  if (!deepEqual(reconstructed, body)) fail();
  return reconstructed;
}
