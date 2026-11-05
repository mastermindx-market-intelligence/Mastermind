/** A bounded, detached supervision projection over the existing canonical
 * Control Room autonomy read. Presentation input only: this module never
 * fetches, stores, dispatches or admits work. Reported currentness stays
 * owner-reported historical evidence and never becomes live authority.
 *
 * The exact root/work identity engine remains `programsFromControlRoom` in
 * ../mission; this module reuses its ProgramCard output and only validates
 * the additional autonomy fields it consumes. Any bad consumed field fails
 * the whole projection closed (no truncation, no partial ledger), and no
 * underlying exception text is ever surfaced.
 */
import { programsFromControlRoom, type ProgramCard } from "../mission";
import { MAX_RESPONSE_BYTES } from "../public-config";

export type SupervisionSourceReceipt = {
  readonly owner: string;
  readonly ref: string;
  readonly observedAt: string;
  readonly freshness: string;
};

export type SupervisionRow = {
  /** Program identity below is validated by the existing ../mission parser. */
  readonly workRef: string;
  readonly title: string | null;
  readonly state: string | null;
  readonly rootJobId: string | null;
  readonly rootState: ProgramCard["rootState"];
  readonly rootCandidates: readonly string[];
  /** Autonomy responsibility facts consumed by this bounded read. */
  readonly accountableSeat: string | null;
  readonly owedSeat: string | null;
  readonly owedReason: string | null;
  /** Owner-reported evidence only; never a currentness or liveness proof. */
  readonly freshness: "current" | "stale" | "unknown";
  readonly queryStatus: "ok" | "degraded" | "unknown" | "refused";
  readonly dispatchState: string | null;
  readonly dispatchHistorical: boolean | null;
  /** null means the source named no current worker: unknown, not "none". */
  readonly workerEffect: "none" | "applied" | "effect_unknown" | null;
  /** Positive owner observation only; absence never establishes no effect. */
  readonly unresolvedEffect?: true;
  readonly sources: readonly SupervisionSourceReceipt[];
  /** Same guarded fields as ProgramCard; withheld text never carries over. */
  readonly nextAction: string | null;
  readonly nextActionWithheld: boolean;
};

export type SupervisionRead =
  | {
      readonly state: "UNAVAILABLE";
      readonly reason: "SOURCE_UNAVAILABLE" | "SOURCE_INVALID";
    }
  | {
      readonly state: "AVAILABLE";
      /** Owner generation timestamp, preserved verbatim. */
      readonly generatedAt: string;
      readonly rows: readonly SupervisionRow[];
      /** Counts only; the underlying entries are never surfaced here. */
      readonly sourceFailureCount: number;
      readonly issueCount: number;
    };

const SEATS = ["chairman", "ceo", "coo", "worker", "unknown"] as const;
const FRESHNESS = ["current", "stale", "unknown"] as const;
const QUERY_STATUS = ["ok", "degraded", "unknown", "refused"] as const;
const EFFECTS = ["none", "applied", "effect_unknown"] as const;

/** Bounded observation limits for this read. */
const MAX_RECEIPTS = 128;
const MAX_COUNTED = 500;
const MAX_REF = 128;
const MAX_LINE = 2048;
const MAX_LABEL = 64;
const MAX_STATE = 128;

class InvalidSupervisionSource extends Error {
  constructor() {
    super("SUPERVISION_SOURCE_INVALID");
  }
}
const fail: () => never = () => {
  throw new InvalidSupervisionSource();
};

/** Ensure the incumbent identity parser only receives inert, bounded JSON.
 * This is a data-shape precondition, never an alternative identity engine. */
function inertSource(value: unknown): void {
  const pending = [{value, depth:0}];
  const seen = new Set<object>();
  const encoder = new TextEncoder();
  let nodes = 0, bytes = 0;
  while (pending.length) {
    const item = pending.pop()!;
    if (++nodes > 250000 || item.depth > 40) fail();
    const current = item.value;
    if (current === null || typeof current === "boolean") bytes += 5;
    else if (typeof current === "string") bytes += encoder.encode(current).byteLength + 2;
    else if (typeof current === "number") {
      if (!Number.isFinite(current)) fail();
      bytes += String(current).length;
    } else if (typeof current === "object") {
      if (seen.has(current)) fail();
      seen.add(current);
      const array = Array.isArray(current);
      const proto = Object.getPrototypeOf(current);
      if (array ? proto !== Array.prototype : proto !== Object.prototype && proto !== null) fail();
      for (const key of Reflect.ownKeys(current)) {
        if (typeof key !== "string") fail();
        const descriptor = Object.getOwnPropertyDescriptor(current, key);
        if (!descriptor || !("value" in descriptor)) fail();
        if (array && key === "length") continue;
        if (!descriptor.enumerable) fail();
        bytes += encoder.encode(key).byteLength + 4;
        pending.push({value:descriptor.value, depth:item.depth + 1});
      }
    } else fail();
    if (bytes > MAX_RESPONSE_BYTES) fail();
  }
}

const oneOf = <T extends readonly string[]>(value: unknown, allowed: T): T[number] => {
  if (typeof value === "string" && (allowed as readonly string[]).includes(value)) return value;
  fail();
};

/** A bounded single line of owner text: no control characters, one line. */
const line = (value: unknown, max: number): string => {
  if (
    typeof value !== "string" ||
    value.length === 0 ||
    value.length > max ||
    /[\u0000-\u001f\u007f]/.test(value)
  )
    fail();
  return value;
};
const nline = (value: unknown, max: number): string | null =>
  value === null ? null : line(value, max);

/** Bounded source reference token: no URL, no host path, no spaces. */
const sourceRef = (value: unknown, max: number): string => {
  const ref = line(value, max);
  if (
    !/^[A-Za-z0-9][A-Za-z0-9._:@/-]*$/.test(ref) ||
    ref.includes("://") ||
    /\/(?:Users|home|private|Volumes|var|etc)\//i.test(ref)
  )
    fail();
  return ref;
};

const ISO_TIME = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d{1,6})?Z$/;
const observedAt = (value: unknown): string => {
  if (typeof value !== "string") fail();
  const match = ISO_TIME.exec(value);
  if (!match) fail();
  const [year, month, day, hour, minute, second] = match
    .slice(1, 7)
    .map(Number);
  if (month < 1 || month > 12 || hour > 23 || minute > 59 || second > 59) fail();
  const leap = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
  const days = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  if (day < 1 || day > days[month - 1]) fail();
  return value;
};

/** Plain JSON data only. Accessors are detected through their own property
 * descriptors and are never invoked; functions and undefined are rejected. */
const plainObject = (value: unknown): Record<string, unknown> => {
  if (value === null || typeof value !== "object" || Array.isArray(value)) fail();
  const proto = Object.getPrototypeOf(value);
  if (proto !== Object.prototype && proto !== null) fail();
  const record = value as Record<string, unknown>;
  for (const key of Object.getOwnPropertyNames(record)) {
    const descriptor = Object.getOwnPropertyDescriptor(record, key);
    if (
      !descriptor ||
      descriptor.get !== undefined ||
      descriptor.set !== undefined ||
      descriptor.value === undefined ||
      typeof descriptor.value === "function"
    )
      fail();
  }
  if (Object.getOwnPropertySymbols(record).length > 0) fail();
  return record;
};

const projectRow = (card: ProgramCard, row: Record<string, unknown>): SupervisionRow => {
  const receipts = row.source_receipts;
  if (!Array.isArray(receipts) || receipts.length > MAX_RECEIPTS) fail();
  const sources = receipts.map((entry) => {
    const receipt = plainObject(entry);
    return Object.freeze({
      owner: sourceRef(receipt.owner, MAX_REF),
      ref: sourceRef(receipt.ref, MAX_REF),
      observedAt: observedAt(receipt.observed_at),
      freshness: line(receipt.freshness, MAX_LABEL),
    });
  });

  const accountableSeat =
    row.accountable_seat === null ? null : oneOf(row.accountable_seat, SEATS);

  let owedSeat: string | null = null;
  let owedReason: string | null = null;
  if (row.owed_turn !== null) {
    const turn = plainObject(row.owed_turn);
    owedSeat = turn.seat === null ? null : oneOf(turn.seat, SEATS);
    owedReason = nline(turn.reason, MAX_LINE);
  }

  let dispatchState: string | null = null;
  let dispatchHistorical: boolean | null = null;
  if (row.dispatch !== null) {
    const dispatch = plainObject(row.dispatch);
    if (Object.hasOwn(dispatch, "dispatch_state"))
      dispatchState =
        dispatch.dispatch_state === null
          ? null
          : line(dispatch.dispatch_state, MAX_STATE);
    if (Object.hasOwn(dispatch, "historical")) {
      const historical = dispatch.historical;
      if (historical !== null && typeof historical !== "boolean") fail();
      dispatchHistorical = historical as boolean | null;
    }
  }

  // A null current_worker stays unknown; "none" is never invented here.
  let workerEffect: SupervisionRow["workerEffect"] = null;
  if (row.current_worker !== null) {
    const worker = plainObject(row.current_worker);
    if (Object.hasOwn(worker, "effect_state"))
      workerEffect =
        worker.effect_state === null
          ? null
          : oneOf(worker.effect_state, EFFECTS);
  }

  let unresolvedCompanion = false;
  if (row.current_sol_target !== null) {
    const target = plainObject(row.current_sol_target);
    if (Object.hasOwn(target, "effect_state") && target.effect_state !== null) {
      unresolvedCompanion = oneOf(target.effect_state, EFFECTS) === "effect_unknown";
    }
  }
  if (row.dispatch !== null) {
    const dispatch = plainObject(row.dispatch);
    if (Object.hasOwn(dispatch, "w3c") && dispatch.w3c !== null) {
      const terminal = plainObject(dispatch.w3c);
      if (terminal.state !== null) {
        unresolvedCompanion ||= line(terminal.state, MAX_STATE) === "EFFECT_UNKNOWN";
      }
    }
  }

  return Object.freeze({
    workRef: card.workRef,
    title: card.title,
    state: card.state,
    rootJobId: card.rootJobId,
    rootState: card.rootState,
    // Detached copy: the parser's array aliases the source document.
    rootCandidates: Object.freeze([...card.rootCandidates]),
    accountableSeat,
    owedSeat,
    owedReason,
    freshness: oneOf(row.freshness, FRESHNESS),
    queryStatus: oneOf(row.query_status, QUERY_STATUS),
    dispatchState,
    dispatchHistorical,
    workerEffect,
    ...(unresolvedCompanion ? {unresolvedEffect:true as const} : {}),
    sources: Object.freeze(sources),
    nextAction: card.nextAction,
    nextActionWithheld: card.nextActionWithheld,
  });
};

export function decodeSupervisionRead(controlRoom: unknown): SupervisionRead {
  try {
    if (controlRoom !== null && controlRoom !== undefined) inertSource(controlRoom);
    // The existing parser stays the only root and work identity engine.
    const parsed = programsFromControlRoom(controlRoom);
    if (parsed.state !== "AVAILABLE")
      return Object.freeze({
        state: "UNAVAILABLE",
        reason:
          parsed.reason === "SOURCE_UNAVAILABLE"
            ? "SOURCE_UNAVAILABLE"
            : "SOURCE_INVALID",
      });
    const source = plainObject(controlRoom);
    const autonomy = plainObject(source.autonomy);
    const generatedAt = source.generated_at;
    if (typeof generatedAt !== "string") fail();
    const issues = autonomy.issues;
    const failures = autonomy.source_failures;
    if (
      !Array.isArray(autonomy.responsibilities) ||
      !Array.isArray(issues) ||
      !Array.isArray(failures) ||
      issues.length > MAX_COUNTED ||
      failures.length > MAX_COUNTED
    )
      fail();
    // Exact one-to-one responsibility matching for every projected program:
    // duplicate refs and orphan rows fail the whole projection.
    const rows = new Map<string, Record<string, unknown>>();
    for (const entry of autonomy.responsibilities as unknown[]) {
      const row = plainObject(entry);
      const ref = row.responsibility_ref;
      if (typeof ref !== "string" || rows.has(ref)) fail();
      rows.set(ref, row);
    }
    if (rows.size !== parsed.programs.length) fail();
    const projected: SupervisionRow[] = [];
    for (const card of parsed.programs) {
      const row = rows.get(card.workRef);
      if (!row) fail();
      projected.push(projectRow(card, row));
    }
    return Object.freeze({
      state: "AVAILABLE",
      generatedAt,
      rows: Object.freeze(projected),
      sourceFailureCount: failures.length,
      issueCount: issues.length,
    });
  } catch {
    // Fail closed without surfacing any underlying exception text.
    return Object.freeze({ state: "UNAVAILABLE", reason: "SOURCE_INVALID" });
  }
}
