/**
 * Strict standalone decoder for `mastermind.workspace_project_direction.v1`
 * accepted-direction reads.
 *
 * Pure decoding only: no I/O, no network, no Git, no runtime/UI/publisher
 * authority, and no date/objective/adoption inference. The decoded value is
 * deeply detached from the caller-supplied input and defensively frozen.
 */

export type DirectionSelection = { work_ref: string };

export type DirectionSource = {
  repository: string;
  commit: string;
  path: string;
  content_sha256: string;
};

export type DirectionRevision = {
  decision_ref: string;
  answer: string;
  rationale: string;
  decided_by: string;
  decided_at: string;
  date_precision: 'DAY';
  predecessor: string | null;
  source: DirectionSource;
};

type DirectionHistory = {
  revisions: DirectionRevision[];
  has_more: boolean;
  total_count: number | null;
};

export type AcceptedDirectionRead =
  | {
      schema: 'mastermind.workspace_project_direction.v1';
      selection: DirectionSelection;
      availability: 'AVAILABLE';
      source: DirectionSource;
      direction: {
        work_ref: string;
        workstream_source: DirectionSource;
        current: DirectionRevision;
        history: DirectionHistory;
      };
      reason_codes: [];
    }
  | {
      schema: 'mastermind.workspace_project_direction.v1';
      selection: DirectionSelection;
      availability: 'UNAVAILABLE';
      source: null;
      direction: null;
      reason_codes: string[];
    };

const SCHEMA = 'mastermind.workspace_project_direction.v1';
const REPOSITORY = 'mastermindx-market-intelligence/macro';
const BODY_KEYS = ['schema', 'selection', 'availability', 'source', 'direction', 'reason_codes'];
const SOURCE_KEYS = ['repository', 'commit', 'path', 'content_sha256'];
const DIRECTION_KEYS = ['work_ref', 'workstream_source', 'current', 'history'];
const HISTORY_KEYS = ['revisions', 'has_more', 'total_count'];
const REVISION_KEYS = [
  'decision_ref',
  'answer',
  'rationale',
  'decided_by',
  'decided_at',
  'date_precision',
  'predecessor',
  'source',
];
const REASON_CODES = [
  'NOT_DECLARED',
  'SOURCE_UNAVAILABLE',
  'SOURCE_CHANGED',
  'RECORD_NOT_FOUND',
  'RECORD_INVALID',
  'LINEAGE_CONFLICT',
  'LINEAGE_INCOMPLETE',
  'CONTENT_OVER_BUDGET',
];
const REASON_CODE_SET = new Set<string>(REASON_CODES);

const COMMIT_PATTERN = /^[0-9a-f]{40}$/;
const SHA256_PATTERN = /^[0-9a-f]{64}$/;
const DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/;
const KEY_PATTERN = /^[A-Z0-9]+(?:-[A-Z0-9]+)*$/;

const WORK_KEY_MAX = 64;
const DECISION_KEY_MAX = 128;
const TEXT_MAX = 4096;
const DECIDED_BY_MAX = 256;
const MAX_HISTORY_REVISIONS = 7;
const WIRE_BYTE_BUDGET = 65536;

function invalid(): Error {
  return new Error('DIRECTION_INVALID');
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function hasExactKeys(value: Record<string, unknown>, keys: readonly string[]): boolean {
  const actual = Object.keys(value);
  if (actual.length !== keys.length) return false;
  for (const key of keys) {
    if (!Object.prototype.hasOwnProperty.call(value, key)) return false;
  }
  return true;
}

function isUpperKebabKey(key: string, maxLength: number): boolean {
  return key.length >= 2 && key.length <= maxLength && KEY_PATTERN.test(key);
}

function isWorkRef(value: string): boolean {
  return value.startsWith('WS:') && isUpperKebabKey(value.slice(3), WORK_KEY_MAX);
}

function isDecisionRef(value: string): boolean {
  return value.startsWith('DEC:') && isUpperKebabKey(value.slice(4), DECISION_KEY_MAX);
}

function utf8ByteLength(value: string): number {
  return new TextEncoder().encode(value).byteLength;
}

function boundedText(value: unknown, limit: number): value is string {
  if (typeof value !== 'string' || !value.trim()) return false;
  for (const character of value) {
    const point = character.codePointAt(0)!;
    if (point >= 0xd800 && point <= 0xdfff) return false;
  }
  return utf8ByteLength(value) <= limit;
}

function isCalendarDate(value: string): boolean {
  if (!DATE_PATTERN.test(value)) return false;
  const year = Number(value.slice(0, 4));
  const month = Number(value.slice(5, 7));
  const day = Number(value.slice(8, 10));
  if (year < 1 || year > 9999 || month < 1 || month > 12) return false;
  const leapYear = (year % 4 === 0 && year % 100 !== 0) || year % 400 === 0;
  const monthLengths = [31, leapYear ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  return day >= 1 && day <= monthLengths[month - 1];
}

function decodeSource(value: unknown, expectedPath: string): DirectionSource {
  if (!isPlainObject(value) || !hasExactKeys(value, SOURCE_KEYS)) throw invalid();
  const repository = value.repository;
  if (typeof repository !== 'string' || repository !== REPOSITORY) throw invalid();
  const commit = value.commit;
  if (typeof commit !== 'string' || !COMMIT_PATTERN.test(commit)) throw invalid();
  const path = value.path;
  if (typeof path !== 'string' || path !== expectedPath) throw invalid();
  const contentSha256 = value.content_sha256;
  if (typeof contentSha256 !== 'string' || !SHA256_PATTERN.test(contentSha256)) throw invalid();
  return { repository, commit, path, content_sha256: contentSha256 };
}

function sourcesEqual(left: DirectionSource, right: DirectionSource): boolean {
  return (
    left.repository === right.repository &&
    left.commit === right.commit &&
    left.path === right.path &&
    left.content_sha256 === right.content_sha256
  );
}

function decodeRevision(value: unknown, bodySource: DirectionSource): DirectionRevision {
  if (!isPlainObject(value) || !hasExactKeys(value, REVISION_KEYS)) throw invalid();
  const decisionRef = value.decision_ref;
  if (typeof decisionRef !== 'string' || !isDecisionRef(decisionRef)) throw invalid();
  const answer = value.answer;
  const rationale = value.rationale;
  const decidedBy = value.decided_by;
  if (!boundedText(answer, TEXT_MAX) || !boundedText(rationale, TEXT_MAX) ||
      !boundedText(decidedBy, DECIDED_BY_MAX)) throw invalid();
  const decidedAt = value.decided_at;
  if (typeof decidedAt !== 'string' || !isCalendarDate(decidedAt)) throw invalid();
  if (value.date_precision !== 'DAY') throw invalid();
  let predecessor: string | null = null;
  if (value.predecessor !== null) {
    if (typeof value.predecessor !== 'string') throw invalid();
    if (!isDecisionRef(value.predecessor)) throw invalid();
    if (value.predecessor === decisionRef) throw invalid();
    predecessor = value.predecessor;
  }
  const source = decodeSource(
    value.source,
    'agentos/decisions/DEC-' + decisionRef.slice(4) + '.md',
  );
  if (source.repository !== bodySource.repository || source.commit !== bodySource.commit) {
    throw invalid();
  }
  return {
    decision_ref: decisionRef,
    answer,
    rationale,
    decided_by: decidedBy,
    decided_at: decidedAt,
    date_precision: 'DAY',
    predecessor,
    source,
  };
}

function decodeAvailableState(
  body: Record<string, unknown>,
  selected: DirectionSelection,
  selection: DirectionSelection,
): AcceptedDirectionRead {
  const workKey = selected.work_ref.slice(3);
  const workstreamPath = 'agentos/workstreams/WS-' + workKey + '.md';
  const source = decodeSource(body.source, workstreamPath);
  const direction = body.direction;
  if (!isPlainObject(direction) || !hasExactKeys(direction, DIRECTION_KEYS)) throw invalid();
  const directionWorkRef = direction.work_ref;
  if (typeof directionWorkRef !== 'string' || directionWorkRef !== selected.work_ref) {
    throw invalid();
  }
  const workstreamSource = decodeSource(direction.workstream_source, workstreamPath);
  if (!sourcesEqual(workstreamSource, source)) throw invalid();
  const current = decodeRevision(direction.current, source);
  const history = direction.history;
  if (!isPlainObject(history) || !hasExactKeys(history, HISTORY_KEYS)) throw invalid();
  const historyRows = history.revisions;
  if (!Array.isArray(historyRows) || historyRows.length > MAX_HISTORY_REVISIONS) {
    throw invalid();
  }
  const revisions: DirectionRevision[] = [];
  for (const row of historyRows) revisions.push(decodeRevision(row, source));
  const hasMore = history.has_more;
  if (typeof hasMore !== 'boolean') throw invalid();
  const totalCount = history.total_count;
  const rows: DirectionRevision[] = [current, ...revisions];
  const seenRefs = new Set<string>();
  for (const row of rows) {
    if (seenRefs.has(row.decision_ref)) throw invalid();
    seenRefs.add(row.decision_ref);
  }
  for (let index = 0; index < rows.length - 1; index += 1) {
    if (rows[index].predecessor !== rows[index + 1].decision_ref) throw invalid();
  }
  const lastRow = rows[rows.length - 1];
  let resolvedTotalCount: number | null;
  if (hasMore) {
    if (lastRow.predecessor === null) throw invalid();
    if (seenRefs.has(lastRow.predecessor)) throw invalid();
    if (totalCount !== null) throw invalid();
    resolvedTotalCount = null;
  } else {
    if (lastRow.predecessor !== null) throw invalid();
    if (
      typeof totalCount !== 'number' ||
      !Number.isInteger(totalCount) ||
      totalCount !== rows.length
    ) {
      throw invalid();
    }
    resolvedTotalCount = totalCount;
  }
  const reasonCodes = body.reason_codes;
  if (!Array.isArray(reasonCodes) || reasonCodes.length !== 0) throw invalid();
  return {
    schema: SCHEMA,
    selection,
    availability: 'AVAILABLE',
    source,
    direction: {
      work_ref: directionWorkRef,
      workstream_source: workstreamSource,
      current,
      history: { revisions, has_more: hasMore, total_count: resolvedTotalCount },
    },
    reason_codes: [],
  };
}

function decodeUnavailableState(
  body: Record<string, unknown>,
  selection: DirectionSelection,
): AcceptedDirectionRead {
  if (body.source !== null) throw invalid();
  if (body.direction !== null) throw invalid();
  const reasonCodes = body.reason_codes;
  if (!Array.isArray(reasonCodes) || reasonCodes.length !== 1) throw invalid();
  const reason = reasonCodes[0];
  if (typeof reason !== 'string' || !REASON_CODE_SET.has(reason)) throw invalid();
  return {
    schema: SCHEMA,
    selection,
    availability: 'UNAVAILABLE',
    source: null,
    direction: null,
    reason_codes: [reason],
  };
}

function deepFreeze<T>(value: T): T {
  if (value !== null && typeof value === 'object') {
    const record = value as Record<string, unknown>;
    for (const key of Object.keys(record)) deepFreeze(record[key]);
    Object.freeze(value);
  }
  return value;
}

export function validDirectionSelection(value: unknown): value is DirectionSelection {
  if (!isPlainObject(value)) return false;
  if (!hasExactKeys(value, ['work_ref'])) return false;
  const workRef = value.work_ref;
  return typeof workRef === 'string' && isWorkRef(workRef);
}

function decodeDirection(
  raw: unknown,
  selected: DirectionSelection,
): AcceptedDirectionRead {
  if (!validDirectionSelection(selected)) throw invalid();
  if (!isPlainObject(raw) || !hasExactKeys(raw, BODY_KEYS)) throw invalid();
  let wire: unknown;
  try {
    wire = JSON.stringify({ ok: true, result: raw });
  } catch {
    throw invalid();
  }
  if (typeof wire !== 'string' || utf8ByteLength(wire + '\n') > WIRE_BYTE_BUDGET) {
    throw invalid();
  }
  if (raw.schema !== SCHEMA) throw invalid();
  const selectionValue = raw.selection;
  if (!isPlainObject(selectionValue) || !hasExactKeys(selectionValue, ['work_ref'])) {
    throw invalid();
  }
  const bodyWorkRef = selectionValue.work_ref;
  if (typeof bodyWorkRef !== 'string' || !isWorkRef(bodyWorkRef)) throw invalid();
  if (bodyWorkRef !== selected.work_ref) throw invalid();
  const selection: DirectionSelection = { work_ref: bodyWorkRef };
  if (raw.availability === 'AVAILABLE') {
    return deepFreeze(decodeAvailableState(raw, selected, selection));
  }
  if (raw.availability === 'UNAVAILABLE') {
    return deepFreeze(decodeUnavailableState(raw, selection));
  }
  throw invalid();
}

export function decodeAcceptedDirection(raw: unknown, selected: DirectionSelection): AcceptedDirectionRead {
  try { return decodeDirection(raw, selected); }
  catch { throw invalid(); }
}
