/**
 * Project-source → original unsent draft composition proof.
 *
 * This leaf turns one actually-read project source (a project file, a project
 * record or a saved conversation reply) into an opaque, single-use proof whose
 * exact excerpt may be appended to the genuine unsent conversation draft of
 * one witnessed destination. It composes two existing owner surfaces and adds
 * no authority of its own:
 *
 * - The destination is the narrow `ProjectSourceDraftPort` below, adapted by
 *   the App from the existing conversation drafts state
 *   (`conversations/drafts.ts`) plus the existing `knowledgeDraftBinding`
 *   over the current `ProjectionContext`. The witness therefore already
 *   fences the authentic principal, root, session, binding generation and
 *   the currently observed mission association. Port and witness data are
 *   never a new grant, recipient or permission, and nothing here reads or
 *   reconstructs that binding.
 * - The source arrives only after the parent has actually re-read it from its
 *   fixed source owner with current membership and source SHA qualification.
 *   This module is a process-local composition proof, never authentication.
 *
 * Hard boundaries, deliberately enforced in code:
 * - Read capture is a private WeakMap ticket issued only while a genuine
 *   witness is live (`captureProjectSourceDraftRead`), consumed exactly once
 *   by `completeProjectSourceDraftRead`, and permanently unusable after
 *   `retireProjectSourceDraftRead`. No API here takes a boolean admission,
 *   caller root, recipient or global permission input.
 * - `completeProjectSourceDraftRead` accepts strict closed source shapes
 *   only, snapshots them through own non-accessor data descriptors (no getter
 *   execution) before any await, recomputes the SHA-256 of the exact text
 *   with WebCrypto and requires it to equal the source's declared content
 *   SHA. Canonical Macro Git identity is enforced: the exact Macro repository
 *   namespace, 40-hex commit, 40-hex blob revision, 64-hex content SHA and a
 *   canonical blob path. Retained-result or ResultSelection DTOs cannot pass:
 *   every shape is key-closed and raw result bytes are never relabelled.
 * - The witness, revision and captured method identities are re-checked
 *   before the hash and again after it; any movement refuses the proof. A
 *   proof is a private WeakMap-issued object and cannot be forged or
 *   reconstructed from its public projection alone.
 * - No storage, clock, id minting, registry, send, read, refetch or poll
 *   lives here. `KnowledgeDraftCompanion` is deliberately not imported: the
 *   App adapts that genuine existing port, and this leaf consumes only the
 *   narrow explicit port below. Integration and the actual capture-before-
 *   read / complete-after-read lifecycle stay owned by the parent.
 */

import {validateKnowledgeReadMetadata} from './project-data-observation';
import type { DraftInsertion, DraftSource } from '../../conversations/drafts';
import type { SavedConversationSourceRead } from '../../discovery/saved-conversations';
import { KNOWLEDGE_BUDGETS, KNOWLEDGE_REPOSITORY } from './knowledge-library-contract';
import type { KnowledgeSourceResult } from './knowledge-library-contract';

/* ------------------------------------------------------------------ */
/* Closed patterns and budgets                                         */
/* ------------------------------------------------------------------ */

const WORK_REF_PATTERN = /^WS:[A-Z0-9][A-Za-z0-9._-]{1,63}$/;
const HEX40_PATTERN = /^[0-9a-f]{40}$/;
const HEX64_PATTERN = /^[0-9a-f]{64}$/;
const SOURCE_REF_PATTERNS = {
  PROJECT_FILE: /^project-file\.v1\.[0-9a-f]{64}$/,
  PROJECT_RECORD: /^project-record\.v1\.[0-9a-f]{64}$/,
} as const;
const READ_REF_PATTERN = /^session-reply-[0-9a-f]{64}$/;
const ROOT_JOB_PATTERN = /^JOB-[0-9]{1,9}$/;
/** Real-calendar UTC stamp: ISO 8601 extended, offset strictly Z or +00:00. */
const UTC_STAMP_PATTERN =
  /^([0-9]{4})-([0-9]{2})-([0-9]{2})T([0-9]{2}):([0-9]{2}):([0-9]{2})(?:\.[0-9]+)?(?:Z|\+00:00)$/;
const CONTROL_CHARS_PATTERN = /[\u0000-\u001f\u007f]/;

/** Existing bounded excerpt convention shared with saved-conversation reads. */
const EXCERPT_MAX_UTF8_BYTES = 480;
/** Existing qualified-answer text limit for one saved reply body. */
const SAVED_TEXT_MAX_UTF8_BYTES = 16384;
/** The witness binding is opaque here; only sane inertness is required. */
const BINDING_MAX_CHARS = 4096;

const PATH_SEGMENT_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._-]*$/;

/* ------------------------------------------------------------------ */
/* Public contracts                                                    */
/* ------------------------------------------------------------------ */

export type ProjectSourceDraftSourceKind = 'PROJECT_FILE' | 'PROJECT_RECORD' | 'SAVED_REPLY';

/**
 * Witness over the genuine destination, produced by the App adapter from the
 * existing `knowledgeDraftBinding(currentProjectionContext, port)` plus the
 * current port revision and work ref. The binding string is opaque to this
 * leaf; it must merely be a bounded inert identifier. A witness whose work or
 * binding is invalid, or whose revision disagrees with its port snapshot
 * revision, is unavailable.
 */
export interface ProjectSourceDraftWitness {
  readonly workRef: string;
  readonly binding: string;
  readonly revision: number;
}

/**
 * Narrow destination port over the existing conversation drafts. `text`,
 * `revision` and `insertion` are one plain snapshot of the draft entry;
 * `append`/`undo` (and the optional `edit`) forward to the existing
 * `appendDraftSource`/`undoDraftSource` owner functions and return their
 * boolean. The object carries exactly these fields, all own plain data.
 * Method identities must stay stable across snapshots — a replaced method
 * invalidates every proof bound to it. `readWitness()` returns null unless
 * work and binding are valid and the revision equals this snapshot revision.
 */
export interface ProjectSourceDraftPort {
  readonly text: string;
  readonly revision: number;
  readonly insertion: DraftInsertion | null;
  append(source: DraftSource, expectedRevision: number): boolean;
  undo(identity: string, expectedRevision: number): boolean;
  edit?(): void;
  readWitness(): ProjectSourceDraftWitness | null;
}

/**
 * Narrow contract for one qualified saved-reply source read, produced by the
 * parent from the Session Bridge reference reader plus the existing qualified
 * answer validator. `text` is the exact qualified answer body and
 * `sourceTextSha256` its WebCrypto SHA-256; the reference carries the exact
 * work, read_ref, root job and request-time provenance.
 */
export type {SavedConversationSourceRead} from '../../discovery/saved-conversations';

/** Strict source union: nothing else — in particular no retained-result or
 * ResultSelection DTO, and no raw byte relabelling — can be completed. */
export type ProjectSourceDraftSource =
  | {
      readonly kind: 'PROJECT_FILE' | 'PROJECT_RECORD';
      readonly sourceRef: string;
      readonly result: KnowledgeSourceResult;
    }
  | { readonly kind: 'SAVED_REPLY'; readonly result: SavedConversationSourceRead };

/** Opaque single-use capture ticket. Holders can only pass it back. */
export interface ProjectSourceDraftReadTicket {
  readonly [ticketBrand]: true;
}

/**
 * Opaque issued proof. The public projection is safe plain data (source kind,
 * witnessed work ref and the draft source to append); the private WeakMap
 * record is the only thing that makes consumption possible, so the proof
 * cannot be forged, reconstructed from a public tuple, or downgraded to a
 * synthetic boolean.
 */
export interface ProjectSourceDraftProof {
  readonly [proofBrand]: true;
  readonly sourceKind: ProjectSourceDraftSourceKind;
  readonly workRef: string;
  readonly draftSource: DraftSource;
}

export type ProjectSourceDraftProofState = 'APPENDABLE' | 'UNDOABLE' | 'STALE';

/* ------------------------------------------------------------------ */
/* Private state                                                       */
/* ------------------------------------------------------------------ */

const ticketBrand = Symbol('mastermind.projectSourceDraft.ticket');
const proofBrand = Symbol('mastermind.projectSourceDraft.proof');

interface CapturedMethods {
  readonly append: ProjectSourceDraftPort['append'];
  readonly undo: ProjectSourceDraftPort['undo'];
  readonly readWitness: ProjectSourceDraftPort['readWitness'];
}

interface TicketRecord {
  readonly sourceIsCurrent: () => boolean;
  readonly witness: ProjectSourceDraftWitness;
  readonly methods: CapturedMethods;
}

interface ProofRecord {
  readonly sourceIsCurrent: () => boolean;
  readonly workRef: string;
  readonly binding: string;
  readonly revision: number;
  readonly methods: CapturedMethods;
  readonly draftSource: DraftSource;
}

function sourceCurrent(guard: unknown): boolean {
  try { return typeof guard === 'function' && guard() === true; } catch { return false; }
}

const tickets = new WeakMap<object, TicketRecord>();
const proofs = new WeakMap<object, ProofRecord>();

/* ------------------------------------------------------------------ */
/* Own-data strict readers (no getter execution anywhere)              */
/* ------------------------------------------------------------------ */

const NOT_OWN_DATA = Symbol('mastermind.projectSourceDraft.absent');

function ownRaw(container: object, field: string | symbol): unknown {
  if (!Object.prototype.hasOwnProperty.call(container, field)) return NOT_OWN_DATA;
  const descriptor = Object.getOwnPropertyDescriptor(container, field);
  if (!descriptor || descriptor.get !== undefined || descriptor.set !== undefined) return NOT_OWN_DATA;
  return descriptor.value;
}

function ownString(container: object, field: string): string | null {
  const value = ownRaw(container, field);
  return typeof value === 'string' ? value : null;
}

function ownInteger(container: object, field: string): number | null {
  const value = ownRaw(container, field);
  return typeof value === 'number' && Number.isSafeInteger(value) ? value : null;
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) return false;
  const proto: unknown = Object.getPrototypeOf(value);
  return proto === Object.prototype || proto === null;
}

function hasClosedKeys(value: object, allowed: readonly string[], optional:readonly string[]=[]): boolean {
  const keys=Reflect.ownKeys(value);
  if(keys.some(key=>typeof key!=='string'||!allowed.includes(key)))return false;
  if(allowed.some(key=>!optional.includes(key)&&!Object.hasOwn(value,key)))return false;
  return keys.every(key=>{const d=Object.getOwnPropertyDescriptor(value,key);return !!d&&d.enumerable&&'value' in d;});
}

const PORT_KEYS = ['text', 'revision', 'insertion', 'append', 'undo', 'edit', 'readWitness'] as const;
const INSERTION_KEYS = ['source', 'before', 'after', 'revision'] as const;
const DRAFT_SOURCE_KEYS = ['identity', 'excerpt', 'label'] as const;
const WITNESS_KEYS = ['workRef', 'binding', 'revision'] as const;
const PROJECT_SOURCE_KEYS = ['kind', 'sourceRef', 'result'] as const;
const SAVED_SOURCE_KEYS = ['kind', 'result'] as const;
const KNOWLEDGE_RESULT_KEYS = ['availability', 'source', 'document', 'reasonCodes','codeContext','dataObservation'] as const;
const POINTER_KEYS = ['repository', 'commit', 'path', 'revision', 'contentSha256', 'committedAt'] as const;
const DOCUMENT_KEYS = ['title', 'mediaType', 'contentUtf8', 'contentSha256'] as const;
const SAVED_READ_KEYS = ['state', 'reason', 'reference', 'text', 'sourceTextSha256'] as const;
const REFERENCE_KEYS = ['read_ref', 'operation_key', 'request_ref', 'request_event_id',
  'request_revision', 'requested_at', 'work_ref', 'root_job_id', 'target_ref', 'reference_only'] as const;

/* ------------------------------------------------------------------ */
/* Port, witness and insertion snapshots                               */
/* ------------------------------------------------------------------ */

interface PortSnapshot {
  readonly text: string;
  readonly revision: number;
  readonly insertion: DraftInsertion | null;
  readonly methods: CapturedMethods;
}

function isWorkRef(value: string): boolean {
  return WORK_REF_PATTERN.test(value) && !CONTROL_CHARS_PATTERN.test(value);
}

function isBinding(value: string): boolean {
  return value.length > 0 && value.length <= BINDING_MAX_CHARS && !CONTROL_CHARS_PATTERN.test(value);
}

function asPortMethod<T extends (...args: never[]) => unknown>(value: unknown): T | null {
  return typeof value === 'function' ? (value as T) : null;
}

function readDraftSourceSnapshot(container: object): DraftSource | null {
  if (!isPlainObject(container) || !hasClosedKeys(container, DRAFT_SOURCE_KEYS)) return null;
  const identity = ownString(container, 'identity');
  const excerpt = ownString(container, 'excerpt');
  const label = ownString(container, 'label');
  if (!identity || !excerpt || !label) return null;
  return { identity, excerpt, label };
}

function readInsertionSnapshot(container: object): DraftInsertion | null {
  if (!isPlainObject(container) || !hasClosedKeys(container, INSERTION_KEYS)) return null;
  const before = ownString(container, 'before');
  const after = ownString(container, 'after');
  const revision = ownInteger(container, 'revision');
  const sourceRaw = ownRaw(container, 'source');
  if (before === null || after === null || revision === null || revision < 0) return null;
  if (!isPlainObject(sourceRaw)) return null;
  const source = readDraftSourceSnapshot(sourceRaw);
  return source ? { source, before, after, revision } : null;
}

/** Strict structural read of a port; null for anything malformed. */
function readPortSnapshot(port: unknown): PortSnapshot | null {
  if (!isPlainObject(port) || !hasClosedKeys(port, PORT_KEYS,['edit'])) return null;
  const text = ownString(port, 'text');
  const revision = ownInteger(port, 'revision');
  if (text === null || revision === null || revision < 0) return null;
  const append = asPortMethod<ProjectSourceDraftPort['append']>(ownRaw(port, 'append'));
  const undo = asPortMethod<ProjectSourceDraftPort['undo']>(ownRaw(port, 'undo'));
  const readWitness = asPortMethod<ProjectSourceDraftPort['readWitness']>(ownRaw(port, 'readWitness'));
  if (!append || !undo || !readWitness) return null;
  const edit = ownRaw(port, 'edit');
  if (edit !== NOT_OWN_DATA && edit !== undefined && typeof edit !== 'function') return null;
  const insertionRaw = ownRaw(port, 'insertion');
  if (insertionRaw === null || insertionRaw === undefined) {
    return { text, revision, insertion: null, methods: { append, undo, readWitness } };
  }
  if (!isPlainObject(insertionRaw)) return null;
  const insertion = readInsertionSnapshot(insertionRaw);
  return insertion ? { text, revision, insertion, methods: { append, undo, readWitness } } : null;
}

/**
 * Safely call and validate the live witness. Returns null when it throws, is
 * malformed, carries invalid work/binding, or disagrees with the port's own
 * snapshot revision — the documented unavailable condition.
 */
function readLiveWitness(port: object, snapshot: PortSnapshot): ProjectSourceDraftWitness | null {
  let raw: unknown;
  try {
    raw = snapshot.methods.readWitness();
  } catch {
    return null;
  }
  if (!isPlainObject(raw) || !hasClosedKeys(raw, WITNESS_KEYS)) return null;
  const workRef = ownString(raw, 'workRef');
  const binding = ownString(raw, 'binding');
  const revision = ownInteger(raw, 'revision');
  if (workRef === null || binding === null || revision === null) return null;
  if (!isWorkRef(workRef) || !isBinding(binding) || revision !== snapshot.revision) return null;
  return Object.freeze({ workRef, binding, revision });
}

/** Validated, safe read of the current witness (null when unavailable).
 * Parent panels may use it before mounting the companion. */
export function projectSourceDraftWitnessOf(
  port: ProjectSourceDraftPort | null | undefined,
): ProjectSourceDraftWitness | null {
  const snapshot = readPortSnapshot(port);
  if (!snapshot) return null;
  return readLiveWitness(port as object, snapshot);
}

function sameMethods(a: CapturedMethods, b: CapturedMethods): boolean {
  return a.append === b.append && a.undo === b.undo && a.readWitness === b.readWitness;
}

/* ------------------------------------------------------------------ */
/* Source snapshots                                                    */
/* ------------------------------------------------------------------ */

interface SourceSnapshot {
  readonly kind: ProjectSourceDraftSourceKind;
  readonly identityFields: readonly string[];
  readonly label: string;
  readonly text: string;
  readonly declaredTextSha256: string;
  readonly savedWorkRef: string | null;
  readonly projectScope:Readonly<{sourceRef:string;prefix:string;repository:string;commit:string;path:string;revision:string}>|null;
}

function isCanonicalBlobPath(path: string): boolean {
  if (path.length === 0 || path.length > KNOWLEDGE_BUDGETS.path) return false;
  if (path.startsWith('/') || path.endsWith('/') || path.includes('\\')) return false;
  if (CONTROL_CHARS_PATTERN.test(path)) return false;
  return path.split('/').every(segment => PATH_SEGMENT_PATTERN.test(segment));
}

/** Strict decode of one project file/record result into detached plain data.
 * Availability, empty reason codes, the exact Macro namespace, canonical Git
 * identity and pointer/document SHA agreement are all required. */
function readProjectSnapshot(
  kind: 'PROJECT_FILE' | 'PROJECT_RECORD',
  sourceRef: unknown,
  resultRaw: unknown,
): SourceSnapshot | null {
  if (typeof sourceRef !== 'string' || !SOURCE_REF_PATTERNS[kind].test(sourceRef)) return null;
  if (!isPlainObject(resultRaw) || !hasClosedKeys(resultRaw, KNOWLEDGE_RESULT_KEYS,['codeContext','dataObservation'])) return null;
  if (ownRaw(resultRaw, 'availability') !== 'AVAILABLE') return null;
  const reasonCodes = ownRaw(resultRaw, 'reasonCodes');
  if (!Array.isArray(reasonCodes) || reasonCodes.length !== 0) return null;
  const pointerRaw = ownRaw(resultRaw, 'source');
  const documentRaw = ownRaw(resultRaw, 'document');
  if (!isPlainObject(pointerRaw) || !isPlainObject(documentRaw)) return null;
  if (!hasClosedKeys(pointerRaw, POINTER_KEYS) || !hasClosedKeys(documentRaw, DOCUMENT_KEYS)) return null;
  const repository = ownString(pointerRaw, 'repository');
  const commit = ownString(pointerRaw, 'commit');
  const path = ownString(pointerRaw, 'path');
  const revision = ownString(pointerRaw, 'revision');
  const contentSha256 = ownString(pointerRaw, 'contentSha256');
  if (repository !== KNOWLEDGE_REPOSITORY) return null;
  if (commit === null || !HEX40_PATTERN.test(commit)) return null;
  if (path === null || !isCanonicalBlobPath(path)) return null;
  if (revision === null || !HEX40_PATTERN.test(revision)) return null;
  if (contentSha256 === null || !HEX64_PATTERN.test(contentSha256)) return null;
  const text = ownString(documentRaw, 'contentUtf8');
  if (text === null || text.length === 0) return null;
  if (ownString(documentRaw, 'contentSha256') !== contentSha256) return null;
  if (utf8ByteLength(text) > KNOWLEDGE_BUDGETS.sourceContent) return null;
  let sourceWork:string|null=null;
  if(Object.hasOwn(resultRaw,'codeContext')||Object.hasOwn(resultRaw,'dataObservation')){
    const code=ownRaw(resultRaw,'codeContext');
    if(!isPlainObject(code))return null;
    sourceWork=ownString(code,'work_ref');if(!sourceWork||!isWorkRef(sourceWork))return null;
    validateKnowledgeReadMetadata({source:{commit},code_context:code,
      ...(Object.hasOwn(resultRaw,'dataObservation')?{data_observation:ownRaw(resultRaw,'dataObservation')}:{})},sourceWork);
  }
  return {
    kind,
    identityFields: [kind, sourceRef, repository, commit, path, revision],
    label: `${repository} · ${path} · ${commit} · ${revision}`,
    text,
    declaredTextSha256: contentSha256,
    savedWorkRef: sourceWork,
    projectScope:{sourceRef,prefix:kind==='PROJECT_FILE'?'project-file.v1.':'project-record.v1.',repository:kind==='PROJECT_FILE'?'macro':repository,commit,path,revision},
  };
}

/** Strict decode of one saved-reply source read. The exact reference
 * provenance (work, read_ref, root job, request time) is required and the
 * reference must still be reference-only. */
function readSavedSnapshot(resultRaw: unknown): SourceSnapshot | null {
  if (!isPlainObject(resultRaw) || !hasClosedKeys(resultRaw, SAVED_READ_KEYS)) return null;
  if (ownRaw(resultRaw, 'state') !== 'AVAILABLE' || ownRaw(resultRaw,'reason')!==null) return null;
  const referenceRaw = ownRaw(resultRaw, 'reference');
  if (!isPlainObject(referenceRaw) || !hasClosedKeys(referenceRaw, REFERENCE_KEYS)) return null;
  const workRef = ownString(referenceRaw, 'work_ref');
  const readRef = ownString(referenceRaw, 'read_ref');
  const rootJobId = ownString(referenceRaw, 'root_job_id');
  const requestedAt = ownString(referenceRaw, 'requested_at');
  if (workRef === null || !isWorkRef(workRef)) return null;
  if (readRef === null || !READ_REF_PATTERN.test(readRef)) return null;
  if (rootJobId === null || !ROOT_JOB_PATTERN.test(rootJobId)) return null;
  if (requestedAt === null || requestedAt.length > 64 || !UTC_STAMP_PATTERN.test(requestedAt)) return null;
  const operation=ownString(referenceRaw,'operation_key'),request=ownString(referenceRaw,'request_ref');
  const event=ownInteger(referenceRaw,'request_event_id'),revision=ownString(referenceRaw,'request_revision');
  const target=ownString(referenceRaw,'target_ref');
  if(!operation || !/^session-continue-[0-9a-f]{64}$/.test(operation) || CONTROL_CHARS_PATTERN.test(operation) ||
    !request || request.length>256 || /[\u0000-\u001f\u007f-\u009f]/.test(request) ||
    event===null || event<1 || !revision || !HEX64_PATTERN.test(revision) || CONTROL_CHARS_PATTERN.test(revision) ||
    !target || !/^fabric_attempt:[0-9a-f]{64}$/.test(target) || CONTROL_CHARS_PATTERN.test(target) ||
    CONTROL_CHARS_PATTERN.test(rootJobId) || CONTROL_CHARS_PATTERN.test(requestedAt))return null;
  if (ownRaw(referenceRaw, 'reference_only') !== true) return null;
  const text = ownString(resultRaw, 'text');
  const declaredTextSha256 = ownString(resultRaw, 'sourceTextSha256');
  if (text === null || text.length === 0) return null;
  if (declaredTextSha256 === null || !HEX64_PATTERN.test(declaredTextSha256)) return null;
  if (utf8ByteLength(text) > SAVED_TEXT_MAX_UTF8_BYTES) return null;
  return {
    kind: 'SAVED_REPLY',
    identityFields: ['SAVED_REPLY', readRef, operation, request, String(event), revision, rootJobId, target, requestedAt],
    label: `${readRef} · ${workRef} · ${rootJobId} · ${requestedAt}`,
    text,
    declaredTextSha256,
    savedWorkRef: workRef,
    projectScope:null,
  };
}

function readSourceSnapshot(source: unknown): SourceSnapshot | null {
  if (!isPlainObject(source)) return null;
  const kind = ownString(source, 'kind');
  if (kind === 'PROJECT_FILE' || kind === 'PROJECT_RECORD') {
    if (!hasClosedKeys(source, PROJECT_SOURCE_KEYS)) return null;
    return readProjectSnapshot(kind, ownRaw(source, 'sourceRef'), ownRaw(source, 'result'));
  }
  if (kind === 'SAVED_REPLY') {
    return hasClosedKeys(source, SAVED_SOURCE_KEYS) ? readSavedSnapshot(ownRaw(source, 'result')) : null;
  }
  return null;
}

/* ------------------------------------------------------------------ */
/* Byte and hash helpers                                               */
/* ------------------------------------------------------------------ */

const textEncoder = new TextEncoder();

function utf8ByteLength(text: string): number {
  return textEncoder.encode(text).length;
}

async function sha256Hex(text: string): Promise<string | null> {
  try {
    const subtle = globalThis.crypto?.subtle;
    if (!subtle) return null;
    const digest = await subtle.digest('SHA-256', textEncoder.encode(text));
    return Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, '0')).join('');
  } catch {
    return null;
  }
}

/** Exact first ≤480 UTF-8 bytes taken by whole Unicode code points. No
 * trim, normalize or ellipsis: CRLF, trailing spaces and surrogate pairs are
 * never repaired or summarised. */
function exactExcerpt(text: string): string | null {
  let excerpt = '';
  let bytes = 0;
  for (const point of Array.from(text)) {
    const width = utf8ByteLength(point);
    if (bytes + width > EXCERPT_MAX_UTF8_BYTES) break;
    excerpt += point;
    bytes += width;
  }
  return excerpt.length > 0 ? excerpt : null;
}

/* ------------------------------------------------------------------ */
/* Capture / retire / complete                                         */
/* ------------------------------------------------------------------ */

/**
 * Issue the single-use capture ticket for one actual source read, binding the
 * live witness and the exact port method identities. The parent must call
 * this immediately before the actual source read and pass the same ticket to
 * `completeProjectSourceDraftRead` immediately after it. Returns null when
 * the port, witness or requested work is unavailable or inconsistent.
 */
export function captureProjectSourceDraftRead(
  port: ProjectSourceDraftPort,
  workRef: string,
  sourceIsCurrent: () => boolean,
): ProjectSourceDraftReadTicket | null {
  if (!sourceCurrent(sourceIsCurrent)) return null;
  const snapshot = readPortSnapshot(port);
  if (!snapshot) return null;
  if (typeof workRef !== 'string' || !isWorkRef(workRef)) return null;
  const witness = readLiveWitness(port as object, snapshot);
  if (!witness || witness.workRef !== workRef) return null;
  const ticket: ProjectSourceDraftReadTicket = Object.freeze({ [ticketBrand]: true } as const);
  tickets.set(ticket, { witness, methods: snapshot.methods, sourceIsCurrent });
  return ticket;
}

/** Safely retire a ticket so it can never be completed. */
export function retireProjectSourceDraftRead(ticket: ProjectSourceDraftReadTicket): void {
  if (isTicket(ticket)) tickets.delete(ticket);
}

function isTicket(value: unknown): value is ProjectSourceDraftReadTicket {
  return isPlainObject(value) && ownRaw(value, ticketBrand) === true;
}

/**
 * Consume the ticket exactly once — after the parent has actually read the
 * source from its fixed source owner with current membership and SHA
 * qualification — and issue the proof, or refuse with null.
 *
 * The exact source text is snapshotted through own data descriptors before
 * any await; the SHA-256 of the exact text is recomputed with WebCrypto and
 * must equal the declared content SHA; the witness, revision and captured
 * method identities are re-checked before and again after hashing. Any
 * failure spends the ticket and returns null: the parent captures a fresh
 * read rather than retrying a stale one.
 */
export async function completeProjectSourceDraftRead(
  ticket: ProjectSourceDraftReadTicket,
  source: ProjectSourceDraftSource,
  currentPort: ProjectSourceDraftPort,
): Promise<ProjectSourceDraftProof | null> {
  try {
    if (!isTicket(ticket)) return null;
    const captured = tickets.get(ticket);
    tickets.delete(ticket);
    if (!captured || !sourceCurrent(captured.sourceIsCurrent)) return null;
    const snapshot = readSourceSnapshot(source);
    if (!snapshot) return null;
    const before = readPortSnapshot(currentPort);
    if (!before || !sameMethods(before.methods, captured.methods)) return null;
    const witnessBefore = readLiveWitness(currentPort as object, before);
    if (!witnessBefore
      || witnessBefore.workRef !== captured.witness.workRef
      || witnessBefore.binding !== captured.witness.binding
      || witnessBefore.revision !== captured.witness.revision) return null;
    if (snapshot.savedWorkRef !== null && snapshot.savedWorkRef !== witnessBefore.workRef) return null;
    if(snapshot.projectScope){
      const p=snapshot.projectScope;
      const hash=await sha256Hex([p.repository,p.commit,witnessBefore.workRef,p.path,p.revision].join('\u0000'));
      if(hash===null || p.prefix+hash!==p.sourceRef)return null;
    }
    const textSha256 = await sha256Hex(snapshot.text);
    if (textSha256 === null || textSha256 !== snapshot.declaredTextSha256) return null;
    const identity = await sha256Hex(JSON.stringify([
      'mastermind.projectSourceDraft.v1',
      witnessBefore.workRef,
      ...snapshot.identityFields,
      textSha256,
    ]));
    if (identity === null) return null;
    const after = readPortSnapshot(currentPort);
    if (!after || !sameMethods(after.methods, captured.methods)) return null;
    const witnessAfter = readLiveWitness(currentPort as object, after);
    if (!witnessAfter
      || witnessAfter.workRef !== captured.witness.workRef
      || witnessAfter.binding !== captured.witness.binding
      || witnessAfter.revision !== captured.witness.revision) return null;
    const excerpt = exactExcerpt(snapshot.text);
    if (!excerpt) return null;
    const draftSource: DraftSource = Object.freeze({ identity, excerpt, label: snapshot.label });
    const proof: ProjectSourceDraftProof = Object.freeze({
      [proofBrand]: true,
      sourceKind: snapshot.kind,
      workRef: witnessAfter.workRef,
      draftSource,
    } as const);
    if (!sourceCurrent(captured.sourceIsCurrent)) return null;
    proofs.set(proof, {
      sourceIsCurrent: captured.sourceIsCurrent,
      workRef: witnessAfter.workRef,
      binding: witnessAfter.binding,
      revision: witnessAfter.revision,
      methods: captured.methods,
      draftSource,
    });
    return proof;
  } catch {
    return null;
  }
}

/* ------------------------------------------------------------------ */
/* Currentness of an issued proof                                      */
/* ------------------------------------------------------------------ */

const STALE_CHECK = { state: 'STALE', identity: null, revision: null } as const;

interface ProofCheck {
  readonly state: ProjectSourceDraftProofState;
  readonly identity: string | null;
  readonly revision: number | null;
}

function checkProof(proof: unknown, port: unknown): ProofCheck {
  if (!isPlainObject(proof) || ownRaw(proof, proofBrand) !== true) return STALE_CHECK;
  const record = proofs.get(proof);
  if (!record || !sourceCurrent(record.sourceIsCurrent)) return STALE_CHECK;
  const snapshot = readPortSnapshot(port);
  if (!snapshot || !sameMethods(snapshot.methods, record.methods)) return STALE_CHECK;
  const witness = readLiveWitness(port as object, snapshot);
  if (!witness
    || witness.workRef !== record.workRef
    || witness.binding !== record.binding) return STALE_CHECK;
  const identity = record.draftSource.identity;
  if (snapshot.revision === record.revision) {
    return sourceCurrent(record.sourceIsCurrent)?{ state: 'APPENDABLE', identity, revision: snapshot.revision }:STALE_CHECK;
  }
  if (snapshot.revision === record.revision + 1 && snapshot.insertion
    && snapshot.insertion.source.identity === identity
    && snapshot.insertion.revision === snapshot.revision
    && snapshot.text === snapshot.insertion.after) {
    return sourceCurrent(record.sourceIsCurrent)?{ state: 'UNDOABLE', identity, revision: snapshot.revision }:STALE_CHECK;
  }
  return STALE_CHECK;
}

/**
 * Currentness of a proof against the live port. Snapshot object identity is
 * never currentness: the private proof record, the port method identities,
 * the witness work/binding and the revision are all re-derived here.
 * APPENDABLE requires the original revision; after this module's own append
 * only the matching insertion may be undone (UNDOABLE) — never a new append.
 * Everything else is STALE and must not display the private excerpt.
 */
export function checkProjectSourceDraftProof(
  proof: ProjectSourceDraftProof | null | undefined,
  port: ProjectSourceDraftPort | null | undefined,
): ProjectSourceDraftProofState {
  return checkProof(proof, port).state;
}
