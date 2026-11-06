/**
 * Strict decoder for the Mastermind workspace project-archive READ contract.
 *
 * Body schema: mastermind.workspace_project_archive.v1
 *
 * The decoder is read-only and catalogue-bound: an AVAILABLE sample is only
 * accepted when every item is a member of the qualified catalogue, the
 * coverage counts link to that catalogue, and the commit/path/hash chain
 * matches. Unavailable sources clear their data. An available empty sample proves
 * only absence of declarations in its checked records, and company_total
 * remains null. Every invalid input raises
 * Error('PROJECT_ARCHIVE_INVALID') without echoing the offending value, and
 * the decoded read is a fresh defensive copy.
 */

export type ArchiveUnavailableReason =
  | 'SOURCE_UNAVAILABLE'
  | 'SOURCE_CHANGED'
  | 'CONTENT_OVER_BUDGET';

export interface WorkstreamArchiveStamp {
  schema: 'agentos.workstream_archive.v1';
  state: 'ARCHIVED';
  archived_on: string;
  archived_by: string;
  reason: string;
}

export interface ArchivedProjectSource {
  repository: 'macro';
  commit: string;
  path: string;
  content_sha256: string;
}

export interface ArchivedProject {
  work_ref: string;
  title: string;
  objective: string;
  archive: WorkstreamArchiveStamp;
  source: ArchivedProjectSource;
}

export interface ProjectArchiveSampleCoverage {
  kind: 'QUALIFIED_CATALOGUE_SAMPLE';
  supplied_count: number;
  observed_count: number;
  company_total: null;
}

export interface ProjectArchiveSample {
  schema: 'agentos.project_archive_sample.v1';
  source_commit: string;
  coverage: ProjectArchiveSampleCoverage;
  availability: 'AVAILABLE';
  reason: null;
  items: ArchivedProject[];
  can_restore: false;
}

export interface ArchivedCatalogue {
  document_digest: string;
  macro_sha: string;
  work_refs: string[];
  qualified_catalogue_count: number;
}

export interface AvailableArchiveRead {
  schema: 'mastermind.workspace_project_archive.v1';
  availability: 'AVAILABLE';
  catalogue: ArchivedCatalogue;
  sample: ProjectArchiveSample;
  reason_codes: [];
}

export interface UnavailableArchiveRead {
  schema: 'mastermind.workspace_project_archive.v1';
  availability: 'UNAVAILABLE';
  catalogue: null;
  sample: null;
  reason_codes: ArchiveUnavailableReason[];
}

export type ProjectArchiveRead = AvailableArchiveRead | UnavailableArchiveRead;

const BODY_SCHEMA = 'mastermind.workspace_project_archive.v1';
const SAMPLE_SCHEMA = 'agentos.project_archive_sample.v1';
const ARCHIVE_SCHEMA = 'agentos.workstream_archive.v1';
const COVERAGE_KIND = 'QUALIFIED_CATALOGUE_SAMPLE';
const ARCHIVE_PATH_PREFIX = 'agentos/workstreams/WS-';
const ARCHIVE_PATH_SUFFIX = '.md';
const MAX_RESPONSE_BYTES = 262144;
const MAX_MEMBERS = 128;
const MAX_QUALIFIED_COUNT = 500;
const REASONS: readonly string[] = [
  'SOURCE_UNAVAILABLE',
  'SOURCE_CHANGED',
  'CONTENT_OVER_BUDGET',
];

const BODY_KEYS: readonly string[] = [
  'schema',
  'availability',
  'catalogue',
  'sample',
  'reason_codes',
];
const CATALOGUE_KEYS: readonly string[] = [
  'document_digest',
  'macro_sha',
  'work_refs',
  'qualified_catalogue_count',
];
const SAMPLE_KEYS: readonly string[] = [
  'schema',
  'source_commit',
  'coverage',
  'availability',
  'reason',
  'items',
  'can_restore',
];
const COVERAGE_KEYS: readonly string[] = [
  'kind',
  'supplied_count',
  'observed_count',
  'company_total',
];
const ITEM_KEYS: readonly string[] = ['work_ref', 'title', 'objective', 'archive', 'source'];
const ARCHIVE_KEYS: readonly string[] = [
  'schema',
  'state',
  'archived_on',
  'archived_by',
  'reason',
];
const SOURCE_KEYS: readonly string[] = ['repository', 'commit', 'path', 'content_sha256'];

const HEX64 = /^[0-9a-f]{64}$/;
const HEX40 = /^[0-9a-f]{40}$/;
const WORK_REF = /^WS:[A-Z0-9]+(?:-[A-Z0-9]+)*$/;
const DAY = /^[0-9]{4}-[0-9]{2}-[0-9]{2}$/;
const PYTHON_SPACE = /[\t\n\v\f\r \x1c\x1d\x1e\x1f\x85\xa0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]/;

const encoder = new TextEncoder();

function fail(): never {
  throw new Error('PROJECT_ARCHIVE_INVALID');
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) return false;
  const proto: unknown = Object.getPrototypeOf(value);
  return proto === Object.prototype || proto === null;
}

function isArray(value: unknown): value is readonly unknown[] {
  return Array.isArray(value);
}

function hasExactKeys(value: Record<string, unknown>, keys: readonly string[]): boolean {
  const own: readonly string[] = Object.keys(value);
  if (own.length !== keys.length) return false;
  for (const key of keys) {
    if (!Object.prototype.hasOwnProperty.call(value, key)) return false;
  }
  return true;
}

function isWellFormed(value: string): boolean {
  let index = 0;
  while (index < value.length) {
    const unit = value.charCodeAt(index);
    if (unit >= 0xdc00 && unit <= 0xdfff) return false;
    if (unit >= 0xd800 && unit <= 0xdbff) {
      const next = index + 1 < value.length ? value.charCodeAt(index + 1) : 0;
      if (next < 0xdc00 || next > 0xdfff) return false;
      index += 2;
      continue;
    }
    index += 1;
  }
  return true;
}

function isText(value: unknown, limit: number): value is string {
  if (typeof value !== 'string' || !isWellFormed(value)) return false;
  if (encoder.encode(value).length > limit) return false;
  for (const character of value) {
    if (!PYTHON_SPACE.test(character)) return true;
  }
  return false;
}

function isHexDigest(value: unknown, pattern: RegExp): value is string {
  return typeof value === 'string' && pattern.exec(value)?.[0] === value;
}

function isInt(value: unknown): value is number {
  return typeof value === 'number' && Number.isInteger(value);
}

function isWorkRef(value: unknown): value is string {
  return typeof value === 'string' && value.length >= 5 && value.length <= 67 && WORK_REF.exec(value)?.[0] === value;
}

function isReason(value: unknown): value is ArchiveUnavailableReason {
  return typeof value === 'string' && REASONS.includes(value);
}

function daysInMonth(year: number, month: number): number {
  if (month === 4 || month === 6 || month === 9 || month === 11) return 30;
  if (month !== 2) return 31;
  const leap = (year % 4 === 0 && year % 100 !== 0) || year % 400 === 0;
  return leap ? 29 : 28;
}

function isDay(value: unknown): value is string {
  if (typeof value !== 'string' || value.length !== 10 || !DAY.test(value)) return false;
  const year = Number(value.slice(0, 4));
  const month = Number(value.slice(5, 7));
  const day = Number(value.slice(8, 10));
  if (year < 1) return false;
  if (month < 1 || month > 12) return false;
  return day >= 1 && day <= daysInMonth(year, month);
}

function compareCodePoints(left: string, right: string): number {
  const leftPoints = Array.from(left);
  const rightPoints = Array.from(right);
  const shared = Math.min(leftPoints.length, rightPoints.length);
  for (let index = 0; index < shared; index += 1) {
    const a = leftPoints[index]?.codePointAt(0);
    const b = rightPoints[index]?.codePointAt(0);
    if (a === undefined || b === undefined) return 0;
    if (a !== b) return a < b ? -1 : 1;
  }
  if (leftPoints.length === rightPoints.length) return 0;
  return leftPoints.length < rightPoints.length ? -1 : 1;
}

function decodeUnavailable(body: Record<string, unknown>): UnavailableArchiveRead {
  if (body.catalogue !== null || body.sample !== null) fail();
  const codes = body.reason_codes;
  if (!isArray(codes) || codes.length !== 1) fail();
  const code = codes[0];
  if (!isReason(code)) fail();
  return {
    schema: BODY_SCHEMA,
    availability: 'UNAVAILABLE',
    catalogue: null,
    sample: null,
    reason_codes: [code],
  };
}

function decodeItem(
  value: unknown,
  refs: ReadonlySet<string>,
  commit: string,
): ArchivedProject {
  if (!isPlainObject(value)) fail();
  if (!hasExactKeys(value, ITEM_KEYS)) fail();

  const workRef = value.work_ref;
  if (!isWorkRef(workRef) || !refs.has(workRef)) fail();
  const title = value.title;
  if (!isText(title, 4096)) fail();
  const objective = value.objective;
  if (!isText(objective, 16384)) fail();

  const rawArchive = value.archive;
  if (!isPlainObject(rawArchive) || !hasExactKeys(rawArchive, ARCHIVE_KEYS)) fail();
  if (rawArchive.schema !== ARCHIVE_SCHEMA) fail();
  if (rawArchive.state !== 'ARCHIVED') fail();
  const archivedOn = rawArchive.archived_on;
  if (!isDay(archivedOn)) fail();
  const archivedBy = rawArchive.archived_by;
  if (!isText(archivedBy, 256)) fail();
  const archiveReason = rawArchive.reason;
  if (!isText(archiveReason, 2000)) fail();

  const rawSource = value.source;
  if (!isPlainObject(rawSource) || !hasExactKeys(rawSource, SOURCE_KEYS)) fail();
  if (rawSource.repository !== 'macro') fail();
  const sourceCommit = rawSource.commit;
  if (typeof sourceCommit !== 'string' || sourceCommit !== commit) fail();
  const path = rawSource.path;
  const expectedPath = ARCHIVE_PATH_PREFIX + workRef.slice(3) + ARCHIVE_PATH_SUFFIX;
  if (typeof path !== 'string' || path !== expectedPath) fail();
  const contentSha = rawSource.content_sha256;
  if (!isHexDigest(contentSha, HEX64)) fail();

  return {
    work_ref: workRef,
    title,
    objective,
    archive: {
      schema: ARCHIVE_SCHEMA,
      state: 'ARCHIVED',
      archived_on: archivedOn,
      archived_by: archivedBy,
      reason: archiveReason,
    },
    source: {
      repository: 'macro',
      commit: sourceCommit,
      path,
      content_sha256: contentSha,
    },
  };
}

function decodeSample(
  value: unknown,
  refs: readonly string[],
  commit: string,
): ProjectArchiveSample {
  if (!isPlainObject(value)) fail();
  if (!hasExactKeys(value, SAMPLE_KEYS)) fail();
  if (value.schema !== SAMPLE_SCHEMA) fail();
  const sourceCommit = value.source_commit;
  if (typeof sourceCommit !== 'string' || sourceCommit !== commit) fail();
  if (value.availability !== 'AVAILABLE') fail();
  if (value.reason !== null) fail();
  if (value.can_restore !== false) fail();

  const rawCoverage = value.coverage;
  if (!isPlainObject(rawCoverage) || !hasExactKeys(rawCoverage, COVERAGE_KEYS)) fail();
  if (rawCoverage.kind !== COVERAGE_KIND) fail();
  if (rawCoverage.company_total !== null) fail();
  const suppliedCount = rawCoverage.supplied_count;
  const observedCount = rawCoverage.observed_count;
  if (!isInt(suppliedCount) || !isInt(observedCount)) fail();
  if (suppliedCount !== observedCount || suppliedCount !== refs.length) fail();

  const rawItems = value.items;
  if (!isArray(rawItems) || rawItems.length > refs.length) fail();
  const members = new Set<string>(refs);
  const used = new Set<string>();
  const items: ArchivedProject[] = [];
  for (const row of rawItems) {
    const decoded = decodeItem(row, members, commit);
    if (used.has(decoded.work_ref)) fail();
    used.add(decoded.work_ref);
    items.push(decoded);
  }

  const coverage: ProjectArchiveSampleCoverage = {
    kind: COVERAGE_KIND,
    supplied_count: suppliedCount,
    observed_count: observedCount,
    company_total: null,
  };
  return {
    schema: SAMPLE_SCHEMA,
    source_commit: sourceCommit,
    coverage,
    availability: 'AVAILABLE',
    reason: null,
    items,
    can_restore: false,
  };
}

function decodeAvailable(body: Record<string, unknown>): AvailableArchiveRead {
  if (body.availability !== 'AVAILABLE') fail();
  const codes = body.reason_codes;
  if (!isArray(codes) || codes.length !== 0) fail();

  const rawCatalogue = body.catalogue;
  if (!isPlainObject(rawCatalogue)) fail();
  if (!hasExactKeys(rawCatalogue, CATALOGUE_KEYS)) fail();

  const documentDigest = rawCatalogue.document_digest;
  if (!isHexDigest(documentDigest, HEX64)) fail();
  const macroSha = rawCatalogue.macro_sha;
  if (!isHexDigest(macroSha, HEX40)) fail();

  const rawRefs = rawCatalogue.work_refs;
  if (!isArray(rawRefs) || rawRefs.length > MAX_MEMBERS) fail();
  const workRefs: string[] = [];
  const seen = new Set<string>();
  let previous: string | null = null;
  for (const candidate of rawRefs) {
    if (!isWorkRef(candidate) || seen.has(candidate)) fail();
    seen.add(candidate);
    if (previous !== null && compareCodePoints(previous, candidate) >= 0) fail();
    previous = candidate;
    workRefs.push(candidate);
  }

  const qualifiedCount = rawCatalogue.qualified_catalogue_count;
  if (!isInt(qualifiedCount)) fail();
  if (qualifiedCount < workRefs.length || qualifiedCount > MAX_QUALIFIED_COUNT) fail();

  const catalogue: ArchivedCatalogue = {
    document_digest: documentDigest,
    macro_sha: macroSha,
    work_refs: workRefs,
    qualified_catalogue_count: qualifiedCount,
  };
  const sample = decodeSample(body.sample, workRefs, macroSha);
  return {
    schema: BODY_SCHEMA,
    availability: 'AVAILABLE',
    catalogue,
    sample,
    reason_codes: [],
  };
}

function decodeArchiveBody(input: unknown): ProjectArchiveRead {
  if (!isPlainObject(input)) fail();
  const body: Record<string, unknown> = input;
  if (!hasExactKeys(body, BODY_KEYS)) fail();
  if (body.schema !== BODY_SCHEMA) fail();
  const read: ProjectArchiveRead =
    body.availability === 'UNAVAILABLE'
      ? decodeUnavailable(body)
      : decodeAvailable(body);
  const serialized = JSON.stringify({ ok: true, result: read });
  if (encoder.encode(serialized).length + 1 > MAX_RESPONSE_BYTES) fail();
  return read;
}

/** Public invalid-input boundary never exposes thrown getters or source values. */
export function decodeProjectArchive(input: unknown): ProjectArchiveRead {
  try { return decodeArchiveBody(input); }
  catch { throw new Error('PROJECT_ARCHIVE_INVALID'); }
}
