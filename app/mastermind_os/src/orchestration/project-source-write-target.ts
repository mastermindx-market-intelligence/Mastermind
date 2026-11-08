/**
 * Closed durable source-write lookup target codec.
 *
 * A target is the exact string `project-source-write.v1:` followed by one
 * canonical JSON object holding exactly six fields in lexicographic key order
 * with no whitespace. Canonical serialization equality is the acceptance rule:
 * a stored target string is never rewritten, trimmed or re-escaped. It either
 * already is byte-identical to the canonical form of what it parses to, or it
 * is rejected.
 *
 * This module is a pure bounded codec. It performs no transport, storage,
 * grant, permission or source-existence work. A matching operation key or a
 * parsed digest is a lookup fact only; it never mints an identity and never
 * verifies that a source exists. The same-controller owner rechecks the actual
 * current principal and grant at submission/status time.
 */

import {canonicalJson} from './operation-key';
import {validateDiscoveryCorrectionTarget,type DiscoveryCorrectionTarget} from '../knowledge/library/project-discovery-correction';
const SOURCE_WRITE_TARGET_PREFIX = 'project-source-write.v1:';
const CORRECTION_TARGET_PREFIX = 'project-source-write.v2:';
const SOURCE_WRITE_TARGET_MAX_LENGTH = 2048;
const WORK_REF_PREFIX = 'WS:';
const WORK_REF_KEY_MIN_LENGTH = 2;
const WORK_REF_KEY_MAX_LENGTH = 64;

const PROJECT_SOURCE_WRITE_TARGET_ACTIONS = [
  'add_project_file',
  'set_project_communication_preference',
] as const;

export type ProjectSourceWriteTargetAction =
  (typeof PROJECT_SOURCE_WRITE_TARGET_ACTIONS)[number] | 'correct_project_discovery';
type LegacyAction = (typeof PROJECT_SOURCE_WRITE_TARGET_ACTIONS)[number];

interface LegacyProjectSourceWriteTarget {
  readonly action: LegacyAction;
  readonly work_ref: string;
  readonly source_commit: string;
  readonly base_revision: string;
  readonly request_sha256: string;
  readonly expected_preference_revision: string | null;
}
export type ProjectSourceWriteTarget = LegacyProjectSourceWriteTarget | DiscoveryCorrectionTarget;

/** Canonical JSON key order: lexicographically sorted field names. */
const TARGET_FIELD_NAMES = [
  'action',
  'base_revision',
  'expected_preference_revision',
  'request_sha256',
  'source_commit',
  'work_ref',
] as const;

type TargetFieldName = (typeof TARGET_FIELD_NAMES)[number];

function fullMatch(pattern: RegExp, value: string): boolean { return pattern.exec(value)?.[0] === value; }

const LOWER_HEX_40 = /^[0-9a-f]{40}$/;
const LOWER_HEX_64 = /^[0-9a-f]{64}$/;
const UPPER_KEBAB_KEY = /^[A-Z0-9]+(?:-[A-Z0-9]+)*$/;

/** Fixed lookup key shapes, paired one to one with the two actions. */
const OPERATION_KEY_PATTERNS: Readonly<
  Record<LegacyAction, RegExp>
> = {
  add_project_file: /^mmos-project-file-add-[0-9a-f]{40}$/,
  set_project_communication_preference: /^mmos-project-preference-set-[0-9a-f]{40}$/,
};

interface RawTargetValues {
  readonly action: string;
  readonly base_revision: string;
  readonly expected_preference_revision: string | null;
  readonly request_sha256: string;
  readonly source_commit: string;
  readonly work_ref: string;
}

type OwnFieldRead =
  | { readonly kind: 'absent' }
  | { readonly kind: 'invalid' }
  | { readonly kind: 'value'; readonly value: unknown };

/**
 * Reads one own property without ever invoking a getter, a setter or toJSON.
 * Accessor-backed and non-enumerable own fields are reported invalid so hidden
 * values cannot smuggle themselves past the exact six-field shape check.
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
 * Narrows to a record whose own properties are exactly the six target field
 * names. Inherited, symbolic, hidden and accessor-backed fields are rejected;
 * no field is ever read off the prototype chain.
 */
function toTargetRecord(value: unknown): Record<string, unknown> | null {
  if (!isPlainRecordCandidate(value)) {
    return null;
  }
  const ownNames = Object.getOwnPropertyNames(value);
  if (ownNames.length !== TARGET_FIELD_NAMES.length) {
    return null;
  }
  const allowedNames: readonly string[] = TARGET_FIELD_NAMES;
  for (const name of ownNames) {
    if (!allowedNames.includes(name)) {
      return null;
    }
  }
  return value;
}

type FieldRead<T> = { readonly ok: true; readonly value: T } | { readonly ok: false };

function readStringField(
  record: Record<string, unknown>,
  key: TargetFieldName,
): FieldRead<string> {
  const read = readOwnDataField(record, key);
  if (read.kind !== 'value' || typeof read.value !== 'string') {
    return { ok: false };
  }
  return { ok: true, value: read.value };
}

function readExpectedPreferenceRevision(
  record: Record<string, unknown>,
): FieldRead<string | null> {
  const read = readOwnDataField(record, 'expected_preference_revision');
  if (read.kind !== 'value') {
    return { ok: false };
  }
  if (read.value === null) {
    return { ok: true, value: null };
  }
  if (typeof read.value !== 'string' || !fullMatch(LOWER_HEX_64, read.value)) {
    return { ok: false };
  }
  return { ok: true, value: read.value };
}

function isTargetAction(value: string): value is LegacyAction {
  return (PROJECT_SOURCE_WRITE_TARGET_ACTIONS as readonly string[]).includes(value);
}

function isCanonicalWorkRef(value: string): boolean {
  if (!value.startsWith(WORK_REF_PREFIX)) {
    return false;
  }
  const key = value.slice(WORK_REF_PREFIX.length);
  if (key.length < WORK_REF_KEY_MIN_LENGTH || key.length > WORK_REF_KEY_MAX_LENGTH) {
    return false;
  }
  return fullMatch(UPPER_KEBAB_KEY, key);
}

function toTarget(record: Record<string, unknown>): LegacyProjectSourceWriteTarget | null {
  const action = readStringField(record, 'action');
  if (!action.ok || !isTargetAction(action.value)) {
    return null;
  }
  const workRef = readStringField(record, 'work_ref');
  if (!workRef.ok || !isCanonicalWorkRef(workRef.value)) {
    return null;
  }
  const sourceCommit = readStringField(record, 'source_commit');
  if (!sourceCommit.ok || !fullMatch(LOWER_HEX_40, sourceCommit.value)) {
    return null;
  }
  const baseRevision = readStringField(record, 'base_revision');
  if (!baseRevision.ok || !fullMatch(LOWER_HEX_64, baseRevision.value)) {
    return null;
  }
  const requestSha256 = readStringField(record, 'request_sha256');
  if (!requestSha256.ok || !fullMatch(LOWER_HEX_64, requestSha256.value)) {
    return null;
  }
  const expectedPreferenceRevision = readExpectedPreferenceRevision(record);
  if (!expectedPreferenceRevision.ok) {
    return null;
  }
  if (
    action.value === 'add_project_file' &&
    expectedPreferenceRevision.value !== null
  ) {
    return null;
  }
  return {
    action: action.value,
    work_ref: workRef.value,
    source_commit: sourceCommit.value,
    base_revision: baseRevision.value,
    request_sha256: requestSha256.value,
    expected_preference_revision: expectedPreferenceRevision.value,
  };
}

function toRawValues(record: Record<string, unknown>): RawTargetValues | null {
  const action = readStringField(record, 'action');
  const baseRevision = readStringField(record, 'base_revision');
  const expectedPreferenceRevision = readExpectedPreferenceRevision(record);
  const requestSha256 = readStringField(record, 'request_sha256');
  const sourceCommit = readStringField(record, 'source_commit');
  const workRef = readStringField(record, 'work_ref');
  if (
    !action.ok ||
    !baseRevision.ok ||
    !expectedPreferenceRevision.ok ||
    !requestSha256.ok ||
    !sourceCommit.ok ||
    !workRef.ok
  ) {
    return null;
  }
  return {
    action: action.value,
    base_revision: baseRevision.value,
    expected_preference_revision: expectedPreferenceRevision.value,
    request_sha256: requestSha256.value,
    source_commit: sourceCommit.value,
    work_ref: workRef.value,
  };
}

/**
 * Emits the canonical JSON body: the six fields in lexicographic key order,
 * no whitespace, JSON.stringify primitive escaping for every value.
 */
function canonicalTargetBody(values: RawTargetValues): string {
  const fieldsByName: Record<TargetFieldName, string | null> = {
    action: values.action,
    base_revision: values.base_revision,
    expected_preference_revision: values.expected_preference_revision,
    request_sha256: values.request_sha256,
    source_commit: values.source_commit,
    work_ref: values.work_ref,
  };
  let body = '{';
  let isFirstField = true;
  for (const name of TARGET_FIELD_NAMES) {
    if (!isFirstField) {
      body += ',';
    }
    isFirstField = false;
    const value = fieldsByName[name];
    body += `${JSON.stringify(name)}:${value === null ? 'null' : JSON.stringify(value)}`;
  }
  return `${body}}`;
}

function parseTargetString(value: string): ProjectSourceWriteTarget | null {
  if (value.length > SOURCE_WRITE_TARGET_MAX_LENGTH) {
    return null;
  }
  if (value.startsWith(CORRECTION_TARGET_PREFIX)) {
    const body=value.slice(CORRECTION_TARGET_PREFIX.length);
    const target=validateDiscoveryCorrectionTarget(JSON.parse(body));
    return canonicalJson(target)===body?target:null;
  }
  if (!value.startsWith(SOURCE_WRITE_TARGET_PREFIX)) {
    return null;
  }
  const body = value.slice(SOURCE_WRITE_TARGET_PREFIX.length);
  if (body.length === 0) {
    return null;
  }

  let parsed: unknown;
  try {
    parsed = JSON.parse(body);
  } catch {
    return null;
  }

  const record = toTargetRecord(parsed);
  if (record === null) {
    return null;
  }

  // Canonical serialization equality: the stored body must already be byte
  // identical to the canonical form of what it parses to. This single check
  // rejects duplicate keys, noncanonical key order, whitespace, extra JSON
  // documents and trailing newlines without ever rewriting the stored target.
  const rawValues = toRawValues(record);
  if (rawValues === null) {
    return null;
  }
  if (canonicalTargetBody(rawValues) !== body) {
    return null;
  }
  return toTarget(record);
}

/**
 * Parses a stored source-write lookup target. Accepts the exact target string
 * form, or a strictly shaped plain object holding exactly the six fields.
 * Accessor-backed inputs are rejected without ever reading them. Returns a
 * detached plain object, or null when anything fails; no caller input is
 * thrown or echoed.
 */
export function parseProjectSourceWriteTarget(
  value: unknown,
): ProjectSourceWriteTarget | null {
  try {
    if (typeof value === 'string') {
      return parseTargetString(value);
    }
    try {return validateDiscoveryCorrectionTarget(value);} catch { /* Original v1 remains exact. */ }
    const record = toTargetRecord(value);
    if (record === null) {
      return null;
    }
    return toTarget(record);
  } catch {
    return null;
  }
}

/**
 * Serializes a strictly shaped target record into the canonical target string.
 * Key insertion order of the input is irrelevant; the output is always the
 * canonical lexicographic byte form.
 */
export function serializeProjectSourceWriteTarget(value: unknown): string | null {
  try {
    try {
      const target=validateDiscoveryCorrectionTarget(value);
      const serialized=CORRECTION_TARGET_PREFIX+canonicalJson(target);
      return serialized.length<=SOURCE_WRITE_TARGET_MAX_LENGTH?serialized:null;
    } catch { /* Original v1 remains exact. */ }
    const record = toTargetRecord(value);
    if (record === null) {
      return null;
    }
    const rawValues = toRawValues(record);
    if (rawValues === null) {
      return null;
    }
    const target = toTarget(record);
    if (target === null) {
      return null;
    }
    const serialized = SOURCE_WRITE_TARGET_PREFIX + canonicalTargetBody(rawValues);
    if (serialized.length > SOURCE_WRITE_TARGET_MAX_LENGTH) {
      return null;
    }
    return serialized;
  } catch {
    return null;
  }
}

/**
 * Reports whether an operation key is the exact fixed lookup key shape paired
 * with the target action. This is a fixed string match only: it never mints a
 * key or identity, never grants permission and never verifies that the
 * referenced source exists. A target that no longer satisfies the target shape
 * matches nothing.
 */
export function projectSourceWriteKeyMatches(
  operationKey: unknown,
  target: ProjectSourceWriteTarget,
): boolean {
  try {
    const correction=parseProjectSourceWriteTarget(target);
    if (correction?.action==='correct_project_discovery') {
      return typeof operationKey==='string'&&fullMatch(/^mmos-project-discovery-correct-[0-9a-f]{40}$/,operationKey);
    }
    const record = toTargetRecord(target);
    if (record === null) {
      return false;
    }
    const validated = toTarget(record);
    if (validated === null) {
      return false;
    }
    if (typeof operationKey !== 'string') {
      return false;
    }
    return fullMatch(OPERATION_KEY_PATTERNS[validated.action], operationKey);
  } catch {
    return false;
  }
}
