/**
 * Bounded public project-knowledge request construction.
 *
 * Two helpers build *closed, detached, deep-frozen* public request objects for
 * the project knowledge write path:
 *   - `buildProjectFileRequest`  — one user-selected browser File -> text request body.
 *   - `buildProjectPreferenceRequest` — one literal communication preference value.
 *
 * plus `canonicalPublicRequest` / `publicRequestSha256`, which revalidate the
 * exact closed public request shape and produce its canonical JSON text and
 * SHA-256 digest. The hash verifies the exact public validated request; it is
 * NOT the private server-side recipe fingerprint and carries no preimage.
 *
 * Hard boundary: this module is pure construction. It is NOT authorization, a
 * receipt, an upload, or a save. No UI, no persistence, no permission issuer,
 * no host/transport/network/path/service/provider calls. The public caller
 * always supplies the already-original host `requestId`; nothing here mints,
 * randomizes or retries identifiers. No paths, actor, grant, origin or clock
 * are accepted or emitted. A successfully built request is only *ready to be
 * submitted once through the actual canonical owner* (parent integration);
 * it is never uploaded, saved or published here.
 */

/** Maximum accepted file size in bytes (read and validated before decoding). */
export const MAX_FILE_BYTES = 32768;

/** Maximum communication preference literal size in UTF-8 bytes. */
export const MAX_PREFERENCE_BYTES = 2000;

/** Wire schema discriminator for a project file add request. */
const FILE_REQUEST_SCHEMA = 'mastermind.project_file_add_request.v1';

/** Wire schema discriminator for a project preference set request. */
const PREFERENCE_REQUEST_SCHEMA = 'mastermind.project_preference_set_request.v1';

/** Trusted extension -> media type mapping (extension match is case-insensitive). */
const MEDIA_TYPES = {
  markdown: 'text/markdown',
  plain: 'text/plain',
} as const;

export type ProjectKnowledgeMediaType = (typeof MEDIA_TYPES)['markdown' | 'plain'];

/** Fixed safe error codes; no thrown input/exception text is ever retained. */
export type KnowledgeInputErrorCode =
  | 'INVALID_CONTEXT'
  | 'INVALID_REQUEST_ID'
  | 'INVALID_FILE'
  | 'UNSUPPORTED_FILE_TYPE'
  | 'FILE_TOO_LARGE'
  | 'INVALID_TEXT'
  | 'INVALID_PREFERENCE'
  | 'SOURCE_CHANGED'
  | 'CANCELLED'
  | 'READ_FAILED';

const WORK_REF_BODY_PATTERN = /^[A-Z0-9]+(?:-[A-Z0-9]+)*$/;
const LOWER_HEX_40_PATTERN = /^[0-9a-f]{40}$/;
const LOWER_HEX_64_PATTERN = /^[0-9a-f]{64}$/;
const FILE_REQUEST_ID_PATTERN = /^mmos-project-file-add-[0-9a-f]{40}$/;
const PREFERENCE_REQUEST_ID_PATTERN = /^mmos-project-preference-set-[0-9a-f]{40}$/;
const FILE_REQUEST_ID_PREFIX = 'mmos-project-file-add-';
const PREFERENCE_REQUEST_ID_PREFIX = 'mmos-project-preference-set-';
const WORK_REF_PREFIX = 'WS:';
const CONTEXT_FIELDS = ['workRef', 'sourceCommit', 'baseRevision'] as const;
const DISPLAY_NAME_MAX_BYTES = 128;
const UTF8_ENCODER = new TextEncoder();

/** Exact source context the caller must present (strict, closed). */
export interface ProjectKnowledgeSourceContext {
  workRef: string;
  sourceCommit: string;
  baseRevision: string;
}

/** Closed file part of the public file add request. */
export interface ProjectFileAddRequestFile {
  display_name: string;
  media_type: ProjectKnowledgeMediaType;
  content_utf8: string;
}

/** Exact closed wire shape of a project file add request. */
export interface ProjectFileAddRequest {
  schema: typeof FILE_REQUEST_SCHEMA;
  request_id: string;
  work_ref: string;
  source_commit: string;
  base_revision: string;
  file: ProjectFileAddRequestFile;
}

/** Exact closed wire shape of a project preference set request. */
export interface ProjectPreferenceSetRequest {
  schema: typeof PREFERENCE_REQUEST_SCHEMA;
  request_id: string;
  work_ref: string;
  source_commit: string;
  base_revision: string;
  expected_preference_revision: string | null;
  value: string;
}

/**
 * Callback the caller supplies to re-prove source currency. It must return the
 * exact same three context fields on start and after every awaited read; it
 * may throw, which is reported as SOURCE_CHANGED. It grants nothing.
 */
export type ProjectSourceCurrentFn = (
  snapshot: ProjectKnowledgeSourceContext,
) => ProjectKnowledgeSourceContext;

/** Error with a fixed safe code; never carries input or exception text. */
export class KnowledgeInputError extends Error {
  readonly code: KnowledgeInputErrorCode;

  constructor(code: KnowledgeInputErrorCode, _message?: string) {
    const closed = ['INVALID_CONTEXT','INVALID_REQUEST_ID','INVALID_FILE','UNSUPPORTED_FILE_TYPE',
      'FILE_TOO_LARGE','INVALID_TEXT','INVALID_PREFERENCE','SOURCE_CHANGED','CANCELLED','READ_FAILED'];
    const safeCode = closed.includes(code) ? code : 'READ_FAILED';
    super(safeCode);
    this.name = 'KnowledgeInputError';
    this.code = safeCode as KnowledgeInputErrorCode;
    Object.freeze(this);
  }
}

function reject(code: KnowledgeInputErrorCode, message: string): never {
  throw new KnowledgeInputError(code, message);
}

/**
 * True only for an ordinary plain data object: ordinary or null prototype,
 * no symbols, and every own property an enumerable *data* property (accessors
 * rejected). Descriptors never invoke getters. Frozen objects are accepted —
 * the module's own outputs are deep-frozen.
 */
function isPlainDataObject(value: unknown): value is Record<string, unknown> {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    return false;
  }
  let proto: unknown;
  try { proto = Object.getPrototypeOf(value); } catch { return false; }
  if (proto !== Object.prototype && proto !== null) {
    return false;
  }
  let descriptors: Record<string, PropertyDescriptor>;
  try {
    if (Object.getOwnPropertySymbols(value).length !== 0) return false;
    descriptors = Object.getOwnPropertyDescriptors(value);
  } catch {
    return false;
  }
  for (const key of Object.keys(descriptors)) {
    const descriptor = descriptors[key];
    if (!descriptor) return false;
    if (descriptor.get !== undefined || descriptor.set !== undefined) return false;
    if (!('value' in descriptor)) return false;
    if (descriptor.enumerable !== true) return false;
  }
  return true;
}

/** Exact own-key-set check on an already plain data object. */
function requireExactKeys(
  object: Record<string, unknown>,
  expected: readonly string[],
  code: KnowledgeInputErrorCode,
): void {
  const actual = Object.getOwnPropertyNames(object);
  if (actual.length !== expected.length) {
    reject(code, 'object must contain exactly the expected fields');
  }
  for (const key of expected) {
    if (!Object.prototype.hasOwnProperty.call(object, key)) {
      reject(code, 'object must contain exactly the expected fields');
    }
  }
}

/** Reads an own string field through its data descriptor (never a getter call path). */
function readStringField(
  object: Record<string, unknown>,
  key: string,
  code: KnowledgeInputErrorCode,
): string {
  const descriptor = Object.getOwnPropertyDescriptor(object, key);
  if (!descriptor || !('value' in descriptor)) {
    reject(code, 'field must be an own data property');
  }
  const value: unknown = descriptor.value;
  if (typeof value !== 'string') {
    reject(code, 'field must be a string');
  }
  return value;
}

function readDataField(
  object: Record<string, unknown>,
  key: string,
  code: KnowledgeInputErrorCode,
): Record<string, unknown> {
  const descriptor = Object.getOwnPropertyDescriptor(object, key);
  if (!descriptor || !('value' in descriptor)) {
    reject(code, 'field must be an own data property');
  }
  const value: unknown = descriptor.value;
  if (!isPlainDataObject(value)) {
    reject(code, 'field must be a plain closed data object');
  }
  return value;
}

/**
 * Validates the strict source context and returns an immutable detached
 * snapshot taken before any read. Trailing newlines are rejected because the
 * patterns are anchored to the actual full string.
 */
function validateSourceContext(
  context: ProjectKnowledgeSourceContext,
): ProjectKnowledgeSourceContext {
  if (!isPlainDataObject(context)) {
    reject('INVALID_CONTEXT', 'source context must be a plain closed data object');
  }
  requireExactKeys(context, CONTEXT_FIELDS, 'INVALID_CONTEXT');
  const workRef = readStringField(context, 'workRef', 'INVALID_CONTEXT');
  const sourceCommit = readStringField(context, 'sourceCommit', 'INVALID_CONTEXT');
  const baseRevision = readStringField(context, 'baseRevision', 'INVALID_CONTEXT');
  if (!workRef.startsWith(WORK_REF_PREFIX)) {
    reject('INVALID_CONTEXT', 'workRef must use the WS: namespace');
  }
  const body = workRef.slice(WORK_REF_PREFIX.length);
  if (body.length < 2 || body.length > 64 || !WORK_REF_BODY_PATTERN.test(body)) {
    reject('INVALID_CONTEXT', 'workRef body must be 2..64 uppercase alphanumeric dash groups');
  }
  if (sourceCommit.length !== 40 || !LOWER_HEX_40_PATTERN.test(sourceCommit)) {
    reject('INVALID_CONTEXT', 'sourceCommit must be 40 lowercase hex characters');
  }
  if (baseRevision.length !== 64 || !LOWER_HEX_64_PATTERN.test(baseRevision)) {
    reject('INVALID_CONTEXT', 'baseRevision must be 64 lowercase hex characters');
  }
  return Object.freeze({ workRef, sourceCommit, baseRevision });
}

/** Exact host-supplied request id; the caller owns the original identifier. */
function validateRequestId(requestId: unknown, pattern: RegExp, code: KnowledgeInputErrorCode): string {
  if (typeof requestId !== 'string' || !pattern.test(requestId)) {
    reject(code, 'request_id must be the original host identifier with the exact prefix');
  }
  return requestId;
}

/**
 * Abort fence. A null/undefined signal never aborts. A malformed signal (or a
 * signal access that throws) is treated as unproven and cancels: this helper
 * never produces a request when it cannot prove the caller is still current.
 */
function ensureNotAborted(signal: AbortSignal | null | undefined): void {
  if (signal === null || signal === undefined) return;
  let aborted: unknown;
  try {
    aborted = signal.aborted;
  } catch {
    reject('CANCELLED', 'operation cancelled before request construction');
  }
  if (aborted !== false) {
    reject('CANCELLED', 'operation cancelled before request construction');
  }
}

/** Runs the currency callback and compares against the detached snapshot. */
function requireSourceCurrent(
  current: ProjectSourceCurrentFn,
  snapshot: ProjectKnowledgeSourceContext,
): void {
  let returned: unknown;
  try {
    returned = current(snapshot);
  } catch (error: unknown) {
    if (error instanceof KnowledgeInputError && error.code === 'SOURCE_CHANGED') throw error;
    reject('SOURCE_CHANGED', 'source context changed');
  }
  if (!isPlainDataObject(returned)) {
    reject('SOURCE_CHANGED', 'source context changed');
  }
  requireExactKeys(returned, CONTEXT_FIELDS, 'SOURCE_CHANGED');
  for (const field of CONTEXT_FIELDS) {
    const value = readStringField(returned, field, 'SOURCE_CHANGED');
    if (value !== snapshot[field]) {
      reject('SOURCE_CHANGED', 'source context changed');
    }
  }
}

/**
 * Validates allowed scalar text: only LF, CR and TAB line controls are
 * permitted; all other C0/C1, DEL, NUL and lone surrogates are rejected.
 * No trimming or newline normalization happens anywhere in this module.
 * Returns the exact UTF-8 byte length.
 */
function assertScalarText(
  text: string,
  minBytes: number,
  maxBytes: number,
  options: { nonblank: boolean },
  code: KnowledgeInputErrorCode,
): number {
  const byteLength = UTF8_ENCODER.encode(text).length;
  if (byteLength < minBytes || byteLength > maxBytes) {
    reject(code, 'text byte length out of range');
  }
  for (const character of text) {
    const codePoint = character.codePointAt(0) as number;
    if (codePoint === 0x09 || codePoint === 0x0a || codePoint === 0x0d) continue;
    if (codePoint < 0x20) reject(code, 'control character not allowed');
    if (codePoint >= 0x7f && codePoint <= 0x9f) reject(code, 'control character not allowed');
    if (codePoint >= 0xd800 && codePoint <= 0xdfff) reject(code, 'lone surrogate not allowed');
  }
  if (options.nonblank && !/\S/.test(text)) {
    reject(code, 'value must be nonblank');
  }
  return byteLength;
}

/** Validates a display name that is already a basename (1..128 UTF-8 bytes). */
function validateDisplayName(name: string): string {
  if (typeof name !== 'string' || name.length === 0) {
    reject('INVALID_FILE', 'display name required');
  }
  if (name.includes('/') || name.includes('\\')) {
    reject('INVALID_FILE', 'display name must be a bare basename');
  }
  for (const character of name) {
    const codePoint = character.codePointAt(0) as number;
    if (codePoint < 0x20 || (codePoint >= 0x7f && codePoint <= 0x9f)) {
      reject('INVALID_FILE', 'display name contains forbidden control characters');
    }
    if (codePoint >= 0xd800 && codePoint <= 0xdfff) {
      reject('INVALID_FILE', 'display name contains a lone surrogate');
    }
  }
  if (name === '.' || name === '..' || /^ +$/.test(name)) {
    reject('INVALID_FILE', 'display name is empty, dot-only or space-only');
  }
  const byteLength = UTF8_ENCODER.encode(name).length;
  if (byteLength < 1 || byteLength > DISPLAY_NAME_MAX_BYTES) {
    reject('INVALID_FILE', 'display name must be 1..128 UTF-8 bytes');
  }
  return name;
}

/** Trusted extension mapping; extension match is case-insensitive. */
function mediaTypeForBasename(basename: string): ProjectKnowledgeMediaType | null {
  const lower = basename.toLowerCase();
  if (lower.endsWith('.md')) return MEDIA_TYPES.markdown;
  if (lower.endsWith('.txt')) return MEDIA_TYPES.plain;
  return null;
}

interface CapturedFileMeta {
  readonly name: string;
  readonly size: number;
  readonly type: string;
  readonly read: () => Promise<ArrayBuffer>;
}

function isFileLike(value: unknown): value is File {
  try {
    // The native getter checks the File internal brand across realms. A
    // Symbol.toStringTag label or user-defined read method cannot establish it.
    if (typeof File === 'undefined') return false;
    const name = Object.getOwnPropertyDescriptor(File.prototype, 'name')?.get;
    return typeof name === 'function' && typeof name.call(value) === 'string';
  } catch { return false; }
}

function readMetaProperty(file: File, key: string): unknown {
  try {
    return (file as unknown as Record<string, unknown>)[key];
  } catch {
    return reject('INVALID_FILE', 'file metadata is unreadable');
  }
}

/**
 * Captures original File metadata and the original read method exactly once,
 * safely. Hostile extra caller fields on the File are never serialized;
 * throwing getters are reported as INVALID_FILE.
 */
function captureFileMeta(file: unknown): CapturedFileMeta {
  if (!isFileLike(file)) {
    reject('INVALID_FILE', 'input must be one actual browser File');
  }
  const typedFile = file as File;
  const rawName = readMetaProperty(typedFile, 'name');
  if (typeof rawName !== 'string') {
    reject('INVALID_FILE', 'file name must be a string');
  }
  const rawSize = readMetaProperty(typedFile, 'size');
  if (typeof rawSize !== 'number' || !Number.isSafeInteger(rawSize) || rawSize <= 0) {
    reject('INVALID_FILE', 'file size must be a positive integer');
  }
  if (rawSize > MAX_FILE_BYTES) {
    reject('FILE_TOO_LARGE', 'file exceeds the maximum accepted size');
  }
  const rawType = readMetaProperty(typedFile, 'type');
  if (typeof rawType !== 'string') {
    reject('INVALID_FILE', 'file type must be a string');
  }
  const rawRelativePath = readMetaProperty(typedFile, 'webkitRelativePath');
  if (typeof rawRelativePath === 'string' && rawRelativePath.length > 0) {
    reject('INVALID_FILE', 'directory selection is not accepted');
  }
  const rawRead = readMetaProperty(typedFile, 'arrayBuffer');
  if (typeof rawRead !== 'function') {
    reject('READ_FAILED', 'file byte read backend is unavailable');
  }
  const read = (rawRead as () => Promise<ArrayBuffer>).bind(typedFile);
  return { name: rawName, size: rawSize, type: rawType, read };
}

/** Reads and copies the exact file bytes, verifying the declared size holds. */
async function readFileBytes(meta: CapturedFileMeta): Promise<Uint8Array> {
  let buffer: unknown;
  try {
    buffer = await meta.read();
  } catch (error: unknown) {
    if (error instanceof KnowledgeInputError) throw error;
    reject('READ_FAILED', 'file byte read failed');
  }
  try {
    const lengthGetter = Object.getOwnPropertyDescriptor(ArrayBuffer.prototype, 'byteLength')?.get;
    const size = lengthGetter?.call(buffer);
    if (typeof size !== 'number' || size !== meta.size) reject('READ_FAILED', 'file size changed');
    if (size > MAX_FILE_BYTES) reject('FILE_TOO_LARGE', 'file exceeds maximum accepted size');
    // Native internal-brand checks plus native copy avoid forged tags/getters.
    return new Uint8Array(ArrayBuffer.prototype.slice.call(buffer, 0));
  } catch (error) {
    if (error instanceof KnowledgeInputError) throw error;
    return reject('READ_FAILED', 'file byte read did not return an ArrayBuffer');
  }
}

/** Fatal UTF-8 decode preserving BOM and authored bytes, with exact roundtrip proof. */
function decodeFileText(bytes: Uint8Array): string {
  let text: string;
  try {
    text = new TextDecoder('utf-8', { fatal: true, ignoreBOM: true }).decode(bytes);
  } catch {
    reject('INVALID_TEXT', 'file content is not valid UTF-8 text');
  }
  assertScalarText(text, 1, MAX_FILE_BYTES, { nonblank: false }, 'INVALID_TEXT');
  const roundtrip = UTF8_ENCODER.encode(text);
  if (roundtrip.length !== bytes.length) {
    reject('INVALID_TEXT', 'text roundtrip does not preserve the original bytes');
  }
  for (let index = 0; index < bytes.length; index += 1) {
    if (roundtrip[index] !== bytes[index]) {
      reject('INVALID_TEXT', 'text roundtrip does not preserve the original bytes');
    }
  }
  return text;
}

function deepFreeze<T>(value: T): T {
  Object.freeze(value);
  return value;
}

/**
 * Builds the exact closed public project file add request from one actual
 * browser File the user explicitly selected. Pure construction: on any
 * failure nothing is produced, cached, stored or uploaded.
 */
export async function buildProjectFileRequest(
  context: ProjectKnowledgeSourceContext,
  requestId: string,
  file: File,
  signal: AbortSignal | null | undefined,
  current: ProjectSourceCurrentFn,
): Promise<ProjectFileAddRequest> {
  const snapshot = validateSourceContext(context);
  validateRequestId(requestId, FILE_REQUEST_ID_PATTERN, 'INVALID_REQUEST_ID');
  if (typeof current !== 'function') {
    reject('INVALID_CONTEXT', 'source currency callback must be a function');
  }
  // Fast, fully synchronous input validation before any callback or read.
  const meta = captureFileMeta(file);
  const displayName = validateDisplayName(meta.name);
  const mediaType = mediaTypeForBasename(displayName);
  if (mediaType === null) {
    reject('UNSUPPORTED_FILE_TYPE', 'only .md and .txt files are accepted');
  }
  // File MIME must be either the empty browser-omitted type or the exact
  // expected trusted mapping (ASCII lowercase), never a caller-chosen value.
  if (meta.type !== '' && meta.type !== mediaType) {
    reject('UNSUPPORTED_FILE_TYPE', 'file type does not match the trusted extension mapping');
  }

  // Currency fence at start.
  ensureNotAborted(signal);
  requireSourceCurrent(current, snapshot);

  // The single awaited read; fenced on both sides.
  const bytes = await readFileBytes(meta);
  ensureNotAborted(signal);
  requireSourceCurrent(current, snapshot);

  const text = decodeFileText(bytes);
  // Final fence after the last await before returning the request.
  ensureNotAborted(signal);
  return deepFreeze({
    schema: FILE_REQUEST_SCHEMA,
    request_id: requestId,
    work_ref: snapshot.workRef,
    source_commit: snapshot.sourceCommit,
    base_revision: snapshot.baseRevision,
    file: deepFreeze({
      display_name: displayName,
      media_type: mediaType,
      content_utf8: text,
    }),
  });
}

/**
 * Builds the exact closed public project preference set request from one
 * literal nonblank scalar UTF-8 value. The value is preserved exactly: no
 * extraction, trimming or newline normalization. Sync, pure construction.
 */
export function buildProjectPreferenceRequest(
  context: ProjectKnowledgeSourceContext,
  requestId: string,
  expectedPreferenceRevision: string | null,
  value: string,
): ProjectPreferenceSetRequest {
  const snapshot = validateSourceContext(context);
  validateRequestId(requestId, PREFERENCE_REQUEST_ID_PATTERN, 'INVALID_REQUEST_ID');
  if (expectedPreferenceRevision !== null) {
    if (
      typeof expectedPreferenceRevision !== 'string' ||
      expectedPreferenceRevision.length !== 64 ||
      !LOWER_HEX_64_PATTERN.test(expectedPreferenceRevision)
    ) {
      reject('INVALID_PREFERENCE', 'expected preference revision must be null or 64 lowercase hex characters');
    }
  }
  if (typeof value !== 'string') {
    reject('INVALID_PREFERENCE', 'preference value must be a string');
  }
  assertScalarText(value, 1, MAX_PREFERENCE_BYTES, { nonblank: true }, 'INVALID_PREFERENCE');
  return deepFreeze({
    schema: PREFERENCE_REQUEST_SCHEMA,
    request_id: requestId,
    work_ref: snapshot.workRef,
    source_commit: snapshot.sourceCommit,
    base_revision: snapshot.baseRevision,
    expected_preference_revision: expectedPreferenceRevision,
    value,
  });
}

/**
 * Deterministic canonical JSON: object keys sorted recursively (code-unit
 * order), default JSON separators (no spaces), Unicode emitted unchanged.
 * Only the closed validated copy built below is ever serialized — arbitrary
 * caller getters are never stringified.
 */
function canonicalJson(value: unknown): string {
  if (value === null) return 'null';
  if (typeof value === 'string') return JSON.stringify(value);
  if (typeof value === 'boolean') return value ? 'true' : 'false';
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) reject('INVALID_REQUEST_ID', 'non-finite number in public request');
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) {
    return '[' + value.map((item) => canonicalJson(item)).join(',') + ']';
  }
  if (isPlainDataObject(value)) {
    const keys = Object.keys(value).sort();
    return '{' + keys.map((key) => JSON.stringify(key) + ':' + canonicalJson(value[key])).join(',') + '}';
  }
  reject('INVALID_REQUEST_ID', 'public request contains a non-canonical value');
}

/**
 * Revalidates the exact closed public request shape and returns the trusted
 * validated copy used for canonical recursion. Rejects added fields, accessors,
 * non-plain prototypes, wrong schema, wrong request-id prefix/action pairing
 * and noncanonical invalid strings. Error codes map onto the fixed set:
 * request-level shape -> INVALID_REQUEST_ID, context fields -> INVALID_CONTEXT,
 * file part -> INVALID_FILE / UNSUPPORTED_FILE_TYPE / FILE_TOO_LARGE /
 * INVALID_TEXT, preference fields -> INVALID_PREFERENCE.
 */
function validatePublicRequestCopy(request: unknown): Record<string, unknown> {
  if (!isPlainDataObject(request)) {
    reject('INVALID_REQUEST_ID', 'public request must be a plain closed data object');
  }
  const schema = readStringField(request, 'schema', 'INVALID_REQUEST_ID');
  if (schema === FILE_REQUEST_SCHEMA) {
    requireExactKeys(
      request,
      ['schema', 'request_id', 'work_ref', 'source_commit', 'base_revision', 'file'],
      'INVALID_REQUEST_ID',
    );
    const requestId = validateRequestId(
      readStringField(request, 'request_id', 'INVALID_REQUEST_ID'),
      FILE_REQUEST_ID_PATTERN,
      'INVALID_REQUEST_ID',
    );
    const workRef = validateWorkRefField(request);
    const sourceCommit = validateSourceCommitField(request);
    const baseRevision = validateBaseRevisionField(request);
    const filePart = readDataField(request, 'file', 'INVALID_FILE');
    requireExactKeys(filePart, ['display_name', 'media_type', 'content_utf8'], 'INVALID_FILE');
    const displayName = validateDisplayName(
      readStringField(filePart, 'display_name', 'INVALID_FILE'),
    );
    const mediaType = readStringField(filePart, 'media_type', 'INVALID_FILE');
    if (mediaType !== MEDIA_TYPES.markdown && mediaType !== MEDIA_TYPES.plain) {
      reject('UNSUPPORTED_FILE_TYPE', 'media type must be the exact trusted extension mapping');
    }
    const content = readStringField(filePart, 'content_utf8', 'INVALID_FILE');
    const contentBytes = UTF8_ENCODER.encode(content).length;
    if (contentBytes > MAX_FILE_BYTES) {
      reject('FILE_TOO_LARGE', 'file content exceeds the maximum accepted size');
    }
    assertScalarText(content, 1, MAX_FILE_BYTES, { nonblank: false }, 'INVALID_TEXT');
    return {
      schema,
      request_id: requestId,
      work_ref: workRef,
      source_commit: sourceCommit,
      base_revision: baseRevision,
      file: { display_name: displayName, media_type: mediaType, content_utf8: content },
    };
  }
  if (schema === PREFERENCE_REQUEST_SCHEMA) {
    requireExactKeys(
      request,
      [
        'schema',
        'request_id',
        'work_ref',
        'source_commit',
        'base_revision',
        'expected_preference_revision',
        'value',
      ],
      'INVALID_REQUEST_ID',
    );
    const requestId = validateRequestId(
      readStringField(request, 'request_id', 'INVALID_REQUEST_ID'),
      PREFERENCE_REQUEST_ID_PATTERN,
      'INVALID_REQUEST_ID',
    );
    const workRef = validateWorkRefField(request);
    const sourceCommit = validateSourceCommitField(request);
    const baseRevision = validateBaseRevisionField(request);
    const descriptor = Object.getOwnPropertyDescriptor(request, 'expected_preference_revision');
    if (!descriptor || !('value' in descriptor)) {
      reject('INVALID_PREFERENCE', 'expected preference revision must be an own data property');
    }
    const expected: unknown = descriptor.value;
    if (expected !== null) {
      if (
        typeof expected !== 'string' ||
        expected.length !== 64 ||
        !LOWER_HEX_64_PATTERN.test(expected)
      ) {
        reject('INVALID_PREFERENCE', 'expected preference revision must be null or 64 lowercase hex characters');
      }
    }
    const value = readStringField(request, 'value', 'INVALID_PREFERENCE');
    assertScalarText(value, 1, MAX_PREFERENCE_BYTES, { nonblank: true }, 'INVALID_PREFERENCE');
    return {
      schema,
      request_id: requestId,
      work_ref: workRef,
      source_commit: sourceCommit,
      base_revision: baseRevision,
      expected_preference_revision: expected,
      value,
    };
  }
  reject('INVALID_REQUEST_ID', 'public request schema is not recognized');
}

function validateWorkRefField(request: Record<string, unknown>): string {
  const workRef = readStringField(request, 'work_ref', 'INVALID_CONTEXT');
  if (!workRef.startsWith(WORK_REF_PREFIX)) {
    reject('INVALID_CONTEXT', 'work_ref must use the WS: namespace');
  }
  const body = workRef.slice(WORK_REF_PREFIX.length);
  if (body.length < 2 || body.length > 64 || !WORK_REF_BODY_PATTERN.test(body)) {
    reject('INVALID_CONTEXT', 'work_ref body must be 2..64 uppercase alphanumeric dash groups');
  }
  return workRef;
}

function validateSourceCommitField(request: Record<string, unknown>): string {
  const sourceCommit = readStringField(request, 'source_commit', 'INVALID_CONTEXT');
  if (sourceCommit.length !== 40 || !LOWER_HEX_40_PATTERN.test(sourceCommit)) {
    reject('INVALID_CONTEXT', 'source_commit must be 40 lowercase hex characters');
  }
  return sourceCommit;
}

function validateBaseRevisionField(request: Record<string, unknown>): string {
  const baseRevision = readStringField(request, 'base_revision', 'INVALID_CONTEXT');
  if (baseRevision.length !== 64 || !LOWER_HEX_64_PATTERN.test(baseRevision)) {
    reject('INVALID_CONTEXT', 'base_revision must be 64 lowercase hex characters');
  }
  return baseRevision;
}

/**
 * Canonical JSON text of the exact public validated request. Independent of
 * construction: anything that would not round-trip as the closed wire shape
 * is rejected before any serialization.
 */
export function canonicalPublicRequest(
  request: ProjectFileAddRequest | ProjectPreferenceSetRequest,
): string {
  const validated = validatePublicRequestCopy(request);
  return canonicalJson(validated);
}

/**
 * SHA-256 of the canonical public request, computed with WebCrypto over the
 * independently revalidated request. This verifies the exact public validated
 * request only; it is not the private server recipe fingerprint and never
 * carries preimages. The helper only hashes detached validated data, so no
 * source-currency fence applies here.
 */
export async function publicRequestSha256(
  request: ProjectFileAddRequest | ProjectPreferenceSetRequest,
): Promise<string> {
  const canonical = canonicalPublicRequest(request);
  const subtle: Crypto['subtle'] | undefined =
    typeof crypto !== 'undefined' ? crypto.subtle : undefined;
  if (!subtle || typeof subtle.digest !== 'function') {
    reject('READ_FAILED', 'SHA-256 digest backend is unavailable');
  }
  const digest = await subtle.digest('SHA-256', UTF8_ENCODER.encode(canonical));
  const bytes = new Uint8Array(digest);
  let hex = '';
  for (const byte of bytes) {
    hex += byte.toString(16).padStart(2, '0');
  }
  return hex;
}
