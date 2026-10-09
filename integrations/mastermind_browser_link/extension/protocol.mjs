/** Closed native-host wire contract. These fields are NOT model-facing authority. */
export const MAX_FRAME_BYTES = 65_536;
export const MAX_LIFETIME_MS = 30_000;
export const COMMAND_SCHEMA = 'mastermind.browser_link.command.v1';
export const RESULT_SCHEMA = 'mastermind.browser_link.result.v1';
export const READ_COMMANDS = Object.freeze(['snapshot', 'screenshot']);
const COMMANDS = new Set([...READ_COMMANDS, 'click', 'type', 'scroll', 'navigate']);
const REF = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;
const encoder = new TextEncoder();

export class BrowserLinkError extends Error {
  constructor(code) { super(code); this.name = 'BrowserLinkError'; this.code = code; }
}
export function refuse(code) { throw new BrowserLinkError(code); }
export function byteLength(value) { return encoder.encode(value).byteLength; }
export function boundedJSON(value, maximum = MAX_FRAME_BYTES) {
  let text;
  try { text = JSON.stringify(value); } catch { refuse('INVALID_COMMAND'); }
  if (typeof text !== 'string') refuse('INVALID_COMMAND');
  if (byteLength(text) > maximum) refuse('FRAME_TOO_LARGE');
  return text;
}
function record(value) { return value !== null && typeof value === 'object' && !Array.isArray(value); }
function keys(value, required, optional = []) {
  if (!record(value)) refuse('INVALID_COMMAND');
  const allowed = new Set([...required, ...optional]);
  if (required.some(k => !Object.hasOwn(value, k)) || Object.keys(value).some(k => !allowed.has(k))) refuse('INVALID_COMMAND');
}
function reference(value) { if (typeof value !== 'string' || !REF.test(value)) refuse('INVALID_COMMAND'); }
function integer(value, minimum = 0) { if (!Number.isSafeInteger(value) || value < minimum) refuse('INVALID_COMMAND'); }
export function httpURL(value) {
  if (typeof value !== 'string' || value.length > 2048 || /[\u0000-\u0020]/u.test(value)) refuse('INVALID_COMMAND');
  let url;
  try { url = new URL(value); } catch { refuse('INVALID_COMMAND'); }
  if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password) refuse('INVALID_COMMAND');
  return url;
}

export function validateCommand(input, now) {
  // Snapshot before any await so a caller cannot mutate a checked object later.
  const value = JSON.parse(boundedJSON(input));
  keys(value, ['schema', 'request_id', 'connection_generation', 'tab_id', 'consent_id', 'document_revision', 'expires_at_ms', 'command', 'args'], ['writer']);
  if (value.schema !== COMMAND_SCHEMA || !COMMANDS.has(value.command)) refuse('INVALID_COMMAND');
  for (const key of ['request_id', 'connection_generation', 'consent_id']) reference(value[key]);
  for (const key of ['tab_id', 'document_revision', 'expires_at_ms']) integer(value[key]);
  integer(now);
  if (value.expires_at_ms <= now) refuse('EXPIRED');
  if (value.expires_at_ms - now > MAX_LIFETIME_MS) refuse('INVALID_COMMAND');
  if (READ_COMMANDS.includes(value.command)) {
    if (Object.hasOwn(value, 'writer')) refuse('INVALID_COMMAND');
    keys(value.args, []);
  } else {
    keys(value.writer, ['holder_ref', 'fence']); reference(value.writer.holder_ref); integer(value.writer.fence);
    if (value.command === 'click') { keys(value.args, ['element_ref']); reference(value.args.element_ref); }
    if (value.command === 'type') {
      keys(value.args, ['element_ref', 'text']); reference(value.args.element_ref);
      if (typeof value.args.text !== 'string' || byteLength(value.args.text) > 16_384 || value.args.text.includes('\0')) refuse('INVALID_COMMAND');
    }
    if (value.command === 'scroll') {
      keys(value.args, ['delta_x', 'delta_y']);
      for (const field of ['delta_x', 'delta_y']) if (!Number.isSafeInteger(value.args[field]) || Math.abs(value.args[field]) > 2000) refuse('INVALID_COMMAND');
    }
    if (value.command === 'navigate') { keys(value.args, ['url']); value.args.url = httpURL(value.args.url).href; }
    Object.freeze(value.writer);
  }
  Object.freeze(value.args);
  return Object.freeze(value);
}
