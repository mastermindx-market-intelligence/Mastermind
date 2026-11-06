/**
 * project-conversation-catalogue-contract.ts
 *
 * Dependency-free strict wire contract for the actual project conversation
 * catalogue and the bounded session-window read (native session grouping,
 * not renamed individual saved replies).
 *
 * - snake_case JSON DTO keys are preserved verbatim; no camelCase translation.
 * - Decoded output is detached from the input and deep-frozen.
 * - Validators are pure: no fetch, no clock reads, no authority inference.
 * - Any invalid input throws Error('PROJECT_CONVERSATION_UNAVAILABLE').
 */

export interface ProjectConversationRequest {
  readonly read_ref: string;
  readonly request_revision: string;
}

export interface ProjectConversationRow {
  readonly conversation_ref: string;
  readonly revision: string;
  readonly root_job_id: string;
  readonly title: null;
  readonly last_request_at: string;
  readonly requests: readonly ProjectConversationRequest[];
}

export interface ProjectConversationCatalogue {
  readonly schema: 'mastermind.project_conversation_catalogue.v1';
  readonly work_ref: string;
  readonly coverage: 'PARTIAL';
  readonly conversations: readonly ProjectConversationRow[];
  readonly next_cursor: string | null;
  readonly high_water: number;
  readonly can_send: false;
}

export interface ProjectConversationReply {
  readonly text: string;
  readonly next_step: string;
  readonly read_ref: string;
  readonly message_key: string;
  readonly fingerprint: string;
  readonly parent_consumed: false;
}

export interface ProjectConversationTurn {
  readonly read_ref: string;
  readonly request_revision: string;
  readonly requested_at: string;
  readonly instruction: string | null;
  readonly stop_condition: string | null;
  readonly reply: ProjectConversationReply | null;
  readonly state: 'AVAILABLE' | 'UNAVAILABLE';
}

export interface ProjectConversationRead {
  readonly schema: 'mastermind.project_conversation_read.v1';
  readonly work_ref: string;
  readonly conversation_ref: string;
  readonly revision: string;
  readonly root_job_id: string;
  readonly title: null;
  readonly coverage: 'PARTIAL';
  readonly can_send: false;
  readonly turns: readonly ProjectConversationTurn[];
}

export interface ProjectConversationSelection {
  readonly work_ref: string;
  readonly conversation_ref: string;
  readonly revision: string;
  readonly requests: readonly ProjectConversationRequest[];
}

export interface ProjectConversationReadExpectation {
  readonly workRef: string;
  readonly conversationRef: string;
  readonly revision: string;
  readonly requests: readonly ProjectConversationRequest[];
}

const CATALOGUE_SCHEMA: 'mastermind.project_conversation_catalogue.v1' =
  'mastermind.project_conversation_catalogue.v1';
const READ_SCHEMA: 'mastermind.project_conversation_read.v1' =
  'mastermind.project_conversation_read.v1';

const MAX_WIRE_JSON_UTF8 = 32768;
const MAX_SELECTION_UTF8 = 4096;
const MAX_LITERAL_CODEPOINTS = 700;
const MAX_LITERAL_UTF8 = 4096;
const MAX_CURSOR_LENGTH = 2048;
const MAX_CONVERSATIONS = 8;
const MAX_REQUESTS = 4;
const MAX_TURNS = 4;
const MIN_WORKREF_LENGTH = 2;
const MAX_WORKREF_LENGTH = 64;

const HEX64 = /^[0-9a-f]{64}$/;
const HEX40 = /^[0-9a-f]{40}$/;
const CONVERSATION_REF = /^conversation-[0-9a-f]{64}$/;
const READ_REF = /^session-reply-[0-9a-f]{64}$/;
const MESSAGE_KEY = /^asd-native-reply-[0-9a-f]{40}$/;
const ROOT_JOB_ID = /^JOB-[0-9]+$/;
const WORK_REF = /^WS:[A-Z0-9]+(?:-[A-Z0-9]+)*$/;
const CURSOR = /^[A-Za-z0-9_=-]+$/;
const TIMESTAMP =
  /^([0-9]{4})-([0-9]{2})-([0-9]{2})T([0-9]{2}):([0-9]{2}):([0-9]{2})(\.[0-9]+)?(?:Z|\+00:00)$/;

function matches(pattern: RegExp, value: string): boolean {
  const match = pattern.exec(value); return match !== null && match[0] === value;
}

function fail(): never {
  throw new Error('PROJECT_CONVERSATION_UNAVAILABLE');
}

/** Plain object: Object.prototype or null prototype only. */
function isPlainObject(value: unknown): value is Record<string, unknown> {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    return false;
  }
  const proto: unknown = Object.getPrototypeOf(value);
  return proto === Object.prototype || proto === null;
}

function asObject(value: unknown): Record<string, unknown> {
  try {
    if (!isPlainObject(value)) fail();
    const copy: Record<string, unknown> = Object.create(null);
    for (const key of Reflect.ownKeys(value)) {
      if (typeof key !== 'string') fail();
      const field = Object.getOwnPropertyDescriptor(value, key);
      if (!field || !field.enumerable || !('value' in field)) fail();
      copy[key] = field.value;
    }
    return copy;
  } catch { fail(); }
}

/**
 * Own enumerable string-keyed data properties only, no symbols, no hidden
 * non-enumerable props, no accessors. Nothing hostile is ever invoked.
 */
function expectKeys(value: object, expected: readonly string[]): void {
  const names = Object.getOwnPropertyNames(value);
  if (names.length !== expected.length) fail();
  for (const name of names) {
    const descriptor = Object.getOwnPropertyDescriptor(value, name);
    if (descriptor === undefined) fail();
    if (descriptor.enumerable !== true) fail();
    if (!('value' in descriptor)) fail();
    if (descriptor.get !== undefined || descriptor.set !== undefined) fail();
  }
  if (Object.getOwnPropertySymbols(value).length !== 0) fail();
  const allowed = new Set<string>(expected);
  for (const name of names) {
    if (!allowed.has(name)) fail();
  }
}

/** Standard-proto array, no holes, no custom properties, no accessors. */
function asArray(value: unknown): unknown[] {
  try {
    if (!Array.isArray(value) || Object.getPrototypeOf(value) !== Array.prototype) fail();
    const lengthField = Object.getOwnPropertyDescriptor(value, 'length');
    if (!lengthField || !('value' in lengthField)) fail();
    const length: unknown = lengthField.value;
    if (typeof length !== 'number' || !Number.isSafeInteger(length) || length < 0 || length > 64) fail();
    const keys = Reflect.ownKeys(value);
    if (keys.length !== length + 1 || keys.some(key => typeof key !== 'string')) fail();
    const copy: unknown[] = [];
    for (let i = 0; i < length; i++) {
      const field = Object.getOwnPropertyDescriptor(value, String(i));
      if (!field || !field.enumerable || !('value' in field)) fail();
      copy.push(field.value);
    }
    return copy;
  } catch { fail(); }
}

/** Scalar Unicode only: lone surrogates rejected. */
function isScalarUnicode(text: string): boolean {
  let index = 0;
  while (index < text.length) {
    const code = text.charCodeAt(index);
    if (code >= 0xd800 && code <= 0xdbff) {
      const next = index + 1 < text.length ? text.charCodeAt(index + 1) : 0;
      if (next < 0xdc00 || next > 0xdfff) return false;
      index += 2;
    } else if (code >= 0xdc00 && code <= 0xdfff) {
      return false;
    } else {
      index += 1;
    }
  }
  return true;
}

function asScalarString(value: unknown): string {
  if (typeof value !== 'string') fail();
  if (!isScalarUnicode(value)) fail();
  return value;
}

function codePointLength(text: string): number {
  let count = 0;
  let index = 0;
  while (index < text.length) {
    const code = text.codePointAt(index) as number;
    index += code > 0xffff ? 2 : 1;
    count += 1;
  }
  return count;
}

function utf8Length(text: string): number {
  let bytes = 0;
  let index = 0;
  while (index < text.length) {
    const code = text.codePointAt(index) as number;
    if (code < 0x80) bytes += 1;
    else if (code < 0x800) bytes += 2;
    else if (code < 0x10000) bytes += 3;
    else bytes += 4;
    index += code > 0xffff ? 2 : 1;
  }
  return bytes;
}

/** Nonempty literal bounded by codepoints and UTF-8 bytes; never trimmed. */
function asBoundedLiteral(value: unknown): string {
  const text = asScalarString(value);
  if (text.length === 0) fail();
  if (codePointLength(text) > MAX_LITERAL_CODEPOINTS) fail();
  if (utf8Length(text) > MAX_LITERAL_UTF8) fail();
  return text;
}

function asWorkRef(value: unknown): string {
  const text = asScalarString(value);
  if (text.length - 3 < MIN_WORKREF_LENGTH || text.length - 3 > MAX_WORKREF_LENGTH) fail();
  if (!matches(WORK_REF, text)) fail();
  return text;
}

function asConversationRef(value: unknown): string {
  const text = asScalarString(value);
  if (!matches(CONVERSATION_REF, text)) fail();
  return text;
}

function asRevision(value: unknown): string {
  const text = asScalarString(value);
  if (!matches(HEX64, text)) fail();
  return text;
}

function asReadRef(value: unknown): string {
  const text = asScalarString(value);
  if (!matches(READ_REF, text)) fail();
  return text;
}

function asRootJobId(value: unknown): string {
  const text = asScalarString(value);
  if (!matches(ROOT_JOB_ID, text)) fail();
  return text;
}

/** Actual Runtime UTC timestamp, preserving Z or +00:00 spelling verbatim. */
function asTimestamp(value: unknown): string {
  const text = asScalarString(value);
  const match = TIMESTAMP.exec(text);
  if (match === null || match[0] !== text || text.length > 64) fail();
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const hour = Number(match[4]);
  const minute = Number(match[5]);
  const second = Number(match[6]);
  if (month < 1 || month > 12) fail();
  if (day < 1 || day > daysInMonth(year, month)) fail();
  if (hour > 23 || minute > 59 || second > 59) fail();
  return text;
}

function isLeapYear(year: number): boolean {
  return year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
}

function daysInMonth(year: number, month: number): number {
  if (month === 2) return isLeapYear(year) ? 29 : 28;
  if (month === 4 || month === 6 || month === 9 || month === 11) return 30;
  return 31;
}

function decodeCursor(value: unknown): string | null {
  if (value === null) return null;
  const text = asScalarString(value);
  if (text.length === 0 || text.length > MAX_CURSOR_LENGTH) fail();
  if (!matches(CURSOR, text)) fail();
  return text;
}

function decodeHighWater(value: unknown): number {
  if (typeof value !== 'number' || !Number.isSafeInteger(value) || value < 0) fail();
  return value;
}

function decodeRequests(
  value: unknown,
  minimum: number,
): ProjectConversationRequest[] {
  const items = asArray(value);
  if (items.length < minimum || items.length > MAX_REQUESTS) fail();
  const seen = new Set<string>();
  const requests: ProjectConversationRequest[] = [];
  for (const item of items) {
    const record = asObject(item);
    expectKeys(record, ['read_ref', 'request_revision']);
    const read_ref = asReadRef(record.read_ref);
    const request_revision = asRevision(record.request_revision);
    if (seen.has(read_ref)) fail();
    seen.add(read_ref);
    requests.push({ read_ref, request_revision });
  }
  return requests;
}

function decodeRow(value: unknown): ProjectConversationRow {
  const record = asObject(value);
  expectKeys(record, [
    'conversation_ref',
    'revision',
    'root_job_id',
    'title',
    'last_request_at',
    'requests',
  ]);
  const conversation_ref = asConversationRef(record.conversation_ref);
  const revision = asRevision(record.revision);
  const root_job_id = asRootJobId(record.root_job_id);
  if (record.title !== null) fail();
  const last_request_at = asTimestamp(record.last_request_at);
  const requests = decodeRequests(record.requests, 1);
  return {
    conversation_ref,
    revision,
    root_job_id,
    title: null,
    last_request_at,
    requests,
  };
}

function decodeRows(value: unknown): ProjectConversationRow[] {
  const items = asArray(value);
  if (items.length < 1 || items.length > MAX_CONVERSATIONS) fail();
  const seenConversations = new Set<string>();
  const seenReadRefs = new Set<string>();
  const rows: ProjectConversationRow[] = [];
  for (const item of items) {
    const row = decodeRow(item);
    if (seenConversations.has(row.conversation_ref)) fail();
    seenConversations.add(row.conversation_ref);
    for (const request of row.requests) {
      if (seenReadRefs.has(request.read_ref)) fail();
      seenReadRefs.add(request.read_ref);
    }
    rows.push(row);
  }
  return rows;
}

function decodeReply(
  value: unknown,
  turnReadRef: string,
): ProjectConversationReply {
  const record = asObject(value);
  expectKeys(record, [
    'text',
    'next_step',
    'read_ref',
    'message_key',
    'fingerprint',
    'parent_consumed',
  ]);
  const text = asBoundedLiteral(record.text);
  const next_step = asBoundedLiteral(record.next_step);
  const read_ref = asReadRef(record.read_ref);
  if (read_ref !== turnReadRef) fail();
  const message_key = asScalarString(record.message_key);
  if (!matches(MESSAGE_KEY, message_key)) fail();
  const fingerprint = asScalarString(record.fingerprint);
  if (!matches(HEX64, fingerprint)) fail();
  if (record.parent_consumed !== false) fail();
  return {
    text,
    next_step,
    read_ref,
    message_key,
    fingerprint,
    parent_consumed: false,
  };
}

function decodeTurn(
  value: unknown,
  expectedRequest: ProjectConversationRequest,
): ProjectConversationTurn {
  const record = asObject(value);
  expectKeys(record, [
    'read_ref',
    'request_revision',
    'requested_at',
    'instruction',
    'stop_condition',
    'reply',
    'state',
  ]);
  const read_ref = asReadRef(record.read_ref);
  const request_revision = asRevision(record.request_revision);
  if (read_ref !== expectedRequest.read_ref) fail();
  if (request_revision !== expectedRequest.request_revision) fail();
  const requested_at = asTimestamp(record.requested_at);
  const state = record.state;
  if (state !== 'AVAILABLE' && state !== 'UNAVAILABLE') fail();
  let instruction: string | null;
  let stop_condition: string | null;
  let reply: ProjectConversationReply | null;
  if (state === 'AVAILABLE') {
    instruction = asBoundedLiteral(record.instruction);
    stop_condition = asBoundedLiteral(record.stop_condition);
    if (record.reply === null || typeof record.reply !== 'object' || Array.isArray(record.reply)) {
      fail();
    }
    reply = decodeReply(record.reply, read_ref);
  } else {
    if (record.instruction !== null) fail();
    if (record.stop_condition !== null) fail();
    if (record.reply !== null) fail();
    instruction = null;
    stop_condition = null;
    reply = null;
  }
  return {
    read_ref,
    request_revision,
    requested_at,
    instruction,
    stop_condition,
    reply,
    state,
  };
}

function decodeTurns(
  value: unknown,
  expectedRequests: readonly ProjectConversationRequest[],
): ProjectConversationTurn[] {
  const items = asArray(value);
  if (items.length < 1 || items.length > MAX_TURNS) fail();
  if (items.length !== expectedRequests.length) fail();
  const turns: ProjectConversationTurn[] = [];
  for (let index = 0; index < items.length; index++) {
    const expectedRequest = expectedRequests[index];
    if (expectedRequest === undefined) fail();
    turns.push(decodeTurn(items[index], expectedRequest));
  }
  return turns;
}

/** Fresh plain deep copy built only from already-validated JSON data. */
function detach(value: unknown): unknown {
  if (Array.isArray(value)) {
    const copy: unknown[] = [];
    for (const item of value) copy.push(detach(item));
    return copy;
  }
  if (value !== null && typeof value === 'object') {
    const copy: Record<string, unknown> = {};
    for (const key of Object.keys(value)) {
      copy[key] = detach((value as Record<string, unknown>)[key]);
    }
    return copy;
  }
  return value;
}

function deepFreeze<T>(value: T): T {
  if (value !== null && typeof value === 'object') {
    for (const key of Object.keys(value as Record<string, unknown>)) {
      deepFreeze((value as Record<string, unknown>)[key]);
    }
    Object.freeze(value);
  }
  return value;
}

/** Safe-detach, stringify the detached copy, enforce the wire UTF-8 budget. */
function finalizeWire<T>(value: T): T {
  const detached = detach(value);
  let wire: string;
  try {
    const serialized: string = JSON.stringify(detached);
    wire = serialized;
  } catch {
    fail();
  }
  if (utf8Length(wire) > MAX_WIRE_JSON_UTF8) fail();
  return deepFreeze(value);
}

export function decodeProjectConversationCatalogue(
  raw: unknown,
  expectedWorkRef: string,
): ProjectConversationCatalogue {
  const workRef = asWorkRef(expectedWorkRef);
  const record = asObject(raw);
  expectKeys(record, [
    'schema',
    'work_ref',
    'coverage',
    'conversations',
    'next_cursor',
    'high_water',
    'can_send',
  ]);
  if (record.schema !== CATALOGUE_SCHEMA) fail();
  const work_ref = asWorkRef(record.work_ref);
  if (work_ref !== workRef) fail();
  if (record.coverage !== 'PARTIAL') fail();
  if (record.can_send !== false) fail();
  const conversations = decodeRows(record.conversations);
  const next_cursor = decodeCursor(record.next_cursor);
  const high_water = decodeHighWater(record.high_water);
  return finalizeWire({
    schema: CATALOGUE_SCHEMA,
    work_ref,
    coverage: 'PARTIAL',
    conversations,
    next_cursor,
    high_water,
    can_send: false,
  });
}

export function decodeProjectConversationRead(
  raw: unknown,
  expected: ProjectConversationReadExpectation,
): ProjectConversationRead {
  const expectation = asObject(expected);
  expectKeys(expectation, ['workRef', 'conversationRef', 'revision', 'requests']);
  const expectedWorkRef = asWorkRef(expectation.workRef);
  const expectedConversationRef = asConversationRef(expectation.conversationRef);
  const expectedRevision = asRevision(expectation.revision);
  const expectedRequests = decodeRequests(expectation.requests, 1);
  const record = asObject(raw);
  expectKeys(record, [
    'schema',
    'work_ref',
    'conversation_ref',
    'revision',
    'root_job_id',
    'title',
    'coverage',
    'can_send',
    'turns',
  ]);
  if (record.schema !== READ_SCHEMA) fail();
  const work_ref = asWorkRef(record.work_ref);
  if (work_ref !== expectedWorkRef) fail();
  const conversation_ref = asConversationRef(record.conversation_ref);
  if (conversation_ref !== expectedConversationRef) fail();
  const revision = asRevision(record.revision);
  if (revision !== expectedRevision) fail();
  const root_job_id = asRootJobId(record.root_job_id);
  if (record.title !== null) fail();
  if (record.coverage !== 'PARTIAL') fail();
  if (record.can_send !== false) fail();
  const turns = decodeTurns(record.turns, expectedRequests);
  return finalizeWire({
    schema: READ_SCHEMA,
    work_ref,
    conversation_ref,
    revision,
    root_job_id,
    title: null,
    coverage: 'PARTIAL',
    can_send: false,
    turns,
  });
}

export function validateProjectConversationSelection(
  raw: unknown,
): ProjectConversationSelection {
  const record = asObject(raw);
  expectKeys(record, ['work_ref', 'conversation_ref', 'revision', 'requests']);
  const work_ref = asWorkRef(record.work_ref);
  const conversation_ref = asConversationRef(record.conversation_ref);
  const revision = asRevision(record.revision);
  const requests = decodeRequests(record.requests, 1);
  const selection: ProjectConversationSelection = {
    work_ref,
    conversation_ref,
    revision,
    requests,
  };
  const detached = detach(selection);
  let wire: string;
  try {
    const serialized: string = JSON.stringify(detached);
    wire = serialized;
  } catch {
    fail();
  }
  if (utf8Length(wire) > MAX_SELECTION_UTF8) fail();
  return deepFreeze(selection);
}
