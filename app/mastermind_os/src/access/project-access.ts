/**
 * Strict pure decoder for `mastermind.workspace_project_access.v1` —
 * own-profile Workspace permission observations, never action eligibility.
 * Frontend READ decoder only: no IO, no mutation, no getters invoked, no
 * brands, no external imports, no grants or action authority. Inputs must be
 * plain canonical JSON (exact own enumerable data keys, data properties only,
 * no symbols, no cycles, bounded depth and size); every field is validated
 * against the closed Python contract and anything else decodes to `null`.
 */
export interface ProjectAccessSelection { work_ref: string }
export interface ProjectAccessSource {
  repository: string;
  commit: string;
  content_sha256: string;
  path: string;
}
export interface ProjectAccessMembership { workspace_read: 'QUALIFIED' }
export type ProjectAccessScope = 'WORKSPACE' | 'PROJECT' | 'INSTRUCTION';
export type ProjectAccessSupply = 'SUPPLIED' | 'NOT_SUPPLIED';
export type ProjectAccessReasonCode = 'ACCESS_DENIED' | 'SOURCE_UNAVAILABLE' | 'SOURCE_CHANGED' | 'OWNER_NOT_READY';
export interface ProjectAccessGrantRow {
  action: typeof ACTIONS[number];
  scope: ProjectAccessScope;
  work_ref: string | null;
  instruction_ref: string | null;
  supply: ProjectAccessSupply;
}
/** Closed positional row tuple: exactly one row per action, in order. */
export type ProjectAccessGrantRows = [
  ProjectAccessGrantRow, ProjectAccessGrantRow, ProjectAccessGrantRow, ProjectAccessGrantRow,
  ProjectAccessGrantRow, ProjectAccessGrantRow, ProjectAccessGrantRow, ProjectAccessGrantRow,
];

const WORKSPACE_ACCESS_SCHEMA = 'mastermind.workspace_project_access.v1';
const SOURCE_REPOSITORY = 'mastermindx-market-intelligence/macro';
const SOURCE_PATH_PREFIX = 'agentos/workstreams/WS-';
const SOURCE_PATH_SUFFIX = '.md';
const MAX_RESPONSE_BYTES = 16384;
// bounded_canonical({'ok':True,'result':body}, limit=MAX_RESPONSE_BYTES-1): the
// canonical envelope may not exceed 16383 bytes and adds a fixed 21 bytes around
// the body ('{"ok":true,"result":' + '}'), so the body itself must fit in 16362.
const BODY_CANONICAL_MAX_BYTES = MAX_RESPONSE_BYTES - 1 - 21;
const WORK_KEY_MIN_LENGTH = 2;
const WORK_KEY_MAX_LENGTH = 64;
const MAX_JSON_DEPTH = 24;

const ACTIONS = [
  'publish_project_proposal', 'pause_workstream_admission', 'resume_workstream_admission',
  'ADOPT_PLAN', 'ACCEPT_DIRECTION', 'add_project_file', 'set_project_communication_preference',
  'pause_instruction_admission',
] as const;
const REASON_CODES = ['ACCESS_DENIED', 'SOURCE_UNAVAILABLE', 'SOURCE_CHANGED', 'OWNER_NOT_READY'] as const;
const REASON_CODE_SET: ReadonlySet<string> = new Set(REASON_CODES);
const BODY_KEYS = ['schema', 'selection', 'availability', 'source', 'membership', 'declaration', 'grants', 'reason_codes'] as const;
const SOURCE_KEYS = ['repository', 'commit', 'content_sha256', 'path'] as const;
const MEMBERSHIP_KEYS = ['workspace_read'] as const;
const GRANT_ROW_KEYS = ['action', 'scope', 'work_ref', 'instruction_ref', 'supply'] as const;
const NULLABLE_WHEN_UNAVAILABLE_KEYS = ['source', 'membership', 'declaration', 'grants'] as const;
// Work keys: 2..64 uppercase ASCII letters/digits, optionally separated by single
// hyphens; numeric keys permitted; no leading, trailing or consecutive hyphen. The
// anchored patterns must consume the entire string, so a trailing newline is rejected.
const WORK_KEY_SOURCE = '[A-Z0-9]+(?:-[A-Z0-9]+)*';
const WS_REF_PATTERN = new RegExp(`^WS:(${WORK_KEY_SOURCE})$`);
const INS_REF_PATTERN = new RegExp(`^INS:(${WORK_KEY_SOURCE})$`);
const COMMIT_PATTERN = /^[0-9a-f]{40}$/;
const CONTENT_SHA256_PATTERN = /^[0-9a-f]{64}$/;

interface DecodedSelection { readonly selection: ProjectAccessSelection; readonly key: string }

export type ProjectAccessRead =
  | {
    availability: 'UNAVAILABLE'; declaration: null; grants: null; membership: null;
    reason_codes: readonly [ProjectAccessReasonCode];
    schema: typeof WORKSPACE_ACCESS_SCHEMA; selection: ProjectAccessSelection; source: null;
  }
  | {
    availability: 'AVAILABLE'; declaration: 'NOT_DECLARED'; grants: null;
    membership: ProjectAccessMembership; reason_codes: readonly [];
    schema: typeof WORKSPACE_ACCESS_SCHEMA; selection: ProjectAccessSelection; source: ProjectAccessSource;
  }
  | {
    availability: 'AVAILABLE'; declaration: 'SUPPLIED'; grants: ProjectAccessGrantRows;
    membership: ProjectAccessMembership; reason_codes: readonly [];
    schema: typeof WORKSPACE_ACCESS_SCHEMA; selection: ProjectAccessSelection; source: ProjectAccessSource;
  };

function isPlainObject(value: unknown): value is Record<string, unknown> {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) return false;
  if (Object.getPrototypeOf(value) !== Object.prototype) return false;
  if (Object.getOwnPropertySymbols(value).length !== 0) return false;
  const names = Object.getOwnPropertyNames(value);
  if (Object.keys(value).length !== names.length) return false;
  for (const name of names) {
    const descriptor = Object.getOwnPropertyDescriptor(value, name);
    if (descriptor === undefined || !Object.hasOwn(descriptor,"value") || descriptor.get !== undefined || descriptor.set !== undefined) return false;
  }
  return true;
}

function isPlainArray(value: unknown): value is unknown[] {
  if (!Array.isArray(value) || Object.getPrototypeOf(value)!==Array.prototype || Object.getOwnPropertySymbols(value).length !== 0) return false;
  if (Object.getOwnPropertyNames(value).length !== value.length + 1) return false;
  for (let index = 0; index < value.length; index += 1) {
    const field=Object.getOwnPropertyDescriptor(value,String(index));
    if (!field || !field.enumerable || !Object.hasOwn(field,"value")) return false;
  }
  return true;
}

function hasExactKeys(value: Record<string, unknown>, keys: readonly string[]): boolean {
  const names = Object.getOwnPropertyNames(value);
  if (names.length !== keys.length) return false;
  for (const key of keys) if (!Object.prototype.hasOwnProperty.call(value, key)) return false;
  return true;
}

/** Rejects cycles, excess depth, accessors, symbols and non-JSON scalars. */
function isCanonicalJson(value: unknown, seen: Set<object>, depth: number): boolean {
  if (value === null) return true;
  if (typeof value === 'string' || typeof value === 'boolean') return true;
  if (typeof value === 'number') return Number.isFinite(value);
  if (typeof value !== 'object' || depth >= MAX_JSON_DEPTH || seen.has(value)) return false;
  seen.add(value);
  let ok = true;
  if (isPlainObject(value)) {
    for (const name of Object.getOwnPropertyNames(value)) {
      const nested = Object.getOwnPropertyDescriptor(value, name);
      if (nested === undefined || !isCanonicalJson(nested.value, seen, depth + 1)) { ok = false; break; }
    }
  } else if (isPlainArray(value)) {
    for (let index = 0; index < value.length; index += 1) {
      const nested = Object.getOwnPropertyDescriptor(value, String(index));
      if (nested === undefined || !isCanonicalJson(nested.value, seen, depth + 1)) { ok = false; break; }
    }
  } else {
    ok = false;
  }
  seen.delete(value);
  return ok;
}

function isValidWorkKey(key: string): boolean {
  return key.length >= WORK_KEY_MIN_LENGTH && key.length <= WORK_KEY_MAX_LENGTH && /^[A-Z0-9]+(?:-[A-Z0-9]+)*$/.exec(key)?.[0]===key;
}

function matchBoundedRef(value: unknown, pattern: RegExp): string | null {
  if (typeof value !== 'string') return null;
  const match = pattern.exec(value);
  if (match === null || match[0]!==value) return null;
  const key = match[1];
  return typeof key === 'string' && isValidWorkKey(key) ? key : null;
}

function decodeWorkSelection(value: unknown): DecodedSelection | null {
  if (!isPlainObject(value) || !hasExactKeys(value, ['work_ref'])) return null;
  const workRef = value.work_ref;
  if (typeof workRef !== 'string') return null;
  const key = matchBoundedRef(workRef, WS_REF_PATTERN);
  return key === null ? null : { selection: { work_ref: workRef }, key };
}

export function validProjectAccessSelection(value: unknown): value is ProjectAccessSelection {
  try{return decodeWorkSelection(value) !== null;}catch{return false;}
}

function decodeSource(value: unknown, workKey: string): ProjectAccessSource | null {
  if (!isPlainObject(value) || !hasExactKeys(value, SOURCE_KEYS)) return null;
  if (value.repository !== SOURCE_REPOSITORY) return null;
  if (typeof value.commit !== 'string' || COMMIT_PATTERN.exec(value.commit)?.[0]!==value.commit) return null;
  if (typeof value.content_sha256 !== 'string' || CONTENT_SHA256_PATTERN.exec(value.content_sha256)?.[0]!==value.content_sha256) return null;
  const path = SOURCE_PATH_PREFIX + workKey + SOURCE_PATH_SUFFIX;
  if (value.path !== path) return null;
  return { repository: SOURCE_REPOSITORY, commit: value.commit, content_sha256: value.content_sha256, path };
}

function decodeUnavailableBody(body: Record<string, unknown>, decoded: DecodedSelection): ProjectAccessRead | null {
  for (const key of NULLABLE_WHEN_UNAVAILABLE_KEYS) if (body[key] !== null) return null;
  const reasons = body.reason_codes;
  if (!isPlainArray(reasons) || reasons.length !== 1) return null;
  const reason = reasons[0];
  if (typeof reason !== 'string' || !REASON_CODE_SET.has(reason)) return null;
  return {
    schema: WORKSPACE_ACCESS_SCHEMA, selection: decoded.selection, availability: 'UNAVAILABLE',
    source: null, membership: null, declaration: null, grants: null,
    reason_codes: [reason as ProjectAccessReasonCode],
  };
}

function decodeGrantRow(value: unknown, action: typeof ACTIONS[number], scope: ProjectAccessScope, workRef: string): ProjectAccessGrantRow | null {
  if (!isPlainObject(value) || !hasExactKeys(value, GRANT_ROW_KEYS)) return null;
  if (value.action !== action || value.scope !== scope) return null;
  if (value.supply !== 'SUPPLIED' && value.supply !== 'NOT_SUPPLIED') return null;
  const rowWorkRef = scope === 'WORKSPACE' ? null : workRef;
  if (value.work_ref !== rowWorkRef) return null;
  let instructionRef: string | null = null;
  if (scope === 'INSTRUCTION' && value.supply === 'SUPPLIED') {
    if (typeof value.instruction_ref !== 'string') return null;
    if (matchBoundedRef(value.instruction_ref,INS_REF_PATTERN)===null) return null;
    instructionRef = value.instruction_ref;
  } else if (value.instruction_ref !== null) return null;
  return { action, scope, work_ref: rowWorkRef, instruction_ref: instructionRef, supply: value.supply };
}

function grantRowScope(index: number): ProjectAccessScope {
  if (index === 0) return 'WORKSPACE';
  if (index === ACTIONS.length - 1) return 'INSTRUCTION';
  return 'PROJECT';
}

function decodeGrantRows(value: unknown, workRef: string): ProjectAccessGrantRows | null {
  if (!isPlainArray(value) || value.length !== ACTIONS.length) return null;
  const rows: ProjectAccessGrantRow[] = [];
  let position = 0;
  for (const action of ACTIONS) {
    const row = decodeGrantRow(value[position], action, grantRowScope(position), workRef);
    if (row === null) return null;
    rows.push(row);
    position += 1;
  }
  return rows as unknown as ProjectAccessGrantRows;
}

function decodeAvailableBody(body: Record<string, unknown>, decoded: DecodedSelection): ProjectAccessRead | null {
  const source = decodeSource(body.source, decoded.key);
  if (source === null) return null;
  const membership = body.membership;
  if (!isPlainObject(membership) || !hasExactKeys(membership, MEMBERSHIP_KEYS) || membership.workspace_read !== 'QUALIFIED') {
    return null;
  }
  const reasons = body.reason_codes;
  if (!isPlainArray(reasons) || reasons.length !== 0) return null;
  const base = {
    schema: WORKSPACE_ACCESS_SCHEMA, selection: decoded.selection, availability: 'AVAILABLE',
    source, membership: { workspace_read: 'QUALIFIED' }, reason_codes: [],
  } as const;
  if (body.declaration === 'NOT_DECLARED') {
    if (body.grants !== null) return null;
    return { ...base, declaration: 'NOT_DECLARED', grants: null };
  }
  if (body.declaration === 'SUPPLIED') {
    const grants = decodeGrantRows(body.grants, decoded.selection.work_ref);
    if (grants === null) return null;
    return { ...base, declaration: 'SUPPLIED', grants };
  }
  return null;
}

function utf8ByteLength(text: string): number {
  let bytes = 0;
  for (let index = 0; index < text.length; index += 1) {
    const code = text.charCodeAt(index);
    const pair = code >= 0xd800 && code < 0xdc00 && index + 1 < text.length
      && text.charCodeAt(index + 1) >= 0xdc00 && text.charCodeAt(index + 1) < 0xe000;
    if (code < 0x80) bytes += 1;
    else if (code < 0x800) bytes += 2;
    else if (pair) { bytes += 4; index += 1; }
    else bytes += 3;
  }
  return bytes;
}

function isWithinBodyBudget(value: unknown): boolean {
  try {
    const encoded = JSON.stringify(value);
    return typeof encoded === 'string' && utf8ByteLength(encoded) <= BODY_CANONICAL_MAX_BYTES;
  } catch {
    return false;
  }
}

export function decodeProjectAccess(value: unknown, expected: ProjectAccessSelection): ProjectAccessRead | null {
 try {
  const expectedSelection = decodeWorkSelection(expected);
  if (expectedSelection === null) return null;
  if (!isCanonicalJson(value, new Set<object>(), 0)) return null;
  if (!isPlainObject(value) || !hasExactKeys(value, BODY_KEYS)) return null;
  const body = value;
  if (body.schema !== WORKSPACE_ACCESS_SCHEMA) return null;
  const bodySelection = decodeWorkSelection(body.selection);
  if (bodySelection === null || bodySelection.selection.work_ref !== expectedSelection.selection.work_ref) return null;
  const decoded =
    body.availability === 'UNAVAILABLE' ? decodeUnavailableBody(body, bodySelection)
    : body.availability === 'AVAILABLE' ? decodeAvailableBody(body, bodySelection)
    : null;
  return decoded !== null && isWithinBodyBudget(body) ? decoded : null;
 }catch{return null;}
}
