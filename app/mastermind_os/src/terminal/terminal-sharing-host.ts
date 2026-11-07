/**
 * Native Terminal sharing host: the distinct Terminal Supabase session epoch,
 * the bounded sharing-request feed read and the fixed review handoff.
 *
 * Pure composition over the supplied native ports. No browser fallback, no
 * global Auth0 borrowing, no raw tokens, codes, URLs, user or session UUIDs;
 * only opaque scope hashes and explicit issued requests cross this boundary.
 *
 * Every failure surfaces as the single closed code `TERMINAL_SHARING_UNAVAILABLE`
 * with no exception text. Reads never sign in, refresh or retry; a dropped read
 * (abort, dispose, logout or epoch change) resolves without a feed. Review is
 * provenance-guarded: only decoded request objects issued by this host's own
 * reads are accepted, one attempt per auth epoch and request tuple per host
 * lifetime, and every outcome — rejection, malformed or mismatched receipt — is
 * retained, never replayed.
 */

import {
  dataRecord,
  decodeTerminalSessionStatus,
  decodeTerminalSharingFeed,
  terminalSharingUnavailable,
  type TerminalSessionStatus,
  type TerminalSharingFeed,
  type TerminalSharingRequest,
} from "./terminal-sharing-contract";

export type { TerminalSessionStatus };

/** Native invoke port; commands and argument shapes are fixed below. */
export type TerminalSharingInvoke = (
  command: string,
  args?: Record<string, unknown>,
) => Promise<unknown>;

/** Native event subscribe port; returns the unlisten function. */
export type TerminalSharingListen = (
  event: string,
  handler: (payload: unknown) => void,
) => Promise<() => void>;

const SESSION_CHANGED_EVENT = "terminal-session-changed";
const STATUS_COMMAND = "terminal_session_status";
const SIGN_IN_COMMAND = "terminal_sign_in";
const DISCONNECT_COMMAND = "terminal_disconnect";
const READ_COMMAND = "read_terminal_sharing_requests";
const OPEN_COMMAND = "open_terminal_sharing_request";

const HANDOFF_SCHEMA = "mastermind.terminal_sharing_handoff.v1";
const HANDOFF_OUTCOME = "HANDOFF_REQUESTED";
const HANDOFF_KEYS = [
  "schema",
  "request_ref",
  "revision",
  "delivery_id",
  "outcome",
] as const;

export interface TerminalSharingHandoffReceipt {
  readonly schema: "mastermind.terminal_sharing_handoff.v1";
  readonly request_ref: string;
  readonly revision: 1;
  readonly delivery_id: string;
  readonly outcome: "HANDOFF_REQUESTED";
}

export interface TerminalSharingFeedRead {
  /** Auth epoch the feed was read under; the hook binds rows to it. */
  readonly generation: number;
  readonly feed: TerminalSharingFeed;
}

export interface TerminalSharingHost {
  /** Last known public own status; opaque scope hashes only. */
  getState(): TerminalSessionStatus;
  subscribe(listener: (state: TerminalSessionStatus) => void): () => void;
  /** Explicit sign-in command only; resolves without any URL, token or grant. */
  connect(): Promise<void>;
  /** Explicit disconnect command only. */
  disconnect(): Promise<void>;
  /**
   * One bounded feed read under the current signed-in snapshot. Resolves
   * `null` when the read is dropped (aborted, disposed, epoch or scopes moved
   * pre/post); rejects with the closed code otherwise. Never signs in,
   * refreshes, retries or polls.
   */
  readRequests(request: { signal: AbortSignal }): Promise<TerminalSharingFeedRead | null>;
  /**
   * Requests review navigation for a request object issued by this host's
   * current read. Forged or cloned objects, stale epochs and repeated
   * attempts for the same epoch and tuple are refused without a native call.
   */
  reviewRequest(request: TerminalSharingRequest): Promise<TerminalSharingHandoffReceipt>;
  /** Unsubscribes the session listener and fences all pending work. */
  dispose(): void;
}

function sameStatus(a: TerminalSessionStatus, b: TerminalSessionStatus): boolean {
  return (
    a.state === b.state &&
    a.generation === b.generation &&
    a.reason === b.reason &&
    a.available === b.available &&
    a.principal_scope === b.principal_scope &&
    a.session_scope === b.session_scope
  );
}

interface IssuedProvenance {
  readonly generation: number;
  readonly principalScope: string;
  readonly sessionScope: string;
}

function decodeHandoffReceipt(
  value: unknown,
  requestRef: string,
  deliveryId: string,
): TerminalSharingHandoffReceipt {
  const record = dataRecord(value, HANDOFF_KEYS);
  if (record === null) throw terminalSharingUnavailable();
  if (record["schema"] !== HANDOFF_SCHEMA) throw terminalSharingUnavailable();
  if (record["outcome"] !== HANDOFF_OUTCOME) throw terminalSharingUnavailable();
  if (typeof record["revision"] !== "number" || record["revision"] !== 1) {
    throw terminalSharingUnavailable();
  }
  // Exact echo of the selected tuple; any Shared/closed outcome or foreign ref
  // is refused outright, never interpreted as navigation.
  if (record["request_ref"] !== requestRef) throw terminalSharingUnavailable();
  if (record["delivery_id"] !== deliveryId) throw terminalSharingUnavailable();
  return {
    schema: HANDOFF_SCHEMA,
    request_ref: requestRef,
    revision: 1,
    delivery_id: deliveryId,
    outcome: HANDOFF_OUTCOME,
  };
}

export async function createTerminalSharingHost(
  invoke: TerminalSharingInvoke,
  listen: TerminalSharingListen,
): Promise<TerminalSharingHost> {
  let disposed = false;
  let status: TerminalSessionStatus | null = null;
  let unlisten: (() => void) | null = null;
  const listeners = new Set<(state: TerminalSessionStatus) => void>();
  const issuedRequests = new WeakMap<TerminalSharingRequest, IssuedProvenance>();
  const reviewAttempts = new Map<string, true>();

  let statusRevision = 0;
  const publish = (next: TerminalSessionStatus): void => {
    if (status !== null && next.generation < status.generation) return;
    if (status !== null && sameStatus(status, next)) return;
    status = next;
    for (const listener of [...listeners]) listener(status);
  };

  // Coalesced status re-read with a race guard: an event arriving while a read
  // is in flight schedules exactly one follow-up read; stale completions never
  // publish. A failed status read keeps the last known status, never
  // synthesizes a replacement and never retries by itself.
  let reading = false;
  let rerun = false;
  const refresh = async (): Promise<void> => {
    if (disposed || reading) {
      rerun = true;
      return;
    }
    reading = true;
    try {
      do {
        rerun = false;
        const revision = statusRevision;
        const next = decodeTerminalSessionStatus(await invoke(STATUS_COMMAND));
        if (disposed) return;
        if (revision === statusRevision) publish(next);
      } while (rerun && !disposed);
    } catch {
      // Closed native failure; a later explicit change event re-reads.
    } finally {
      reading = false;
    }
  };

  const readRequests = async (
    request: { signal: AbortSignal },
  ): Promise<TerminalSharingFeedRead | null> => {
    if (disposed || status === null) throw terminalSharingUnavailable();
    const snapshot = status;
    // Current own signed-in snapshot only; a missing capability is never
    // replaced by a global grant, an automatic sign-in or a refresh.
    if (
      snapshot.state !== "SIGNED_IN" ||
      !snapshot.available ||
      snapshot.principal_scope === null ||
      snapshot.session_scope === null
    ) {
      throw terminalSharingUnavailable();
    }
    if (request.signal.aborted) return null;
    const principalScope = snapshot.principal_scope;
    const sessionScope = snapshot.session_scope;
    const generation = snapshot.generation;
    let raw: unknown;
    try {
      raw = await invoke(READ_COMMAND); // zero arguments by contract
    } catch {
      throw terminalSharingUnavailable();
    }
    if (disposed || request.signal.aborted) return null;
    const current = status;
    if (
      current === null ||
      current.state !== "SIGNED_IN" ||
      !current.available ||
      current.generation !== generation ||
      current.principal_scope !== principalScope ||
      current.session_scope !== sessionScope
    ) {
      return null; // post logout or epoch move: drop, never replay
    }
    const feed = decodeTerminalSharingFeed(raw, {
      principalScope,
      sessionScope,
    });
    for (const issued of feed.requests) {
      issuedRequests.set(issued, { generation, principalScope, sessionScope });
    }
    return { generation, feed };
  };

  const reviewRequest = async (
    request: TerminalSharingRequest,
  ): Promise<TerminalSharingHandoffReceipt> => {
    if (disposed || status === null) throw terminalSharingUnavailable();
    const current = status;
    const provenance = issuedRequests.get(request);
    if (provenance === undefined) throw terminalSharingUnavailable();
    if (
      current.state !== "SIGNED_IN" ||
      !current.available ||
      provenance.generation !== current.generation ||
      provenance.principalScope !== current.principal_scope ||
      provenance.sessionScope !== current.session_scope
    ) {
      throw terminalSharingUnavailable();
    }
    const deliveryId = request.delivery.delivery_id;
    const attemptKey = [
      provenance.generation,
      request.request_ref,
      request.revision,
      deliveryId,
      request.delivery.content_sha256,
    ].join("|");
    // One attempt per auth epoch and request tuple per host lifetime;
    // rejections and malformed outcomes are retained, never replayed.
    if (reviewAttempts.has(attemptKey)) throw terminalSharingUnavailable();
    reviewAttempts.set(attemptKey, true);
    let raw: unknown;
    try {
      // No URL, team, principal or grant argument: the native side
      // revalidates the request against the actual current feed.
      raw = await invoke(OPEN_COMMAND, { selection: {
        request_ref: request.request_ref,
        revision: 1,
        delivery_id: deliveryId,
        content_sha256: request.delivery.content_sha256,
      } });
    } catch {
      throw terminalSharingUnavailable();
    }
    if (disposed || status !== current) throw terminalSharingUnavailable();
    return decodeHandoffReceipt(raw, request.request_ref, deliveryId);
  };

  try {
    // Subscribe before the first status read so no change event is lost; the
    // race guard collapses any change that lands during that read.
    unlisten = await listen(SESSION_CHANGED_EVENT, payload => {
      statusRevision++;
      try { publish(decodeTerminalSessionStatus(payload)); }
      catch { void refresh(); }
    });
    await refresh();
  } catch {
    throw terminalSharingUnavailable();
  } finally {
    if (status === null && unlisten !== null) {
      const pending = unlisten;
      unlisten = null;
      try {
        pending();
      } catch {
        // Native unlisten failure never masks the closed constructor outcome.
      }
    }
  }
  if (disposed || status === null) throw terminalSharingUnavailable();

  return {
    getState: () => {
      if (status === null) throw terminalSharingUnavailable();
      return status;
    },
    subscribe: (listener) => {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    connect: async () => {
      if (disposed) throw terminalSharingUnavailable();
      try {
        const next = decodeTerminalSessionStatus(await invoke(SIGN_IN_COMMAND));
        if (!disposed) { statusRevision++; publish(next); }
      } catch {
        throw terminalSharingUnavailable();
      }
    },
    disconnect: async () => {
      if (disposed) throw terminalSharingUnavailable();
      try {
        const next = decodeTerminalSessionStatus(await invoke(DISCONNECT_COMMAND));
        if (!disposed) { statusRevision++; publish(next); }
      } catch {
        throw terminalSharingUnavailable();
      }
    },
    readRequests,
    reviewRequest,
    dispose: () => {
      if (disposed) return;
      disposed = true;
      listeners.clear();
      if (unlisten !== null) {
        const pending = unlisten;
        unlisten = null;
        try {
          pending();
        } catch {
          // A native unlisten failure never leaks past dispose.
        }
      }
    },
  };
}

/** A not-yet-observed Terminal session remains unknown; it never delays Auth0. */
export interface TerminalSharingSource extends Omit<TerminalSharingHost, "getState"> {
  getState(): TerminalSessionStatus | null;
}

/** Initialize this independent capability only when its own consumer subscribes. */
export function createLazyTerminalSharingHost(
  invoke: TerminalSharingInvoke, listen: TerminalSharingListen,
): TerminalSharingSource {
  let actual: TerminalSharingHost | null = null;
  let pending: Promise<TerminalSharingHost> | null = null;
  let disposed = false;
  let stop: (() => void) | null = null;
  const listeners = new Set<(status: TerminalSessionStatus) => void>();
  const start = (): Promise<TerminalSharingHost> => {
    if (disposed) return Promise.reject(terminalSharingUnavailable());
    if (pending === null) pending = createTerminalSharingHost(invoke, listen).then(host => {
      if (disposed) { host.dispose(); throw terminalSharingUnavailable(); }
      actual = host;
      stop = host.subscribe(status => { for (const listener of [...listeners]) listener(status); });
      for (const listener of [...listeners]) listener(host.getState());
      return host;
    });
    return pending;
  };
  return {
    getState: () => actual?.getState() ?? null,
    subscribe: listener => {
      listeners.add(listener);
      if (actual !== null) listener(actual.getState());
      else void start().catch(() => {});
      return () => { listeners.delete(listener); };
    },
    connect: async () => { await (await start()).connect(); },
    disconnect: async () => { await (await start()).disconnect(); },
    readRequests: async request => (await start()).readRequests(request),
    reviewRequest: async request => (await start()).reviewRequest(request),
    dispose: () => { disposed = true; stop?.(); actual?.dispose(); listeners.clear(); },
  };
}
