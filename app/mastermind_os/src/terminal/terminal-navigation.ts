/**
 * Fixed Terminal navigation consumer port for the host `open_terminal_briefs` command.
 * Pure module: no imports, no I/O, no globals, no URLs, no auth, timers, retry or fallback.
 * The Terminal destination is fixed owner-side and is deliberately not represented here:
 * a resolved receipt states only that a handoff was requested. It never proves that the
 * browser loaded, signed in or rendered content, nor any audience access, sharing or receipt.
 */

/** Closed landing receipt produced by the fixed host command. */
export interface TerminalBriefsLandingReceipt {
  readonly schema: 'mastermind.terminal_navigation.v1';
  readonly destination: 'TERMINAL_BRIEFS';
  readonly outcome: 'HANDOFF_REQUESTED';
}

/** Zero-input frontend navigation port: request the handoff once, decode, nothing else. */
export type TerminalBriefsNavigationPort = () => Promise<TerminalBriefsLandingReceipt>;

const RECEIPT_SCHEMA = 'mastermind.terminal_navigation.v1';
const RECEIPT_DESTINATION = 'TERMINAL_BRIEFS';
const RECEIPT_OUTCOME = 'HANDOFF_REQUESTED';
const RECEIPT_KEYS = ['schema', 'destination', 'outcome'];
const HANDOFF_UNAVAILABLE = 'TERMINAL_HANDOFF_UNAVAILABLE';

function handoffUnavailable(): Error {
  return new Error(HANDOFF_UNAVAILABLE);
}

function plainRecord(value: unknown): Record<string, unknown> | null {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) return null;
  const prototype = Object.getPrototypeOf(value);
  return prototype === Object.prototype || prototype === null
    ? (value as Record<string, unknown>)
    : null;
}

function tryDecode(value: unknown): TerminalBriefsLandingReceipt | null {
  try {
    const record = plainRecord(value);
    if (record === null || Reflect.ownKeys(record).length !== RECEIPT_KEYS.length) return null;
    for (const key of RECEIPT_KEYS) {
      if (!Object.prototype.hasOwnProperty.call(record, key)) return null;
    }
    if (
      record.schema !== RECEIPT_SCHEMA ||
      record.destination !== RECEIPT_DESTINATION ||
      record.outcome !== RECEIPT_OUTCOME
    ) {
      return null;
    }
    return { schema: RECEIPT_SCHEMA, destination: RECEIPT_DESTINATION, outcome: RECEIPT_OUTCOME };
  } catch {
    return null; // Native inspection failures never leak input or exception contents.
  }
}

export function decodeTerminalBriefsLandingReceipt(value: unknown): TerminalBriefsLandingReceipt {
  const decoded = tryDecode(value);
  if (decoded === null) throw handoffUnavailable();
  return decoded;
}

export function createTerminalBriefsNavigationPort(
  invoke: (command: 'open_terminal_briefs') => Promise<unknown>,
): TerminalBriefsNavigationPort {
  // No abort signal: an already requested external navigation cannot be undone client-side.
  return async (): Promise<TerminalBriefsLandingReceipt> => {
    let raw: unknown;
    try {
      raw = await invoke('open_terminal_briefs');
    } catch {
      throw handoffUnavailable(); // No retry; uncertainty is never interpreted as success.
    }
    return decodeTerminalBriefsLandingReceipt(raw);
  };
}
