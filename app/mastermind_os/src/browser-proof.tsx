/**
 * SOURCE FIXTURE — compiled-browser test harness for the Mastermind OS
 * selected-session answer flow (source pin e93). TEST-ONLY ENTRY.
 *
 * Guarantees:
 *  - This file is never imported by the product entry and no product module
 *    imports it. The default `npm run build` keeps input index.html, so this
 *    harness can never enter the production bundle (see the separate
 *    vite.browser-proof.config.ts beside the app root).
 *  - It mounts the REAL product App with the REAL session host factory
 *    (createOsExecutiveSessionHost) and the REAL durable IndexedDB pending
 *    pointer store (createIndexedDbSessionPendingPointerStore). Reload
 *    retention of the original operation pointer is proven by that real
 *    store, not by any new persistence mechanism.
 *  - Every transport payload below is a loudly synthetic, correctly shaped
 *    fixture envelope matching the pin-e93 transport contracts. There is no
 *    authentication, provider task, real SEND or parent consumption anywhere.
 *  - The signed_in display is a fixture default for tests only; it is not
 *    real authentication evidence. No user emails, accounts or secrets exist
 *    in this file; every scope/ref/key/fingerprint is a synthetic constant.
 *  - Requires a dedicated localhost test origin: the durable store uses the
 *    production database name (mastermind-os-session-pending-v1) by design,
 *    so this harness must never share an origin with a real profile.
 */
import { useSyncExternalStore, type CSSProperties } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { createOsExecutiveSessionHost } from "./orchestration/os-executive-session-host";
import type { OsExecutiveSessionHost } from "./orchestration/os-executive-session-host";
import { createIndexedDbSessionPendingPointerStore } from "./orchestration/indexeddb-session-pending-pointer-store";
import { sha256Hex } from "./orchestration/operation-key";
import type { ExecutiveSessionTransport } from "./orchestration/executive-session-command-port";
import type { AuthState } from "./host";
import type { MissionSelection } from "./mission";
import "./styles.css";

// ── Synthetic fixture vocabulary (never real identifiers) ────────────────────

const SCOPE = "c".repeat(64);
const REF = `fabric_attempt:${"a".repeat(64)}`;
const ORIGINAL_KEY = `session-continue-${"b".repeat(64)}`;
const ADVANCED_KEY = `session-continue-${"d".repeat(64)}`;
const OTHER_REF = `fabric_attempt:${"9".repeat(64)}`;
const OTHER_KEY = `session-continue-${"e".repeat(64)}`;
const TARGET_GENERATION = "a".repeat(24);
const FINGERPRINT = "f".repeat(64);
const THREAD_TS = "1789999999.123456";
const READ_REF = "read-ref-1";
const REQUEST_REF = "request-ref-1";
const CONTINUE_DOMAIN = "mastermind.session_bridge.continue.v1\n";
const NATIVE_REPLY_DOMAIN = "mastermind.session_bridge.native_reply.v1\n";
const FIXTURE_SELECTION: MissionSelection = { workRef: "WS:ALPHA", rootJobId: "JOB-1" };

/** Canonical owner derivations, verbatim from the pin-e93 port contract. */
const continueCarrierKey = (operationKey: string): string =>
  "asd-dot-continue-" + sha256Hex(CONTINUE_DOMAIN + operationKey).slice(0, 40);
const nativeReplyKeyOf = (operationKey: string): string =>
  "asd-native-reply-" + sha256Hex(NATIVE_REPLY_DOMAIN + operationKey).slice(0, 40);

const signedIn: AuthState = {
  status: "signed_in",
  reason: null,
  acquisition: false,
  content: false,
};
const signedOut: AuthState = {
  status: "signed_out",
  reason: null,
  acquisition: false,
  content: false,
};

// ── Mutable fixture state and driver controls ────────────────────────────────

const fixture = {
  auth: signedIn,
  generation: 1,
  canonicalKey: ORIGINAL_KEY,
  replyAvailable: false,
  delayReply: false,
  loseSend: false,
  sendCount: 0,
  replyCount: 0,
  /** Keys this synthetic owner ever issued; reply fails closed otherwise. */
  issuedKeys: new Set<string>([ORIGINAL_KEY, ADVANCED_KEY, OTHER_KEY]),
  deferred: [] as Array<{ envelope: unknown; resolve: (value: unknown) => void }>,
};

const authListeners = new Set<(state: AuthState) => void>();
const transportListeners = new Set<() => void>();

interface FixtureSnapshot {
  sendCount: number;
  replyCount: number;
  deferredCount: number;
  generation: number;
  authStatus: AuthState["status"];
  replyAvailable: boolean;
  delayReply: boolean;
  loseSend: boolean;
  canonicalKey: string;
}

let fixtureSnapshot: FixtureSnapshot = {
  sendCount: 0,
  replyCount: 0,
  deferredCount: 0,
  generation: 1,
  authStatus: signedIn.status,
  replyAvailable: false,
  delayReply: false,
  loseSend: false,
  canonicalKey: ORIGINAL_KEY,
};
const controlsListeners = new Set<() => void>();

function bumpFixtureSnapshot(): void {
  fixtureSnapshot = {
    sendCount: fixture.sendCount,
    replyCount: fixture.replyCount,
    deferredCount: fixture.deferred.length,
    generation: fixture.generation,
    authStatus: fixture.auth.status,
    replyAvailable: fixture.replyAvailable,
    delayReply: fixture.delayReply,
    loseSend: fixture.loseSend,
    canonicalKey: fixture.canonicalKey,
  };
  for (const listener of controlsListeners) listener();
}

function subscribeFixture(listener: () => void): () => void {
  controlsListeners.add(listener);
  return () => {
    controlsListeners.delete(listener);
  };
}

function notifyAuthAndTransport(): void {
  const snapshotAuth = { ...fixture.auth };
  for (const listener of authListeners) listener(snapshotAuth);
  for (const listener of transportListeners) listener();
  bumpFixtureSnapshot();
}

function invalidateAuthEpoch(): void {
  fixture.generation += 1;
  notifyAuthAndTransport();
}

function notifyPublicSignedOut(): void {
  fixture.auth = signedOut;
  fixture.generation += 1;
  notifyAuthAndTransport();
}

function selectFixtureMission(original: boolean): void {
  const params = new URLSearchParams({ work_ref: original ? "WS:ALPHA" : "WS:BETA", root_job_id: original ? "JOB-1" : "JOB-2" });
  window.history.replaceState(null, "", `${window.location.pathname}?${params}`);
  window.dispatchEvent(new PopStateEvent("popstate"));
}

function releaseDeferredReplies(): void {
  const pending = fixture.deferred.splice(0);
  for (const entry of pending) entry.resolve(entry.envelope);
  bumpFixtureSnapshot();
}

let mountedSessionHost: OsExecutiveSessionHost | null = null;

function advanceCanonicalKey(): void {
  fixture.canonicalKey = ADVANCED_KEY;
  // Owner projection change only: target ref and target generation stay
  // unchanged and no auth epoch is bumped (not a Wake). The real host
  // factory re-qualifies through the context envelope.
  void mountedSessionHost?.refresh(FIXTURE_SELECTION);
  bumpFixtureSnapshot();
}

function setReplyAvailable(value: boolean): void {
  fixture.replyAvailable = value;
  bumpFixtureSnapshot();
}

function setDelayReply(value: boolean): void {
  fixture.delayReply = value;
  bumpFixtureSnapshot();
}

function setLoseSend(value: boolean): void {
  fixture.loseSend = value;
  bumpFixtureSnapshot();
}

// ── Synthetic transport envelopes (exact pin-e93 field sets) ─────────────────

const resultEnvelope = (operation: string, patch: Record<string, unknown>): unknown => ({
  schema: "mastermind.os.executive.session_result.v1",
  operation,
  ok: true,
  effect: "NONE",
  operation_key: null,
  data: null,
  error: null,
  ...patch,
});

const contextEnvelope = (selection: { workRef: string; rootJobId: string }): unknown =>
  resultEnvelope("context", {
    data: {
      schema: "mastermind.os.executive.session_context.v1",
      principal_scope: SCOPE,
      verified_expiry: Math.floor(Date.now() / 1000) + 3600,
      selection: { work_ref: selection.workRef, root_job_id: selection.rootJobId },
      selection_state: "RESOLVED",
      target: {
        target_ref: selection.workRef === "WS:ALPHA" && selection.rootJobId === "JOB-1" ? REF : OTHER_REF,
        generation: selection.workRef === "WS:ALPHA" && selection.rootJobId === "JOB-1" ? TARGET_GENERATION : "9".repeat(24),
        addressable: true,
        kind: "fabric_attempt",
        continuation_operation_key: selection.workRef === "WS:ALPHA" && selection.rootJobId === "JOB-1" ? fixture.canonicalKey : OTHER_KEY,
        work_ref: selection.workRef,
        root_job_id: selection.rootJobId,
      },
      capabilities: { send: true, reply_read: true, stop: false },
    },
  });

const sendEnvelopeFor = (args: { target_ref: string; operation_key: string }): unknown =>
  resultEnvelope("send", {
    ok: true,
    effect: "CONTINUATION_COMMITTED",
    operation_key: args.operation_key,
    data: {
      target_ref: args.target_ref,
      reply_committed: true,
      carrier: {
        reply_committed: true,
        action: "POSTED",
        message_key: continueCarrierKey(args.operation_key),
        fingerprint: FINGERPRINT,
        thread_ts: THREAD_TS,
      },
      attention: { state: "UNAVAILABLE" },
      read_ref: READ_REF,
    },
  });

const exactReplyEnvelope = (operationKey: string): unknown =>
  resultEnvelope("reply", {
    ok: true,
    effect: "CONTINUATION_COMMITTED",
    operation_key: operationKey,
    data: {
      schema: "mastermind.native_reply_read.v1",
      read_ref: READ_REF,
      request_ref: REQUEST_REF,
      in_reply_to: continueCarrierKey(operationKey),
      message_key: nativeReplyKeyOf(operationKey),
      fingerprint: FINGERPRINT,
      text: "SOURCE FIXTURE answer for original instruction",
      next_step: "SOURCE FIXTURE owner supplied next step",
      primary_ts: THREAD_TS,
      reply_committed: true,
      parent_consumed: false,
      operation_key: operationKey,
    },
  });

/** Correctly closed unknown envelope: the port retains the pointer on it. */
const closedReplyEnvelope = (): unknown =>
  resultEnvelope("reply", {
    ok: false,
    effect: "UNKNOWN",
    operation_key: null,
    data: null,
    error: { code: "effect_unknown", message: "SOURCE FIXTURE reply not available" },
  });

// ── Synthetic transport (no network, provider, auth or parent calls) ─────────

const transport: ExecutiveSessionTransport = {
  available: () => fixture.auth.status === "signed_in",
  authGeneration: () => fixture.generation,
  subscribe: (listener) => {
    transportListeners.add(listener);
    return () => {
      transportListeners.delete(listener);
    };
  },
  context: async (selection) => contextEnvelope(selection),
  send: async (args) => {
    fixture.sendCount += 1;
    bumpFixtureSnapshot();
    if (fixture.loseSend) {
      throw new Error("SOURCE FIXTURE: simulated lost SEND response");
    }
    return sendEnvelopeFor(args);
  },
  reply: async (args) => {
    fixture.replyCount += 1;
    bumpFixtureSnapshot();
    if (!fixture.issuedKeys.has(args.operation_key)) {
      return closedReplyEnvelope();
    }
    // The envelope is captured before any deferral: Release resolves the
    // exact captured envelope even if the checkboxes changed meanwhile.
    const envelope = fixture.replyAvailable
      ? exactReplyEnvelope(args.operation_key)
      : closedReplyEnvelope();
    if (fixture.delayReply) {
      return new Promise((resolve) => {
        fixture.deferred.push({ envelope, resolve });
        bumpFixtureSnapshot();
      });
    }
    return envelope;
  },
};

// ── Fixture driver controls (rendered OUTSIDE the App root) ──────────────────

const controlsPanelStyle: CSSProperties = {
  margin: "8px",
  padding: "8px 12px",
  border: "1px dashed #6b7280",
  borderRadius: "6px",
  font: "13px/1.6 ui-monospace, SFMono-Regular, Menlo, monospace",
  color: "#d1d5db",
  background: "#111827",
  maxWidth: "960px",
};
const controlsSummaryStyle: CSSProperties = {
  fontWeight: 700,
  cursor: "pointer",
};
const controlsRowStyle: CSSProperties = {
  margin: "4px 0",
  display: "flex",
  flexWrap: "wrap",
  gap: "12px",
  alignItems: "center",
};
const controlsTelemetryStyle: CSSProperties = {
  margin: "6px 0 0",
  borderTop: "1px solid #374151",
  paddingTop: "6px",
  whiteSpace: "pre-wrap",
};

function FixtureControls() {
  const snap = useSyncExternalStore(subscribeFixture, () => fixtureSnapshot);
  const keyTail = snap.canonicalKey.slice(
    "session-continue-".length,
    "session-continue-".length + 8,
  );
  return (
    <details style={controlsPanelStyle}>
      <summary style={controlsSummaryStyle}>
        SOURCE FIXTURE controls — test-only driver surface, not product UI
      </summary>
      <div style={controlsRowStyle}>
        <label>
          <input
            type="checkbox"
            checked={snap.replyAvailable}
            onChange={(event) => setReplyAvailable(event.target.checked)}
          />{" "}
          Fixture: reply available (exact bound answer)
        </label>
        <label>
          <input
            type="checkbox"
            checked={snap.delayReply}
            onChange={(event) => setDelayReply(event.target.checked)}
          />{" "}
          Fixture: delay reply (deferred until release)
        </label>
        <label>
          <input
            type="checkbox"
            checked={snap.loseSend}
            onChange={(event) => setLoseSend(event.target.checked)}
          />{" "}
          Fixture: lose SEND response
        </label>
      </div>
      <div style={controlsRowStyle}>
        <button type="button" onClick={invalidateAuthEpoch}>
          Fixture: invalidate auth epoch (public stays signed_in)
        </button>
        <button type="button" onClick={notifyPublicSignedOut}>
          Fixture: public signed_out
        </button>
      </div>
      <div style={controlsRowStyle}>
        <button type="button" onClick={() => selectFixtureMission(false)}>Fixture: select other mission</button>
        <button type="button" onClick={() => selectFixtureMission(true)}>Fixture: select original mission</button>
      </div>
      <div style={controlsRowStyle}>
        <button type="button" onClick={releaseDeferredReplies}>
          Fixture: release delayed reply
        </button>
        <button type="button" onClick={advanceCanonicalKey}>
          Fixture: advance canonical continuation key
        </button>
      </div>
      <p style={controlsTelemetryStyle}>
        {`Fixture telemetry — transport counters only, never worker or provider lifecycle:
send calls: ${snap.sendCount} | reply calls: ${snap.replyCount} | deferred replies: ${snap.deferredCount}
auth generation: ${snap.generation} | public auth: ${snap.authStatus} | canonical continuation key: …${keyTail}…`}
      </p>
    </details>
  );
}

// ── Mount ─────────────────────────────────────────────────────────────────────

function requireElement(id: string): HTMLElement {
  const el = document.getElementById(id);
  if (!el) {
    throw new Error(`SOURCE FIXTURE: missing #${id} element`);
  }
  return el;
}

/** Preserve either exact synthetic selection on reload; default absent/invalid selection to A. */
function ensureFixtureSelectionQuery(): void {
  const params = new URLSearchParams(window.location.search);
  if ((params.get("work_ref") === "WS:ALPHA" && params.get("root_job_id") === "JOB-1") ||
      (params.get("work_ref") === "WS:BETA" && params.get("root_job_id") === "JOB-2")) {
    return;
  }
  const next = new URLSearchParams({ work_ref: "WS:ALPHA", root_job_id: "JOB-1" });
  window.history.replaceState(
    null,
    "",
    `${window.location.pathname}?${next.toString()}${window.location.hash}`,
  );
}

if (!["localhost", "127.0.0.1", "[::1]"].includes(window.location.hostname)) {
  requireElement("fixture-controls").textContent = "SOURCE FIXTURE REFUSED: use a dedicated localhost origin.";
} else if (typeof indexedDB === "undefined") {
  const controls = document.getElementById("fixture-controls");
  if (controls) {
    controls.textContent =
      "SOURCE FIXTURE error: IndexedDB is unavailable; the real durable session " +
      "pending-pointer store is required for this harness.";
  }
} else {
  ensureFixtureSelectionQuery();
  // The REAL durable store: reload retention below is proven by IndexedDB,
  // not by a new persistence mechanism. Dedicated localhost test origin
  // required (production database name is fixed by the product module).
  const store = createIndexedDbSessionPendingPointerStore(indexedDB);
  const sessionHost = createOsExecutiveSessionHost(transport, store);
  mountedSessionHost = sessionHost;
  window.MastermindMissionHost = {
    sessionCommandBinding: sessionHost.binding,
    session: {
      refresh: (selection: unknown) => sessionHost.refresh(selection as MissionSelection),
      setStopCondition: (provider: () => unknown) => sessionHost.setStopCondition(provider),
    },
    auth: {
      getState: (): AuthState => ({ ...fixture.auth }),
      subscribe: (listener: (state: AuthState) => void) => {
        authListeners.add(listener);
        return () => {
          authListeners.delete(listener);
        };
      },
      signIn: async () => undefined,
      signOut: async () => { notifyPublicSignedOut(); },
    },
  };
  createRoot(requireElement("fixture-controls")).render(<FixtureControls />);
  createRoot(requireElement("root")).render(<App />);
  console.info(
    "[SOURCE FIXTURE] mounted — synthetic transport only; no authentication, " +
      "provider task, real SEND or parent consumption.",
  );
}
