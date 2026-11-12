/**
 * Pure browser-input decoder for the existing Agent OS ADOPT_PLAN compiler
 * request shape (`agentos.plan_adoption_request.v1`).
 *
 * This module checks the closed request-side field
 * validation performed by the immutable Macro adoption compiler's
 * `_candidate_recipe` on the ``request`` argument, plus the pure source
 * reference contract (`validate_source_ref` and the closed macro workstream
 * record path rule) that the compiler delegates to.
 *
 * Scope (parent-owned integration excluded here):
 *
 * * ``decodePlanAdoptionRequest`` -- closed-shaped, detached decoding of one
 *   already-serialised browser input value against the exact compiler
 *   request schema.  It is an input contract only: it never compiles a
 *   recipe, never inspects a snapshot, and never asserts that any grant,
 *   snapshot, source, adoption or effect exists or happened.
 * * No I/O, network, filesystem, Git, clock, timers, randomness or
 *   environment access; no imports; deterministic; plain objects/strings
 *   only.
 * * Every rejection raises one value-free ``Error`` whose message is
 *   ``PLAN_ADOPTION_REQUEST_INVALID``; no offending input value is ever
 *   echoed.
 * * Returned values are freshly built ("detached"): mutating caller input
 *   afterwards cannot change a returned value, and mutating a returned value
 *   cannot change caller input or a second decode result.
 * * Raw string values are preserved exactly as supplied; no trimming,
 *   case folding, path separator rewriting or Unicode normalization ever
 *   feeds a returned value.
 * * No endpoint, controller, publisher, grant, lease, status enum,
 *   ``accepted`` boolean or authority field is introduced or honoured;
 *   unknown request fields are rejected.
 */

/** Detached, validated immutable source reference (exact four fields). */
export interface PlanAdoptionSourceRef {
  readonly repository: string;
  readonly path: string;
  readonly commit: string;
  readonly content_sha256: string;
}

/** Detached, validated ADOPT_PLAN compiler request (exact eight fields). */
export interface PlanAdoptionRequest {
  readonly schema: string;
  readonly request_id: string;
  readonly work_ref: string;
  readonly expected_commit: string;
  readonly expected_adoption: string | null;
  readonly proposal_source: PlanAdoptionSourceRef;
  readonly base_source: PlanAdoptionSourceRef;
  readonly candidate_sha256: string;
}

const REQUEST_SCHEMA = "agentos.plan_adoption_request.v1";
const MACRO_REPOSITORY = "mastermindx-market-intelligence/macro";
const MASTERMIND_REPOSITORY = "mastermindx-market-intelligence/Mastermind";

const WS_PREFIX = "WS:";
const DEC_PREFIX = "DEC:";
const MACRO_WORKSTREAMS_DIR = "agentos/workstreams/";
const PATH_SUFFIX = ".md";

const MAX_PATH_CHARS = 512;
const MAX_WORK_REF_KEY_CHARS = 64;
const MAX_KEY_CHARS = 128;

const REQUEST_KEYS = [
  "schema",
  "request_id",
  "work_ref",
  "expected_commit",
  "expected_adoption",
  "proposal_source",
  "base_source",
  "candidate_sha256",
];

const SOURCE_REF_KEYS = ["repository", "path", "commit", "content_sha256"];

const LOWER_HEX_40 = /^[0-9a-f]{40}$/;
const LOWER_HEX_64 = /^[0-9a-f]{64}$/;
const REQUEST_ID_RE = /^mmos-project-adopt-[0-9a-f]{40}$/;
const UPPER_KEBAB_RE = /^[A-Z0-9]+(?:-[A-Z0-9]+)*$/;

const INVALID_MESSAGE = "PLAN_ADOPTION_REQUEST_INVALID";

function invalid(): Error {
  return new Error(INVALID_MESSAGE);
}

/** Character (Unicode code point) length, matching the source helper's ``len``. */
function charLength(value: string): number {
  return Array.from(value).length;
}

/** True when the string is encodable as UTF-8: no unpaired surrogate. */
function isWellFormedUtf8(value: string): boolean {
  for (const char of value) {
    const code = char.codePointAt(0) as number;
    if (code >= 0xd800 && code <= 0xdfff) {
      return false;
    }
  }
  return true;
}

/** Accept only a real string that is encodable as UTF-8; never normalize. */
function asString(value: unknown): string {
  if (typeof value !== "string" || !isWellFormedUtf8(value)) {
    throw invalid();
  }
  return value;
}

/** JSON-style plain object: ``Object.prototype`` or ``null`` prototype only. */
function isPlainObject(value: unknown): value is Record<string, unknown> {
  if (value === null || typeof value !== "object") {
    return false;
  }
  const proto = Object.getPrototypeOf(value);
  return proto === Object.prototype || proto === null;
}

function hasExactKeys(value: Record<string, unknown>, expected: string[]): boolean {
  if (Object.getOwnPropertySymbols(value).length !== 0) {
    return false;
  }
  const names = Object.getOwnPropertyNames(value);
  if (names.length !== expected.length) {
    return false;
  }
  const present = new Set(names);
  return expected.every((key) => present.has(key));
}

/** ``WS:`` + UPPER-KEBAB, key length 2..64 (compiler request contract). */
function validateWorkRef(value: unknown): string {
  const workRef = asString(value);
  if (!workRef.startsWith(WS_PREFIX)) {
    throw invalid();
  }
  const key = workRef.slice(WS_PREFIX.length);
  if (!UPPER_KEBAB_RE.test(key) || charLength(key) < 2 || charLength(key) > MAX_WORK_REF_KEY_CHARS) {
    throw invalid();
  }
  return workRef;
}

/** ``DEC:`` + UPPER-KEBAB, key length 2..128 (canonical DEC ref). */
function validateDecRef(value: unknown): string {
  const decRef = asString(value);
  if (!decRef.startsWith(DEC_PREFIX)) {
    throw invalid();
  }
  const key = decRef.slice(DEC_PREFIX.length);
  if (!UPPER_KEBAB_RE.test(key) || charLength(key) < 2 || charLength(key) > MAX_KEY_CHARS) {
    throw invalid();
  }
  return decRef;
}

function validateLowerHex(value: string, pattern: RegExp): string {
  if (!pattern.test(value)) {
    throw invalid();
  }
  return value;
}

/** Exact pure-contract source path semantics; the exact string is preserved. */
function validateSourcePath(value: unknown): string {
  const path = asString(value);
  if (path.length === 0 || charLength(path) > MAX_PATH_CHARS) {
    throw invalid();
  }
  if (path.startsWith("/")) {
    throw invalid();
  }
  if (path.includes("\u0000") || path.includes("\n") || path.includes("\r")) {
    throw invalid();
  }
  if (path.includes("\\")) {
    throw invalid();
  }
  if (!path.endsWith(PATH_SUFFIX)) {
    throw invalid();
  }
  for (const part of path.split("/")) {
    if (part === "" || part === "." || part === "..") {
      throw invalid();
    }
  }
  return path;
}

/**
 * Closed macro workstream record path rule: a macro repository reference
 * whose path lies inside ``agentos/workstreams/`` (case-insensitive prefix)
 * must equal ``agentos/workstreams/WS-<KEY>.md`` for the selected work ref.
 * Other repositories carry no macro workstream ownership here.
 */
function checkMacroWorkstreamPath(
  repository: string,
  path: string,
  workRefKey: string,
): void {
  if (repository !== MACRO_REPOSITORY) {
    return;
  }
  if (!path.toLowerCase().startsWith(MACRO_WORKSTREAMS_DIR)) {
    return;
  }
  if (path !== MACRO_WORKSTREAMS_DIR + "WS-" + workRefKey + PATH_SUFFIX) {
    throw invalid();
  }
}

/**
 * Exact four-field source reference; ``allowedRepositories`` carries the
 * per-role repository closure (proposal: macro only; base: macro or
 * Mastermind).  Shape only -- no qualification, availability or authority.
 */
function validateSourceRef(
  value: unknown,
  workRefKey: string,
  allowedRepositories: readonly string[],
): PlanAdoptionSourceRef {
  if (!isPlainObject(value) || !hasExactKeys(value, SOURCE_REF_KEYS)) {
    throw invalid();
  }
  const repository = asString(value["repository"]);
  if (!allowedRepositories.includes(repository)) {
    throw invalid();
  }
  const path = validateSourcePath(value["path"]);
  const commit = validateLowerHex(asString(value["commit"]), LOWER_HEX_40);
  const contentSha256 = validateLowerHex(asString(value["content_sha256"]), LOWER_HEX_64);
  checkMacroWorkstreamPath(repository, path, workRefKey);
  return { repository: repository, path: path, commit: commit, content_sha256: contentSha256 };
}

/**
 * Decode one browser-supplied ADOPT_PLAN compiler request value.
 *
 * ``expectedWorkRef`` is the selected target work ref of the enclosing
 * operation; it must itself be a strict work ref and the decoded request
 * ``work_ref`` must equal it exactly.  The result is detached recorded-shape
 * data only: it never asserts availability, qualification, grants or that
 * any adoption or effect happened.
 */
export function decodePlanAdoptionRequest(
  value: unknown,
  expectedWorkRef: string,
): PlanAdoptionRequest {
  const workRef = validateWorkRef(expectedWorkRef);
  const workRefKey = workRef.slice(WS_PREFIX.length);
  try {
    if (!isPlainObject(value) || !hasExactKeys(value, REQUEST_KEYS)) {
      throw invalid();
    }
    const schema = asString(value["schema"]);
    if (schema !== REQUEST_SCHEMA) {
      throw invalid();
    }
    const requestId = asString(value["request_id"]);
    if (!REQUEST_ID_RE.test(requestId)) {
      throw invalid();
    }
    const requestWorkRef = validateWorkRef(value["work_ref"]);
    if (requestWorkRef !== workRef) {
      throw invalid();
    }
    const expectedCommit = validateLowerHex(asString(value["expected_commit"]), LOWER_HEX_40);
    const candidateSha256 = validateLowerHex(asString(value["candidate_sha256"]), LOWER_HEX_64);
    const expectedAdoptionRaw = value["expected_adoption"];
    const expectedAdoption =
      expectedAdoptionRaw === null ? null : validateDecRef(expectedAdoptionRaw);
    const proposalSource = validateSourceRef(value["proposal_source"], workRefKey, [
      MACRO_REPOSITORY,
    ]);
    const baseSource = validateSourceRef(value["base_source"], workRefKey, [
      MACRO_REPOSITORY,
      MASTERMIND_REPOSITORY,
    ]);
    return {
      schema: schema,
      request_id: requestId,
      work_ref: requestWorkRef,
      expected_commit: expectedCommit,
      expected_adoption: expectedAdoption,
      proposal_source: proposalSource,
      base_source: baseSource,
      candidate_sha256: candidateSha256,
    };
  } catch {
    // Never return or inspect a hostile thrown object, even if its message
    // resembles our closed code. It may carry private properties/getters.
    throw invalid();
  }
}
