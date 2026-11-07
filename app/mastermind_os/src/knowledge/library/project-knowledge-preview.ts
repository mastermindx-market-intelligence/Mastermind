/**
 * Pure strict TypeScript decoder for the closed Knowledge prepare-preview DTO
 * (`mastermind.workspace_source_operation_preview.v1`) that the frozen
 * workspace owner service (dd9671026f0547c69f3fb30e5d897538272912a7) returns
 * for the two project knowledge source operations: `FILE_ADD` and
 * `COMMUNICATION_PREFERENCE`.
 *
 * Boundaries (P16.T1.S22):
 *
 * - This leaf only decodes already computed owner output. It performs no
 *   transport, auth, control, store, network or filesystem effect, computes
 *   no digest and mints no identifier. `expectedPublicRequestSha256` is the
 *   caller's independently computed canonical public request hash; a SHA,
 *   preview or context here is a source fact to display, never authority,
 *   grant, acceptance or publication.
 * - `expectedRequest` must be an already validated request built by
 *   `./project-knowledge-requests`. Its closed shape is re-checked enough to
 *   fail closed on invalid direct calls; this module introduces no competing
 *   request compiler and expands no input permission.
 * - Only closed inert own plain data is accepted at every level: exact key
 *   sets, enumerable own data properties, no symbols, no hidden fields, no
 *   getters or setters, no exotic prototypes, no arbitrary records, paths or
 *   URLs. Malformed, mismatched or over-budget input always decodes to
 *   `null`; this module never throws and never carries a private error.
 * - The decoded value is a detached, deeply frozen plain DTO. Raw and request
 *   references are never retained, so later mutation of either input cannot
 *   change a returned preview.
 * - The complete canonical (sorted-key, compact) UTF-8 wrapper text must stay
 *   within `PROJECT_KNOWLEDGE_PREVIEW_MAX_UTF8_BYTES`.
 */

import {
  canonicalPublicRequest,
  type ProjectFileAddRequest,
  type ProjectPreferenceSetRequest,
  type ProjectKnowledgeRequest,
} from './project-knowledge-requests';
import {DISCOVERY_CORRECTION_ACTION,DISCOVERY_CORRECTION_SCHEMA,discoveryReplacementRef,
  discoveryCorrectionPreimages,type ProjectDiscoveryCorrectionRequest,type DiscoveryCorrectionPreviewChange} from './project-discovery-correction';

const FILE_REQUEST_SCHEMA='mastermind.project_file_add_request.v1';
const PREFERENCE_REQUEST_SCHEMA='mastermind.project_preference_set_request.v1';

/** Exact wrapper schema of the Knowledge prepare-preview DTO. */
export const PROJECT_KNOWLEDGE_PREVIEW_WRAPPER_SCHEMA =
  'mastermind.workspace_source_operation_preview.v1';
/** Exact schema of the decoded preview body. */
export const PROJECT_KNOWLEDGE_PREVIEW_SCHEMA = 'mastermind.project_knowledge_preview.v1';
/** Exact schema of the witnessed original terminal input reference. */
export const PROJECT_KNOWLEDGE_ORIGINAL_INPUT_SCHEMA =
  'mastermind.terminal_original_input_reference.v1';

/** Action selected by a project file add request. */
export const PROJECT_KNOWLEDGE_PREVIEW_ACTION_FILE_ADD = 'add_project_file';
/** Action selected by a project communication preference set request. */
export const PROJECT_KNOWLEDGE_PREVIEW_ACTION_COMMUNICATION_PREFERENCE =
  'set_project_communication_preference';

/** Canonical UTF-8 budget of the complete wrapper. */
export const PROJECT_KNOWLEDGE_PREVIEW_MAX_UTF8_BYTES = 32768;
/** UTF-8 budget of a communication preference value. */
export const PROJECT_KNOWLEDGE_PREFERENCE_VALUE_MAX_UTF8_BYTES = 2000;

/** Closed action vocabulary of the two previewed source operations. */
export type ProjectKnowledgePreviewAction =
  | typeof PROJECT_KNOWLEDGE_PREVIEW_ACTION_FILE_ADD
  | typeof PROJECT_KNOWLEDGE_PREVIEW_ACTION_COMMUNICATION_PREFERENCE
  | typeof DISCOVERY_CORRECTION_ACTION;

/** Witnessed original terminal input reference (shape-checked only). */
export interface ProjectKnowledgeOriginalInputReference {
  readonly schema: typeof PROJECT_KNOWLEDGE_ORIGINAL_INPUT_SCHEMA;
  readonly input_ref: string;
  readonly artifact_sha256: string;
  readonly payload_sha256: string;
}

/** Witness binding the preview to one terminal input and one recipe build. */
export interface ProjectKnowledgePreviewWitness {
  readonly original_input: ProjectKnowledgeOriginalInputReference;
  readonly recipe_fingerprint_sha256: string;
}

/** Exact selected request identity echoed by the owner. */
export interface ProjectKnowledgePreviewSelection {
  readonly action: ProjectKnowledgePreviewAction;
  readonly request_id: string;
  readonly work_ref: string;
}

/** Opaque owner scope context; not a login, grant or capability. */
export interface ProjectKnowledgePreviewOwnerContext {
  readonly principal_scope: string;
}

/** Change applied by a previewed `FILE_ADD` operation. */
export interface ProjectKnowledgeFileAddPreviewChange {
  readonly kind: 'FILE_ADD';
  readonly display_name: string;
  readonly size_bytes: number;
}

/** Change applied by a previewed `COMMUNICATION_PREFERENCE` operation. */
export interface ProjectKnowledgeCommunicationPreferencePreviewChange {
  readonly kind: 'COMMUNICATION_PREFERENCE';
  readonly value: string;
}

/** Closed union over the two previewed change kinds. */
export type ProjectKnowledgePreviewChange =
  | ProjectKnowledgeFileAddPreviewChange
  | ProjectKnowledgeCommunicationPreferencePreviewChange
  | DiscoveryCorrectionPreviewChange;

/** One expected postimage of the previewed operation; preimage may be null. */
export interface ProjectKnowledgePreviewPostimage {
  readonly path: string;
  readonly content_sha256: string;
  readonly expected_preimage_sha256: string | null;
}

/** Preview body shared by both actions, exact to the owner's wire shape. */
export interface ProjectKnowledgePreparedPreviewBody {
  readonly schema: typeof PROJECT_KNOWLEDGE_PREVIEW_SCHEMA;
  readonly state: 'DRAFT_ONLY';
  readonly action: ProjectKnowledgePreviewAction;
  readonly work_ref: string;
  readonly source_commit: string;
  readonly change: ProjectKnowledgePreviewChange;
  readonly postimages: readonly ProjectKnowledgePreviewPostimage[];
}

/** Exact detached, deeply frozen prepare-preview DTO, or decode failures. */
export interface ProjectKnowledgePreparedPreview {
  readonly schema: typeof PROJECT_KNOWLEDGE_PREVIEW_WRAPPER_SCHEMA;
  readonly selection: ProjectKnowledgePreviewSelection;
  readonly owner_context: ProjectKnowledgePreviewOwnerContext;
  readonly request_sha256: string;
  readonly recipe_fingerprint_sha256: string;
  readonly preview_witness: ProjectKnowledgePreviewWitness;
  readonly preview: ProjectKnowledgePreparedPreviewBody;
}

const WRAPPER_KEYS: readonly string[] = [
  'schema',
  'selection',
  'owner_context',
  'request_sha256',
  'recipe_fingerprint_sha256',
  'preview_witness',
  'preview',
];
const SELECTION_KEYS: readonly string[] = ['action', 'request_id', 'work_ref'];
const OWNER_CONTEXT_KEYS: readonly string[] = ['principal_scope'];
const WITNESS_KEYS: readonly string[] = ['original_input', 'recipe_fingerprint_sha256'];
const ORIGINAL_INPUT_KEYS: readonly string[] = [
  'schema',
  'input_ref',
  'artifact_sha256',
  'payload_sha256',
];
const PREVIEW_KEYS: readonly string[] = [
  'schema',
  'state',
  'action',
  'work_ref',
  'source_commit',
  'change',
  'postimages',
];
const FILE_CHANGE_KEYS: readonly string[] = ['kind', 'display_name', 'size_bytes'];
const PREFERENCE_CHANGE_KEYS: readonly string[] = ['kind', 'value'];
const POSTIMAGE_KEYS: readonly string[] = ['path', 'content_sha256', 'expected_preimage_sha256'];
const FILE_REQUEST_KEYS: readonly string[] = [
  'schema',
  'request_id',
  'work_ref',
  'source_commit',
  'base_revision',
  'file',
];
const FILE_PART_KEYS: readonly string[] = ['display_name', 'media_type', 'content_utf8'];
const PREFERENCE_REQUEST_KEYS: readonly string[] = [
  'schema',
  'request_id',
  'work_ref',
  'source_commit',
  'base_revision',
  'expected_preference_revision',
  'value',
];

const TERMINAL_INPUT_PREFIX = 'terminal-input:';
const WORKSTREAM_POSTIMAGE_PREFIX = 'agentos/workstreams/WS-';
const PROJECT_FILE_POSTIMAGE_PREFIX = 'agentos/project-files/WS-';
const PREFERENCE_DECISION_POSTIMAGE_PREFIX =
  'agentos/decisions/DEC-PROJECT-COMMUNICATION-PREFERENCE-';

/**
 * Workstream selection key grammar of the supplied workspace owners:
 * `WS:` plus a 2..64 character key of `[A-Z0-9]` segments joined by single
 * hyphens. The key is reused verbatim inside every postimage path.
 */
const WORK_REF_PATTERN = /^WS:([A-Z0-9]+(?:-[A-Z0-9]+)*)$/;
const WORK_REF_KEY_MIN = 2;
const WORK_REF_KEY_MAX = 64;

const LOWER_HEX64_PATTERN = /^[0-9a-f]{64}$/;
const LOWER_HEX40_PATTERN = /^[0-9a-f]{40}$/;

/** Closed media-type to path-extension pairing of project file postimages. */
const MEDIA_TYPE_EXTENSIONS: Readonly<Record<string, string>> = {
  'text/markdown': 'md',
  'text/plain': 'txt',
};

const UTF8_ENCODER = new TextEncoder();

/** Request-side facts the decoder re-proves before decoding any wrapper. */
interface QualifiedRequestBase {
  readonly action: ProjectKnowledgePreviewAction;
  readonly requestId: string;
  readonly workRef: string;
  readonly workRefKey: string;
  readonly sourceCommit: string;
  readonly baseRevision: string;
}

interface QualifiedFileAddRequest extends QualifiedRequestBase {
  readonly action: typeof PROJECT_KNOWLEDGE_PREVIEW_ACTION_FILE_ADD;
  readonly displayName: string;
  readonly extension: string;
  readonly sizeBytes: number;
}

interface QualifiedPreferenceSetRequest extends QualifiedRequestBase {
  readonly action: typeof PROJECT_KNOWLEDGE_PREVIEW_ACTION_COMMUNICATION_PREFERENCE;
  readonly expectedPreferenceRevision: string | null;
  readonly value: string;
}

interface QualifiedCorrectionRequest extends QualifiedRequestBase {
  readonly action:typeof DISCOVERY_CORRECTION_ACTION;
  readonly request:ProjectDiscoveryCorrectionRequest;
}
type QualifiedRequest = QualifiedFileAddRequest | QualifiedPreferenceSetRequest | QualifiedCorrectionRequest;

/** Plain record with the Object prototype (or none) only; never exotic. */
function isPlainObject(value: unknown): value is Record<string, unknown> {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    return false;
  }
  const prototype: unknown = Object.getPrototypeOf(value);
  return prototype === Object.prototype || prototype === null;
}

/** Dense plain array: Array prototype, index names plus `length`, no symbols. */
function isPlainArray(value: unknown): value is unknown[] {
  if (!Array.isArray(value) || Object.getPrototypeOf(value) !== Array.prototype) {
    return false;
  }
  if (Object.getOwnPropertySymbols(value).length !== 0) {
    return false;
  }
  const names = Object.getOwnPropertyNames(value);
  return names.length === value.length + 1 && names.includes('length');
}

/**
 * Exact closed record shape: every expected key present exactly once as an
 * own enumerable data property, no accessor, no hidden field, no symbol and
 * no extra name. Returns the record for direct own-property reads.
 */
function closedRecord(value: unknown, keys: readonly string[]): Record<string, unknown> | null {
  if (!isPlainObject(value)) {
    return null;
  }
  if (Object.getOwnPropertyNames(value).length !== keys.length) {
    return null;
  }
  if (Object.getOwnPropertySymbols(value).length !== 0) {
    return null;
  }
  for (const key of keys) {
    const descriptor = Object.getOwnPropertyDescriptor(value, key);
    if (descriptor === undefined || !descriptor.enumerable) {
      return null;
    }
    if (descriptor.get !== undefined || descriptor.set !== undefined) {
      return null;
    }
  }
  return value;
}

function isNonemptyString(value: unknown): value is string {
  return typeof value === 'string' && value.length > 0;
}

function isLowerHex64(value: unknown): value is string {
  return typeof value === 'string' && LOWER_HEX64_PATTERN.test(value);
}

function isLowerHex40(value: unknown): value is string {
  return typeof value === 'string' && LOWER_HEX40_PATTERN.test(value);
}

/** Workstream key extracted from a valid `WS:<key>` selection work_ref. */
function workRefKeyOf(value: unknown): string | null {
  if (typeof value !== 'string') {
    return null;
  }
  const match = WORK_REF_PATTERN.exec(value);
  if (match === null) {
    return null;
  }
  const key = match[1];
  if (key === undefined || key.length < WORK_REF_KEY_MIN || key.length > WORK_REF_KEY_MAX) {
    return null;
  }
  return key;
}

/** Display basename: never a path, never empty, never control punctuation. */
function isDisplayBasename(value: unknown): value is string {
  if (typeof value !== 'string' || value.length === 0 || value === '.' || value === '..') {
    return false;
  }
  for (const character of value) {
    const code = character.codePointAt(0);
    if (code === undefined || code < 0x20 || code === 0x7f) {
      return false;
    }
    if (character === '/' || character === '\\') {
      return false;
    }
  }
  return true;
}

/** TextEncoder UTF-8 byte length of a string. */
function utf8ByteLength(text: string): number {
  return UTF8_ENCODER.encode(text).length;
}

/**
 * Canonical (sorted-key, compact) JSON text of already validated plain data,
 * or `null` for values that cannot canonicalize (non-finite numbers and
 * exotic values never appear in a decoded preview).
 */
function canonicalJsonText(value: unknown): string | null {
  if (typeof value === 'string') {
    return JSON.stringify(value);
  }
  if (value === null) {
    return 'null';
  }
  if (typeof value === 'number') {
    return Number.isFinite(value) ? JSON.stringify(value) : null;
  }
  if (isPlainArray(value)) {
    const parts: string[] = [];
    for (const item of value) {
      const text = canonicalJsonText(item);
      if (text === null) {
        return null;
      }
      parts.push(text);
    }
    return `[${parts.join(',')}]`;
  }
  if (isPlainObject(value)) {
    const parts: string[] = [];
    for (const key of Object.keys(value).sort()) {
      const text = canonicalJsonText((value as Record<string, unknown>)[key]);
      if (text === null) {
        return null;
      }
      parts.push(`${JSON.stringify(key)}:${text}`);
    }
    return `{${parts.join(',')}}`;
  }
  return null;
}

/** Canonical UTF-8 byte length of a value, or `null` when uncannotonical. */
export function projectKnowledgePreviewCanonicalUtf8Bytes(value: unknown): number | null {
  const text = canonicalJsonText(value);
  return text === null ? null : utf8ByteLength(text);
}

interface RequestCommonFields {
  readonly requestId: string;
  readonly workRef: string;
  readonly workRefKey: string;
  readonly sourceCommit: string;
  readonly baseRevision: string;
}

/** Re-proofs the identity fields shared by both closed request shapes. */
function requestCommonFields(record: Record<string, unknown>): RequestCommonFields | null {
  const requestId = record['request_id'];
  if (!isNonemptyString(requestId)) {
    return null;
  }
  const workRef = record['work_ref'];
  const workRefKey = workRefKeyOf(workRef);
  if (typeof workRef !== 'string' || workRefKey === null) {
    return null;
  }
  const sourceCommit = record['source_commit'];
  if (!isLowerHex40(sourceCommit)) {
    return null;
  }
  const baseRevision = record['base_revision'];
  if (!isLowerHex64(baseRevision)) {
    return null;
  }
  return {
    requestId,
    workRef,
    workRefKey,
    sourceCommit,
    baseRevision,
  };
}

function qualifyFileAddRequest(value: unknown): QualifiedFileAddRequest | null {
  const record = closedRecord(value, FILE_REQUEST_KEYS);
  if (record === null) {
    return null;
  }
  const common = requestCommonFields(record);
  if (common === null) {
    return null;
  }
  const file = closedRecord(record['file'], FILE_PART_KEYS);
  if (file === null) {
    return null;
  }
  const displayName = file['display_name'];
  if (!isDisplayBasename(displayName)) {
    return null;
  }
  const mediaType = file['media_type'];
  const extension =
    typeof mediaType === 'string' ? MEDIA_TYPE_EXTENSIONS[mediaType] : undefined;
  if (extension === undefined) {
    return null;
  }
  const contentUtf8 = file['content_utf8'];
  if (typeof contentUtf8 !== 'string') {
    return null;
  }
  const sizeBytes = utf8ByteLength(contentUtf8);
  if (
    !Number.isSafeInteger(sizeBytes) ||
    sizeBytes < 0 ||
    sizeBytes > PROJECT_KNOWLEDGE_PREVIEW_MAX_UTF8_BYTES
  ) {
    return null;
  }
  return {
    action: PROJECT_KNOWLEDGE_PREVIEW_ACTION_FILE_ADD,
    requestId: common.requestId,
    workRef: common.workRef,
    workRefKey: common.workRefKey,
    sourceCommit: common.sourceCommit,
    baseRevision: common.baseRevision,
    displayName,
    extension,
    sizeBytes,
  };
}

function qualifyPreferenceSetRequest(value: unknown): QualifiedPreferenceSetRequest | null {
  const record = closedRecord(value, PREFERENCE_REQUEST_KEYS);
  if (record === null) {
    return null;
  }
  const common = requestCommonFields(record);
  if (common === null) {
    return null;
  }
  const expectedPreferenceRevision = record['expected_preference_revision'];
  if (expectedPreferenceRevision !== null && !isLowerHex64(expectedPreferenceRevision)) {
    return null;
  }
  const preferenceValue = record['value'];
  if (!isNonemptyString(preferenceValue)) {
    return null;
  }
  if (utf8ByteLength(preferenceValue) > PROJECT_KNOWLEDGE_PREFERENCE_VALUE_MAX_UTF8_BYTES) {
    return null;
  }
  return {
    action: PROJECT_KNOWLEDGE_PREVIEW_ACTION_COMMUNICATION_PREFERENCE,
    requestId: common.requestId,
    workRef: common.workRef,
    workRefKey: common.workRefKey,
    sourceCommit: common.sourceCommit,
    baseRevision: common.baseRevision,
    expectedPreferenceRevision,
    value: preferenceValue,
  };
}

/**
 * Re-proofs the caller's already validated request just enough to fail
 * closed on invalid direct calls: exact closed shape, one of the two actual
 * request schemas, and the field assumptions the preview pins itself to.
 */
function qualifyRequest(value: unknown): QualifiedRequest | null {
  // Reuse the actual accepted request owner; a lookalike request ID/schema,
  // invalid literal text or getter must not become a prepared original.
  value=JSON.parse(canonicalPublicRequest(value as ProjectKnowledgeRequest));
  if (!isPlainObject(value)) {
    return null;
  }
  const schema = (value as Record<string, unknown>)['schema'];
  if (schema === FILE_REQUEST_SCHEMA) {
    return qualifyFileAddRequest(value);
  }
  if (schema === PREFERENCE_REQUEST_SCHEMA) {
    return qualifyPreferenceSetRequest(value);
  }
  if (schema === DISCOVERY_CORRECTION_SCHEMA) {
    const common=requestCommonFields(value);
    return common?{...common,action:DISCOVERY_CORRECTION_ACTION,request:value as unknown as ProjectDiscoveryCorrectionRequest}:null;
  }
  return null;
}

/** Second postimage path of a `FILE_ADD` preview, content-addressed name. */
function isProjectFilePostimagePath(path: string, prefix: string, extension: string): boolean {
  if (!path.startsWith(prefix)) {
    return false;
  }
  const remainder = path.slice(prefix.length);
  const suffix = `.${extension}`;
  if (!remainder.endsWith(suffix)) {
    return false;
  }
  return isLowerHex64(remainder.slice(0, remainder.length - suffix.length));
}

function decodeFileAddChange(
  value: unknown,
  request: QualifiedFileAddRequest,
): ProjectKnowledgeFileAddPreviewChange | null {
  const record = closedRecord(value, FILE_CHANGE_KEYS);
  if (record === null) {
    return null;
  }
  if (record['kind'] !== 'FILE_ADD') {
    return null;
  }
  if (record['display_name'] !== request.displayName) {
    return null;
  }
  const sizeBytes = record['size_bytes'];
  if (
    typeof sizeBytes !== 'number' ||
    !Number.isSafeInteger(sizeBytes) ||
    sizeBytes !== request.sizeBytes
  ) {
    return null;
  }
  return {
    kind: 'FILE_ADD',
    display_name: request.displayName,
    size_bytes: request.sizeBytes,
  };
}

function decodePreferenceChange(
  value: unknown,
  request: QualifiedPreferenceSetRequest,
): ProjectKnowledgeCommunicationPreferencePreviewChange | null {
  const record = closedRecord(value, PREFERENCE_CHANGE_KEYS);
  if (record === null) {
    return null;
  }
  if (record['kind'] !== 'COMMUNICATION_PREFERENCE') {
    return null;
  }
  if (record['value'] !== request.value) {
    return null;
  }
  return {
    kind: 'COMMUNICATION_PREFERENCE',
    value: request.value,
  };
}

/**
 * Decodes the two closed postimages: the workstream note (preimage is the
 * request's base revision) plus the action-specific second file. Paths are
 * matched against the exact owner templates only; the returned order keeps
 * the owner's own order.
 */
function decodePostimages(
  value: unknown,
  request: QualifiedRequest,
  principalScope:string,
): ProjectKnowledgePreviewPostimage[] | null {
  if (!isPlainArray(value) || value.length !== (request.action===DISCOVERY_CORRECTION_ACTION?3:2)) {
    return null;
  }
  const entries: ProjectKnowledgePreviewPostimage[] = [];
  const seenPaths = new Set<string>();
  for (const entryValue of value) {
    const entry = closedRecord(entryValue, POSTIMAGE_KEYS);
    if (entry === null) {
      return null;
    }
    const path = entry['path'];
    if (!isNonemptyString(path)) {
      return null;
    }
    const contentSha256 = entry['content_sha256'];
    if (!isLowerHex64(contentSha256)) {
      return null;
    }
    const expectedPreimage = entry['expected_preimage_sha256'];
    if (expectedPreimage !== null && !isLowerHex64(expectedPreimage)) {
      return null;
    }
    if (seenPaths.has(path)) {
      return null;
    }
    seenPaths.add(path);
    entries.push({
      path,
      content_sha256: contentSha256,
      expected_preimage_sha256: expectedPreimage,
    });
  }
  if(request.action===DISCOVERY_CORRECTION_ACTION){
    const expected=discoveryCorrectionPreimages(request.request,principalScope);
    return entries.every(entry=>Object.hasOwn(expected,entry.path)&&expected[entry.path]===entry.expected_preimage_sha256)?entries:null;
  }
  const workstreamPath = `${WORKSTREAM_POSTIMAGE_PREFIX}${request.workRefKey}.md`;
  const projectFilePrefix = `${PROJECT_FILE_POSTIMAGE_PREFIX}${request.workRefKey}/`;
  const decisionPath = `${PREFERENCE_DECISION_POSTIMAGE_PREFIX}${request.workRefKey}.md`;
  let workstreamEntry: ProjectKnowledgePreviewPostimage | null = null;
  let secondEntry: ProjectKnowledgePreviewPostimage | null = null;
  for (const entry of entries) {
    if (entry.path === workstreamPath) {
      workstreamEntry = entry;
    } else if (
      request.action === PROJECT_KNOWLEDGE_PREVIEW_ACTION_FILE_ADD
        ? isProjectFilePostimagePath(entry.path, projectFilePrefix, request.extension)
        : entry.path === decisionPath
    ) {
      secondEntry = entry;
    }
  }
  if (workstreamEntry === null || secondEntry === null) {
    return null;
  }
  if (workstreamEntry.expected_preimage_sha256 !== request.baseRevision) {
    return null;
  }
  const requiredSecondPreimage =
    request.action === PROJECT_KNOWLEDGE_PREVIEW_ACTION_FILE_ADD
      ? null
      : request.expectedPreferenceRevision;
  if (secondEntry.expected_preimage_sha256 !== requiredSecondPreimage) {
    return null;
  }
  return entries;
}

function decodePreparedPreview(
  raw: unknown,
  expectedRequest: ProjectKnowledgeRequest,
  expectedPublicRequestSha256: string,
): ProjectKnowledgePreparedPreview | null {
  const request = qualifyRequest(expectedRequest);
  if (request === null) {
    return null;
  }
  if (!isLowerHex64(expectedPublicRequestSha256)) {
    return null;
  }
  const wrapper = closedRecord(raw, WRAPPER_KEYS);
  if (wrapper === null || wrapper['schema'] !== PROJECT_KNOWLEDGE_PREVIEW_WRAPPER_SCHEMA) {
    return null;
  }
  const selection = closedRecord(wrapper['selection'], SELECTION_KEYS);
  if (
    selection === null ||
    selection['action'] !== request.action ||
    selection['request_id'] !== request.requestId ||
    selection['work_ref'] !== request.workRef
  ) {
    return null;
  }
  const ownerContext = closedRecord(wrapper['owner_context'], OWNER_CONTEXT_KEYS);
  if (ownerContext === null || !isLowerHex64(ownerContext['principal_scope'])) {
    return null;
  }
  const requestSha256 = wrapper['request_sha256'];
  if (!isLowerHex64(requestSha256) || requestSha256 !== expectedPublicRequestSha256) {
    return null;
  }
  const fingerprintSha256 = wrapper['recipe_fingerprint_sha256'];
  if (!isLowerHex64(fingerprintSha256)) {
    return null;
  }
  const witness = closedRecord(wrapper['preview_witness'], WITNESS_KEYS);
  if (witness === null || witness['recipe_fingerprint_sha256'] !== fingerprintSha256) {
    return null;
  }
  const originalInput = closedRecord(witness['original_input'], ORIGINAL_INPUT_KEYS);
  if (originalInput === null || originalInput['schema'] !== PROJECT_KNOWLEDGE_ORIGINAL_INPUT_SCHEMA) {
    return null;
  }
  const inputRef = originalInput['input_ref'];
  if (
    typeof inputRef !== 'string' ||
    !inputRef.startsWith(TERMINAL_INPUT_PREFIX) ||
    !isLowerHex64(inputRef.slice(TERMINAL_INPUT_PREFIX.length))
  ) {
    return null;
  }
  const artifactSha256 = originalInput['artifact_sha256'];
  if (!isLowerHex64(artifactSha256)) {
    return null;
  }
  const payloadSha256 = originalInput['payload_sha256'];
  if (!isLowerHex64(payloadSha256)) {
    return null;
  }
  const preview = closedRecord(wrapper['preview'], PREVIEW_KEYS);
  if (
    preview === null ||
    preview['schema'] !== PROJECT_KNOWLEDGE_PREVIEW_SCHEMA ||
    preview['state'] !== 'DRAFT_ONLY' ||
    preview['action'] !== request.action ||
    preview['work_ref'] !== request.workRef ||
    preview['source_commit'] !== request.sourceCommit
  ) {
    return null;
  }
  const change: ProjectKnowledgePreviewChange | null =
    request.action === PROJECT_KNOWLEDGE_PREVIEW_ACTION_FILE_ADD
      ? decodeFileAddChange(preview['change'], request)
      : request.action===DISCOVERY_CORRECTION_ACTION
        ? decodeCorrectionChange(preview['change'],request,ownerContext['principal_scope'])
        : decodePreferenceChange(preview['change'], request);
  if (change === null) {
    return null;
  }
  const postimages = decodePostimages(preview['postimages'], request,ownerContext['principal_scope']);
  if (postimages === null) {
    return null;
  }
  const prepared: ProjectKnowledgePreparedPreview = {
    schema: PROJECT_KNOWLEDGE_PREVIEW_WRAPPER_SCHEMA,
    selection: {
      action: request.action,
      request_id: request.requestId,
      work_ref: request.workRef,
    },
    owner_context: { principal_scope: ownerContext['principal_scope'] },
    request_sha256: requestSha256,
    recipe_fingerprint_sha256: fingerprintSha256,
    preview_witness: {
      original_input: {
        schema: PROJECT_KNOWLEDGE_ORIGINAL_INPUT_SCHEMA,
        input_ref: inputRef,
        artifact_sha256: artifactSha256,
        payload_sha256: payloadSha256,
      },
      recipe_fingerprint_sha256: fingerprintSha256,
    },
    preview: {
      schema: PROJECT_KNOWLEDGE_PREVIEW_SCHEMA,
      state: 'DRAFT_ONLY',
      action: request.action,
      work_ref: request.workRef,
      source_commit: request.sourceCommit,
      change,
      postimages,
    },
  };
  const canonicalBytes = projectKnowledgePreviewCanonicalUtf8Bytes(prepared);
  if (
    canonicalBytes === null ||
    canonicalBytes > PROJECT_KNOWLEDGE_PREVIEW_MAX_UTF8_BYTES
  ) {
    return null;
  }
  return deepFreeze(prepared);
}

/**
 * Decodes one closed Knowledge prepare-preview wrapper against an already
 * validated request and the caller's independently computed public request
 * hash. Returns the detached, deeply frozen exact DTO, or `null` for any
 * malformed, mismatched, over-budget or non-plain input. Decoding is pure,
 * never throws, and grants nothing.
 */
export function decodeProjectKnowledgePreview(
  raw: unknown,
  expectedRequest: ProjectKnowledgeRequest,
  expectedPublicRequestSha256: string,
): ProjectKnowledgePreparedPreview | null {
  try {
    return decodePreparedPreview(raw, expectedRequest, expectedPublicRequestSha256);
  } catch {
    return null;
  }
}

function decodeCorrectionChange(raw:unknown,qualified:QualifiedCorrectionRequest,scope:string):DiscoveryCorrectionPreviewChange|null {
  const value=closedRecord(raw,['kind','discovery_ref','replacement_ref','correction_reason','replacement']);
  const request=qualified.request;
  if(!value||value.kind!=='DISCOVERY_CORRECTION'||value.discovery_ref!==request.discovery_ref
    ||value.replacement_ref!==discoveryReplacementRef(request,scope)||value.correction_reason!==request.correction_reason)return null;
  // The actual public request validator rejects getters, extra fields, invalid
  // evidence and invalid dates before equality; no unknown object is serialized.
  if(canonicalPublicRequest({...request,replacement:value.replacement as ProjectDiscoveryCorrectionRequest['replacement']})!==canonicalPublicRequest(request))return null;
  return {kind:'DISCOVERY_CORRECTION',discovery_ref:request.discovery_ref,replacement_ref:value.replacement_ref as string,
    correction_reason:request.correction_reason,replacement:request.replacement};
}

/** Freezes every plain object and array of a freshly built plain value. */
function deepFreeze<T>(value: T): T {
  if (isPlainArray(value)) {
    for (const item of value) {
      deepFreeze(item);
    }
    Object.freeze(value);
    return value;
  }
  if (isPlainObject(value)) {
    for (const key of Object.keys(value)) {
      deepFreeze((value as Record<string, unknown>)[key]);
    }
    Object.freeze(value);
  }
  return value;
}
