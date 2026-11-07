/**
 * Pure TypeScript mirror of the frozen Mastermind workspace source-operation
 * STATUS contract (`mastermind.workspace_source_operation_status.v1`).
 *
 * This is a decode-side consumer contract for the ADOPT frontend port. It is a
 * mirror of the Python producer validator; it implements no producer logic and
 * edits no Python file.
 *
 * Purity:
 *   - no network, clock, storage, DOM, auth, worker/controller or publication
 *     effect of any kind; the module imports nothing and performs no I/O.
 *   - the decoder never computes, compares or verifies a digest for meaning.
 *     A well-formed hash is a wire-grammar fact only. It never proves receipt
 *     authenticity, grant, ownership or source authenticity, and it never
 *     implies that an effect happened or did not happen.
 *   - decoding grants no authority and dispatches nothing.
 *
 * Typing rules mirrored from the Python producer ("exact builtin types"):
 *   - an object must be a plain record: `Object.getPrototypeOf` is exactly
 *     `Object.prototype` or `null`. Class instances, arrays, functions and
 *     primitives are rejected.
 *   - symbol-keyed objects are rejected.
 *   - accessor (getter/setter) own properties are rejected. Field values are
 *     read from the own property descriptor, so a hostile getter is never
 *     invoked, and no user code runs during decoding.
 *   - booleans are never accepted where an integer is required; numbers must
 *     be safe integers (`Number.isSafeInteger`), so NaN/Infinity/fractions,
 *     `Number` wrappers and bigint are rejected.
 *   - strings must be well-formed UTF-16 (no lone surrogates) so that every
 *     accepted value has a well-defined UTF-8 encoding.
 *
 * Canonical budget: the whole accepted status serialises as sorted-key,
 * separator-compact, non-ASCII-preserving JSON whose UTF-8 byte length plus a
 * single trailing LF is at most 32768.
 *
 * Every rejection throws `new Error('SOURCE_OPERATION_STATUS_INVALID')`. No
 * untrusted value, key, reason or upstream error text is ever echoed.
 */

/** Single constant rejection message for every invalid input. */
export const SOURCE_OPERATION_STATUS_INVALID =
  "SOURCE_OPERATION_STATUS_INVALID" as const;

/** Exact schema discriminator of the status envelope. */
export const SOURCE_OPERATION_STATUS_SCHEMA =
  "mastermind.workspace_source_operation_status.v1" as const;

/**
 * Strict original operation-id prefixes, one per action. The full id is
 * `<prefix>` + 40 lowercase hex characters. Ids are never minted here.
 */
export const ORIGINAL_OPERATION_ID_PREFIXES = {
  publish_project_proposal: "mmos-project-create-",
  ADOPT_PLAN: "mmos-project-adopt-",
  ACCEPT_DIRECTION: "mmos-direction-accept-",
  add_project_file: "mmos-project-file-add-",
  set_project_communication_preference: "mmos-project-preference-set-",
} as const;

/** The five source-operation actions of the shared schema. */
export type SourceOperationAction = keyof typeof ORIGINAL_OPERATION_ID_PREFIXES;

/** Actions that carry the ADOPTION phase instead of PUBLICATION. */
export type AdoptionAction = "ADOPT_PLAN";

/** Original operation id: `<prefix><40 lowercase hex>`, action-bound. */
export type OriginalOperationId = string & {
  readonly __originalOperationId: unique symbol;
};
/** Workspace key reference, `WS:` + 2..64 uppercase kebab key. */
export type WorkRef = string & { readonly __workRef: unique symbol };
/** Owner principal scope, 64 lowercase hex. */
export type PrincipalScope = string & {
  readonly __principalScope: unique symbol;
};
/** Generic 64 lowercase hex digest field. */
export type LowerHex64 = string & { readonly __lowerHex64: unique symbol };
/** 40 lowercase hex commit digest field. */
export type LowerHex40 = string & { readonly __lowerHex40: unique symbol };
/** Normal relative POSIX source path, at most 512 UTF-8 bytes. */
export type SourcePath = string & { readonly __sourcePath: unique symbol };
/** Safe short ASCII git branch name. */
export type GitBranchName = string & {
  readonly __gitBranchName: unique symbol;
};

export type Disposition = "accepted" | "refused" | "unknown";

/** Closed reason set of the status contract. */
export type StatusReason =
  | "ORIGINAL_OPERATION_NOT_OBSERVED"
  | "IN_PROGRESS"
  | "PHASE_ATTEMPT_UNRESOLVED"
  | "READY_FOR_ADVANCE"
  | "PRECONDITION_UNAVAILABLE"
  | "PRIVATE_INPUT_UNAVAILABLE"
  | "SOURCE_UNAVAILABLE"
  | "CONFLICT"
  | "NOT_DISPATCHED"
  | "REFUSED";

/** Phase of the observed operation. */
export type OperationPhase = "PUBLICATION" | "CANDIDATE" | "ADOPTION";

export type ReceiptKind =
  "INTENT" | "PHASE_ATTEMPTED" | "PROPOSAL_OBSERVED" | "SOURCE_OBSERVED";

export interface StatusSelection {
  readonly action: SourceOperationAction;
  readonly request_id: OriginalOperationId;
  readonly work_ref: WorkRef;
}

export interface OwnerContext {
  readonly principal_scope: PrincipalScope;
}

export interface SourceRef {
  readonly repository: "macro";
  readonly commit: LowerHex40;
  readonly path: SourcePath;
  readonly content_sha256: LowerHex64;
}

export interface PullRequestRef {
  readonly number: number;
  readonly url: string;
  readonly head_commit: LowerHex40;
  readonly head_branch: GitBranchName;
}

export interface StatusReceipt {
  readonly kind: ReceiptKind;
  readonly event_id: number;
  readonly recorded_at_ms: number;
  readonly receipt_sha256: LowerHex64;
  readonly sources: readonly SourceRef[];
  readonly proposal: PullRequestRef | null;
}

export interface StatusAdvance {
  readonly phase_receipt_digest: LowerHex64;
}

export interface SourceOperationStatus {
  readonly schema: typeof SOURCE_OPERATION_STATUS_SCHEMA;
  readonly selection: StatusSelection;
  readonly owner_context: OwnerContext;
  readonly disposition: Disposition;
  readonly reason: StatusReason | null;
  readonly request_sha256: LowerHex64 | null;
  readonly recipe_fingerprint_sha256: LowerHex64 | null;
  readonly phase: OperationPhase | null;
  readonly receipt: StatusReceipt | null;
  readonly advance: StatusAdvance | null;
}

/* ------------------------------------------------------------------ *
 * rejection + assertion helpers
 * ------------------------------------------------------------------ */

function fail(): never {
  throw new Error(SOURCE_OPERATION_STATUS_INVALID);
}

function req(condition: unknown): void {
  if (condition !== true) fail();
}

/* ------------------------------------------------------------------ *
 * string / scalar grammar
 * ------------------------------------------------------------------ */

const LOWER_HEX_64 = /^[0-9a-f]{64}$/;
const LOWER_HEX_40 = /^[0-9a-f]{40}$/;
const WORK_REF_KEY = /^[A-Z0-9]+(?:-[A-Z0-9]+)*$/;
const WS_PREFIX = "WS:";

/** True when the string has no unpaired surrogate, i.e. encodes to UTF-8. */
function wellFormed(s: string): boolean {
  for (let i = 0; i < s.length; i++) {
    const c = s.charCodeAt(i);
    if (c >= 0xd800 && c <= 0xdbff) {
      if (i + 1 >= s.length) return false;
      const d = s.charCodeAt(i + 1);
      if (d < 0xdc00 || d > 0xdfff) return false;
      i++;
    } else if (c >= 0xdc00 && c <= 0xdfff) {
      return false;
    }
  }
  return true;
}

/** UTF-8 byte length of a well-formed string, without allocating. */
function utf8ByteLength(s: string): number {
  let n = 0;
  for (let i = 0; i < s.length; i++) {
    const c = s.charCodeAt(i);
    if (c >= 0xd800 && c <= 0xdbff && i + 1 < s.length) {
      const d = s.charCodeAt(i + 1);
      if (d >= 0xdc00 && d <= 0xdfff) {
        n += 4;
        i++;
        continue;
      }
    }
    if (c < 0x80) n += 1;
    else if (c < 0x800) n += 2;
    else if (c < 0x10000) n += 3;
    else n += 4;
  }
  return n;
}

function reqString(value: unknown): string {
  req(typeof value === "string");
  const s = value as string;
  req(wellFormed(s));
  return s;
}

function reqLowerHex64(value: unknown): LowerHex64 {
  const s = reqString(value);
  req(LOWER_HEX_64.test(s));
  return s as LowerHex64;
}

function reqLowerHex40(value: unknown): LowerHex40 {
  const s = reqString(value);
  req(LOWER_HEX_40.test(s));
  return s as LowerHex40;
}

/**
 * Safe integer scalar. Booleans are rejected explicitly: in this position a
 * boolean is a type confusion, not a truthy integer.
 */
function reqSafeInt(value: unknown, min: number, max: number): number {
  if (typeof value === "boolean") fail();
  req(typeof value === "number");
  req(Number.isSafeInteger(value as number));
  const n = value as number;
  req(n >= min && n <= max);
  return n;
}

function reqAction(value: unknown): SourceOperationAction {
  const s = reqString(value);
  req(Object.prototype.hasOwnProperty.call(ORIGINAL_OPERATION_ID_PREFIXES, s));
  return s as SourceOperationAction;
}

function reqWorkRef(value: unknown): WorkRef {
  const s = reqString(value);
  req(s.startsWith(WS_PREFIX));
  const key = s.slice(WS_PREFIX.length);
  req(key.length >= 2 && key.length <= 64);
  req(WORK_REF_KEY.test(key));
  return s as WorkRef;
}

function reqRequestId(
  value: unknown,
  action: SourceOperationAction,
): OriginalOperationId {
  const s = reqString(value);
  req(s.startsWith(ORIGINAL_OPERATION_ID_PREFIXES[action]));
  req(
    LOWER_HEX_40.test(s.slice(ORIGINAL_OPERATION_ID_PREFIXES[action].length)),
  );
  return s as OriginalOperationId;
}

function reqPrincipalScope(value: unknown): PrincipalScope {
  const s = reqString(value);
  req(LOWER_HEX_64.test(s));
  return s as PrincipalScope;
}

/**
 * Normal relative POSIX path: no empty, "." or ".." segment, no backslash, no
 * control character, not absolute, at most 512 UTF-8 bytes.
 */
const SOURCE_PATH_MAX_UTF8_BYTES = 512;
function reqSourcePath(value: unknown): SourcePath {
  const s = reqString(value);
  req(s.length > 0);
  req(s.charCodeAt(0) !== 0x2f);
  req(utf8ByteLength(s) <= SOURCE_PATH_MAX_UTF8_BYTES);
  for (let i = 0; i < s.length; i++) {
    const c = s.charCodeAt(i);
    req(c >= 0x20 && (c < 0x7f || c > 0x9f));
    req(c !== 0x5c);
  }
  const segments = s.split("/");
  for (const segment of segments) {
    req(segment.length > 0 && segment !== "." && segment !== "..");
  }
  return s as SourcePath;
}

/**
 * Safe short git branch name: printable ASCII only (no whitespace, no control
 * character, no non-ASCII), at most 200 characters, and free of git refname
 * injection (leading dash, leading/trailing slash, "//", "..", "@{", trailing
 * ".", ".lock" component, backslash and git's forbidden punctuation).
 */
const GIT_BRANCH_MAX_CHARS = 200;
const GIT_BRANCH_FORBIDDEN = "~^:?*[]\\";
function reqBranchName(value: unknown): GitBranchName {
  const s = reqString(value);
  req(s.length > 0 && s.length <= GIT_BRANCH_MAX_CHARS);
  for (let i = 0; i < s.length; i++) {
    const c = s.charCodeAt(i);
    req(c >= 0x21 && c <= 0x7e);
    req(GIT_BRANCH_FORBIDDEN.indexOf(s.charAt(i)) === -1);
  }
  req(s.charCodeAt(0) !== 0x2d);
  req(s.charCodeAt(0) !== 0x2f);
  req(s.charCodeAt(s.length - 1) !== 0x2f);
  req(s.indexOf("//") === -1);
  req(s.indexOf("..") === -1);
  req(s.indexOf("@{") === -1);
  req(s.charCodeAt(s.length - 1) !== 0x2e);
  const components = s.split("/");
  for (const component of components) {
    req(component.length > 0);
    req(component.charCodeAt(0) !== 0x2e);
    req(!component.endsWith(".lock"));
  }
  return s as GitBranchName;
}

const REPOSITORY_NAME = "macro";
const PR_URL_PREFIX =
  "https://github.com/mastermindx-market-intelligence/macro/pull/";

function reqPullRequest(value: unknown): PullRequestRef {
  reqPlainObject(value);
  reqExactKeys(value, PULL_REQUEST_KEYS);
  const number = reqSafeInt(field(value, "number"), 1, Number.MAX_SAFE_INTEGER);
  const url = reqString(field(value, "url"));
  req(url === PR_URL_PREFIX + String(number));
  return {
    number,
    url,
    head_commit: reqLowerHex40(field(value, "head_commit")),
    head_branch: reqBranchName(field(value, "head_branch")),
  };
}

function reqSourceRef(value: unknown): SourceRef {
  reqPlainObject(value);
  reqExactKeys(value, SOURCE_REF_KEYS);
  req(reqString(field(value, "repository")) === REPOSITORY_NAME);
  return {
    repository: REPOSITORY_NAME,
    commit: reqLowerHex40(field(value, "commit")),
    path: reqSourcePath(field(value, "path")),
    content_sha256: reqLowerHex64(field(value, "content_sha256")),
  };
}

const RECEIPT_KINDS = [
  "INTENT",
  "PHASE_ATTEMPTED",
  "PROPOSAL_OBSERVED",
  "SOURCE_OBSERVED",
] as const;
const RECEIPT_MAX_SOURCES = 3;
const EVENT_ID_MAX = 9007199254740991; // 2^53 - 1

function reqReceipt(value: unknown): StatusReceipt {
  reqPlainObject(value);
  reqExactKeys(value, RECEIPT_KEYS);
  const kind = reqString(field(value, "kind"));
  req(hasValue(RECEIPT_KINDS, kind));
  const event_id = reqSafeInt(field(value, "event_id"), 1, EVENT_ID_MAX);
  const recorded_at_ms = reqSafeInt(
    field(value, "recorded_at_ms"),
    0,
    EVENT_ID_MAX,
  );
  const receipt_sha256 = reqLowerHex64(field(value, "receipt_sha256"));
  const rawSources = field(value, "sources");
  reqArray(rawSources);
  const sourceCount = reqSafeInt(
    field(rawSources, "length"),
    0,
    RECEIPT_MAX_SOURCES,
  );
  req(Object.getOwnPropertyNames(rawSources).length === sourceCount + 1);
  const sources: SourceRef[] = [];
  // Indexed walk, never `for..of`: a null-prototype array carries no iterator,
  // and relying on one would raise a foreign TypeError instead of the
  // contract's single constant rejection.
  for (let i = 0; i < sourceCount; i += 1) {
    sources.push(reqSourceRef(field(rawSources, String(i))));
  }
  const rawProposal = field(value, "proposal");
  const proposal = rawProposal === null ? null : reqPullRequest(rawProposal);
  return {
    kind: kind as ReceiptKind,
    event_id,
    recorded_at_ms,
    receipt_sha256,
    sources,
    proposal,
  };
}

/* ------------------------------------------------------------------ *
 * plain-object access (never invokes user code)
 * ------------------------------------------------------------------ */

const STATUS_KEYS = [
  "advance",
  "disposition",
  "owner_context",
  "phase",
  "reason",
  "receipt",
  "recipe_fingerprint_sha256",
  "request_sha256",
  "schema",
  "selection",
] as const;

const SELECTION_KEYS = ["action", "request_id", "work_ref"] as const;
const OWNER_CONTEXT_KEYS = ["principal_scope"] as const;
const RECEIPT_KEYS = [
  "event_id",
  "kind",
  "proposal",
  "receipt_sha256",
  "recorded_at_ms",
  "sources",
] as const;
const SOURCE_REF_KEYS = [
  "commit",
  "content_sha256",
  "path",
  "repository",
] as const;
const PULL_REQUEST_KEYS = [
  "head_branch",
  "head_commit",
  "number",
  "url",
] as const;
const ADVANCE_KEYS = ["phase_receipt_digest"] as const;

const DISPOSITIONS = ["accepted", "refused", "unknown"] as const;
const PHASES = ["PUBLICATION", "CANDIDATE", "ADOPTION"] as const;

/**
 * Rejects anything that is not a plain record: prototypes other than
 * `Object.prototype`/`null` (class instances), arrays, primitives, functions
 * and symbol-keyed objects. No property is read here, so no getter runs.
 */
function reqPlainObject(
  value: unknown,
): asserts value is Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value))
    fail();
  const proto = Object.getPrototypeOf(value as object);
  if (proto !== Object.prototype && proto !== null) fail();
  if (Object.getOwnPropertySymbols(value as object).length !== 0) fail();
}

/**
 * Rejects anything that is not a builtin array, mirroring the producer's exact
 * `list` check: array subclasses and arrays whose prototype was replaced are
 * rejected. Reads no element and no property.
 */
function reqArray(value: unknown): asserts value is readonly unknown[] {
  if (!Array.isArray(value)) fail();
  const proto = Object.getPrototypeOf(value as object);
  if (proto !== Array.prototype && proto !== null) fail();
  if (Object.getOwnPropertySymbols(value as object).length !== 0) fail();
}

/** Exact closed key set: no missing key, no extra key, hidden or not. */
function reqExactKeys(
  value: Record<string, unknown>,
  keys: readonly string[],
): void {
  const own = Object.getOwnPropertyNames(value);
  if (own.length !== keys.length) fail();
  for (const key of keys) {
    if (!Object.prototype.hasOwnProperty.call(value, key)) fail();
  }
}

/**
 * Own data-property value only. Accessor descriptors are rejected instead of
 * being invoked, so a throwing or counting getter never executes.
 */
function field(value: object, key: string): unknown {
  const descriptor = Object.getOwnPropertyDescriptor(value, key);
  if (descriptor === undefined) fail();
  if (descriptor.get !== undefined || descriptor.set !== undefined) fail();
  return descriptor.value;
}

function hasValue<T extends string>(
  closed: readonly T[],
  candidate: string,
): boolean {
  return hasOwnIndex(closed, candidate);
}

function hasOwnIndex(closed: readonly string[], candidate: string): boolean {
  for (let i = 0; i < closed.length; i++) {
    if (closed[i] === candidate) return true;
  }
  return false;
}

/* ------------------------------------------------------------------ *
 * closed reason <-> disposition pairing
 * ------------------------------------------------------------------ */

/**
 * Closed default mapping. CONFLICT and NOT_DISPATCHED also admit UNKNOWN:
 * a later phase refusal must retain an already-partial original operation.
 * `reason === null` admits only final accepted source observation.
 */
const REASON_DISPOSITION: { readonly [R in StatusReason]: Disposition } = {
  ORIGINAL_OPERATION_NOT_OBSERVED: "unknown",
  IN_PROGRESS: "unknown",
  PHASE_ATTEMPT_UNRESOLVED: "unknown",
  READY_FOR_ADVANCE: "unknown",
  PRECONDITION_UNAVAILABLE: "unknown",
  PRIVATE_INPUT_UNAVAILABLE: "unknown",
  SOURCE_UNAVAILABLE: "unknown",
  CONFLICT: "refused",
  NOT_DISPATCHED: "refused",
  REFUSED: "refused",
};

/* ------------------------------------------------------------------ *
 * canonical JSON + whole-status budget
 * ------------------------------------------------------------------ */

const STATUS_BUDGET_UTF8_BYTES_WITH_LF = 32768;

function canonicalJson(value: unknown): string {
  if (value === null) return "null";
  const type = typeof value;
  if (type === "number") return String(value as number);
  if (type === "string") return JSON.stringify(value as string);
  if (type === "boolean") fail();
  if (Array.isArray(value)) {
    let out = "";
    for (let i = 0; i < value.length; i++) {
      if (i > 0) out += ",";
      out += canonicalJson((value as readonly unknown[])[i]);
    }
    return "[" + out + "]";
  }
  if (type === "object") {
    const record = value as Record<string, unknown>;
    const keys = Object.keys(record).sort(compareCodeUnits);
    let out = "{";
    for (let i = 0; i < keys.length; i++) {
      if (i > 0) out += ",";
      out += JSON.stringify(keys[i]) + ":" + canonicalJson(record[keys[i]]);
    }
    return out + "}";
  }
  fail();
}

function compareCodeUnits(a: string, b: string): number {
  if (a < b) return -1;
  if (a > b) return 1;
  return 0;
}

/* ------------------------------------------------------------------ *
 * public API
 * ------------------------------------------------------------------ */

/**
 * Decodes and fully validates a source-operation STATUS value of unknown
 * provenance into a deeply detached, closed-shape result.
 *
 * This is a shape/grammar decoder only. It grants no authority, produces no
 * owner receipt, and treats every hash as an opaque wire token: a matching or
 * well-formed digest never implies receipt, grant, source authenticity or that
 * any effect occurred.
 *
 * Throws `new Error('SOURCE_OPERATION_STATUS_INVALID')` on any invalid input,
 * without echoing the input.
 */
function decodeStatus(value: unknown): SourceOperationStatus {
  reqPlainObject(value);
  reqExactKeys(value, STATUS_KEYS);

  const schema = reqString(field(value, "schema"));
  req(schema === SOURCE_OPERATION_STATUS_SCHEMA);

  const rawSelection = field(value, "selection");
  reqPlainObject(rawSelection);
  reqExactKeys(rawSelection, SELECTION_KEYS);
  const action = reqAction(field(rawSelection, "action"));
  const selection: StatusSelection = {
    action,
    request_id: reqRequestId(field(rawSelection, "request_id"), action),
    work_ref: reqWorkRef(field(rawSelection, "work_ref")),
  };

  const rawOwnerContext = field(value, "owner_context");
  reqPlainObject(rawOwnerContext);
  reqExactKeys(rawOwnerContext, OWNER_CONTEXT_KEYS);
  const owner_context: OwnerContext = {
    principal_scope: reqPrincipalScope(
      field(rawOwnerContext, "principal_scope"),
    ),
  };

  const rawDisposition = reqString(field(value, "disposition"));
  req(hasValue(DISPOSITIONS, rawDisposition));
  const disposition = rawDisposition as Disposition;

  const rawReason = field(value, "reason");
  const reason =
    rawReason === null ? null : (reqClosedReason(rawReason) as StatusReason);

  const rawRequestSha = field(value, "request_sha256");
  const request_sha256 =
    rawRequestSha === null ? null : reqLowerHex64(rawRequestSha);
  const rawRecipeFingerprint = field(value, "recipe_fingerprint_sha256");
  const recipe_fingerprint_sha256 =
    rawRecipeFingerprint === null ? null : reqLowerHex64(rawRecipeFingerprint);
  if (request_sha256 !== null && recipe_fingerprint_sha256 !== null)
    req(request_sha256 !== recipe_fingerprint_sha256);

  const rawPhase = field(value, "phase");
  let phase: OperationPhase | null = null;
  if (rawPhase !== null) {
    const phaseName = reqString(rawPhase);
    req(hasValue(PHASES, phaseName));
    phase = phaseName as OperationPhase;
  }

  const rawReceipt = field(value, "receipt");
  const receipt = rawReceipt === null ? null : reqReceipt(rawReceipt);

  const rawAdvance = field(value, "advance");
  let advance: StatusAdvance | null = null;
  if (rawAdvance !== null) {
    reqPlainObject(rawAdvance);
    reqExactKeys(rawAdvance, ADVANCE_KEYS);
    advance = {
      phase_receipt_digest: reqLowerHex64(
        field(rawAdvance, "phase_receipt_digest"),
      ),
    };
  }

  /* ---- semantic pairing -------------------------------------------- */

  // Phase conflict/non-dispatch can leave the overall operation UNKNOWN.
  // Null reason admits only the accepted final state.
  if (reason === null) req(disposition === "accepted");
  else if (reason === "CONFLICT" || reason === "NOT_DISPATCHED")
    req(disposition === "unknown" || disposition === "refused");
  else req(REASON_DISPOSITION[reason] === disposition);

  const isAdoption = action === "ADOPT_PLAN";

  if (receipt === null) {
    // No receipt: no phase and no fingerprint of either kind. A missing
    // receipt is never read as proof that no effect happened.
    req(
      phase === null &&
        request_sha256 === null &&
        recipe_fingerprint_sha256 === null,
    );
    if (reason === "ORIGINAL_OPERATION_NOT_OBSERVED") req(advance === null);
  } else {
    // Any receipt requires both hashes and a non-null phase.
    req(
      request_sha256 !== null &&
        recipe_fingerprint_sha256 !== null &&
        phase !== null,
    );
    if (receipt.kind === "INTENT" || receipt.kind === "PHASE_ATTEMPTED") {
      req(receipt.sources.length === 0 && receipt.proposal === null);
      req(disposition === "unknown");
    } else if (receipt.kind === "PROPOSAL_OBSERVED") {
      req(receipt.proposal !== null && receipt.sources.length === 0);
      req(disposition === "unknown");
    } else {
      req(receipt.sources.length >= 1 && receipt.proposal === null);
    }
    // Phase/action pairing.
    if (isAdoption) req(phase === "CANDIDATE" || phase === "ADOPTION");
    else req(phase === "PUBLICATION");
  }

  if (disposition === "accepted") {
    // Accepted only as the final source observation: PUBLICATION for
    // non-ADOPT actions, ADOPTION for ADOPT_PLAN.
    req(receipt !== null && receipt.kind === "SOURCE_OBSERVED");
    req(reason === null && advance === null);
    req(isAdoption ? phase === "ADOPTION" : phase === "PUBLICATION");
  }

  if (disposition === "refused") {
    // Refusal only from the closed refusal trio, with no receipt, no hashes,
    // no phase and no advance. A partially published operation is never
    // reported as refused here.
    req(receipt === null);
    req(
      reason === "NOT_DISPATCHED" ||
        reason === "REFUSED" ||
        reason === "CONFLICT",
    );
    req(
      phase === null &&
        request_sha256 === null &&
        recipe_fingerprint_sha256 === null,
    );
    req(advance === null);
  }

  if (reason === "READY_FOR_ADVANCE") {
    // The advance witness exists only here, and only with the exact receipt
    // digest, so the digest is never replayed onto another state.
    req(
      disposition === "unknown" &&
        isAdoption &&
        receipt !== null &&
        receipt.kind === "SOURCE_OBSERVED" &&
        phase === "CANDIDATE" &&
        advance !== null &&
        advance.phase_receipt_digest === receipt.receipt_sha256,
    );
  } else {
    req(advance === null);
  }

  if (reason === "ORIGINAL_OPERATION_NOT_OBSERVED") {
    req(disposition === "unknown" && receipt === null && advance === null);
  }

  const status: SourceOperationStatus = {
    schema: SOURCE_OPERATION_STATUS_SCHEMA,
    selection,
    owner_context,
    disposition,
    reason,
    request_sha256,
    recipe_fingerprint_sha256,
    phase,
    receipt,
    advance,
  };

  // Whole-status canonical budget: sorted-key compact JSON whose UTF-8 length
  // plus one trailing LF stays inside the contract bound.
  const canonical = canonicalJson(status);
  req(utf8ByteLength(canonical) + 1 <= STATUS_BUDGET_UTF8_BYTES_WITH_LF);

  return status;
}

/** All input/reflection failures stay value-free, including hostile proxies. */
export function decodeSourceOperationStatus(
  value: unknown,
): SourceOperationStatus {
  try {
    return decodeStatus(value);
  } catch {
    return fail();
  }
}

function reqClosedReason(value: unknown): string {
  const s = reqString(value);
  req(Object.prototype.hasOwnProperty.call(REASON_DISPOSITION, s));
  return s;
}

/**
 * Builds the exact no-evidence unknown body:
 * `unknown` / `ORIGINAL_OPERATION_NOT_OBSERVED` with a null receipt, null
 * hashes, null phase and null advance.
 *
 * The action, request id, work ref and principal scope are validated by the
 * same grammar as any other status, so an unusable selection is rejected
 * instead of being wrapped in a plausible-looking body. The returned body is
 * deeply detached. This reports that nothing was observed; it never asserts
 * that no effect occurred and it authorises nothing.
 */
export function unavailableSourceOperationStatus(
  action: SourceOperationAction,
  requestId: string,
  workRef: string,
  principalScope: string,
): SourceOperationStatus {
  return decodeSourceOperationStatus({
    schema: SOURCE_OPERATION_STATUS_SCHEMA,
    selection: { action, request_id: requestId, work_ref: workRef },
    owner_context: { principal_scope: principalScope },
    disposition: "unknown",
    reason: "ORIGINAL_OPERATION_NOT_OBSERVED",
    request_sha256: null,
    recipe_fingerprint_sha256: null,
    phase: null,
    receipt: null,
    advance: null,
  });
}

/**
 * Canonical sorted-key compact JSON for an already decoded status. Pure and
 * deterministic; the frontend uses this to forward the status without
 * re-shaping it.
 */
export function canonicalSourceOperationStatusJson(
  status: SourceOperationStatus,
): string {
  return canonicalJson(status);
}
