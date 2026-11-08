/** Bounded original-turn content through the incumbent cold Session reader.
 * Every call re-reads the sealed native prefix. No transcript cache, Session
 * lifecycle, follower, provider call, or execution authority is introduced.
 */
import {createHash} from "node:crypto";
import type {CompanySessionReader} from "./company-peer";

type Json = Record<string, unknown>;
const plain = (v: unknown): v is Json => !!v && typeof v === "object" && Object.getPrototypeOf(v) === Object.prototype;
const keys = (v: unknown, expected: readonly string[]): v is Json =>
  plain(v) && Object.keys(v).length === expected.length && expected.every(k => Object.hasOwn(v, k));
const safe = (v: unknown): v is number => typeof v === "number" && Number.isSafeInteger(v) && v >= 0 && !Object.is(v, -0);
const id = (v: unknown): v is string => typeof v === "string" && /^[A-Za-z0-9][A-Za-z0-9._:\\-]{0,127}$/u.test(v);
const requestId = (v: unknown): v is string | number => id(v) || safe(v);
const sha = (v: unknown): v is string => typeof v === "string" && /^[0-9a-f]{64}$/u.test(v);
const canonical = (value: unknown): string => JSON.stringify(value, (_key, item: unknown) =>
  plain(item) ? Object.fromEntries(Object.keys(item).sort().map(key => [key, item[key]])) : item);
export const RESULT_CONTENT_BYTES = 4 * 1024 * 1024;
const FRAGMENT_BYTES = 4096, MAX_PAGES = 64, MAX_RECORDS = 4096;
export interface NativeClaim {
  schema: "mastermind.dsh.native_prompt_claim.v1";
  operationId: string; requestId: string | number; sessionId: string; messageId: string;
  nativeTurn: number; throughSeq: number;
}
export interface NativeTerminal {
  schema: "mastermind.dsh.native_prompt_terminal.v1";
  operationId: string; requestId: string | number; claim: NativeClaim;
  throughSeq: number; observedLastTurn: number; observedTurnCount: number;
}
export interface NativeResultRead {
  kind: "result"; claim: NativeClaim; terminal: NativeTerminal;
  offset_bytes: number; expected_sha256: string | null;
}
function claim(value: unknown): value is NativeClaim {
  return keys(value, ["schema", "operationId", "requestId", "sessionId", "messageId", "nativeTurn", "throughSeq"]) &&
    value.schema === "mastermind.dsh.native_prompt_claim.v1" && id(value.operationId) && requestId(value.requestId) &&
    id(value.sessionId) && id(value.messageId) && safe(value.nativeTurn) && safe(value.throughSeq);
}
export function isNativeResultRead(value: unknown): value is NativeResultRead {
  if (!keys(value, ["kind", "claim", "terminal", "offset_bytes", "expected_sha256"]) ||
      value.kind !== "result" || !claim(value.claim) || !safe(value.offset_bytes) ||
      value.offset_bytes >= RESULT_CONTENT_BYTES || !(value.expected_sha256 === null || sha(value.expected_sha256)) ||
      value.offset_bytes > 0 && value.expected_sha256 === null) return false;
  const terminal = value.terminal;
  return keys(terminal, ["schema", "operationId", "requestId", "claim", "throughSeq", "observedLastTurn", "observedTurnCount"]) &&
    terminal.schema === "mastermind.dsh.native_prompt_terminal.v1" && terminal.operationId === value.claim.operationId &&
    terminal.requestId === value.claim.requestId && claim(terminal.claim) && canonical(terminal.claim) === canonical(value.claim) &&
    safe(terminal.throughSeq) && terminal.throughSeq >= value.claim.throughSeq &&
    safe(terminal.observedLastTurn) && terminal.observedLastTurn >= value.claim.nativeTurn &&
    safe(terminal.observedTurnCount) && terminal.observedTurnCount >= 1;
}
type RecordEntry = {type: "event"; event: Json & {seq: number; type: string; data: Json}};
function unavailable(): never {throw new Error("Original native result content is unavailable");}
function record(value: unknown): value is RecordEntry {
  return plain(value) && value.type === "event" && plain(value.event) && safe(value.event.seq) &&
    typeof value.event.type === "string" && plain(value.event.data);
}

/** Exact Runtime claim/terminal arrives over the original trusted private port.
 * The Session address always comes from that port's installed association.
 */
export async function readNativeResultContent(reader: CompanySessionReader, read: NativeResultRead,
  sessionId: string, signal: AbortSignal, current: () => void) {
  if (!isNativeResultRead(read) || read.claim.sessionId !== sessionId) unavailable();
  const selected = canonical(read);
  const check = () => {signal.throwIfAborted(); current(); if (canonical(read) !== selected) unavailable();};
  const turn = read.claim.nativeTurn, through = read.terminal.throughSeq;
  let before: number | undefined, records: RecordEntry[] = [];
  let found = false;
  for (let pageNumber = 0; pageNumber < MAX_PAGES; pageNumber++) {
    check();
    const page = await reader.page({throughSeq: through, maxMessages: 8, ...(before === undefined ? {} : {beforeSeq: before})}, signal);
    check();
    if (!plain(page) || !Array.isArray(page.records) || typeof page.hasMore !== "boolean" ||
        page.records.length === 0 || page.records.length + records.length > MAX_RECORDS ||
        !page.records.every(record)) unavailable();
    const rows = page.records as RecordEntry[];
    const end = before ?? through + 1;
    if (rows[rows.length - 1]!.event.seq !== end - 1 ||
        rows.some((row, index) => index > 0 && row.event.seq !== rows[index - 1]!.event.seq + 1)) unavailable();
    records = [...rows, ...records];
    const starts = records.flatMap((row, index) => row.event.type === "turn/start" && row.event.data.turn === turn ? [index] : []);
    if (starts.length > 1) unavailable();
    if (starts.length === 1) {
      records = records.slice(starts[0]);
      found = true;
      break;
    }
    if (!page.hasMore || rows[0]!.event.seq === 0) unavailable();
    before = rows[0]!.event.seq;
    if (Buffer.byteLength(canonical({records}), "utf8") > RESULT_CONTENT_BYTES) unavailable();
  }
  if (!found) unavailable();
  const ends = records.flatMap((row, index) => row.event.type === "turn/end" && row.event.data.turn === turn ? [index] : []);
  if (ends.length !== 1) unavailable();
  records = records.slice(0, ends[0]! + 1);
  const start = records[0]!.event.seq, end = records[records.length - 1]!.event.seq;
  if (start > read.claim.throughSeq || end < read.claim.throughSeq ||
      records.slice(1).some(row => row.event.type === "turn/start")) unavailable();
  const users = records.filter(row => row.event.type === "user/message");
  const matched = users.filter(row => row.event.data.id === read.claim.messageId);
  const assistants = records.filter(row => row.event.type === "assistant/message");
  if (matched.length > 1 || users.some(row => row.event.data.id !== read.claim.messageId &&
        (!plain(row.event.data.source) || row.event.data.source.kind !== "runtime-context")) ||
      assistants.some(row => row.event.data.turn !== turn || !plain(row.event.data.message))) unavailable();
  const ending = records[records.length - 1]!.event.data.reason;
  const blocked = keys(ending, ["kind"]) && ending.kind === "blocked";
  const emptyCompleted = keys(ending, ["kind"]) && ending.kind === "completed" &&
    !records.some(row => row.event.type === "step/start" || row.event.type === "step/end");
  const userAborted = keys(ending, ["kind", "reason"]) && ending.kind === "aborted" &&
    keys(ending.reason, ["kind"]) && ending.reason.kind === "user";
  const closedEmpty = (blocked || emptyCompleted || userAborted) && end > read.claim.throughSeq &&
    users.length === 0 && assistants.length === 0;
  if (matched.length !== 1 && !closedEmpty) unavailable();
  const metadata = {
    kind: "result" as const, state: assistants.length ? "CONTENT" as const : "NO_ANSWER" as const,
    claim: read.claim, terminal: read.terminal, turn_start_seq: start, turn_end_seq: end,
    user_message_seq: matched[0]?.event.seq ?? null,
    assistant_message_seqs: assistants.map(row => row.event.seq),
  };
  check();
  if (!assistants.length) {
    if (read.offset_bytes !== 0 || read.expected_sha256 !== null) unavailable();
    return {...metadata, content: null};
  }
  const bytes = Buffer.from(canonical({records}), "utf8");
  if (bytes.byteLength > RESULT_CONTENT_BYTES || read.offset_bytes >= bytes.byteLength) unavailable();
  const digest = createHash("sha256").update(bytes).digest("hex");
  if (read.expected_sha256 !== null && read.expected_sha256 !== digest) unavailable();
  const next = Math.min(bytes.byteLength, read.offset_bytes + FRAGMENT_BYTES);
  const content = {encoding: "base64" as const, format: "dsh-session-history-records-json" as const,
    sha256: digest, total_bytes: bytes.byteLength, offset_bytes: read.offset_bytes,
    next_offset_bytes: next < bytes.byteLength ? next : null,
    data: bytes.subarray(read.offset_bytes, next).toString("base64")};
  check();
  return {...metadata, content};
}
