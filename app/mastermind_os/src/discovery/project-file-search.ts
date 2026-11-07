/**
 * Bounded file-content search over the canonical project catalogue and the
 * sealed per-file source reads supplied by a Mastermind project owner.
 *
 * Boundary of this composer:
 * - It consumes ALREADY DECODED strict DTOs returned by the owner's real fixed
 *   reads (the parent owns the actual sealed reader and the strict body
 *   decoders). Nothing here authenticates owner methods, widens permissions,
 *   or turns catalogue metadata into arbitrary reader authority.
 * - A single explicit query reads exactly one catalogue and at most four
 *   candidate file entries from the ordered list slice
 *   [pageStart, pageStart + 4). There is no hidden walk, no auto page
 *   advance, no retry, and no re-resolution of a different file.
 * - Sources are opened only through the owner's opaque `source_ref` plus the
 *   exact expected revision. Public source paths are metadata copied from the
 *   actual source DTO; they are never opened, fetched or joined into a URL.
 * - Every await is followed by an owner context/auth/method re-identity check
 *   and an abort check. Abort, auth drift, host drift, A-B-A drift or method
 *   drift clears all content: no partial private prefix ever escapes.
 * - No identifier minting, randomness, clock, timers, polling, caches,
 *   persisted state, private-body indices, network, or filesystem access.
 */

import {validateKnowledgeReadMetadata,sameKnowledgeCodeContext,type ProjectKnowledgeCodeContext} from '../knowledge/library/project-data-observation';

export type CanonicalSourceRepository = 'mastermindx-market-intelligence/macro';
export type FileSearchFileRepository = 'macro' | 'terminal' | 'mastermind';
export type FileSearchFileState =
  | 'READABLE'
  | 'SOURCE_MISSING'
  | 'SOURCE_INVALID'
  | 'CONTENT_OVER_BUDGET'
  | 'UNSUPPORTED_SOURCE';
export type FileSearchOriginKind = 'PRINCIPAL_UPLOAD' | 'DECLARED_ARTIFACT';
export type FileSearchViewerRelation = 'UNKNOWN' | 'CURRENT_PRINCIPAL' | 'OTHER_PRINCIPAL';
export type FileSearchMediaType = 'text/markdown' | 'text/plain';

export interface FileSearchCatalogueSourceIdentity {
  readonly repository: CanonicalSourceRepository;
  /** 40 lowercase hex characters. */
  readonly commit: string;
  /** 64 lowercase hex characters. */
  readonly workstream_sha256: string;
}

export interface FileSearchCatalogueFileCoverage {
  readonly state: 'COMPLETE' | 'PARTIAL';
  readonly declared: number;
  readonly listed: number;
  readonly omitted: number;
}

export interface FileSearchCatalogueCoverage {
  readonly files: FileSearchCatalogueFileCoverage;
  readonly records: unknown;
}

export interface FileSearchCatalogueOrigin {
  readonly kind: FileSearchOriginKind;
  readonly actor_ref: string | null;
  readonly request_sha256: string | null;
}

export interface FileSearchCatalogueFileRow {
  /** Opaque owner identity: 'project-file.v1.' + 64 lowercase hex. */
  readonly source_ref: string;
  readonly repository: FileSearchFileRepository | null;
  readonly path: string | null;
  readonly revision: string | null;
  readonly display_name: string;
  readonly media_type: FileSearchMediaType | null;
  readonly content_sha256: string | null;
  readonly state: FileSearchFileState;
  readonly origin: FileSearchCatalogueOrigin;
  readonly viewer_relation: FileSearchViewerRelation;
}

export interface FileSearchCatalogueProject {
  readonly title: string;
  readonly files: readonly FileSearchCatalogueFileRow[];
  readonly records: readonly unknown[];
  readonly memory: unknown;
  readonly coverage: FileSearchCatalogueCoverage;
}

export interface FileSearchCatalogue {
  readonly schema: 'mastermind.workspace_project_knowledge.v1';
  readonly selection: { readonly work_ref: string };
  readonly availability: 'AVAILABLE' | 'UNAVAILABLE';
  readonly reason_codes: readonly string[];
  readonly source: FileSearchCatalogueSourceIdentity | null;
  readonly project: FileSearchCatalogueProject | null;
}

export interface FileSearchSourceIdentity {
  readonly repository: CanonicalSourceRepository;
  readonly commit: string;
  readonly path: string;
  readonly revision: string;
  readonly content_sha256: string;
  readonly committed_at: string | null;
}

export interface FileSearchSourceDocument {
  readonly title: string;
  readonly media_type: FileSearchMediaType;
  readonly content_utf8: string;
  readonly content_sha256: string;
}

export interface FileSearchSource {
  readonly schema: 'mastermind.workspace_project_source.v1';
  readonly selection: { readonly work_ref: string; readonly source_ref: string };
  readonly availability: 'AVAILABLE' | 'UNAVAILABLE';
  readonly reason_codes: readonly string[];
  readonly source: FileSearchSourceIdentity | null;
  readonly document: FileSearchSourceDocument | null;
}

export interface ProjectFileSearchRequest {
  readonly workRef: string;
  readonly query: string;
  readonly signal: AbortSignal;
  /** 0..31, default 0. Values > 0 require `expectedCommit`. */
  readonly pageStart?: number;
  /** 40 lowercase hex characters from a prior actual catalogue. */
  readonly expectedCommit?: string;
}

export interface ProjectFileSearchOwnerContext {
  readonly generation: string;
}

/**
 * Narrow readonly owner surface. The methods return already decoded strict
 * real DTOs produced by the parent's actual fixed read + decoders; this
 * composer cannot authenticate them and must not try.
 */
export interface ProjectFileSearchOwner {
  context(): ProjectFileSearchOwnerContext | null;
  authGeneration(): number;
  readCatalogue(request: { workRef: string; signal: AbortSignal }): Promise<FileSearchCatalogue>;
  readSource(request: {
    workRef: string;
    sourceRef: string;
    expectedRevision: string;
    signal: AbortSignal;
  }): Promise<FileSearchSource>;
}

export interface ProjectFileMatchSource {
  readonly repository: CanonicalSourceRepository;
  readonly commit: string;
  readonly path: string;
  readonly revision: string;
  readonly content_sha256: string;
  readonly committed_at: string | null;
}

export interface ProjectFileMatch {
  readonly sourceRef: string;
  readonly expectedRevision: string;
  readonly displayName: string;
  /** Exact document content around the first match, <= 480 UTF-8 bytes. */
  readonly excerpt: string;
  /** SHA-256 of the exact full source text, hex. */
  readonly sourceTextSha256: string;
  readonly source: ProjectFileMatchSource;
}

export interface ProjectFileSearchCoverage {
  readonly status: 'COMPLETE' | 'PARTIAL';
  readonly declared: number;
  readonly listed: number;
  readonly scanned: number;
  readonly matched: number;
  readonly unavailable: number;
  readonly nextPageStart: number | null;
}

export type ProjectFileSearchFailureReason =
  | 'INVALID_INPUT'
  | 'OWNER_UNAVAILABLE'
  | 'INVALID_SOURCE'
  | 'SOURCE_CHANGED'
  | 'OVER_BUDGET';

/**
 * Closed canonical result. It never carries full source bodies, never claims
 * total company or file-corpus coverage, and is frozen detached data.
 */
export interface ProjectFileSearchResult {
  readonly state: 'AVAILABLE' | 'UNAVAILABLE';
  readonly reason: ProjectFileSearchFailureReason | null;
  readonly workRef: string;
  readonly query: string;
  readonly scope: 'CANONICAL_PROJECT_FILES';
  readonly sourceCommit: string | null;
  readonly items: readonly ProjectFileMatch[];
  readonly coverage: ProjectFileSearchCoverage;
}

const CATALOGUE_SCHEMA = 'mastermind.workspace_project_knowledge.v1';
const SOURCE_SCHEMA = 'mastermind.workspace_project_source.v1';
const CANONICAL_REPO: CanonicalSourceRepository = 'mastermindx-market-intelligence/macro';
const WORK_REF_RE = /^WS:[A-Z0-9][A-Za-z0-9._-]{1,63}$/;
const HEX40_RE = /^[0-9a-f]{40}$/;
const HEX64_RE = /^[0-9a-f]{64}$/;
const SOURCE_REF_RE = /^project-file\.v1\.[0-9a-f]{64}$/;
const MAX_PAGE = 4;
const MAX_LISTED_FILES = 32;
const MAX_PAGE_START = 31;
const MIN_QUERY_SCALARS = 2;
const MAX_QUERY_SCALARS = 128;
const MAX_CONTENT_BYTES = 32768;
const MAX_EXCERPT_BYTES = 480;
const MAX_RESULT_BYTES = 65536;
const MAX_DISPLAY_NAME_SCALARS = 256;
const MAX_PATH_SCALARS = 1024;
const MAX_COMMITTED_AT_SCALARS = 128;
const MAX_REASON_CODES = 64;
const MAX_ACTOR_REF_SCALARS = 256;
const MAX_TITLE_SCALARS = 1024;
const HEX_ALPHABET = '0123456789abcdef';
const TEXT_ENCODER = new TextEncoder();

/**
 * Reads one own data property without invoking any accessor. Malformed or
 * getter-backed DTO data therefore fails closed instead of running foreign
 * code or leaking exception text.
 */
function field(obj: unknown, key: string): { ok: true; value: unknown } | null {
  if (typeof obj !== 'object' || obj === null) return null;
  const desc = Object.getOwnPropertyDescriptor(obj, key);
  if (desc === undefined) return null;
  if (desc.get !== undefined || desc.set !== undefined) return null;
  if (!('value' in desc)) return null;
  return { ok: true, value: desc.value };
}

/** Same rule for array slots (own data properties only). */
function arrayItem(arr: unknown, index: number): { ok: true; value: unknown } | null {
  if (!Array.isArray(arr) || index < 0 || index >= arr.length) return null;
  const desc = Object.getOwnPropertyDescriptor(arr, index);
  if (desc === undefined) return null;
  if (desc.get !== undefined || desc.set !== undefined) return null;
  if (!('value' in desc)) return null;
  return { ok: true, value: desc.value };
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function isHex(value: unknown, re: RegExp): value is string {
  return typeof value === 'string' && re.test(value);
}

/** Unicode scalar count, not UTF-16 code units. */
function scalarLength(s: string): number {
  let count = 0;
  let i = 0;
  while (i < s.length) {
    const cp = s.codePointAt(i) as number;
    i += cp > 0xffff ? 2 : 1;
    count += 1;
  }
  return count;
}

function isBounded(s: string, maxScalars: number): boolean {
  return scalarLength(s) >= 1 && scalarLength(s) <= maxScalars;
}

function hasLoneSurrogate(s: string): boolean {
  for (let i = 0; i < s.length; i += 1) {
    const unit = s.charCodeAt(i);
    if (unit >= 0xd800 && unit <= 0xdbff) {
      const next = i + 1 < s.length ? s.charCodeAt(i + 1) : 0;
      if (next < 0xdc00 || next > 0xdfff) return true;
      i += 1;
    } else if (unit >= 0xdc00 && unit <= 0xdfff) {
      return true;
    }
  }
  return false;
}

/** C0, C1 and DEL with no exceptions (used for query text). */
function hasControlChar(s: string): boolean {
  for (let i = 0; i < s.length; i += 1) {
    const unit = s.charCodeAt(i);
    if (unit < 0x20) return true;
    if (unit === 0x7f) return true;
    if (unit >= 0x80 && unit <= 0x9f) return true;
  }
  return false;
}

/** C0/C1/DEL except LF, CR, TAB (used for document content). */
function hasForbiddenControlChar(s: string): boolean {
  for (let i = 0; i < s.length; i += 1) {
    const unit = s.charCodeAt(i);
    if (unit < 0x20 && unit !== 0x09 && unit !== 0x0a && unit !== 0x0d) return true;
    if (unit === 0x7f) return true;
    if (unit >= 0x80 && unit <= 0x9f) return true;
  }
  return false;
}

function isValidQuery(query: unknown): query is string {
  if (typeof query !== 'string') return false;
  const scalars = scalarLength(query);
  if (scalars < MIN_QUERY_SCALARS || scalars > MAX_QUERY_SCALARS) return false;
  if (hasLoneSurrogate(query)) return false;
  if (hasControlChar(query)) return false;
  return true;
}

/**
 * Literal (non-regex) Unicode case-insensitive search over the exact
 * document text. Returns the first match position and length in the
 * original string, or null.
 */
function findLiteralMatch(text: string, query: string): { index: number; length: number } | null {
  let re: RegExp;
  try {
    re = new RegExp(escapeRegExpLiteral(query), 'ui');
  } catch {
    return null;
  }
  let m: RegExpExecArray | null;
  try {
    m = re.exec(text);
  } catch {
    return null;
  }
  if (m === null || m[0].length === 0) return null;
  return { index: m.index, length: m[0].length };
}

function escapeRegExpLiteral(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/** SHA-256 over the exact original UTF-8 text; null when unavailable. */
async function sha256Hex(text: string): Promise<string | null> {
  const holder = globalThis as { crypto?: { subtle?: { digest(alg: string, data: Uint8Array): Promise<ArrayBuffer> } } };
  const subtle = holder.crypto?.subtle;
  if (!subtle) return null;
  try {
    const digest = await subtle.digest('SHA-256', TEXT_ENCODER.encode(text));
    const bytes = new Uint8Array(digest);
    let hex = '';
    for (let i = 0; i < bytes.length; i += 1) {
      hex += HEX_ALPHABET[bytes[i] >> 4] + HEX_ALPHABET[bytes[i] & 0x0f];
    }
    return hex;
  } catch {
    return null;
  }
}

interface OwnerSnapshot {
  readonly generation: string;
  readonly authGeneration: number;
  readonly contextFn: ProjectFileSearchOwner['context'];
  readonly authFn: ProjectFileSearchOwner['authGeneration'];
  readonly readCatalogueFn: ProjectFileSearchOwner['readCatalogue'];
  readonly readSourceFn: ProjectFileSearchOwner['readSource'];
}

/**
 * Captures the actual owner context, finite auth generation and the real
 * method identities before any read. Missing or malformed context or methods
 * means zero reads and OWNER_UNAVAILABLE.
 */
function captureOwner(owner: ProjectFileSearchOwner): OwnerSnapshot | null {
  try {
    const contextFn = owner.context;
    const authFn = owner.authGeneration;
    const readCatalogueFn = owner.readCatalogue;
    const readSourceFn = owner.readSource;
    if (typeof contextFn !== 'function') return null;
    if (typeof authFn !== 'function') return null;
    if (typeof readCatalogueFn !== 'function') return null;
    if (typeof readSourceFn !== 'function') return null;
    const ctx: unknown = contextFn.call(owner);
    if (!isPlainObject(ctx)) return null;
    const generation = field(ctx, 'generation');
    if (generation === null) return null;
    if (typeof generation.value !== 'string') return null;
    if (!isBounded(generation.value, 512)) return null;
    const auth: unknown = authFn.call(owner);
    if (typeof auth !== 'number' || !Number.isFinite(auth)) return null;
    return {
      generation: generation.value,
      authGeneration: auth,
      contextFn,
      authFn,
      readCatalogueFn,
      readSourceFn,
    };
  } catch {
    return null;
  }
}

/**
 * Re-reads the exact same context, finite auth generation and method
 * identities. Called after EVERY await, before the next source read and
 * before the final return. Any change is drift and clears all content.
 */
function ownerUnchanged(owner: ProjectFileSearchOwner, snap: OwnerSnapshot): boolean {
  try {
    if (owner.context !== snap.contextFn) return false;
    if (owner.authGeneration !== snap.authFn) return false;
    if (owner.readCatalogue !== snap.readCatalogueFn) return false;
    if (owner.readSource !== snap.readSourceFn) return false;
    const ctx: unknown = snap.contextFn.call(owner);
    if (!isPlainObject(ctx)) return false;
    const generation = field(ctx, 'generation');
    if (generation === null) return false;
    if (generation.value !== snap.generation) return false;
    const auth: unknown = snap.authFn.call(owner);
    if (typeof auth !== 'number' || !Number.isFinite(auth) || auth !== snap.authGeneration) return false;
    return true;
  } catch {
    return false;
  }
}

/** Frozen scalar-safe snapshot of one catalogue file row. */
interface CatalogueFileEntry {
  readonly valid: boolean;
  readonly sourceRef: string;
  readonly state: FileSearchFileState | null;
  readonly repository: FileSearchFileRepository | null;
  readonly path: string | null;
  readonly revision: string | null;
  readonly displayName: string;
  readonly mediaType: FileSearchMediaType | null;
  readonly contentSha256: string | null;
}

/** A row this composer may actually open: READABLE canonical macro member. */
interface ReadableCatalogueFileEntry extends CatalogueFileEntry {
  readonly valid: true;
  readonly state: 'READABLE';
  readonly repository: 'macro';
  readonly path: string;
  readonly revision: string;
  readonly displayName: string;
  readonly mediaType: FileSearchMediaType;
}

function isReadableCandidate(entry: CatalogueFileEntry): entry is ReadableCatalogueFileEntry {
  return (
    entry.valid &&
    entry.state === 'READABLE' &&
    entry.repository === 'macro' &&
    typeof entry.path === 'string' &&
    typeof entry.revision === 'string' &&
    entry.mediaType !== null
  );
}

/**
 * Decodes one row into a frozen snapshot without invoking accessors. Rows
 * that are malformed, cross-repository, or READABLE without the exact fixed
 * ref/revision/path/media metadata stay `invalid`: they count unavailable and
 * are never fetched through any path or URL.
 */
function decodeRow(row: unknown): CatalogueFileEntry {
  const invalid: CatalogueFileEntry = Object.freeze({
    valid: false,
    sourceRef: '',
    state: null,
    repository: null,
    path: null,
    revision: null,
    displayName: '',
    mediaType: null,
    contentSha256: null,
  });
  if (!isPlainObject(row)) return invalid;
  const sourceRef = field(row, 'source_ref');
  if (sourceRef === null || typeof sourceRef.value !== 'string' || !SOURCE_REF_RE.test(sourceRef.value)) return invalid;
  const repository = field(row, 'repository');
  if (repository === null) return invalid;
  if (
    repository.value !== null &&
    repository.value !== 'macro' &&
    repository.value !== 'terminal' &&
    repository.value !== 'mastermind'
  ) {
    return invalid;
  }
  const path = field(row, 'path');
  if (path === null) return invalid;
  if (path.value !== null && (typeof path.value !== 'string' || !isBounded(path.value, MAX_PATH_SCALARS))) return invalid;
  const revision = field(row, 'revision');
  if (revision === null) return invalid;
  if (revision.value !== null && !isHex(revision.value, HEX40_RE)) return invalid;
  const displayName = field(row, 'display_name');
  if (displayName === null || typeof displayName.value !== 'string' || !isBounded(displayName.value, MAX_DISPLAY_NAME_SCALARS)) {
    return invalid;
  }
  const mediaType = field(row, 'media_type');
  if (mediaType === null) return invalid;
  if (mediaType.value !== null && mediaType.value !== 'text/markdown' && mediaType.value !== 'text/plain') return invalid;
  const contentSha256 = field(row, 'content_sha256');
  if (contentSha256 === null) return invalid;
  if (contentSha256.value !== null && !isHex(contentSha256.value, HEX64_RE)) return invalid;
  const state = field(row, 'state');
  if (
    state === null ||
    (state.value !== 'READABLE' &&
      state.value !== 'SOURCE_MISSING' &&
      state.value !== 'SOURCE_INVALID' &&
      state.value !== 'CONTENT_OVER_BUDGET' &&
      state.value !== 'UNSUPPORTED_SOURCE')
  ) {
    return invalid;
  }
  const origin = field(row, 'origin');
  if (origin === null || !isPlainObject(origin.value)) return invalid;
  const originKind = field(origin.value, 'kind');
  if (originKind === null || (originKind.value !== 'PRINCIPAL_UPLOAD' && originKind.value !== 'DECLARED_ARTIFACT')) return invalid;
  const actorRef = field(origin.value, 'actor_ref');
  if (actorRef === null) return invalid;
  if (actorRef.value !== null && (typeof actorRef.value !== 'string' || !isBounded(actorRef.value, MAX_ACTOR_REF_SCALARS))) return invalid;
  const requestSha256 = field(origin.value, 'request_sha256');
  if (requestSha256 === null) return invalid;
  if (requestSha256.value !== null && !isHex(requestSha256.value, HEX64_RE)) return invalid;
  const viewerRelation = field(row, 'viewer_relation');
  if (
    viewerRelation === null ||
    (viewerRelation.value !== 'UNKNOWN' && viewerRelation.value !== 'CURRENT_PRINCIPAL' && viewerRelation.value !== 'OTHER_PRINCIPAL')
  ) {
    return invalid;
  }
  // A READABLE row must be an actual canonical macro member with the exact
  // fixed ref/40-hex revision/path/media metadata this composer can open.
  if (state.value === 'READABLE') {
    if (repository.value !== 'macro') return invalid;
    if (typeof path.value !== 'string') return invalid;
    if (typeof revision.value !== 'string') return invalid;
    if (mediaType.value === null) return invalid;
  }
  return Object.freeze({
    valid: true,
    sourceRef: sourceRef.value,
    state: state.value as FileSearchFileState,
    repository: repository.value as FileSearchFileRepository | null,
    path: path.value as string | null,
    revision: revision.value as string | null,
    displayName: displayName.value,
    mediaType: mediaType.value as FileSearchMediaType | null,
    contentSha256: contentSha256.value as string | null,
  });
}

type CatalogueOutcome =
  | { kind: 'MALFORMED' }
  | { kind: 'IDENTITY_MISMATCH' }
  | { kind: 'UNAVAILABLE' }
  | {
      kind: 'OK';
      codeContext?:ProjectKnowledgeCodeContext;
      sourceCommit: string;
      files: readonly CatalogueFileEntry[];
      declared: number;
      listed: number;
      filesPartial: boolean;
    };

/**
 * Strict narrow re-validation of the exact selection and bounds this
 * composer uses. The full catalogue validator stays in the parent; records
 * and memory contents are ignored entirely and never traversed or
 * serialized.
 */
function decodeCatalogue(body: unknown, workRef: string): CatalogueOutcome {
  if (!isPlainObject(body)) return { kind: 'MALFORMED' };
  let metadata;try{metadata=validateKnowledgeReadMetadata(body,workRef);}catch{return {kind:'MALFORMED'};}
  const schema = field(body, 'schema');
  if (schema === null || schema.value !== CATALOGUE_SCHEMA) return { kind: 'MALFORMED' };
  const selection = field(body, 'selection');
  if (selection === null || !isPlainObject(selection.value)) return { kind: 'MALFORMED' };
  const selectionWorkRef = field(selection.value, 'work_ref');
  if (selectionWorkRef === null || typeof selectionWorkRef.value !== 'string') return { kind: 'MALFORMED' };
  if (selectionWorkRef.value !== workRef) return { kind: 'IDENTITY_MISMATCH' };
  const availability = field(body, 'availability');
  if (availability === null || (availability.value !== 'AVAILABLE' && availability.value !== 'UNAVAILABLE')) {
    return { kind: 'MALFORMED' };
  }
  const reasonCodes = field(body, 'reason_codes');
  if (reasonCodes === null || !Array.isArray(reasonCodes.value) || reasonCodes.value.length > MAX_REASON_CODES) {
    return { kind: 'MALFORMED' };
  }
  for (let i = 0; i < reasonCodes.value.length; i += 1) {
    const code = arrayItem(reasonCodes.value, i);
    if (code === null || typeof code.value !== 'string') return { kind: 'MALFORMED' };
  }
  if (availability.value === 'UNAVAILABLE') return { kind: 'UNAVAILABLE' };
  const source = field(body, 'source');
  const project = field(body, 'project');
  if (source === null || project === null) return { kind: 'MALFORMED' };
  if (!isPlainObject(source.value)) return { kind: 'UNAVAILABLE' };
  const repo = field(source.value, 'repository');
  const commit = field(source.value, 'commit');
  const workstreamSha256 = field(source.value, 'workstream_sha256');
  if (repo === null || commit === null || workstreamSha256 === null) return { kind: 'MALFORMED' };
  if (repo.value !== CANONICAL_REPO) return { kind: 'MALFORMED' };
  if (!isHex(commit.value, HEX40_RE) || !isHex(workstreamSha256.value, HEX64_RE)) return { kind: 'MALFORMED' };
  if (!isPlainObject(project.value)) return { kind: 'UNAVAILABLE' };
  const title = field(project.value, 'title');
  if (title === null || typeof title.value !== 'string' || !isBounded(title.value, MAX_TITLE_SCALARS)) return { kind: 'MALFORMED' };
  const files = field(project.value, 'files');
  if (files === null || !Array.isArray(files.value) || files.value.length > MAX_LISTED_FILES) return { kind: 'MALFORMED' };
  const records = field(project.value, 'records');
  if (records === null || !Array.isArray(records.value)) return { kind: 'MALFORMED' };
  // `memory` contents are ignored entirely; only its presence is checked.
  const memory = field(project.value, 'memory');
  if (memory === null) return { kind: 'MALFORMED' };
  const coverage = field(project.value, 'coverage');
  if (coverage === null || !isPlainObject(coverage.value)) return { kind: 'MALFORMED' };
  const coverageFiles = field(coverage.value, 'files');
  if (coverageFiles === null || !isPlainObject(coverageFiles.value)) return { kind: 'MALFORMED' };
  const coverageState = field(coverageFiles.value, 'state');
  const declared = field(coverageFiles.value, 'declared');
  const listed = field(coverageFiles.value, 'listed');
  const omitted = field(coverageFiles.value, 'omitted');
  if (coverageState === null || declared === null || listed === null || omitted === null) return { kind: 'MALFORMED' };
  if (coverageState.value !== 'COMPLETE' && coverageState.value !== 'PARTIAL') return { kind: 'MALFORMED' };
  const declaredValue = declared.value;
  const listedValue = listed.value;
  const omittedValue = omitted.value;
  for (const value of [declaredValue, listedValue, omittedValue]) {
    if (typeof value !== 'number' || !Number.isSafeInteger(value) || value < 0) return { kind: 'MALFORMED' };
  }
  if (typeof declaredValue !== 'number' || typeof listedValue !== 'number' || typeof omittedValue !== 'number') {
    return { kind: 'MALFORMED' };
  }
  const coverageRecords = field(coverage.value, 'records');
  if (coverageRecords === null) return { kind: 'MALFORMED' };
  // Snapshot every candidate row synchronously, before any further await, so
  // a later mutation of the catalogue object cannot retarget the next read.
  const entries: CatalogueFileEntry[] = [];
  for (let i = 0; i < files.value.length; i += 1) {
    const row = arrayItem(files.value, i);
    if (row === null) return { kind: 'MALFORMED' };
    entries.push(decodeRow(row.value));
  }
  return {
    kind: 'OK',
    ...(metadata.codeContext?{codeContext:metadata.codeContext}:{}),
    sourceCommit: commit.value,
    files: Object.freeze(entries),
    declared: declaredValue,
    listed: listedValue,
    filesPartial: coverageState.value === 'PARTIAL',
  };
}

type SourceOutcome =
  | { kind: 'MALFORMED' }
  | { kind: 'IDENTITY_MISMATCH' }
  | { kind: 'UNAVAILABLE' }
  | { kind: 'INVALID' }
  | {
      kind: 'SYNC_OK';
      content: string;
      /** Declared digest; still verified against a fresh WebCrypto digest. */
      contentSha256: string;
      path: string;
      revision: string;
      committedAt: string | null;
    };

interface SourceExpectation {
  readonly codeContext?:ProjectKnowledgeCodeContext;
  readonly workRef: string;
  readonly sourceRef: string;
  readonly expectedRevision: string;
  readonly catalogueCommit: string;
  readonly rowPath: string;
  readonly rowMediaType: FileSearchMediaType;
  readonly rowDeclaredSha256: string | null;
}

/**
 * Strict narrow re-validation of one actual source body. Wrong work/ref,
 * commit, revision or path is identity drift for the whole query
 * (SOURCE_CHANGED, all items cleared, no prefix leakage); malformed,
 * unavailable, tampered or oversize bodies only count one unavailable entry
 * with no excerpt.
 */
function decodeSource(body: unknown, expected: SourceExpectation): SourceOutcome {
  if (!isPlainObject(body)) return { kind: 'MALFORMED' };
  let metadata;try{metadata=validateKnowledgeReadMetadata(body,expected.workRef);}catch{return {kind:'MALFORMED'};}
  if(!sameKnowledgeCodeContext(expected.codeContext,metadata.codeContext))return {kind:'IDENTITY_MISMATCH'};
  const schema = field(body, 'schema');
  if (schema === null || schema.value !== SOURCE_SCHEMA) return { kind: 'MALFORMED' };
  const selection = field(body, 'selection');
  if (selection === null || !isPlainObject(selection.value)) return { kind: 'MALFORMED' };
  const selectionWorkRef = field(selection.value, 'work_ref');
  const selectionSourceRef = field(selection.value, 'source_ref');
  if (selectionWorkRef === null || selectionSourceRef === null) return { kind: 'MALFORMED' };
  if (typeof selectionWorkRef.value !== 'string' || typeof selectionSourceRef.value !== 'string') return { kind: 'MALFORMED' };
  if (selectionWorkRef.value !== expected.workRef) return { kind: 'IDENTITY_MISMATCH' };
  if (selectionSourceRef.value !== expected.sourceRef) return { kind: 'IDENTITY_MISMATCH' };
  const availability = field(body, 'availability');
  if (availability === null || (availability.value !== 'AVAILABLE' && availability.value !== 'UNAVAILABLE')) {
    return { kind: 'MALFORMED' };
  }
  const reasonCodes = field(body, 'reason_codes');
  if (reasonCodes === null || !Array.isArray(reasonCodes.value) || reasonCodes.value.length > MAX_REASON_CODES) {
    return { kind: 'MALFORMED' };
  }
  for (let i = 0; i < reasonCodes.value.length; i += 1) {
    const code = arrayItem(reasonCodes.value, i);
    if (code === null || typeof code.value !== 'string') return { kind: 'MALFORMED' };
  }
  if (availability.value === 'UNAVAILABLE') return { kind: 'UNAVAILABLE' };
  const source = field(body, 'source');
  const document = field(body, 'document');
  if (source === null || document === null) return { kind: 'MALFORMED' };
  if (!isPlainObject(source.value)) return { kind: 'UNAVAILABLE' };
  const repo = field(source.value, 'repository');
  const commit = field(source.value, 'commit');
  const path = field(source.value, 'path');
  const revision = field(source.value, 'revision');
  const contentSha256 = field(source.value, 'content_sha256');
  const committedAt = field(source.value, 'committed_at');
  if (repo === null || commit === null || path === null || revision === null || contentSha256 === null || committedAt === null) {
    return { kind: 'MALFORMED' };
  }
  if (repo.value !== CANONICAL_REPO) return { kind: 'IDENTITY_MISMATCH' };
  if (!isHex(commit.value, HEX40_RE) || !isHex(revision.value, HEX40_RE) || !isHex(contentSha256.value, HEX64_RE)) {
    return { kind: 'MALFORMED' };
  }
  if (commit.value !== expected.catalogueCommit) return { kind: 'IDENTITY_MISMATCH' };
  if (revision.value !== expected.expectedRevision) return { kind: 'IDENTITY_MISMATCH' };
  if (typeof path.value !== 'string') return { kind: 'MALFORMED' };
  if (path.value !== expected.rowPath) return { kind: 'IDENTITY_MISMATCH' };
  if (committedAt.value !== null && (typeof committedAt.value !== 'string' || !isBounded(committedAt.value, MAX_COMMITTED_AT_SCALARS))) {
    return { kind: 'MALFORMED' };
  }
  if (!isPlainObject(document.value)) return { kind: 'UNAVAILABLE' };
  const title = field(document.value, 'title');
  if (title === null || typeof title.value !== 'string' || !isBounded(title.value, MAX_TITLE_SCALARS)) return { kind: 'MALFORMED' };
  const mediaType = field(document.value, 'media_type');
  if (mediaType === null || (mediaType.value !== 'text/markdown' && mediaType.value !== 'text/plain')) return { kind: 'MALFORMED' };
  if (mediaType.value !== expected.rowMediaType) return { kind: 'INVALID' };
  const contentUtf8 = field(document.value, 'content_utf8');
  const documentSha256 = field(document.value, 'content_sha256');
  if (contentUtf8 === null || documentSha256 === null) return { kind: 'MALFORMED' };
  if (typeof contentUtf8.value !== 'string' || !isHex(documentSha256.value, HEX64_RE)) return { kind: 'MALFORMED' };
  const content = contentUtf8.value;
  if (TEXT_ENCODER.encode(content).length > MAX_CONTENT_BYTES) return { kind: 'INVALID' };
  if (hasForbiddenControlChar(content)) return { kind: 'INVALID' };
  if (hasLoneSurrogate(content)) return { kind: 'INVALID' };
  if (contentSha256.value !== documentSha256.value) return { kind: 'INVALID' };
  // Declared uploaded digest, when the row carries one, must agree too.
  if (expected.rowDeclaredSha256 !== null && expected.rowDeclaredSha256 !== documentSha256.value) return { kind: 'INVALID' };
  return {
    kind: 'SYNC_OK',
    content,
    contentSha256: documentSha256.value,
    path: path.value,
    revision: revision.value,
    committedAt: committedAt.value as string | null,
  };
}

interface ValidatedInput {
  readonly workRef: string;
  readonly query: string;
  readonly pageStart: number;
  readonly expectedCommit: string | null;
  readonly signal: AbortSignal;
}

type InputOutcome =
  | { ok: true; input: ValidatedInput }
  | { ok: false; echoWorkRef: string; echoQuery: string };

/**
 * Snapshots and validates the request before any read. Invalid or missing
 * input means zero reads; unbounded invalid values are never echoed back.
 */
function captureInput(request: unknown): InputOutcome {
  let echoWorkRef = '';
  let echoQuery = '';
  try {
    if (!isPlainObject(request)) return { ok: false, echoWorkRef, echoQuery };
    const workRef = field(request, 'workRef');
    const query = field(request, 'query');
    if (workRef === null || query === null) return { ok: false, echoWorkRef, echoQuery };
    if (typeof workRef.value === 'string' && WORK_REF_RE.test(workRef.value)) echoWorkRef = workRef.value;
    if (isValidQuery(query.value)) echoQuery = query.value;
    if (echoWorkRef === '' || echoQuery === '') return { ok: false, echoWorkRef, echoQuery };
    const signal = field(request, 'signal');
    if (signal === null || !isPlainObject(signal.value)) return { ok: false, echoWorkRef, echoQuery };
    // `aborted` is a prototype accessor on a real AbortSignal, so it is read
    // directly (never through `field`) and guarded against throwing getters.
    let aborted: unknown;
    let addEventListener: unknown;
    let removeEventListener: unknown;
    try {
      const candidate = signal.value as {
        aborted?: unknown;
        addEventListener?: unknown;
        removeEventListener?: unknown;
      };
      aborted = candidate.aborted;
      addEventListener = candidate.addEventListener;
      removeEventListener = candidate.removeEventListener;
    } catch {
      return { ok: false, echoWorkRef, echoQuery };
    }
    if (typeof aborted !== 'boolean' || typeof addEventListener !== 'function' || typeof removeEventListener !== 'function') {
      return { ok: false, echoWorkRef, echoQuery };
    }
    const pageStartField = field(request, 'pageStart');
    let pageStart = 0;
    if (pageStartField !== null) {
      const value = pageStartField.value;
      if (typeof value !== 'number' || !Number.isSafeInteger(value) || value < 0 || value > MAX_PAGE_START) {
        return { ok: false, echoWorkRef, echoQuery };
      }
      pageStart = value;
    }
    const expectedCommitField = field(request, 'expectedCommit');
    let expectedCommit: string | null = null;
    if (expectedCommitField !== null) {
      const value = expectedCommitField.value;
      if (typeof value !== 'string' || !HEX40_RE.test(value)) return { ok: false, echoWorkRef, echoQuery };
      expectedCommit = value;
    }
    if (pageStart > 0 && expectedCommit === null) return { ok: false, echoWorkRef, echoQuery };
    return {
      ok: true,
      input: {
        workRef: echoWorkRef,
        query: echoQuery,
        pageStart,
        expectedCommit,
        signal: signal.value as unknown as AbortSignal,
      },
    };
  } catch {
    return { ok: false, echoWorkRef, echoQuery };
  }
}

interface GraphemeSegmenterLike {
  segment(input: string): Iterable<{ readonly index: number }>;
}

function getGraphemeSegmenter(): GraphemeSegmenterLike | null {
  try {
    const holder = globalThis as {
      Intl?: { Segmenter?: new (locales?: string[], options?: { granularity?: string }) => GraphemeSegmenterLike };
    };
    const Segmenter = holder.Intl?.Segmenter;
    if (typeof Segmenter !== 'function') return null;
    return new Segmenter(undefined, { granularity: 'grapheme' });
  } catch {
    return null;
  }
}

/** Start index of the scalar that ends at `index`, or -1 at the text start. */
function prevScalarStart(text: string, index: number): number {
  if (index <= 0) return -1;
  let start = index - 1;
  const unit = text.charCodeAt(start);
  if (unit >= 0xdc00 && unit <= 0xdfff && start > 0) {
    const prev = text.charCodeAt(start - 1);
    if (prev >= 0xd800 && prev <= 0xdbff) start -= 1;
  }
  return start;
}

/** End index (exclusive) of the scalar that starts at `index`, or null. */
function nextScalarEnd(text: string, index: number): number | null {
  if (index >= text.length) return null;
  const codePoint = text.codePointAt(index) as number;
  return index + (codePoint > 0xffff ? 2 : 1);
}

function largestBoundaryAtOrBefore(boundaries: readonly number[], target: number): number | null {
  for (let i = boundaries.length - 1; i >= 0; i -= 1) {
    const boundary = boundaries[i];
    if (boundary <= target) return boundary;
  }
  return null;
}

/**
 * Exact excerpt of the document text around the first match: at most
 * MAX_EXCERPT_BYTES UTF-8 bytes, cut only at scalar/grapheme boundaries.
 * No ellipsis, summary or filename is ever added.
 */
function buildExcerpt(text: string, matchStart: number, matchLength: number): string {
  const segmenter = getGraphemeSegmenter();
  const byteLength = (slice: string): number => TEXT_ENCODER.encode(slice).length;
  const matchEnd = matchStart + matchLength;
  let windowStart = matchStart;
  let windowEnd = matchEnd;
  const matchBytes = byteLength(text.slice(windowStart, windowEnd));
  if (matchBytes > MAX_EXCERPT_BYTES) {
    // The match itself exceeds the budget: cut inside the match at a scalar
    // boundary instead of fabricating a shorter stand-in.
    while (windowEnd > windowStart && byteLength(text.slice(windowStart, windowEnd)) > MAX_EXCERPT_BYTES) {
      const next = prevScalarStart(text, windowEnd);
      if (next <= windowStart) break;
      windowEnd = next;
    }
  } else {
    let remaining = MAX_EXCERPT_BYTES - matchBytes;
    let leftUsed = 0;
    let rightUsed = 0;
    const leftBudget = Math.floor(remaining / 2);
    while (leftUsed < leftBudget) {
      const start = prevScalarStart(text, windowStart);
      if (start < 0) break;
      const bytes = byteLength(text.slice(start, windowStart));
      if (leftUsed + bytes > leftBudget) break;
      leftUsed += bytes;
      windowStart = start;
    }
    const rightBudget = remaining - leftUsed;
    while (rightUsed < rightBudget) {
      const end = nextScalarEnd(text, windowEnd);
      if (end === null) break;
      const bytes = byteLength(text.slice(windowEnd, end));
      if (rightUsed + bytes > rightBudget) break;
      rightUsed += bytes;
      windowEnd = end;
    }
    // Context that was short on one side is re-offered to the other side.
    let leftover = remaining - leftUsed - rightUsed;
    while (leftover > 0) {
      const start = prevScalarStart(text, windowStart);
      if (start < 0) break;
      const bytes = byteLength(text.slice(start, windowStart));
      if (leftUsed + bytes > remaining - rightUsed) break;
      leftUsed += bytes;
      windowStart = start;
      leftover = remaining - leftUsed - rightUsed;
    }
  }
  if (segmenter !== null) {
    // Shrink-only snap to grapheme boundaries; never cut into the match.
    const boundaries: number[] = [];
    try {
      for (const segment of segmenter.segment(text)) {
        const index = segment.index;
        if (index > windowEnd) break;
        if (boundaries.length === 0 || index > boundaries[boundaries.length - 1]) boundaries.push(index);
      }
    } catch {
      boundaries.length = 0;
    }
    if (boundaries.length > 0) {
      const snappedStart = largestBoundaryAtOrBefore(boundaries, windowStart);
      if (snappedStart !== null && snappedStart <= matchStart) windowStart = snappedStart;
      const snappedEnd = largestBoundaryAtOrBefore(boundaries, windowEnd);
      if (snappedEnd !== null && snappedEnd >= matchEnd) windowEnd = snappedEnd;
    }
  }
  let excerpt = text.slice(windowStart, windowEnd);
  while (byteLength(excerpt) > MAX_EXCERPT_BYTES) {
    const next = prevScalarStart(text, windowEnd);
    if (next <= windowStart) break;
    windowEnd = next;
    excerpt = text.slice(windowStart, windowEnd);
  }
  return excerpt;
}

/**
 * Closed failure result: empty items, null sourceCommit, null nextPageStart
 * and zero counters. Nothing about the failure echoes unbounded input,
 * exception text, provider details or private body content.
 */
function unavailableResult(
  reason: ProjectFileSearchFailureReason | null,
  workRef: string,
  query: string,
): ProjectFileSearchResult {
  return Object.freeze({
    state: 'UNAVAILABLE',
    reason,
    workRef,
    query,
    scope: 'CANONICAL_PROJECT_FILES' as const,
    sourceCommit: null,
    items: Object.freeze([]) as readonly ProjectFileMatch[],
    coverage: Object.freeze({
      status: 'PARTIAL' as const,
      declared: 0,
      listed: 0,
      scanned: 0,
      matched: 0,
      unavailable: 0,
      nextPageStart: null,
    }),
  });
}

/**
 * Runs one explicit bounded file-content search. Reads one catalogue, then
 * at most four candidate entries from the ordered list slice; every await is
 * followed by owner/abort re-identity checks that clear all content on any
 * drift.
 */
export async function searchProjectFiles(
  request: ProjectFileSearchRequest,
  owner: ProjectFileSearchOwner,
): Promise<ProjectFileSearchResult> {
  const input = captureInput(request);
  if (!input.ok) return unavailableResult('INVALID_INPUT', input.echoWorkRef, input.echoQuery);
  // Values are snapshotted primitives: a caller mutating the request object
  // mid-flight cannot retarget later reads.
  const { workRef, query, pageStart, expectedCommit, signal } = input.input;
  if (signal.aborted) return unavailableResult('OWNER_UNAVAILABLE', workRef, query);
  const snap = captureOwner(owner);
  if (snap === null) return unavailableResult('OWNER_UNAVAILABLE', workRef, query);

  let catalogueBody: unknown;
  try {
    catalogueBody = await snap.readCatalogueFn.call(owner, { workRef, signal });
  } catch {
    return unavailableResult('OWNER_UNAVAILABLE', workRef, query);
  }
  if (signal.aborted) return unavailableResult('OWNER_UNAVAILABLE', workRef, query);
  if (!ownerUnchanged(owner, snap)) return unavailableResult('SOURCE_CHANGED', workRef, query);

  const catalogue = decodeCatalogue(catalogueBody, workRef);
  if (catalogue.kind === 'MALFORMED') return unavailableResult('INVALID_SOURCE', workRef, query);
  if (catalogue.kind === 'IDENTITY_MISMATCH') return unavailableResult('SOURCE_CHANGED', workRef, query);
  if (catalogue.kind === 'UNAVAILABLE') return unavailableResult(null, workRef, query);

  if (expectedCommit !== null && expectedCommit !== catalogue.sourceCommit) {
    // Optimistic concurrency against the current catalogue commit: no body reads.
    return unavailableResult('SOURCE_CHANGED', workRef, query);
  }

  const sliceEnd = Math.min(pageStart + MAX_PAGE, catalogue.files.length);
  const items: ProjectFileMatch[] = [];
  const seenRefs = new Set<string>();
  let scanned = 0;
  let matched = 0;
  let unavailable = 0;
  let sourceReads = 0;

  for (let index = pageStart; index < sliceEnd; index += 1) {
    const entry = catalogue.files[index];
    if (entry === undefined) break;
    scanned += 1;
    if (sourceReads >= MAX_PAGE) break;
    if (!isReadableCandidate(entry) || seenRefs.has(entry.sourceRef)) {
      // Non-READABLE, invalid or duplicate identity: unavailable, no body read,
      // and never any fetch through a path or URL.
      unavailable += 1;
      continue;
    }
    seenRefs.add(entry.sourceRef);
    if (signal.aborted) return unavailableResult('OWNER_UNAVAILABLE', workRef, query);
    if (!ownerUnchanged(owner, snap)) return unavailableResult('SOURCE_CHANGED', workRef, query);
    let sourceBody: unknown;
    sourceReads += 1;
    try {
      sourceBody = await snap.readSourceFn.call(owner, {
        workRef,
        sourceRef: entry.sourceRef,
        expectedRevision: entry.revision,
        signal,
      });
    } catch {
      unavailable += 1;
      continue;
    }
    if (signal.aborted) return unavailableResult('OWNER_UNAVAILABLE', workRef, query);
    if (!ownerUnchanged(owner, snap)) return unavailableResult('SOURCE_CHANGED', workRef, query);
    const source = decodeSource(sourceBody, {
      ...(catalogue.codeContext?{codeContext:catalogue.codeContext}:{}),
      workRef,
      sourceRef: entry.sourceRef,
      expectedRevision: entry.revision,
      catalogueCommit: catalogue.sourceCommit,
      rowPath: entry.path,
      rowMediaType: entry.mediaType,
      rowDeclaredSha256: entry.contentSha256,
    });
    if (source.kind === 'IDENTITY_MISMATCH') {
      // Wrong work/ref, commit, revision or path: the whole query becomes
      // SOURCE_CHANGED and every collected item is dropped to prevent prefix
      // leakage. No retry and no re-resolution of another file.
      return unavailableResult('SOURCE_CHANGED', workRef, query);
    }
    if (source.kind !== 'SYNC_OK') {
      unavailable += 1;
      continue;
    }
    const digest = await sha256Hex(source.content);
    if (signal.aborted) return unavailableResult('OWNER_UNAVAILABLE', workRef, query);
    if (!ownerUnchanged(owner, snap)) return unavailableResult('SOURCE_CHANGED', workRef, query);
    if (digest === null || digest !== source.contentSha256) {
      unavailable += 1;
      continue;
    }
    const match = findLiteralMatch(source.content, query);
    if (match === null) continue;
    const excerpt = buildExcerpt(source.content, match.index, match.length);
    items.push(
      Object.freeze({
        sourceRef: entry.sourceRef,
        expectedRevision: entry.revision,
        displayName: entry.displayName,
        excerpt,
        sourceTextSha256: digest,
        source: Object.freeze({
          repository: CANONICAL_REPO,
          commit: catalogue.sourceCommit,
          path: source.path,
          revision: source.revision,
          content_sha256: digest,
          committed_at: source.committedAt,
        }),
      }),
    );
    matched += 1;
  }

  if (signal.aborted) return unavailableResult('OWNER_UNAVAILABLE', workRef, query);
  if (!ownerUnchanged(owner, snap)) return unavailableResult('SOURCE_CHANGED', workRef, query);

  const hasMoreEntries = sliceEnd < catalogue.files.length;
  const partial = catalogue.filesPartial || unavailable > 0 || hasMoreEntries;
  const result: ProjectFileSearchResult = Object.freeze({
    state: 'AVAILABLE',
    reason: null,
    workRef,
    query,
    scope: 'CANONICAL_PROJECT_FILES' as const,
    sourceCommit: catalogue.sourceCommit,
    items: Object.freeze(items) as readonly ProjectFileMatch[],
    coverage: Object.freeze({
      status: partial ? 'PARTIAL' : 'COMPLETE',
      declared: catalogue.declared,
      listed: catalogue.listed,
      scanned,
      matched,
      unavailable,
      nextPageStart: hasMoreEntries ? sliceEnd : null,
    }),
  });
  let encoded: string | null = null;
  try {
    encoded = JSON.stringify(result);
  } catch {
    encoded = null;
  }
  if (encoded === null || TEXT_ENCODER.encode(encoded).length > MAX_RESULT_BYTES) {
    return unavailableResult('OVER_BUDGET', workRef, query);
  }
  return result;
}
