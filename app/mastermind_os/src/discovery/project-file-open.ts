/**
 * Bounded, one-shot open of exactly one Search file match previously returned
 * by the canonical project file search composer (`searchProjectFiles`).
 *
 * Boundary of this composer:
 * - The caller match is re-validated FIRST, through own data descriptors
 *   only, against the exact closed `ProjectFileMatch` shape. Accessor-backed
 *   or otherwise malformed caller data fails closed as INVALID_INPUT before
 *   any owner method is touched: a hostile getter causes zero owner reads and
 *   never executes, and no `toString`/`toJSON` of caller data is ever called.
 *   Validated fields are snapshotted into detached frozen primitives before
 *   the first await, so a caller mutating the request mid-flight cannot
 *   retarget a read or the returned reference.
 * - Opening reads exactly one current catalogue through the owner's real
 *   `readCatalogue` and re-validates it with the parent's strict
 *   `validate_catalogue`. The open proceeds only for an AVAILABLE catalogue
 *   on the same work ref whose canonical macro commit equals the match's
 *   recorded commit and that lists EXACTLY ONE READABLE macro row with the
 *   match's opaque ref, revision, path and display name. No such membership
 *   means SOURCE_CHANGED with ZERO detail reads; there is no alternate, no
 *   latest-version resolution and no path-based re-resolution.
 * - The body is then read with exactly one `readSource` request carrying only
 *   `workRef`, `sourceRef`, `expectedRevision` and the caller signal, and
 *   re-validated with the parent's strict `validate_source` on the same work
 *   ref and source ref. The pointer tuple (commit, path, revision) must
 *   equal the catalogue row and match, the document media type must equal the
 *   actual row media, and the freshly computed SHA-256 over the exact UTF-8
 *   text must equal the match's recorded full-text digest. The match excerpt
 *   must be contiguous in the actual text. BOM, CRLF, CJK and emoji text is
 *   preserved byte-exactly; nothing is normalized, trimmed or re-encoded.
 * - The returned document is the parent's existing strict decoded
 *   `KnowledgeSourceResult` (deeply frozen by that validator), returned only
 *   after the final currentness check; the returned reference echoes the
 *   caller's validated match and never re-derives metadata (title, excerpt)
 *   from the freshly read body.
 * - The owner context is exactly `{ generation: string }` or null; there is
 *   no principal-scope dependency and no missing-context fallback. The
 *   context, a finite nonnegative safe-integer auth generation and the exact
 *   method identities are captured before any await and re-checked after
 *   every await (including after the digest) and immediately before the
 *   return. The fixed host independently enforces the signed principal, READ
 *   scope, current-project membership and pre/post revocation; the typed
 *   result shape below is data only and is not an authorization grant.
 * - Abort, generation drift, auth drift, method drift, hash mismatch, body
 *   mismatch or a late completion discards everything: unavailable results
 *   carry null reference and null document, and no exception text, partial
 *   content, retry, fallback or cache ever escapes.
 * - No identifier minting, randomness, clock, timers, polling, caches,
 *   persisted state, private-body indices, network, or filesystem access.
 */

import type { ProjectFileMatch, ProjectFileSearchOwner } from './project-file-search';
import {sameKnowledgeCodeContext} from '../knowledge/library/project-data-observation';
import { sha256Hex, validate_catalogue, validate_source } from '../knowledge/library/knowledge-library-contract';
import type { KnowledgeSourceResult } from '../knowledge/library/knowledge-library-contract';

/* ------------------------------------------------------------------ */
/* Closed public result                                                */
/* ------------------------------------------------------------------ */

export type ProjectFileOpenFailureReason =
  | 'INVALID_INPUT'
  | 'OWNER_UNAVAILABLE'
  | 'SOURCE_CHANGED'
  | 'INVALID_SOURCE'
  | 'OVER_BUDGET';

export interface ProjectFileOpenRequest {
  readonly workRef: string;
  readonly match: ProjectFileMatch;
  readonly signal: AbortSignal;
}

/**
 * Closed canonical open result. AVAILABLE only when every catalogue,
 * membership, source, digest and currentness check actually passed;
 * UNAVAILABLE results carry no private fields at all. Frozen detached data;
 * it never grants any authority by itself.
 */
export interface ProjectFileOpenRead {
  readonly state: 'AVAILABLE' | 'UNAVAILABLE';
  readonly reason: ProjectFileOpenFailureReason | null;
  readonly reference: ProjectFileMatch | null;
  readonly document: KnowledgeSourceResult | null;
}

/* ------------------------------------------------------------------ */
/* Bounds and scalars (mirroring the parent composer's budgets)         */
/* ------------------------------------------------------------------ */

type CanonicalRepository = 'mastermindx-market-intelligence/macro';

const CANONICAL_REPO: CanonicalRepository = 'mastermindx-market-intelligence/macro';
const WORK_REF_RE = /^WS:[A-Z0-9][A-Za-z0-9._-]{1,63}$/;
const HEX40_RE = /^[0-9a-f]{40}$/;
const HEX64_RE = /^[0-9a-f]{64}$/;
const SOURCE_REF_RE = /^project-file\.v1\.[0-9a-f]{64}$/;
const MAX_EXCERPT_BYTES = 480;
const MAX_RESULT_BYTES = 65536;
const MAX_DISPLAY_NAME_SCALARS = 256;
const MAX_PATH_SCALARS = 1024;
const MAX_COMMITTED_AT_SCALARS = 128;
const MAX_GENERATION_SCALARS = 512;
const TEXT_ENCODER = new TextEncoder();

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
    const codePoint = s.codePointAt(i) as number;
    i += codePoint > 0xffff ? 2 : 1;
    count += 1;
  }
  return count;
}

/** Rejects lone surrogates: the string must be made of Unicode scalars. */
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

/** C0/C1/DEL except LF, CR and TAB — the authored-text-safe control set. */
function hasForbiddenControlChar(s: string): boolean {
  for (let i = 0; i < s.length; i += 1) {
    const unit = s.charCodeAt(i);
    if (unit < 0x20 && unit !== 0x09 && unit !== 0x0a && unit !== 0x0d) return true;
    if (unit === 0x7f) return true;
    if (unit >= 0x80 && unit <= 0x9f) return true;
  }
  return false;
}

/** Well-formed bounded scalar string of 1..maxScalars scalars, LF/CR/TAB safe. */
function isValidText(value: unknown, maxScalars: number): value is string {
  if (typeof value !== 'string') return false;
  if (scalarLength(value) < 1 || scalarLength(value) > maxScalars) return false;
  if (hasLoneSurrogate(value)) return false;
  if (hasForbiddenControlChar(value)) return false;
  return true;
}

function isValidAuthGeneration(value: unknown): value is number {
  return typeof value === 'number' && Number.isSafeInteger(value) && value >= 0;
}

/**
 * Reads one own data property without invoking any accessor. Getter-backed
 * or missing fields return null and fail closed instead of executing
 * foreign code.
 */
function ownData(obj: unknown, key: string): { ok: true; value: unknown } | null {
  if (typeof obj !== 'object' || obj === null) return null;
  const descriptor = Object.getOwnPropertyDescriptor(obj, key);
  if (descriptor === undefined) return null;
  if (descriptor.get !== undefined || descriptor.set !== undefined) return null;
  if (!('value' in descriptor)) return null;
  return { ok: true, value: descriptor.value };
}

/** Exact closed key set on own string-keyed properties (no accessors here). */
function hasExactKeys(obj: Record<string, unknown>, expected: readonly string[]): boolean {
  const actual = Object.getOwnPropertyNames(obj).sort();
  const wanted = [...expected].sort();
  if (actual.length !== wanted.length) return false;
  for (let i = 0; i < actual.length; i += 1) {
    if (actual[i] !== wanted[i]) return false;
  }
  return true;
}

/* ------------------------------------------------------------------ */
/* Caller input snapshot (validated before any owner interaction)       */
/* ------------------------------------------------------------------ */

interface MatchSourceSnapshot {
  readonly repository: CanonicalRepository;
  readonly commit: string;
  readonly path: string;
  readonly revision: string;
  readonly contentSha256: string;
  readonly committedAt: string | null;
}

interface MatchSnapshot {
  readonly sourceRef: string;
  readonly expectedRevision: string;
  readonly displayName: string;
  readonly excerpt: string;
  readonly sourceTextSha256: string;
  readonly source: MatchSourceSnapshot;
}

interface OpenSnapshot {
  readonly workRef: string;
  readonly signal: AbortSignal;
  readonly match: MatchSnapshot;
}

type InputOutcome = { ok: true; input: OpenSnapshot } | { ok: false };

/**
 * Validates the exact closed caller data through own descriptors and
 * snapshots it into detached frozen primitives. Any accessor, missing field,
 * extra field or out-of-bound value fails closed before a single owner
 * method is touched.
 */
function captureOpenInput(request: unknown): InputOutcome {
  try {
    if (!isPlainObject(request)) return { ok: false };
    const workRef = ownData(request, 'workRef');
    if (workRef === null || typeof workRef.value !== 'string' || !WORK_REF_RE.test(workRef.value)) {
      return { ok: false };
    }
    const matchField = ownData(request, 'match');
    if (matchField === null || !isPlainObject(matchField.value)) return { ok: false };
    const signalField = ownData(request, 'signal');
    if (signalField === null || !isPlainObject(signalField.value)) return { ok: false };
    const match = captureMatch(matchField.value);
    if (match === null) return { ok: false };
    const signal = captureSignal(signalField.value);
    if (signal === null) return { ok: false };
    return {
      ok: true,
      input: Object.freeze({ workRef: workRef.value, signal, match }),
    };
  } catch {
    return { ok: false };
  }
}

/** Exact 6-field closed `ProjectFileMatch` snapshot (cross-checked tuple). */
function captureMatch(value: Record<string, unknown>): MatchSnapshot | null {
  if (
    !hasExactKeys(value, [
      'sourceRef',
      'expectedRevision',
      'displayName',
      'excerpt',
      'sourceTextSha256',
      'source',
    ])
  ) {
    return null;
  }
  const sourceRef = ownData(value, 'sourceRef');
  if (sourceRef === null || !isHex(sourceRef.value, SOURCE_REF_RE)) return null;
  const expectedRevision = ownData(value, 'expectedRevision');
  if (expectedRevision === null || !isHex(expectedRevision.value, HEX40_RE)) return null;
  const displayName = ownData(value, 'displayName');
  if (displayName === null || !isValidText(displayName.value, MAX_DISPLAY_NAME_SCALARS)) return null;
  const excerptField = ownData(value, 'excerpt');
  if (excerptField === null || typeof excerptField.value !== 'string') return null;
  const excerpt = excerptField.value;
  if (scalarLength(excerpt) < 1) return null;
  if (TEXT_ENCODER.encode(excerpt).length > MAX_EXCERPT_BYTES) return null;
  if (hasLoneSurrogate(excerpt) || hasForbiddenControlChar(excerpt)) return null;
  const digestField = ownData(value, 'sourceTextSha256');
  if (digestField === null || !isHex(digestField.value, HEX64_RE)) return null;
  const sourceField = ownData(value, 'source');
  if (sourceField === null || !isPlainObject(sourceField.value)) return null;
  const source = captureMatchSource(sourceField.value);
  if (source === null) return null;
  // The declared source tuple must agree with the match's own expectations.
  if (source.revision !== expectedRevision.value) return null;
  if (source.contentSha256 !== digestField.value) return null;
  return Object.freeze({
    sourceRef: sourceRef.value,
    expectedRevision: expectedRevision.value,
    displayName: displayName.value,
    excerpt,
    sourceTextSha256: digestField.value,
    source,
  });
}

/** Exact closed `ProjectFileMatchSource` snapshot; canonical macro only. */
function captureMatchSource(value: Record<string, unknown>): MatchSourceSnapshot | null {
  if (
    !hasExactKeys(value, ['repository', 'commit', 'path', 'revision', 'content_sha256', 'committed_at'])
  ) {
    return null;
  }
  const repository = ownData(value, 'repository');
  if (repository === null || repository.value !== CANONICAL_REPO) return null;
  const commit = ownData(value, 'commit');
  if (commit === null || !isHex(commit.value, HEX40_RE)) return null;
  const path = ownData(value, 'path');
  if (path === null || !isValidText(path.value, MAX_PATH_SCALARS)) return null;
  const revision = ownData(value, 'revision');
  if (revision === null || !isHex(revision.value, HEX40_RE)) return null;
  const digest = ownData(value, 'content_sha256');
  if (digest === null || !isHex(digest.value, HEX64_RE)) return null;
  const committedAt = ownData(value, 'committed_at');
  if (committedAt === null) return null;
  if (committedAt.value !== null && !isValidText(committedAt.value, MAX_COMMITTED_AT_SCALARS)) return null;
  return Object.freeze({
    repository: CANONICAL_REPO,
    commit: commit.value,
    path: path.value,
    revision: revision.value,
    contentSha256: digest.value,
    committedAt: committedAt.value as string | null,
  });
}

/**
 * Validates the signal shape. `aborted` is a prototype accessor on a real
 * AbortSignal, so it is read directly (never through `ownData`) and guarded
 * against throwing getters.
 */
function captureSignal(value: Record<string, unknown>): AbortSignal | null {
  try {
    const candidate = value as {
      aborted?: unknown;
      addEventListener?: unknown;
      removeEventListener?: unknown;
    };
    const aborted = candidate.aborted;
    const addEventListener = candidate.addEventListener;
    const removeEventListener = candidate.removeEventListener;
    if (typeof aborted !== 'boolean') return null;
    if (typeof addEventListener !== 'function' || typeof removeEventListener !== 'function') return null;
    return value as unknown as AbortSignal;
  } catch {
    return null;
  }
}

/* ------------------------------------------------------------------ */
/* Owner identity snapshot                                              */
/* ------------------------------------------------------------------ */

interface OwnerSnapshot {
  readonly generation: string;
  readonly authGeneration: number;
  readonly contextFn: ProjectFileSearchOwner['context'];
  readonly authFn: ProjectFileSearchOwner['authGeneration'];
  readonly readCatalogueFn: ProjectFileSearchOwner['readCatalogue'];
  readonly readSourceFn: ProjectFileSearchOwner['readSource'];
}

/**
 * Captures the actual owner context (`{ generation }` or null — there is no
 * principal-scope dependency and no fallback), a finite nonnegative
 * safe-integer auth generation and the real method identities before any
 * read. Anything missing or malformed means zero reads.
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
    const generation = ownData(ctx, 'generation');
    if (generation === null) return null;
    if (!isValidText(generation.value, MAX_GENERATION_SCALARS)) return null;
    const auth: unknown = authFn.call(owner);
    if (!isValidAuthGeneration(auth)) return null;
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
 * Re-reads the exact same context, nonnegative auth generation and method
 * identities. Called after EVERY await (including the digest) and
 * immediately before the return. Any change is drift and clears all content.
 */
function ownerUnchanged(owner: ProjectFileSearchOwner, snap: OwnerSnapshot): boolean {
  try {
    if (owner.context !== snap.contextFn) return false;
    if (owner.authGeneration !== snap.authFn) return false;
    if (owner.readCatalogue !== snap.readCatalogueFn) return false;
    if (owner.readSource !== snap.readSourceFn) return false;
    const ctx: unknown = snap.contextFn.call(owner);
    if (!isPlainObject(ctx)) return false;
    const generation = ownData(ctx, 'generation');
    if (generation === null) return false;
    if (generation.value !== snap.generation) return false;
    const auth: unknown = snap.authFn.call(owner);
    if (!isValidAuthGeneration(auth) || auth !== snap.authGeneration) return false;
    return true;
  } catch {
    return false;
  }
}

/* ------------------------------------------------------------------ */
/* Narrow identity pre-reads on owner bodies                            */
/* ------------------------------------------------------------------ */

/**
 * Own-descriptor read of one `selection.<key>` string. Getters or malformed
 * shapes return "not found" and are left to the strict parent validator,
 * which rejects them without executing them.
 */
function selectionString(body: unknown, key: string): { found: true; value: string } | { found: false } {
  if (!isPlainObject(body)) return { found: false };
  const selection = ownData(body, 'selection');
  if (selection === null || !isPlainObject(selection.value)) return { found: false };
  const entry = ownData(selection.value, key);
  if (entry === null || typeof entry.value !== 'string') return { found: false };
  return { found: true, value: entry.value };
}

/* ------------------------------------------------------------------ */
/* Catalogue and source gate                                            */
/* ------------------------------------------------------------------ */

type CatalogueResult = ReturnType<typeof validate_catalogue>;
type CatalogueFileRow = NonNullable<CatalogueResult['catalogue']>['files'][number];

/** Closed failure result: every private field is null and nothing leaks. */
function unavailableRead(reason: ProjectFileOpenFailureReason | null): ProjectFileOpenRead {
  return Object.freeze({
    state: 'UNAVAILABLE' as const,
    reason,
    reference: null,
    document: null,
  });
}

/**
 * Opens exactly one previously returned Search file match: one current
 * catalogue read, one membership gate with zero detail reads on any
 * mismatch, one opaque source read, strict parent re-validation, an actual
 * UTF-8 SHA-256 digest check and an excerpt contiguity check. Single shot:
 * no retry, no fallback, no cached search text.
 */
export async function readProjectFileMatchSource(
  request: ProjectFileOpenRequest,
  owner: ProjectFileSearchOwner,
): Promise<ProjectFileOpenRead> {
  const input = captureOpenInput(request);
  if (!input.ok) return unavailableRead('INVALID_INPUT');
  const { workRef, signal, match } = input.input;
  if (signal.aborted) return unavailableRead('OWNER_UNAVAILABLE');
  const snap = captureOwner(owner);
  if (snap === null) return unavailableRead('OWNER_UNAVAILABLE');

  /* --- One current catalogue read, strictly re-validated --- */
  let catalogueRaw: unknown;
  try {
    catalogueRaw = await snap.readCatalogueFn.call(owner, { workRef, signal });
  } catch {
    return unavailableRead('OWNER_UNAVAILABLE');
  }
  if (signal.aborted) return unavailableRead('OWNER_UNAVAILABLE');
  if (!ownerUnchanged(owner, snap)) return unavailableRead('SOURCE_CHANGED');

  // Identity first: a body for another work ref is drift, not corruption.
  const catalogueWorkRef = selectionString(catalogueRaw, 'work_ref');
  if (catalogueWorkRef.found && catalogueWorkRef.value !== workRef) {
    return unavailableRead('SOURCE_CHANGED');
  }
  let catalogueResult: CatalogueResult;
  try {
    catalogueResult = validate_catalogue(catalogueRaw, workRef);
  } catch {
    return unavailableRead('INVALID_SOURCE');
  }
  if (catalogueResult.availability !== 'AVAILABLE') return unavailableRead(null);
  const catalogue = catalogueResult.catalogue;
  if (catalogue === null) return unavailableRead('INVALID_SOURCE');
  if (catalogue.workRef !== workRef) return unavailableRead('SOURCE_CHANGED');

  /* --- Membership: EXACTLY ONE READABLE macro row for this match --- */
  if (catalogue.sourceCommit !== match.source.commit) return unavailableRead('SOURCE_CHANGED');
  let row: CatalogueFileRow | null = null;
  const files = catalogue.files;
  for (let i = 0; i < files.length; i += 1) {
    const candidate = files[i];
    if (candidate.sourceRef !== match.sourceRef) continue;
    if (row !== null) return unavailableRead('SOURCE_CHANGED'); // validator forbids; defensive
    row = candidate;
  }
  if (row === null) return unavailableRead('SOURCE_CHANGED');
  if (row.state !== 'READABLE' || row.repository !== 'macro') return unavailableRead('SOURCE_CHANGED');
  if (row.revision !== match.expectedRevision) return unavailableRead('SOURCE_CHANGED');
  if (row.path !== match.source.path) return unavailableRead('SOURCE_CHANGED');
  if (row.displayName !== match.displayName) return unavailableRead('SOURCE_CHANGED');
  if (row.mediaType === null) return unavailableRead('INVALID_SOURCE');
  if (row.contentSha256 !== null && row.contentSha256 !== match.sourceTextSha256) {
    return unavailableRead('SOURCE_CHANGED');
  }

  /* --- One opaque source read for exactly this tuple --- */
  if (signal.aborted) return unavailableRead('OWNER_UNAVAILABLE');
  if (!ownerUnchanged(owner, snap)) return unavailableRead('SOURCE_CHANGED');
  let sourceRaw: unknown;
  try {
    sourceRaw = await snap.readSourceFn.call(owner, {
      workRef,
      sourceRef: match.sourceRef,
      expectedRevision: match.expectedRevision,
      signal,
    });
  } catch {
    return unavailableRead('OWNER_UNAVAILABLE');
  }
  if (signal.aborted) return unavailableRead('OWNER_UNAVAILABLE');
  if (!ownerUnchanged(owner, snap)) return unavailableRead('SOURCE_CHANGED');

  const sourceWorkRef = selectionString(sourceRaw, 'work_ref');
  if (sourceWorkRef.found && sourceWorkRef.value !== workRef) return unavailableRead('SOURCE_CHANGED');
  const sourceRefSeen = selectionString(sourceRaw, 'source_ref');
  if (sourceRefSeen.found && sourceRefSeen.value !== match.sourceRef) return unavailableRead('SOURCE_CHANGED');

  let sourceResult: KnowledgeSourceResult;
  try {
    sourceResult = validate_source(sourceRaw, workRef, match.sourceRef);
  } catch {
    return unavailableRead('INVALID_SOURCE');
  }
  if(!sameKnowledgeCodeContext(catalogueResult.codeContext,sourceResult.codeContext))return unavailableRead('SOURCE_CHANGED');
  if (sourceResult.availability !== 'AVAILABLE' || sourceResult.source === null || sourceResult.document === null) {
    return unavailableRead(sourceResult.availability === 'UNAVAILABLE' ? null : 'INVALID_SOURCE');
  }
  const pointer = sourceResult.source;
  const document = sourceResult.document;

  /* --- Pointer tuple, media and digest agreement --- */
  if (pointer.commit !== catalogue.sourceCommit) return unavailableRead('SOURCE_CHANGED');
  if (pointer.path !== row.path) return unavailableRead('SOURCE_CHANGED');
  if (pointer.revision !== match.expectedRevision) return unavailableRead('SOURCE_CHANGED');
  if (document.mediaType !== row.mediaType) return unavailableRead('SOURCE_CHANGED');
  if (document.contentSha256 !== match.sourceTextSha256) return unavailableRead('SOURCE_CHANGED');

  let digest: string;
  try {
    digest = await sha256Hex(document.contentUtf8);
  } catch {
    return unavailableRead('INVALID_SOURCE');
  }
  if (signal.aborted) return unavailableRead('OWNER_UNAVAILABLE');
  if (!ownerUnchanged(owner, snap)) return unavailableRead('SOURCE_CHANGED');
  if (digest !== document.contentSha256 || digest !== match.sourceTextSha256) {
    return unavailableRead('SOURCE_CHANGED');
  }
  // The excerpt must be contiguous in the actual authored text (exact code
  // units: BOM, CRLF, CJK and emoji preserved, nothing normalized).
  if (!document.contentUtf8.includes(match.excerpt)) return unavailableRead('SOURCE_CHANGED');

  /* --- Detached frozen result, budgeted, re-checked before return --- */
  const reference: ProjectFileMatch = Object.freeze({
    sourceRef: match.sourceRef,
    expectedRevision: match.expectedRevision,
    displayName: match.displayName,
    excerpt: match.excerpt,
    sourceTextSha256: match.sourceTextSha256,
    source: Object.freeze({
      repository: match.source.repository,
      commit: match.source.commit,
      path: match.source.path,
      revision: match.source.revision,
      content_sha256: match.source.contentSha256,
      committed_at: match.source.committedAt,
    }),
  });
  const read: ProjectFileOpenRead = Object.freeze({
    state: 'AVAILABLE' as const,
    reason: null,
    reference,
    document: sourceResult,
  });
  let encoded: string | null = null;
  try {
    encoded = JSON.stringify(read);
  } catch {
    encoded = null;
  }
  if (signal.aborted) return unavailableRead('OWNER_UNAVAILABLE');
  if (!ownerUnchanged(owner, snap)) return unavailableRead('SOURCE_CHANGED');
  if (encoded === null || TEXT_ENCODER.encode(encoded).length > MAX_RESULT_BYTES) {
    return unavailableRead('OVER_BUDGET');
  }
  return read;
}
