/** Closed, read-only decoder for the bounded AgentOS project-journal source sample.
 * The HTTP body is the envelope itself (no ok wrapper): extra keys, oversized
 * payloads, duplicate ids, boolean counts and unsafe integers are refused and a
 * detached copy is returned. Recorded dates describe the authored AgentOS record
 * or its Git publication time only; they never describe runtime execution,
 * review, acceptance or release.
 */
export const JOURNAL_BODY_SCHEMA = "mastermind.workspace_project_journal.v1";
export const JOURNAL_SOURCE_REPOSITORY = "mastermindx-market-intelligence/macro";
export const JOURNAL_MAX_BYTES = 131072;
export const JOURNAL_MAX_ENTRIES = 32;

export type JournalAvailability = "AVAILABLE" | "UNAVAILABLE";
export type JournalEntryKind = "DECISION" | "DISCOVERY" | "HANDOFF";
export type JournalTimeBasis =
  | "DECLARED_DECISION_DATE"
  | "DECLARED_VERIFICATION_DATE"
  | "GIT_RECORD_COMMIT_TIME"
  | "UNAVAILABLE";
export type JournalReasonCode =
  | "SOURCE_UNAVAILABLE"
  | "SOURCE_CHANGED"
  | "RECORD_NOT_FOUND"
  | "RECORD_INVALID"
  | "CONTENT_OVER_BUDGET";

export interface JournalSelection { work_ref: string }
export interface JournalSourceRef { repository: string; commit: string }
export interface JournalEntrySource {
  repository: string;
  commit: string;
  path: string;
  content_sha256: string;
}
export interface JournalCoverage {
  state: "BOUNDED_RECORD_SAMPLE";
  scanned: number;
  matched: number;
  omitted: number;
  invalid: number;
}
export interface JournalEntry {
  id: string;
  kind: JournalEntryKind;
  title: string;
  why: string | null;
  next_action: string | null;
  actor: string | null;
  recorded_at: string | null;
  time_basis: JournalTimeBasis;
  source: JournalEntrySource;
}
export interface JournalSection { entries: JournalEntry[]; coverage: JournalCoverage }
export interface ProjectJournalDocument {
  schema: typeof JOURNAL_BODY_SCHEMA;
  selection: JournalSelection;
  availability: JournalAvailability;
  source: JournalSourceRef | null;
  journal: JournalSection | null;
  reason_codes: JournalReasonCode[];
}

export class ProjectJournalDecodeError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "PROJECT_JOURNAL_INVALID";
  }
}

const workRefKey = /^[A-Z0-9]+(?:-[A-Z0-9]+)*$/;
const whole = (shape: RegExp, value: string): boolean => shape.exec(value)?.[0] === value;
const commitShape = /^[0-9a-f]{40}$/;
const digestShape = /^[0-9a-f]{64}$/;
const handoffStemShape = /^[A-Za-z0-9_-]+$/;
const dayShape = /^(\d{4})-(\d{2})-(\d{2})$/;
const stampShape = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d{1,9})?(?:Z|[+-]\d{2}:\d{2})$/;
const knownReasons = new Set<string>([
  "SOURCE_UNAVAILABLE", "SOURCE_CHANGED", "RECORD_NOT_FOUND", "RECORD_INVALID", "CONTENT_OVER_BUDGET",
]);
const monthLengths = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];

const refuse = (why: string): never => {
  throw new ProjectJournalDecodeError(why);
};
const keys = (value: Record<string, unknown>, expected: string[]): void => {
  const extra = Object.keys(value).filter(key => !expected.includes(key));
  if (extra.length > 0) refuse(`unexpected key: ${String(extra[0])}`);
  const missing = expected.filter(key => !Object.hasOwn(value, key));
  if (missing.length > 0) refuse(`missing key: ${String(missing[0])}`);
};
const record = (value: unknown, why: string): Record<string, unknown> => {
  if (typeof value !== "object" || value === null || Array.isArray(value)) refuse(why);
  return value as Record<string, unknown>;
};
const text = (value: unknown, why: string): string => {
  if (typeof value !== "string") throw new ProjectJournalDecodeError(why);
  return value;
};
const bounded = (value: unknown, max: number, why: string): string => {
  const given = text(value, why);
  if (given.length < 1 || given.length > max) refuse(why);
  return given;
};
const optionalBounded = (value: unknown, max: number, why: string): string | null => {
  if (value === null) return null;
  return bounded(value, max, why);
};
const nonNegative = (value: unknown, why: string): number => {
  if (typeof value !== "number" || !Number.isSafeInteger(value) || value < 0) {
    throw new ProjectJournalDecodeError(why);
  }
  return value;
};
const isEntryKind = (value: unknown): value is JournalEntryKind =>
  value === "DECISION" || value === "DISCOVERY" || value === "HANDOFF";

/** WS:UPPER-KEBAB with a key of 2..64 characters. */
export function validJournalWorkRef(value: string): boolean {
  if (!value.startsWith("WS:")) return false;
  const key = value.slice(3);
  return key.length >= 2 && key.length <= 64 && whole(workRefKey, key);
}

function isCalendarDay(year: number, month: number, day: number): boolean {
  if (year < 1 || year > 9999 || month < 1 || month > 12 || day < 1) return false;
  const leapYear = (year % 4 === 0 && year % 100 !== 0) || year % 400 === 0;
  return day <= (month === 2 && leapYear ? 29 : monthLengths[month - 1]);
}
const dayDate = (value: unknown, why: string): string => {
  const given = text(value, why);
  const match = dayShape.exec(given);
  if (match === null || match[0] !== given || !isCalendarDay(Number(match[1]), Number(match[2]), Number(match[3]))) refuse(why);
  return given;
};
const stampedDate = (value: unknown, why: string): string | null => {
  if (value === null) return null;
  const given = text(value, why);
  const match = stampShape.exec(given);
  if (match === null || match[0] !== given) throw new ProjectJournalDecodeError(why);
  const zone = given.endsWith("Z") ? null : given.slice(-6);
  if (zone && (Number(zone.slice(1,3)) > 23 || Number(zone.slice(4,6)) > 59)) refuse(why);
  if (!isCalendarDay(Number(match[1]), Number(match[2]), Number(match[3])) ||
      Number(match[4]) > 23 || Number(match[5]) > 59 || Number(match[6]) > 59) refuse(why);
  return given;
};

function entryKey(id: string, prefix: string, why: string): string {
  if (!id.startsWith(prefix)) refuse(why);
  const key = id.slice(prefix.length);
  if (!whole(workRefKey, key)) refuse(why);
  return key;
}
function handoffStem(id: string, why: string): string {
  if (!id.startsWith("HND:")) refuse(why);
  const stem = id.slice(4);
  if (!whole(handoffStemShape, stem)) refuse(`${why} (stem A-Za-z0-9_-)`);
  return stem;
}

function decodeEntry(value: unknown, source: JournalSourceRef): JournalEntry {
  const entry = record(value, "journal entry must be an object");
  keys(entry, ["id", "kind", "title", "why", "next_action", "actor", "recorded_at", "time_basis", "source"]);
  const kind = entry.kind;
  if (!isEntryKind(kind)) throw new ProjectJournalDecodeError("entry kind must be DECISION, DISCOVERY or HANDOFF");
  const id = text(entry.id, "entry id must be a string");
  const title = bounded(entry.title, 4096, "entry title must be non-empty text of at most 4096 characters");
  const why = optionalBounded(entry.why, 4096, "entry why must be null or non-empty text of at most 4096 characters");
  const nextAction = optionalBounded(entry.next_action, 4096, "entry next_action must be null or non-empty text of at most 4096 characters");
  const actor = optionalBounded(entry.actor, 256, "entry actor must be null or non-empty text of at most 256 characters");
  let recordedAt: string | null;
  let timeBasis: JournalTimeBasis;
  let expectedPath: string;
  if (kind === "DECISION") {
    const key = entryKey(id, "DEC:", "DECISION entry id must be DEC:UPPER-KEBAB");
    expectedPath = `agentos/decisions/DEC-${key}.md`;
    recordedAt = dayDate(entry.recorded_at, "DECISION recorded_at must be a YYYY-MM-DD calendar date");
    timeBasis = "DECLARED_DECISION_DATE";
  } else if (kind === "DISCOVERY") {
    const key = entryKey(id, "DSC:", "DISCOVERY entry id must be DSC:UPPER-KEBAB");
    expectedPath = `agentos/discoveries/DSC-${key}.md`;
    recordedAt = dayDate(entry.recorded_at, "DISCOVERY recorded_at must be a YYYY-MM-DD calendar date");
    timeBasis = "DECLARED_VERIFICATION_DATE";
  } else {
    const stem = handoffStem(id, "HANDOFF entry id must be HND:<stem>");
    expectedPath = `agentos/handoffs/${stem}.md`;
    recordedAt = stampedDate(entry.recorded_at, "HANDOFF recorded_at must be null or an ISO-8601 timestamp with an explicit timezone");
    timeBasis = recordedAt === null ? "UNAVAILABLE" : "GIT_RECORD_COMMIT_TIME";
  }
  if (kind === "DECISION" && (why === null || actor === null || nextAction !== null)) refuse("decision fields do not match the source contract");
  if (kind === "DISCOVERY" && (why === null || actor !== null || nextAction !== null)) refuse("discovery fields do not match the source contract");
  if (kind === "HANDOFF" && (why !== null || actor !== null)) refuse("handoff fields do not match the source contract");
  if (entry.time_basis !== timeBasis) refuse(`entry time_basis must be ${timeBasis} for this kind`);
  const entrySource = record(entry.source, "entry source must be an object");
  keys(entrySource, ["repository", "commit", "path", "content_sha256"]);
  const repository = text(entrySource.repository, "entry source repository must be a string");
  if (repository !== source.repository) refuse("entry source repository must match the document source");
  const commit = text(entrySource.commit, "entry source commit must be a string");
  if (commit !== source.commit) refuse("entry source commit must match the document source");
  const path = text(entrySource.path, "entry source path must be a string");
  if (path !== expectedPath) refuse(`entry source path must be ${expectedPath}`);
  const digest = text(entrySource.content_sha256, "entry source content_sha256 must be a string");
  if (!whole(digestShape, digest)) refuse("entry source content_sha256 must be 64 lowercase hex characters");
  return {
    id,
    kind,
    title,
    why,
    next_action: nextAction,
    actor,
    recorded_at: recordedAt,
    time_basis: timeBasis,
    source: { repository, commit, path, content_sha256: digest },
  };
}

function decodeCoverage(value: unknown, shown: number): JournalCoverage {
  const coverage = record(value, "an AVAILABLE body must carry a journal coverage object");
  keys(coverage, ["state", "scanned", "matched", "omitted", "invalid"]);
  if (coverage.state !== "BOUNDED_RECORD_SAMPLE") {
    refuse("journal coverage state must be BOUNDED_RECORD_SAMPLE");
  }
  const scanned = nonNegative(coverage.scanned, "journal coverage scanned must be a non-negative safe integer");
  const matched = nonNegative(coverage.matched, "journal coverage matched must be a non-negative safe integer");
  const omitted = nonNegative(coverage.omitted, "journal coverage omitted must be a non-negative safe integer");
  const invalid = nonNegative(coverage.invalid, "journal coverage invalid must be a non-negative safe integer");
  if (scanned < matched || invalid > scanned) refuse("journal coverage counts conflict with the captured sample");
  if (matched < shown) refuse("journal coverage matched must be at least the number of shown entries");
  if (omitted < matched - shown) refuse("journal coverage omitted must be at least matched minus the shown entries");
  return { state: "BOUNDED_RECORD_SAMPLE", scanned, matched, omitted, invalid };
}

function decodeJournal(value: unknown, source: JournalSourceRef): JournalSection {
  const journal = record(value, "an AVAILABLE body must carry a journal object");
  keys(journal, ["entries", "coverage"]);
  const rawEntries = journal.entries;
  if (!Array.isArray(rawEntries)) throw new ProjectJournalDecodeError("journal entries must be an array");
  if (rawEntries.length > JOURNAL_MAX_ENTRIES) {
    refuse(`journal entries must not exceed ${JOURNAL_MAX_ENTRIES} entries`);
  }
  const seen = new Set<string>();
  const entries: JournalEntry[] = [];
  for (const item of rawEntries) {
    const entry = decodeEntry(item, source);
    if (seen.has(entry.id)) refuse(`duplicate entry id: ${entry.id}`);
    seen.add(entry.id);
    entries.push(entry);
  }
  return { entries, coverage: decodeCoverage(journal.coverage, entries.length) };
}

/** Decode the raw HTTP body of the workspace project-journal route against the
 * exact requested work ref. Pure: no I/O, no clock, no randomness. */
export function decodeProjectJournal(raw: unknown, workRef: string): ProjectJournalDocument {
  if (typeof workRef !== "string" || !validJournalWorkRef(workRef)) {
    refuse("selection workRef must be WS:UPPER-KEBAB with a key of 2..64 characters");
  }
  let value: unknown = raw;
  if (typeof value === "string") {
    try {
      value = JSON.parse(value);
    } catch {
      refuse("body is not valid JSON text");
    }
  }
  const envelope = record(value, "body must be a JSON object");
  let jsonBytes = 0;
  try {
    jsonBytes = new TextEncoder().encode(JSON.stringify(envelope)).length;
  } catch {
    refuse("body is not JSON-serializable");
  }
  if (jsonBytes > JOURNAL_MAX_BYTES) refuse(`body exceeds the ${JOURNAL_MAX_BYTES}-byte budget`);
  keys(envelope, ["schema", "selection", "availability", "source", "journal", "reason_codes"]);
  if (envelope.schema !== JOURNAL_BODY_SCHEMA) {
    refuse("body schema must be mastermind.workspace_project_journal.v1");
  }
  const selection = record(envelope.selection, "selection must be an object");
  keys(selection, ["work_ref"]);
  const selectionWorkRef = text(selection.work_ref, "selection work_ref must be a string");
  if (selectionWorkRef !== workRef) refuse("selection work_ref must match the requested workRef");
  if (envelope.availability !== "AVAILABLE" && envelope.availability !== "UNAVAILABLE") {
    refuse("availability must be AVAILABLE or UNAVAILABLE");
  }
  const reasonCodes = envelope.reason_codes;
  if (!Array.isArray(reasonCodes)) throw new ProjectJournalDecodeError("reason_codes must be an array");

  if (envelope.availability === "AVAILABLE") {
    if (reasonCodes.length !== 0) refuse("an AVAILABLE body must carry no reason codes");
    const sourceValue = record(envelope.source, "an AVAILABLE body must carry a source object");
    keys(sourceValue, ["repository", "commit"]);
    const repository = text(sourceValue.repository, "source repository must be a string");
    if (repository !== JOURNAL_SOURCE_REPOSITORY) {
      refuse("source repository must be mastermindx-market-intelligence/macro");
    }
    const commit = text(sourceValue.commit, "source commit must be a string");
    if (!whole(commitShape, commit)) refuse("source commit must be 40 lowercase hex characters");
    const source: JournalSourceRef = { repository, commit };
    return {
      schema: JOURNAL_BODY_SCHEMA,
      selection: { work_ref: selectionWorkRef },
      availability: "AVAILABLE",
      source,
      journal: decodeJournal(envelope.journal, source),
      reason_codes: [],
    };
  }
  if (envelope.source !== null) refuse("an UNAVAILABLE body must carry source null");
  if (envelope.journal !== null) refuse("an UNAVAILABLE body must carry journal null");
  if (reasonCodes.length !== 1) refuse("an UNAVAILABLE body must carry exactly one reason code");
  const reason = reasonCodes[0];
  if (typeof reason !== "string" || !knownReasons.has(reason)) {
    refuse("reason code must be one of SOURCE_UNAVAILABLE, SOURCE_CHANGED, RECORD_NOT_FOUND, RECORD_INVALID, CONTENT_OVER_BUDGET");
  }
  return {
    schema: JOURNAL_BODY_SCHEMA,
    selection: { work_ref: selectionWorkRef },
    availability: "UNAVAILABLE",
    source: null,
    journal: null,
    reason_codes: [reason as JournalReasonCode],
  };
}

/** Fixed rootless caller shape. A source identity is not an authorization grant. */
export function validJournalSelection(value: unknown): value is JournalSelection {
  return typeof value === "object" && value !== null && !Array.isArray(value) &&
    Object.keys(value).length === 1 && Object.hasOwn(value, "work_ref") &&
    typeof (value as JournalSelection).work_ref === "string" && validJournalWorkRef((value as JournalSelection).work_ref);
}
