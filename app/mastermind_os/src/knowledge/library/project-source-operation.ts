/**
 * Closed pure decoder for fixed project file/preference source operations.
 *
 * Decodes two wire bodies produced by the existing verified Workspace owner:
 * the inspection context (`mastermind.workspace_source_operation_context.v1`)
 * and the source-operation status (`mastermind.workspace_source_operation_status.v1`)
 * for exactly the two closed frontend actions `add_project_file` and
 * `set_project_communication_preference`. The validation semantics mirror the
 * actual common contract module `common/workspace_source_operation_contract.py`
 * (immutable fec4e87f) for those two non-ADOPT actions; `ADOPT_PLAN`,
 * `publish_project_proposal` and `ACCEPT_DIRECTION` are out of scope here.
 *
 * This module is a pure bounded decoder. It performs no transport, storage,
 * grant, permission, lookup, retry or publication work and never mints an
 * identity, key, digest, timestamp or receipt. A decoded context is an
 * inspection fact only — never a current-source, CAS or write-ready receipt.
 * A decoded status is an owner-reported lookup fact: absence of a receipt is
 * never read as proof that no effect happened and no digest is treated as
 * authenticity. The same-controller owner rechecks the actual current
 * principal and grant at submission/status time.
 */

import {discoveryReplacementRef,validDiscoveryReference} from './project-discovery-correction';
export const PROJECT_SOURCE_OPERATION_INVALID = 'project_source_operation_invalid';

export const PROJECT_SOURCE_CONTEXT_SCHEMA =
  'mastermind.workspace_source_operation_context.v1';
export const PROJECT_SOURCE_STATUS_SCHEMA =
  'mastermind.workspace_source_operation_status.v1';

export const PROJECT_SOURCE_ACTION_ADD_FILE = 'add_project_file';
export const PROJECT_SOURCE_ACTION_SET_PREFERENCE =
  'set_project_communication_preference';
export const PROJECT_SOURCE_ACTION_CORRECT_DISCOVERY = 'correct_project_discovery';

/** The two closed frontend source-write actions decoded by this module. */
export const PROJECT_SOURCE_ACTIONS = [
  PROJECT_SOURCE_ACTION_ADD_FILE,
  PROJECT_SOURCE_ACTION_SET_PREFERENCE,
  PROJECT_SOURCE_ACTION_CORRECT_DISCOVERY,
] as const;

export type ProjectSourceAction = (typeof PROJECT_SOURCE_ACTIONS)[number];

export type ProjectSourceDisposition = 'accepted' | 'refused' | 'unknown';

export type ProjectSourcePhase = 'PUBLICATION' | 'CANDIDATE' | 'ADOPTION';

export type ProjectSourceReceiptKind =
  | 'INTENT'
  | 'PHASE_ATTEMPTED'
  | 'PROPOSAL_OBSERVED'
  | 'SOURCE_OBSERVED';

/** Every reason value of the actual common contract. */
export type ProjectSourceStatusReason =
  | 'ORIGINAL_OPERATION_NOT_OBSERVED'
  | 'IN_PROGRESS'
  | 'PHASE_ATTEMPT_UNRESOLVED'
  | 'READY_FOR_ADVANCE'
  | 'PRECONDITION_UNAVAILABLE'
  | 'PRIVATE_INPUT_UNAVAILABLE'
  | 'SOURCE_UNAVAILABLE'
  | 'CONFLICT'
  | 'NOT_DISPATCHED'
  | 'REFUSED';

export interface ProjectSourceContextSelection {
  readonly action: ProjectSourceAction;
  readonly work_ref: string;
}

export interface ProjectSourceOwnerContext {
  readonly principal_scope: string;
}

/**
 * Exact inspection context supplied by the current signed Workspace owner.
 * This is an inspection context only: it never certifies a current source
 * revision and never makes a write ready.
 */
export interface ProjectSourceContext {
  readonly schema: string;
  readonly selection: ProjectSourceContextSelection;
  readonly owner_context: ProjectSourceOwnerContext;
  readonly can_inspect: true;
}

export interface ProjectSourceOperationSelection {
  readonly action: ProjectSourceAction;
  readonly request_id: string;
  readonly work_ref: string;
}

export interface ProjectSourceStatusSource {
  readonly repository: string;
  readonly commit: string;
  readonly path: string;
  readonly content_sha256: string;
}

export interface ProjectSourceStatusProposal {
  readonly number: number;
  readonly url: string;
  readonly head_commit: string;
  readonly head_branch: string;
}

export interface ProjectSourceStatusReceipt {
  readonly kind: ProjectSourceReceiptKind;
  readonly event_id: number;
  readonly recorded_at_ms: number;
  readonly receipt_sha256: string;
  readonly sources: readonly ProjectSourceStatusSource[];
  readonly proposal: ProjectSourceStatusProposal | null;
}

export interface ProjectSourcePhaseAdvanceWitness {
  readonly phase_receipt_digest: string;
}

/**
 * Exact source-operation status body. The full owner provenance is retained:
 * selection identity, owner scope, reason, public/trusted digests, phase,
 * receipt sources and proposal, and the adopt-plan advance witness when the
 * actual common contract carries one.
 */
export interface ProjectSourceStatus {
  readonly schema: string;
  readonly selection: ProjectSourceOperationSelection;
  readonly owner_context: ProjectSourceOwnerContext;
  readonly disposition: ProjectSourceDisposition;
  readonly reason: ProjectSourceStatusReason | null;
  readonly request_sha256: string | null;
  readonly recipe_fingerprint_sha256: string | null;
  readonly phase: ProjectSourcePhase | null;
  readonly receipt: ProjectSourceStatusReceipt | null;
  readonly advance: ProjectSourcePhaseAdvanceWitness | null;
}

export interface ProjectSourceContextExpectation {
  readonly action: ProjectSourceAction;
  readonly workRef: string;
}

export interface ProjectSourceStatusExpectation {
  readonly action: ProjectSourceAction;
  readonly workRef: string;
  readonly requestId: string;
  readonly requestSha256: string;
  readonly principalScope: string;
}

const REPOSITORY_MACRO = 'macro';
const PR_URL_PREFIX =
  'https://github.com/mastermindx-market-intelligence/macro/pull/';

const MAX_SAFE_INTEGER_CONTRACT = 9007199254740991; // 2**53 - 1
const MAX_SOURCES = 3;
const MAX_PATH_BYTES = 512;
const MAX_BRANCH_CHARS = 200;
const MAX_STATUS_BYTES = 32768; // canonical JSON bytes plus one trailing LF
const WORK_REF_KEY_MIN = 2;
const WORK_REF_KEY_MAX = 64;

const PHASE_PUBLICATION = 'PUBLICATION';
const PHASE_CANDIDATE = 'CANDIDATE';
const PHASE_ADOPTION = 'ADOPTION';
const ALL_PHASES: readonly ProjectSourcePhase[] = [
  PHASE_PUBLICATION,
  PHASE_CANDIDATE,
  PHASE_ADOPTION,
];
/** ADOPT_PLAN is out of scope for this decoder: plain actions publish only. */
const ALLOWED_PHASES_FOR_DECODED_ACTIONS: readonly ProjectSourcePhase[] = [
  PHASE_PUBLICATION,
];

const DISPOSITIONS: readonly ProjectSourceDisposition[] = [
  'accepted',
  'refused',
  'unknown',
];

const REASONS: readonly ProjectSourceStatusReason[] = [
  'ORIGINAL_OPERATION_NOT_OBSERVED',
  'IN_PROGRESS',
  'PHASE_ATTEMPT_UNRESOLVED',
  'READY_FOR_ADVANCE',
  'PRECONDITION_UNAVAILABLE',
  'PRIVATE_INPUT_UNAVAILABLE',
  'SOURCE_UNAVAILABLE',
  'CONFLICT',
  'NOT_DISPATCHED',
  'REFUSED',
];
const REFUSED_REASONS: readonly string[] = ['NOT_DISPATCHED', 'REFUSED', 'CONFLICT'];
const UNKNOWN_REASONS: readonly string[] = REASONS.filter(
  (reason) => reason !== 'REFUSED',
);

const RECEIPT_KINDS: readonly ProjectSourceReceiptKind[] = [
  'INTENT',
  'PHASE_ATTEMPTED',
  'PROPOSAL_OBSERVED',
  'SOURCE_OBSERVED',
];

const CONTEXT_KEYS = ['schema', 'selection', 'owner_context', 'can_inspect'];
const CONTEXT_SELECTION_KEYS = ['action', 'work_ref'];
const OWNER_CONTEXT_KEYS = ['principal_scope'];
const STATUS_KEYS = [
  'schema',
  'selection',
  'owner_context',
  'disposition',
  'reason',
  'request_sha256',
  'recipe_fingerprint_sha256',
  'phase',
  'receipt',
  'advance',
];
const OPERATION_SELECTION_KEYS = ['action', 'request_id', 'work_ref'];
const RECEIPT_KEYS = [
  'kind',
  'event_id',
  'recorded_at_ms',
  'receipt_sha256',
  'sources',
  'proposal',
];
const SOURCE_KEYS = ['repository', 'commit', 'path', 'content_sha256'];
const PROPOSAL_KEYS = ['number', 'url', 'head_commit', 'head_branch'];
const ADVANCE_KEYS = ['phase_receipt_digest'];

const LOWER_HEX_40 = /^[0-9a-f]{40}$/;
const LOWER_HEX_64 = /^[0-9a-f]{64}$/;
const WORK_REF_KEY = /^[A-Z0-9]+(?:-[A-Z0-9]+)*$/;
/** Fixed lookup-key shapes, paired one to one with the two decoded actions. */
const REQUEST_ID_PATTERNS: Readonly<
  Record<ProjectSourceAction, RegExp>
> = {
  add_project_file: /^mmos-project-file-add-[0-9a-f]{40}$/,
  set_project_communication_preference: /^mmos-project-preference-set-[0-9a-f]{40}$/,
  correct_project_discovery: /^mmos-project-discovery-correct-[0-9a-f]{40}$/,
};

const BRANCH_FORBIDDEN_CHARS = ' ~^:?*[';
const ASCII_WHITESPACE = ' \t\n\v\f\r';

function invalid(): never {
  throw new Error(PROJECT_SOURCE_OPERATION_INVALID);
}

/** Exact whole-string match (Python `re.fullmatch` semantics). */
function fullMatch(pattern: RegExp, value: string): boolean {
  return pattern.exec(value)?.[0] === value;
}

type OwnFieldRead =
  | { readonly kind: 'absent' }
  | { readonly kind: 'invalid' }
  | { readonly kind: 'value'; readonly value: unknown };

/**
 * Reads one own property without ever invoking a getter, a setter or toJSON.
 * Accessor-backed and non-enumerable own fields are reported invalid so
 * hidden values cannot smuggle themselves past the exact shape checks.
 */
function readOwnDataField(record: object, key: string): OwnFieldRead {
  const descriptor = Object.getOwnPropertyDescriptor(record, key);
  if (descriptor === undefined) {
    return { kind: 'absent' };
  }
  if (
    typeof descriptor.get === 'function' ||
    typeof descriptor.set === 'function' ||
    !Object.prototype.hasOwnProperty.call(descriptor, 'value') ||
    descriptor.enumerable !== true
  ) {
    return { kind: 'invalid' };
  }
  return { kind: 'value', value: descriptor.value };
}

function isPlainRecordCandidate(value: unknown): value is Record<string, unknown> {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    return false;
  }
  const prototype = Object.getPrototypeOf(value);
  if (prototype !== Object.prototype && prototype !== null) {
    return false;
  }
  return Object.getOwnPropertySymbols(value).length === 0;
}

/**
 * Narrows to a plain data record whose own properties are exactly the given
 * field names. Inherited, symbolic, hidden and accessor-backed fields are
 * rejected; no field is ever read off the prototype chain and no getter or
 * toJSON of the input is ever invoked.
 */
function toExactRecord(
  value: unknown,
  keys: readonly string[],
): Record<string, unknown> | null {
  if (!isPlainRecordCandidate(value)) {
    return null;
  }
  const ownNames = Object.getOwnPropertyNames(value);
  if (ownNames.length !== keys.length) {
    return null;
  }
  for (const name of ownNames) {
    if (!keys.includes(name)) {
      return null;
    }
  }
  return value;
}

/**
 * Narrows to a plain data array of exactly the given length whose index
 * fields are own enumerable data properties. Sparse arrays, accessor-backed
 * indices, extra own fields and array subclasses are rejected.
 */
function toPlainArray(value: unknown, length: number): readonly unknown[] | null {
  if (!Array.isArray(value)) {
    return null;
  }
  if (Object.getPrototypeOf(value) !== Array.prototype) {
    return null;
  }
  if (Object.getOwnPropertySymbols(value).length !== 0) {
    return null;
  }
  if (value.length !== length) {
    return null;
  }
  const ownNames = Object.getOwnPropertyNames(value);
  if (ownNames.length !== length + 1) {
    return null;
  }
  for (let index = 0; index < length; index += 1) {
    if (!ownNames.includes(String(index))) {
      return null;
    }
    const descriptor = Object.getOwnPropertyDescriptor(value, index);
    if (
      descriptor === undefined ||
      typeof descriptor.get === 'function' ||
      typeof descriptor.set === 'function' ||
      !Object.prototype.hasOwnProperty.call(descriptor, 'value') ||
      descriptor.enumerable !== true
    ) {
      return null;
    }
  }
  return value.slice();
}

function readStringField(
  record: Record<string, unknown>,
  key: string,
): string | null {
  const read = readOwnDataField(record, key);
  if (read.kind !== 'value' || typeof read.value !== 'string') {
    return null;
  }
  return read.value;
}

/** Own data field value; absent/hidden/accessor-backed fields read as undefined. */
function rawFieldValue(record: Record<string, unknown>, key: string): unknown {
  const read = readOwnDataField(record, key);
  return read.kind === 'value' ? read.value : undefined;
}

function readHexField(
  record: Record<string, unknown>,
  key: string,
  pattern: RegExp,
): string | null {
  const value = readStringField(record, key);
  if (value === null || !fullMatch(pattern, value)) {
    return null;
  }
  return value;
}

function readOptionalHexField(
  record: Record<string, unknown>,
  key: string,
  pattern: RegExp,
): string | null | undefined {
  const read = readOwnDataField(record, key);
  if (read.kind !== 'value') {
    return undefined;
  }
  if (read.value === null) {
    return null;
  }
  if (typeof read.value !== 'string' || !fullMatch(pattern, read.value)) {
    return undefined;
  }
  return read.value;
}

/**
 * Exact safe-integer read: booleans, floats, strings and out-of-range or
 * unsafe numbers are all rejected without coercion.
 */
function readSafeIntField(
  record: Record<string, unknown>,
  key: string,
  minimum: number,
): number | null {
  const read = readOwnDataField(record, key);
  if (read.kind !== 'value' || typeof read.value !== 'number') {
    return null;
  }
  if (!Number.isSafeInteger(read.value)) {
    return null;
  }
  if (read.value < minimum || read.value > MAX_SAFE_INTEGER_CONTRACT) {
    return null;
  }
  return read.value;
}

/** Rejects strings carrying lone surrogate code units (never UTF-8 round-trippable). */
function hasLoneSurrogate(value: string): boolean {
  for (let index = 0; index < value.length; index += 1) {
    const code = value.charCodeAt(index);
    if (code >= 0xd800 && code <= 0xdfff) {
      if (code <= 0xdbff) {
        const next = index + 1 < value.length ? value.charCodeAt(index + 1) : 0;
        if (next >= 0xdc00 && next <= 0xdfff) {
          index += 1;
          continue;
        }
      }
      return true;
    }
  }
  return false;
}

function isProjectSourceAction(value: string): value is ProjectSourceAction {
  return (PROJECT_SOURCE_ACTIONS as readonly string[]).includes(value);
}

function isCanonicalWorkRef(value: string): boolean {
  if (hasLoneSurrogate(value) || !value.startsWith('WS:')) {
    return false;
  }
  const key = value.slice('WS:'.length);
  if (key.length < WORK_REF_KEY_MIN || key.length > WORK_REF_KEY_MAX) {
    return false;
  }
  return fullMatch(WORK_REF_KEY, key);
}

function utf8ByteLength(value: string): number {
  let bytes = 0;
  for (const character of value) {
    const codePoint = character.codePointAt(0) as number;
    if (codePoint <= 0x7f) {
      bytes += 1;
    } else if (codePoint <= 0x7ff) {
      bytes += 2;
    } else if (codePoint <= 0xffff) {
      bytes += 3;
    } else {
      bytes += 4;
    }
  }
  return bytes;
}

function isCanonicalPath(value: string): boolean {
  if (value.length === 0 || hasLoneSurrogate(value)) {
    return false;
  }
  if (utf8ByteLength(value) > MAX_PATH_BYTES) {
    return false;
  }
  if (value.includes('\\')) {
    return false;
  }
  for (const character of value) {
    const code = character.codePointAt(0) as number;
    if (code < 0x20 || (code >= 0x7f && code <= 0x9f)) {
      return false;
    }
  }
  for (const segment of value.split('/')) {
    if (segment === '' || segment === '.' || segment === '..') {
      return false;
    }
  }
  return true;
}

function isCanonicalBranch(value: string): boolean {
  if (value.length === 0 || value.length > MAX_BRANCH_CHARS) {
    return false;
  }
  if (hasLoneSurrogate(value)) {
    return false;
  }
  for (const character of value) {
    if (character.charCodeAt(0) > 0x7f) {
      return false; // the actual contract requires an ASCII-only branch
    }
    const code = character.charCodeAt(0);
    if (
      code < 0x20 ||
      (code >= 0x7f && code <= 0x9f) ||
      ASCII_WHITESPACE.includes(character) ||
      BRANCH_FORBIDDEN_CHARS.includes(character)
    ) {
      return false;
    }
  }
  if (
    value.startsWith('-') ||
    value.startsWith('/') ||
    value.startsWith('.')
  ) {
    return false;
  }
  if (value.endsWith('/') || value.endsWith('.') || value.endsWith('.lock')) {
    return false;
  }
  if (
    value.includes('..') ||
    value.includes('@{') ||
    value.includes('\\') ||
    value.includes('//')
  ) {
    return false;
  }
  return true;
}

function decodeStatusSource(value: unknown): ProjectSourceStatusSource | null {
  const record = toExactRecord(value, SOURCE_KEYS);
  if (record === null) {
    return null;
  }
  const repository = readStringField(record, 'repository');
  if (repository === null || repository !== REPOSITORY_MACRO) {
    return null;
  }
  const commit = readHexField(record, 'commit', LOWER_HEX_40);
  if (commit === null) {
    return null;
  }
  const path = readStringField(record, 'path');
  if (path === null || !isCanonicalPath(path)) {
    return null;
  }
  const contentSha256 = readHexField(record, 'content_sha256', LOWER_HEX_64);
  if (contentSha256 === null) {
    return null;
  }
  return Object.freeze({
    repository,
    commit,
    path,
    content_sha256: contentSha256,
  });
}

function decodeStatusProposal(value: unknown): ProjectSourceStatusProposal | null {
  const record = toExactRecord(value, PROPOSAL_KEYS);
  if (record === null) {
    return null;
  }
  const number = readSafeIntField(record, 'number', 1);
  if (number === null) {
    return null;
  }
  const url = readStringField(record, 'url');
  if (url === null || url !== PR_URL_PREFIX + String(number)) {
    return null; // no arbitrary URL is ever accepted
  }
  const headCommit = readHexField(record, 'head_commit', LOWER_HEX_40);
  if (headCommit === null) {
    return null;
  }
  const headBranch = readStringField(record, 'head_branch');
  if (headBranch === null || !isCanonicalBranch(headBranch)) {
    return null;
  }
  return Object.freeze({
    number,
    url,
    head_commit: headCommit,
    head_branch: headBranch,
  });
}

function decodeStatusProposalOrNull(value: unknown): ProjectSourceStatusProposal | null {
  if (value === null) {
    return null;
  }
  const decoded = decodeStatusProposal(value);
  if (decoded === null) {
    invalid();
  }
  return decoded;
}

function decodeStatusReceipt(value: unknown): ProjectSourceStatusReceipt {
  const record = toExactRecord(value, RECEIPT_KEYS);
  if (record === null) {
    invalid();
  }
  const kind = readStringField(record, 'kind');
  if (
    kind === null ||
    !(RECEIPT_KINDS as readonly string[]).includes(kind)
  ) {
    invalid();
  }
  const eventId = readSafeIntField(record, 'event_id', 1);
  if (eventId === null) {
    invalid();
  }
  const recordedAtMs = readSafeIntField(record, 'recorded_at_ms', 0);
  if (recordedAtMs === null) {
    invalid();
  }
  const receiptSha256 = readHexField(record, 'receipt_sha256', LOWER_HEX_64);
  if (receiptSha256 === null) {
    invalid();
  }
  const rawSources = rawFieldValue(record, 'sources');
  const sourcesCount =
    Array.isArray(rawSources) && rawSources.length <= MAX_SOURCES
      ? rawSources.length
      : -1;
  const plainSources = sourcesCount >= 0 ? toPlainArray(rawSources, sourcesCount) : null;
  if (plainSources === null) {
    invalid();
  }
  const sources: ProjectSourceStatusSource[] = [];
  for (const entry of plainSources) {
    const decoded = decodeStatusSource(entry);
    if (decoded === null) {
      invalid();
    }
    sources.push(decoded);
  }
  const proposal = decodeStatusProposalOrNull(rawFieldValue(record, 'proposal'));
  return Object.freeze({
    kind: kind as ProjectSourceReceiptKind,
    event_id: eventId,
    recorded_at_ms: recordedAtMs,
    receipt_sha256: receiptSha256,
    sources: Object.freeze(sources),
    proposal,
  });
}

function decodeStatusAdvance(value: unknown): ProjectSourcePhaseAdvanceWitness | null {
  if (value === null) {
    return null;
  }
  const record = toExactRecord(value, ADVANCE_KEYS);
  if (record === null) {
    invalid();
  }
  const digest = readHexField(record, 'phase_receipt_digest', LOWER_HEX_64);
  if (digest === null) {
    invalid();
  }
  return Object.freeze({ phase_receipt_digest: digest });
}

function decodeContextSelection(
  value: unknown,
): ProjectSourceContextSelection {
  const record = toExactRecord(value, CONTEXT_SELECTION_KEYS);
  if (record === null) {
    invalid();
  }
  const action = readStringField(record, 'action');
  if (action === null || !isProjectSourceAction(action)) {
    invalid();
  }
  const workRef = readStringField(record, 'work_ref');
  if (workRef === null || !isCanonicalWorkRef(workRef)) {
    invalid();
  }
  return Object.freeze({ action, work_ref: workRef });
}

function decodeOwnerContext(value: unknown): ProjectSourceOwnerContext {
  const record = toExactRecord(value, OWNER_CONTEXT_KEYS);
  if (record === null) {
    invalid();
  }
  const principalScope = readHexField(record, 'principal_scope', LOWER_HEX_64);
  if (principalScope === null) {
    invalid();
  }
  return Object.freeze({ principal_scope: principalScope });
}

function readBooleanTrueField(
  record: Record<string, unknown>,
  key: string,
): boolean {
  const read = readOwnDataField(record, key);
  return read.kind === 'value' && read.value === true;
}

function assertContextExpectation(
  expected: ProjectSourceContextExpectation,
): void {
  if (expected === null || typeof expected !== 'object') {
    invalid();
  }
  const action = (expected as ProjectSourceContextExpectation).action;
  if (typeof action !== 'string' || !isProjectSourceAction(action)) {
    invalid();
  }
  const workRef = (expected as ProjectSourceContextExpectation).workRef;
  if (typeof workRef !== 'string' || !isCanonicalWorkRef(workRef)) {
    invalid();
  }
}

/**
 * Decodes the current signed-owner inspection context for one fixed file or
 * preference source action. The selected action and work ref must match the
 * expected tuple exactly and the owner scope must be the signed owner's
 * principal — never a request-caller label or grant label. Returns a deeply
 * frozen detached value, or throws the single constant
 * `PROJECT_SOURCE_OPERATION_INVALID` without ever echoing input.
 */
export function decodeProjectSourceOperationContext(
  raw: unknown,
  expected: ProjectSourceContextExpectation,
): ProjectSourceContext {
  assertContextExpectation(expected);
  const record = toExactRecord(raw, CONTEXT_KEYS);
  if (record === null) {
    invalid();
  }
  const schema = readStringField(record, 'schema');
  if (schema !== PROJECT_SOURCE_CONTEXT_SCHEMA) {
    invalid();
  }
  const selection = decodeContextSelection(rawFieldValue(record, 'selection'));
  if (selection.action !== expected.action || selection.work_ref !== expected.workRef) {
    invalid();
  }
  const ownerContext = decodeOwnerContext(rawFieldValue(record, 'owner_context'));
  if (!readBooleanTrueField(record, 'can_inspect')) {
    invalid();
  }
  return Object.freeze({
    schema,
    selection,
    owner_context: ownerContext,
    can_inspect: true,
  });
}

/**
 * Decodes one source-operation status body for a fixed file or preference
 * action. The whole wire contract of the actual common module applies:
 * dispositions, closed reasons, receipt kinds, source/proposal shapes, the
 * phase budget of plain actions, digest pairing and the canonical serialized
 * budget. The status must additionally match the expected tuple exactly:
 * action, work ref, request id, public request SHA (when the wire carries
 * one) and the signed owner's principal scope. Returns a deeply frozen
 * detached value, or throws the single constant
 * `PROJECT_SOURCE_OPERATION_INVALID`.
 */
export function decodeProjectSourceOperationStatus(
  raw: unknown,
  expected: ProjectSourceStatusExpectation,
): ProjectSourceStatus {
  if (expected === null || typeof expected !== 'object') {
    invalid();
  }
  const action = (expected as ProjectSourceStatusExpectation).action;
  if (typeof action !== 'string' || !isProjectSourceAction(action)) {
    invalid();
  }
  const workRef = (expected as ProjectSourceStatusExpectation).workRef;
  if (typeof workRef !== 'string' || !isCanonicalWorkRef(workRef)) {
    invalid();
  }
  const requestId = (expected as ProjectSourceStatusExpectation).requestId;
  if (typeof requestId !== 'string' || !fullMatch(REQUEST_ID_PATTERNS[action], requestId)) {
    invalid();
  }
  const requestSha256 = (expected as ProjectSourceStatusExpectation).requestSha256;
  if (typeof requestSha256 !== 'string' || !fullMatch(LOWER_HEX_64, requestSha256)) {
    invalid();
  }
  const principalScope = (expected as ProjectSourceStatusExpectation).principalScope;
  if (typeof principalScope !== 'string' || !fullMatch(LOWER_HEX_64, principalScope)) {
    invalid();
  }

  const record = toExactRecord(raw, STATUS_KEYS);
  if (record === null) {
    invalid();
  }
  const schema = readStringField(record, 'schema');
  if (schema !== PROJECT_SOURCE_STATUS_SCHEMA) {
    invalid();
  }

  const selectionRecord = toExactRecord(
    rawFieldValue(record, 'selection'),
    OPERATION_SELECTION_KEYS,
  );
  if (selectionRecord === null) {
    invalid();
  }
  const selectionAction = readStringField(selectionRecord, 'action');
  if (selectionAction === null || !isProjectSourceAction(selectionAction)) {
    invalid();
  }
  const selectionRequestId = readStringField(selectionRecord, 'request_id');
  if (
    selectionRequestId === null ||
    !fullMatch(REQUEST_ID_PATTERNS[selectionAction], selectionRequestId)
  ) {
    invalid();
  }
  const selectionWorkRef = readStringField(selectionRecord, 'work_ref');
  if (selectionWorkRef === null || !isCanonicalWorkRef(selectionWorkRef)) {
    invalid();
  }
  if (
    selectionAction !== action ||
    selectionRequestId !== requestId ||
    selectionWorkRef !== workRef
  ) {
    invalid();
  }
  const selection = Object.freeze({
    action: selectionAction,
    request_id: selectionRequestId,
    work_ref: selectionWorkRef,
  });

  const ownerContext = decodeOwnerContext(rawFieldValue(record, 'owner_context'));
  if (ownerContext.principal_scope !== principalScope) {
    invalid();
  }

  const disposition = readStringField(record, 'disposition');
  if (
    disposition === null ||
    !(DISPOSITIONS as readonly string[]).includes(disposition)
  ) {
    invalid();
  }

  const rawReason = rawFieldValue(record, 'reason');
  let reason: ProjectSourceStatusReason | null = null;
  if (rawReason !== null) {
    if (typeof rawReason !== 'string' || !(REASONS as readonly string[]).includes(rawReason)) {
      invalid();
    }
    reason = rawReason as ProjectSourceStatusReason;
  }

  const requestSha = readOptionalHexField(record, 'request_sha256', LOWER_HEX_64);
  if (requestSha === undefined) {
    invalid();
  }
  const recipeFingerprint = readOptionalHexField(
    record,
    'recipe_fingerprint_sha256',
    LOWER_HEX_64,
  );
  if (recipeFingerprint === undefined) {
    invalid();
  }
  // The public request SHA of a decoded status is the public SHA of the
  // expected operation; anything else is a different operation's receipt.
  if (requestSha !== null && requestSha !== requestSha256) {
    invalid();
  }

  const rawPhase = rawFieldValue(record, 'phase');
  let phase: ProjectSourcePhase | null = null;
  if (rawPhase !== null) {
    if (typeof rawPhase !== 'string' || !(ALL_PHASES as readonly string[]).includes(rawPhase)) {
      invalid();
    }
    phase = rawPhase as ProjectSourcePhase;
  }

  const rawReceipt = rawFieldValue(record, 'receipt');
  const receipt = rawReceipt === null ? null : decodeStatusReceipt(rawReceipt);
  const advance = decodeStatusAdvance(rawFieldValue(record, 'advance'));

  checkStatusSemantics(
    disposition as ProjectSourceDisposition,
    reason,
    requestSha,
    recipeFingerprint,
    phase,
    receipt,
    advance,
  );
  if(action==='correct_project_discovery'&&receipt?.kind==='SOURCE_OBSERVED'){
    const sources=receipt.sources,paths=new Set(sources.map(source=>source.path));
    const replacement=discoveryReplacementRef({request_id:requestId,work_ref:workRef},principalScope);
    if(sources.length!==3||paths.size!==3||new Set(sources.map(source=>source.commit)).size!==1
      ||sources.some(source=>source.repository!=='macro')||!paths.delete('agentos/workstreams/WS-'+workRef.slice(3)+'.md')
      ||!paths.delete('agentos/discoveries/DSC-'+replacement.slice(4)+'.md'))invalid();
    const old=[...paths][0]!,prefix='agentos/discoveries/DSC-';
    if(!old.startsWith(prefix)||!old.endsWith('.md')||!validDiscoveryReference('DSC:'+old.slice(prefix.length,-3)))invalid();
  }

  const status: ProjectSourceStatus = {
    schema,
    selection,
    owner_context: ownerContext,
    disposition: disposition as ProjectSourceDisposition,
    reason,
    request_sha256: requestSha,
    recipe_fingerprint_sha256: recipeFingerprint,
    phase,
    receipt,
    advance,
  };
  assertSerializedBudget(status);
  return deepFreeze(status);
}

type DecodedReceipt = ProjectSourceStatusReceipt;
type DecodedAdvance = ProjectSourcePhaseAdvanceWitness | null;

/**
 * Exact semantics of `_check_semantics` in the actual common contract for the
 * two decoded (non-ADOPT) plain actions: ADOPT_PLAN-only phases, reasons and
 * the advance witness cannot occur, `READY_FOR_ADVANCE` can never be the
 * reason of a plain action, and accepted publication requires a
 * SOURCE_OBSERVED receipt at PUBLICATION with no advance witness.
 */
function checkStatusSemantics(
  disposition: ProjectSourceDisposition,
  reason: ProjectSourceStatusReason | null,
  requestSha256: string | null,
  recipeFingerprintSha256: string | null,
  phase: ProjectSourcePhase | null,
  receipt: DecodedReceipt | null,
  advance: DecodedAdvance,
): void {
  if (phase !== null && !ALLOWED_PHASES_FOR_DECODED_ACTIONS.includes(phase)) {
    invalid();
  }

  if (reason === null) {
    if (disposition !== 'accepted') {
      invalid();
    }
  } else {
    if (disposition === 'accepted') {
      invalid();
    }
    if (disposition === 'refused') {
      if (!REFUSED_REASONS.includes(reason)) {
        invalid();
      }
      // A partial publication is never refused.
      if (receipt !== null || advance !== null) {
        invalid();
      }
    } else {
      if (!UNKNOWN_REASONS.includes(reason)) {
        invalid();
      }
    }
  }

  // The public request SHA is never substituted for the trusted fingerprint.
  if (
    requestSha256 !== null &&
    recipeFingerprintSha256 !== null &&
    requestSha256 === recipeFingerprintSha256
  ) {
    invalid();
  }

  if (receipt === null) {
    // No receipt never means "no effect": no digests and no phase may be
    // reported alongside an absent receipt.
    if (phase !== null) {
      invalid();
    }
    if (requestSha256 !== null || recipeFingerprintSha256 !== null) {
      invalid();
    }
    if (advance !== null) {
      invalid();
    }
  } else {
    if (phase === null || requestSha256 === null || recipeFingerprintSha256 === null) {
      invalid();
    }
  }

  if (reason === 'ORIGINAL_OPERATION_NOT_OBSERVED') {
    if (receipt !== null || advance !== null) {
      invalid();
    }
  }

  if (receipt !== null) {
    const { kind, sources, proposal } = receipt;
    if (kind === 'INTENT' || kind === 'PHASE_ATTEMPTED') {
      if (sources.length > 0 || proposal !== null) {
        invalid();
      }
      if (disposition !== 'unknown') {
        invalid();
      }
    } else if (kind === 'PROPOSAL_OBSERVED') {
      if (proposal === null || sources.length > 0) {
        invalid();
      }
      if (disposition !== 'unknown') {
        invalid();
      }
    } else {
      if (sources.length === 0 || proposal !== null) {
        invalid();
      }
      if (phase === PHASE_CANDIDATE && disposition !== 'unknown') {
        invalid();
      }
    }
  }

  if (disposition === 'accepted') {
    if (receipt === null || receipt.kind !== 'SOURCE_OBSERVED') {
      invalid();
    }
    if (phase !== PHASE_PUBLICATION) {
      invalid();
    }
    if (advance !== null) {
      invalid();
    }
  }

  if (reason === 'READY_FOR_ADVANCE') {
    // Unreachable for the two decoded plain actions: READY_FOR_ADVANCE
    // belongs to ADOPT_PLAN candidate adoption only.
    invalid();
  } else if (advance !== null) {
    invalid();
  }
}

type CanonicalValue =
  | null
  | boolean
  | number
  | string
  | readonly CanonicalValue[]
  | { readonly [key: string]: CanonicalValue };

/**
 * Canonical JSON encoding matching the actual contract serializer
 * (`sort_keys=True`, compact separators, `ensure_ascii=False`): object keys
 * in lexicographic order, no whitespace, primitive string escaping only.
 */
function canonicalJson(value: CanonicalValue): string {
  if (value === null) {
    return 'null';
  }
  if (typeof value === 'boolean') {
    return value ? 'true' : 'false';
  }
  if (typeof value === 'number') {
    return String(value);
  }
  if (typeof value === 'string') {
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) {
    const items = value as readonly CanonicalValue[];
    return `[${items.map((item) => canonicalJson(item)).join(',')}]`;
  }
  const record = value as Record<string, CanonicalValue>;
  const keys = Object.keys(record).sort();
  return `{${keys.map((key) => `${JSON.stringify(key)}:${canonicalJson(record[key])}`).join(',')}}`;
}

function statusCanonicalEntries(status: ProjectSourceStatus): Record<string, CanonicalValue> {
  const receipt = status.receipt;
  const proposal = receipt?.proposal ?? null;
  return {
    schema: status.schema,
    selection: {
      action: status.selection.action,
      request_id: status.selection.request_id,
      work_ref: status.selection.work_ref,
    },
    owner_context: {
      principal_scope: status.owner_context.principal_scope,
    },
    disposition: status.disposition,
    reason: status.reason,
    request_sha256: status.request_sha256,
    recipe_fingerprint_sha256: status.recipe_fingerprint_sha256,
    phase: status.phase,
    receipt:
      receipt === null
        ? null
        : {
            kind: receipt.kind,
            event_id: receipt.event_id,
            recorded_at_ms: receipt.recorded_at_ms,
            receipt_sha256: receipt.receipt_sha256,
            proposal:
              proposal === null
                ? null
                : {
                    number: proposal.number,
                    url: proposal.url,
                    head_commit: proposal.head_commit,
                    head_branch: proposal.head_branch,
                  },
            sources: (receipt.sources as readonly ProjectSourceStatusSource[]).map(
              (source) => ({
                repository: source.repository,
                commit: source.commit,
                path: source.path,
                content_sha256: source.content_sha256,
              }),
            ),
          },
    advance:
      status.advance === null
        ? null
        : { phase_receipt_digest: status.advance.phase_receipt_digest },
  };
}

/**
 * Canonical serialized budget of the actual contract: the canonical JSON
 * encoding of the decoded body plus one trailing LF must stay within 32768
 * UTF-8 bytes.
 */
function assertSerializedBudget(status: ProjectSourceStatus): void {
  const encoded = canonicalJson(statusCanonicalEntries(status));
  const budget = utf8ByteLength(encoded) + 1;
  if (budget > MAX_STATUS_BYTES) {
    invalid();
  }
}

function deepFreeze<T>(value: T): T {
  if (value !== null && typeof value === 'object') {
    for (const property of Object.values(value as Record<string, unknown>)) {
      deepFreeze(property);
    }
    Object.freeze(value);
  }
  return value;
}
