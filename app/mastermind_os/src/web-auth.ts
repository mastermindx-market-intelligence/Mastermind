import {hostObservationWebMethods} from "./resources/host-observation-web";
import {freshConversationArguments,FRESH_CONVERSATION_PATHS} from "./orchestration/fresh-conversation-transport";
import { BYOK_ROLES_RESPONSE_CAP } from "./meta-ceo/byok-roles-read";
import {projectAccessPublicSelection} from "./access/project-access-host";
import {instructionPublicRequest,instructionQuery,type InstructionPauseRequest} from "./instructions/instruction-host";
import { projectAdmissionPublicRequest, projectAdmissionQuery, type ProjectAdmissionPauseRequest, type ProjectAdmissionResumeRequest } from "./admission/project-admission-host";
import { validArchiveCursor } from "./projects/archive/project-archive-continuation";
import { knowledgeReadSelection } from "./knowledge/library/knowledge-read-port";
import { validSourceOperationContextSelection } from './source-operations/context';
import {createSourceOperationTransport,SOURCE_OPERATION_CAP} from './source-operations/transport';
import { normalizeProjectAssociationSelection } from "./conversations/project-association";
import { projectHistoryArguments } from "./orchestration/project-history-arguments";
import {projectConversationArguments,PROJECT_CONVERSATION_READ_PATHS} from './conversations/project-conversation-transport';
import { validResourceCapacitySelection } from "./resources/resource-capacity-read";
import { validT3AttemptId } from "./resources/t3-attempt-fleet-contract";
import { isAutonomySelection, AUTONOMY_READ_BODY_SCHEMA } from "./supervision/autonomy-policy";
import { validJournalSelection } from "./project-journal";
import { validDirectionSelection } from "./direction/accepted-direction";
import { validProjectPlanSelection } from "./planning/project-plan";
import { guardAcceptanceRead, missionV4Selection, type MissionV4Selection, type ProductAcceptanceOwner } from "./product-acceptance/owner-observation";
import {
  RESEARCH_SCOPE,
  validateResearchResource,
  EXECUTIVE_SCOPE,
  validateExecutiveResource,
  ACQUISITION_AUDIENCE,
  ACQUISITION_SCOPE,
  CALLBACK_PATH,
  CALLBACK_URL,
  CONTENT_AUDIENCE,
  CONTENT_SCOPE,
  ISSUER,
  MAX_RESPONSE_BYTES,
  TOKEN_RESPONSE_BYTES,
  ORIGIN,
  POPUP_FEATURES,
  READ_TIMEOUT_MS,
  TOKEN_TIMEOUT_MS,
  TRANSACTION_TTL_MS,
  readWebAuthConfig,
  type WebAuthConfig,
} from "./public-config";
import { normalizeSelection, normalizeWorkspaceSelection, type MissionSelection } from "./mission";
import { normalizeResultSelection, RESULT_HTTP_BODY_BYTES } from "./result";
import { DIRECT_RESULT_BYTES, decodeDirectNativeResult, normalizeDirectSelection, parseDirectNativeJson } from "./direct-native-result";
import { validActivitySelection } from "./planning/retained-activity";
import { planningArguments, type PlanningOperation } from "./planning/project-planning-transport";
import { projectExecutionArguments, projectExecutionResult, type ProjectExecutionOperation } from "./planning/project-execution-transport";
import { attendedSelection } from "./fabric/attended-status";
import {
  normalizeExecutiveSessionSelection,
  sessionSelectionWire,
  type ExecutiveSessionTransport,
} from "./orchestration/executive-session-command-port";
import type { ProjectConversationHistoryTransport } from "./conversations/project-conversation-history-owner";
import { projectHistorySelection } from "./conversations/project-history-selection";
import type { AuthState, RawClient } from "./host";
import {
  CONTROL_ROOM_REQUEST_BYTES, CONTROL_ROOM_RESPONSE_BYTES,
  decodeControlRoomActionPayload, decodeControlRoomActionJson,
  ControlRoomActionTransportError,
  type ControlRoomOperation, type ControlRoomActionResult,
} from "./control-room-actions";
import { canNavigateForAutomaticSignIn } from "./auth-navigation-guard";
import { evidenceUrl, EVIDENCE_BODY_BYTES } from "./research/evidence-contract";
export type { AuthState } from "./host";
export interface WebPopup {
  close(): void;
  closed?: boolean;
  set location(value: string);
}
export interface WebAuthDeps {
  /** Internal host composition only. The production default is uncomposed. */
  productAcceptanceOwner?: ProductAcceptanceOwner;
  config?: Partial<WebAuthConfig>;
  crypto?: Crypto;
  fetchFn?: typeof fetch;
  openPopup?: (
    url: string,
    target: string,
    features: string,
  ) => WebPopup | null;
  /** Test-injected top-level OAuth navigation; never a caller-supplied URL. */
  navigate?: (url: string) => void;
  addEventListener?: typeof window.addEventListener;
  removeEventListener?: typeof window.removeEventListener;
  setTimeout?: typeof setTimeout;
  clearTimeout?: typeof clearTimeout;
  now?: () => number;
}
type Resource = "acquisition" | "content" | "executive" | "research";
type Token = { value: string; expires: number; executiveSend?: boolean };
const TYPE = "mastermind-auth-callback";
const opaque = (s: unknown, max = 4096): s is string =>
  typeof s === "string" &&
  s.length > 0 &&
  s.length <= max &&
  !/[\u0000-\u0020\u007f]/.test(s);
const reason = (error: unknown) =>
  error instanceof Error && /^[A-Z_]{1,80}$/.test(error.message)
    ? error.message
    : "AUTH_REQUEST_FAILED";

const REDIRECT_PENDING_KEY = "mastermind-os-auth0-redirect-pkce-v1";
const REDIRECT_ATTEMPT_KEY = "mastermind-os-auth0-redirect-attempt-v1";
const PRIOR_LOGIN_KEY = "mastermind-os-auth0-prior-login-v1:";
type RedirectGrant = { readonly code: string; readonly verifier: string };
let redirectGrant: RedirectGrant | null = null;

function redirectPending(): {
  state: string; verifier: string; clientId: string; started: number;
} | null {
  try {
    const raw = sessionStorage.getItem(REDIRECT_PENDING_KEY);
    if (!raw || raw.length > 1024) return null;
    const v: unknown = JSON.parse(raw);
    if (!v || typeof v !== "object" || Array.isArray(v)) return null;
    const p = v as Record<string, unknown>;
    if (Object.keys(p).sort().join(",") !== "clientId,started,state,verifier" ||
      !opaque(p.state, 128) || !opaque(p.verifier, 128) ||
      typeof p.clientId !== "string" || !/^[A-Za-z0-9_-]{1,128}$/.test(p.clientId) ||
      !Number.isSafeInteger(p.started) || Number(p.started) > Date.now() ||
      Date.now() - Number(p.started) > TRANSACTION_TTL_MS) return null;
    return p as {state: string; verifier: string; clientId: string; started: number};
  } catch { return null; }
}

/** The callback scrubs its URL before any handoff; code/state never reach React. */
export function handleWebAuthCallback(): boolean {
  if (window.location.pathname !== CALLBACK_PATH) return false;
  const { search, hash, origin } = window.location;
  try {
    window.history.replaceState(null, "", CALLBACK_PATH);
  } catch {
    return true;
  }
  const p = new URLSearchParams(search);
  const state = p.get("state"),
    code = p.get("code"),
    error = p.get("error");
  let failure: string | null = null;
  if (
    origin !== ORIGIN ||
    hash ||
    search.length > 8192 ||
    !opaque(state, 128) ||
    [...p.keys()].some(
      (k) =>
        !["state", "code", "error", "error_description", "iss"].includes(k) ||
        p.getAll(k).length !== 1,
    ) ||
    (p.has("iss") && p.get("iss") !== ISSUER) ||
    Boolean(code) === Boolean(error) ||
    (code !== null && !opaque(code))
  )
    failure = "CALLBACK_INVALID";
  const payload = {
    type: TYPE,
    state,
    ...(failure
      ? { failure }
      : error
        ? { failure: "AUTHORIZATION_DENIED" }
        : { code }),
  };
  // A top-level round-trip must be handled before replacing the document
  // body or forwarding to a potentially unrelated opener. React's #root
  // survives; only the private OAuth owner receives the exchanged code.
  const pending = redirectPending();
  const registeredClient = readWebAuthConfig().webClientId;
  if (origin === ORIGIN && window.parent === window && pending &&
      pending.state === state && pending.clientId === registeredClient) {
    try { sessionStorage.removeItem(REDIRECT_PENDING_KEY); } catch { /* denied */ }
    if (!failure && !error && opaque(code)) {
      redirectGrant = { code, verifier: pending.verifier };
    }
    try { window.history.replaceState(null, "", "/os/"); } catch { return true; }
    // Failed prompt=none returns to ordinary manual Sign-in, once only.
    return false;
  }
  // The popup/iframe callback is deliberately not a mounted app.
  document.title = failure || error ? "Sign-in failed" : "Completing sign-in";
  const main = document.createElement("main");
  main.setAttribute("role", "status");
  main.textContent =
    failure || error
      ? "Sign-in failed. Close this window and try again."
      : "Completing sign-in. This window will close automatically.";
  document.body.replaceChildren(main);
  const recipient = window.opener && !window.opener.closed ? window.opener :
    window.parent !== window ? window.parent : null;
  if (origin === ORIGIN && recipient) {
    try { recipient.postMessage(payload, ORIGIN); } catch { /* unavailable */ }
  }
  return true;
}

/** The existing private token owner exposes fixed reads and optional Executive commands. */
export function createWebAuth(deps: WebAuthDeps = {}): RawClient {
  const config = { ...readWebAuthConfig(), ...deps.config };
  const executiveResource = validateExecutiveResource(config.executiveResource);
  const proposedResearch = validateResearchResource(config.researchResource);
  const researchResource = proposedResearch !== executiveResource ? proposedResearch : null;
  const configured =
    typeof config.webClientId === "string" &&
    /^[A-Za-z0-9_-]{1,128}$/.test(config.webClientId) &&
    config.issuer === ISSUER &&
    config.origin === ORIGIN &&
    config.callbackUrl === CALLBACK_URL &&
    config.acquisitionAudience === ACQUISITION_AUDIENCE &&
    config.acquisitionScope === ACQUISITION_SCOPE &&
    config.contentAudience === CONTENT_AUDIENCE &&
    config.contentScope === CONTENT_SCOPE;
  const logoutKey = `mastermind-os-auth-logout-v1:${config.webClientId ?? "unconfigured"}`;
  // Storage errors must not invalidate an otherwise authorized manual login.
  const loggedOutElsewhere = () => {
    try { return localStorage.getItem(logoutKey) === "1"; }
    catch { return false; }
  };
  const cryptoApi = deps.crypto ?? crypto,
    fetchFn = deps.fetchFn ?? fetch.bind(globalThis),
    now = deps.now ?? Date.now;
  const open =
    deps.openPopup ??
    ((url, target, features) =>
      window.open(url, target, features) as unknown as WebPopup | null);
  const navigate = deps.navigate ?? ((url: string) => window.location.assign(url));
  const add = deps.addEventListener ?? window.addEventListener.bind(window),
    remove =
      deps.removeEventListener ?? window.removeEventListener.bind(window);
  const later = deps.setTimeout ?? setTimeout,
    clear = deps.clearTimeout ?? clearTimeout;
  // Same-document logout is an auth-owner fact, not conditional on whether
  // the browser can write the cross-tab storage marker.
  let explicitlySignedOut = false;
  let generation = 0,
    flow: { generation: number; popup: WebPopup; cancel: () => void } | null =
      null,
    lastError: string | null = null;
  const tokens: Record<Resource, Token | null> = {
    acquisition: null,
    content: null,
    executive: null,
    research: null,
  };
  const listeners = new Set<(s: AuthState) => void>();
  const researchListeners = new Set<() => void>();
  const researchRequests = new Set<AbortController>();
  function invalidateResearch() {
    for (const request of researchRequests) request.abort();
    for (const listener of researchListeners) {
      try { listener(); } catch { /* isolate subscribers */ }
    }
  }
  const valid = (resource: Resource) =>
    !loggedOutElsewhere() &&
    Boolean(tokens[resource] && tokens[resource]!.expires > now());
  let executiveGeneration = 0;
  const executiveListeners = new Set<() => void>();
  const executiveRequests = new Set<AbortController>();
  function advanceExecutive() {
    executiveGeneration++;
    for (const request of executiveRequests) request.abort();
    for (const listener of executiveListeners) {
      try { listener(); } catch { /* isolate subscribers */ }
    }
  }
  const resourceScope = (resource: Resource) => resource === "research" ? RESEARCH_SCOPE :
    resource === "executive" ? EXECUTIVE_SCOPE :
    resource === "acquisition" ? ACQUISITION_SCOPE : CONTENT_SCOPE;
  function getState(): AuthState {
    return {
      status: !configured
        ? "unconfigured"
        : flow
          ? "signing_in"
          : lastError
            ? "error"
            : valid("acquisition") || valid("content")
              ? "signed_in"
              : "signed_out",
      reason: !configured ? "CLIENT_NOT_REGISTERED" :
        lastError || (explicitlySignedOut ? "USER_SIGNED_OUT" : null),
      acquisition: valid("acquisition"),
      content: valid("content"),
    };
  }
  function emit() {
    for (const listener of researchListeners) {
      try { listener(); } catch { /* isolate subscribers */ }
    }
    for (const listener of listeners) {
      try {
        listener(getState());
      } catch {
        /* isolate UI */
      }
    }
  }
  function cancel() {
    generation++;
    tokens.research = null;
    invalidateResearch();
    tokens.executive = null;
    advanceExecutive();
    const old = flow;
    flow = null;
    if (old) {
      old.cancel();
      try {
        old.popup.close();
      } catch {
        /* already closed */
      }
    }
  }
  // Cross-tab sign-out revokes this token owner and all pending generation
  // work. A remote logout is never an automatic login instruction.
  const onStorage = (event: StorageEvent) => {
    if (event.key !== logoutKey || event.newValue !== "1") return;
    redirectGrant = null;
    explicitlySignedOut = true;
    cancel();
    tokens.acquisition = null;
    tokens.content = null;
    lastError = null;
    emit();
  };
  if (configured) add("storage", onStorage);
  // BroadcastChannel is a same-origin, nonpersistent logout signal. Unlike
  // localStorage events, it still delivers when quota rejects setItem.
  // Only an explicit logout is broadcast; never send a token or a draft.
  let logoutBroadcast: BroadcastChannel | null = null;
  if (configured && typeof BroadcastChannel !== "undefined") {
    try {
      logoutBroadcast = new BroadcastChannel(logoutKey);
      logoutBroadcast.onmessage = (event: MessageEvent) => {
        if (event.data !== "USER_SIGNED_OUT") return;
        redirectGrant = null;
        explicitlySignedOut = true;
        cancel();
        tokens.acquisition = null;
        tokens.content = null;
        lastError = null;
        emit();
      };
    } catch { /* storage marker remains another logout signal */ }
  }
  const check = (ticket: number) => {
    if (ticket !== generation) throw new Error("TRANSACTION_CANCELLED");
  };
  function random() {
    const b = new Uint8Array(32);
    cryptoApi.getRandomValues(b);
    return base64(b);
  }
  async function exchange(
    code: string,
    verifier: string,
    resource: Resource,
    ticket: number,
    signal: AbortSignal,
  ): Promise<Token> {
    const scope = resourceScope(resource);
    const body = new URLSearchParams({
      grant_type: "authorization_code",
      client_id: config.webClientId!,
      code,
      code_verifier: verifier,
      redirect_uri: CALLBACK_URL,
    });
    const exchangeAbort = new AbortController();
    const timer = later(() => exchangeAbort.abort(), TOKEN_TIMEOUT_MS);
    const abort = () => exchangeAbort.abort();
    signal.addEventListener("abort", abort, { once: true });
    if (signal.aborted) abort();
    try {
      const response = await fetchFn(`${ISSUER}oauth/token`, {
        method: "POST",
        redirect: "error",
        credentials: "omit",
        cache: "no-store",
        headers: {
          "Content-Type": "application/x-www-form-urlencoded",
          Accept: "application/json",
        },
        body: body.toString(),
        signal: exchangeAbort.signal,
      });
      if (!response.ok) throw new Error("TOKEN_ENDPOINT_FAILED");
      const raw = await boundedJson(response, TOKEN_RESPONSE_BYTES);
      check(ticket);
      if (exchangeAbort.signal.aborted) throw new Error("TOKEN_TIMEOUT");
      if (!raw || typeof raw !== "object" || Array.isArray(raw))
        throw new Error("TOKEN_INVALID");
      const t = raw as Record<string, unknown>;
      if (
        t.token_type !== "Bearer" ||
        !opaque(t.access_token, 16384) ||
        !Number.isSafeInteger(t.expires_in) ||
        Number(t.expires_in) < 1 ||
        Number(t.expires_in) > 604800 ||
        (resource === "research"
          ? t.scope !== RESEARCH_SCOPE
          : resource === "executive"
          ? typeof t.scope !== "string" ||
            ![EXECUTIVE_SCOPE.split(" ").sort().join(" "), "mastermind.executive.read"].includes(
              t.scope.trim().split(/\s+/).sort().join(" "),
            )
          : t.scope !== undefined && t.scope !== scope)
      )
        throw new Error("TOKEN_INVALID");
      return {
        value: t.access_token,
        expires: now() + Number(t.expires_in) * 1000,
        ...(resource === "executive" ? {
          executiveSend: typeof t.scope === "string" &&
            t.scope.trim().split(/\s+/).sort().join(" ") === EXECUTIVE_SCOPE.split(" ").sort().join(" "),
        } : {}),
      };
    } catch (e) {
      if (exchangeAbort.signal.aborted)
        throw new Error(
          signal.aborted ? "TRANSACTION_CANCELLED" : "TOKEN_TIMEOUT",
        );
      throw e;
    } finally {
      clear(timer);
      signal.removeEventListener("abort", abort);
    }
  }
  // Keep a prior interactive workspace grant usable while its replacement is
  // obtained silently. Auth0 access-token expiry is not a user logout.
  // Tokens stay private and memory-only; no bearer or refresh secret is persisted.
  function scheduleTokenLifetime(resource: Resource, token: Token, ticket: number, restored: boolean) {
    const owns = () => ticket === generation && tokens[resource] === token;
    const remaining = Math.max(0, token.expires - now());
    if (resource === "acquisition" || resource === "content") {
      // Refresh ahead of common 5-minute Auth0 lifetimes, before the signed-in
      // UI can flicker to the sign-in screen. A rejected silent attempt does
      // not invalidate a still-live token or initiate a redirect.
      const headroom = Math.min(60_000, Math.floor(remaining / 5));
      if (headroom > 0) later(() => {
        if (owns() && !flow && !explicitlySignedOut && !loggedOutElsewhere()) {
          void restore(true).catch(() => {});
        }
      }, Math.max(0, remaining - headroom));
    }
    later(() => {
      if (!owns()) return;
      tokens[resource] = null;
      if (resource === "executive") advanceExecutive();
      if (resource === "research") invalidateResearch();
      emit();
      // Browser sleep/blocked iframes may delay pre-expiry renewal. Recover
      // once again on expiry, with the existing one-attempt navigation guard.
      // Research is an explicitly user-granted scope, never auto-restored.
      if (resource === "acquisition" || resource === "content" ||
          (restored && resource === "executive")) {
        void restore(true).catch(() => {});
      }
    }, Math.max(0, token.expires - now()));
  }
  async function transaction(
    resource: Resource,
    current: NonNullable<typeof flow>,
  ) {
    const ticket = current.generation,
      verifier = random(),
      state = random();
    const challenge = base64(
      new Uint8Array(
        await cryptoApi.subtle.digest(
          "SHA-256",
          new TextEncoder().encode(verifier),
        ),
      ),
    );
    check(ticket);
    if (current.popup.closed) throw new Error("POPUP_CLOSED");
    const url = new URL(`${ISSUER}authorize`);
    const scope = resourceScope(resource);
    const audience =
      resource === "research" ? researchResource! :
      resource === "executive" ? executiveResource! :
      resource === "acquisition" ? ACQUISITION_AUDIENCE : CONTENT_AUDIENCE;
    for (const [key, value] of Object.entries({
      response_type: "code",
      client_id: config.webClientId!,
      redirect_uri: CALLBACK_URL,
      scope,
      audience,
      state,
      code_challenge: challenge,
      code_challenge_method: "S256",
    }))
      url.searchParams.set(key, value);
    let consumed = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let poll: ReturnType<typeof setTimeout> | undefined;
    const deadline = now() + TRANSACTION_TTL_MS,
      abort = new AbortController();
    let resolve!: (value: Token) => void, reject!: (error: Error) => void;
    const completion = new Promise<Token>((yes, no) => {
      resolve = yes;
      reject = no;
    });
    const fail = (code: string) => {
      if (consumed && code !== "TRANSACTION_CANCELLED") return;
      consumed = true;
      abort.abort();
      reject(new Error(code));
    };
    current.cancel = () => fail("TRANSACTION_CANCELLED");
    const listener = (event: MessageEvent) => {
      if (
        consumed ||
        event.source !== (current.popup as unknown as Window) ||
        event.origin !== ORIGIN
      )
        return;
      const data = event.data;
      if (
        !data ||
        typeof data !== "object" ||
        Array.isArray(data) ||
        data.type !== TYPE ||
        data.state !== state
      )
        return;
      if (ticket !== generation) {
        fail("TRANSACTION_CANCELLED");
        return;
      }
      if (now() >= deadline) {
        fail("TRANSACTION_EXPIRED");
        return;
      }
      if (
        Object.keys(data).some(
          (k) => !["type", "state", "code", "failure"].includes(k),
        ) ||
        Boolean(data.code) === Boolean(data.failure) ||
        (data.code !== undefined && !opaque(data.code))
      ) {
        fail("CALLBACK_INVALID");
        return;
      }
      if (data.failure) {
        fail(
          data.failure === "AUTHORIZATION_DENIED"
            ? "AUTHORIZATION_DENIED"
            : "CALLBACK_INVALID",
        );
        return;
      }
      consumed = true;
      remove("message", listener);
      clear(timer);
      clear(poll);
      void exchange(data.code, verifier, resource, ticket, abort.signal).then(
        resolve,
        (e) => reject(new Error(reason(e))),
      );
    };
    add("message", listener);
    timer = later(() => fail("TRANSACTION_EXPIRED"), TRANSACTION_TTL_MS);
    const closed = () => {
      if (!consumed) {
        if (current.popup.closed) fail("POPUP_CLOSED");
        else poll = later(closed, 250);
      }
    };
    poll = later(closed, 250);
    try {
      current.popup.location = url.toString();
      const token = await completion;
      check(ticket);
      tokens[resource] = token;
      if (resource === "executive") advanceExecutive();
      scheduleTokenLifetime(resource, token, ticket, false);
      emit();
    } finally {
      remove("message", listener);
      clear(timer);
      clear(poll);
      abort.abort();
      current.cancel = () => {};
    }
  }
  // Nonsecret explicit-logout flag prevents a reload from silently undoing sign-out.
  const priorKey = PRIOR_LOGIN_KEY + (config.webClientId ?? "unconfigured");
  function rememberSignedIn() {
    try { localStorage.setItem(priorKey, "1"); } catch { /* no persistent hint */ }
  }
  async function redirectFallback(ticket: number): Promise<void> {
    if (!configured || logoutBlocked() || valid("acquisition")) return;
    try {
      if (localStorage.getItem(priorKey) !== "1" ||
          sessionStorage.getItem(REDIRECT_ATTEMPT_KEY) ||
          !canNavigateForAutomaticSignIn()) return;
      const verifier = random(), state = random();
      const challenge = base64(new Uint8Array(await cryptoApi.subtle.digest(
        "SHA-256", new TextEncoder().encode(verifier))));
      check(ticket);
      // Drafts may change while calculating the PKCE code challenge.
      if (!canNavigateForAutomaticSignIn()) return;
      const url = new URL(`${ISSUER}authorize`);
      for (const [key, value] of Object.entries({
        response_type: "code", client_id: config.webClientId!,
        redirect_uri: CALLBACK_URL, audience: ACQUISITION_AUDIENCE,
        scope: ACQUISITION_SCOPE, state, code_challenge: challenge,
        code_challenge_method: "S256", prompt: "none", response_mode: "query",
      })) url.searchParams.set(key, value);
      sessionStorage.setItem(REDIRECT_PENDING_KEY, JSON.stringify({
        clientId: config.webClientId!, state, verifier, started: now(),
      }));
      sessionStorage.setItem(REDIRECT_ATTEMPT_KEY, "1");
      try { navigate(url.toString()); }
      catch {
        sessionStorage.removeItem(REDIRECT_PENDING_KEY);
        sessionStorage.removeItem(REDIRECT_ATTEMPT_KEY);
      }
    } catch { /* storage denied, no navigation or credential persistence */ }
  }
  const logoutBlocked = () => {
    try { return localStorage.getItem(logoutKey) === "1"; } catch { return true; }
  };
  // Restore the Auth0 SSO session with hidden-frame PKCE. No access/refresh
  // tokens are placed in localStorage, cookies, or sessionStorage.
  let restoring: Promise<AuthState> | null = null;
  async function restore(force = false): Promise<AuthState> {
    if (!configured || explicitlySignedOut || logoutBlocked() || flow ||
        (!force && valid("acquisition")) || restoring) {
      return restoring ?? Promise.resolve(getState());
    }
    const ticket = generation;
    const incoming = redirectGrant;
    redirectGrant = null;
    const installToken = (resource: "acquisition" | "content" | "executive", token: Token) => {
      check(ticket);
      tokens[resource] = token;
      if (resource === "acquisition") rememberSignedIn();
      if (resource === "executive") advanceExecutive();
      scheduleTokenLifetime(resource, token, ticket, true);
      emit();
    };
    const restoreOne = async (resource: "acquisition" | "content" | "executive") => {
      const verifier = random(), state = random();
      const challenge = base64(new Uint8Array(await cryptoApi.subtle.digest(
        "SHA-256", new TextEncoder().encode(verifier))));
      check(ticket);
      const url = new URL(`${ISSUER}authorize`);
      const audience = resource === "acquisition" ? ACQUISITION_AUDIENCE :
        resource === "content" ? CONTENT_AUDIENCE : executiveResource!;
      for (const [key, value] of Object.entries({
        response_type: "code", client_id: config.webClientId!,
        redirect_uri: CALLBACK_URL, scope: resourceScope(resource), audience,
        state, code_challenge: challenge, code_challenge_method: "S256",
        prompt: "none", response_mode: "query",
      })) url.searchParams.set(key, value);
      const frame = document.createElement("iframe");
      frame.hidden = true;
      frame.setAttribute("aria-hidden", "true");
      frame.title = "Session restoration";
      const abort = new AbortController();
      let timer: ReturnType<typeof setTimeout> | undefined;
      try {
        const code = await new Promise<string>((resolve, reject) => {
          let settled = false;
          const csp = (event: SecurityPolicyViolationEvent) => {
            if ((event.effectiveDirective === "frame-src" ||
                 event.effectiveDirective === "default-src") &&
                (event.blockedURI === new URL(ISSUER).origin ||
                 event.blockedURI.startsWith(ISSUER)))
              finish("SILENT_AUTH_UNAVAILABLE");
          };
          const listener = (event: MessageEvent) => {
            if (event.origin !== ORIGIN || event.source !== frame.contentWindow) return;
            const data = event.data;
            if (!data || typeof data !== "object" || data.type !== TYPE ||
                data.state !== state) return;
            if (ticket !== generation) return finish("TRANSACTION_CANCELLED");
            if (Object.keys(data).some(k => !["type","state","code","failure"].includes(k)) ||
                Boolean(data.code) === Boolean(data.failure) ||
                (data.code !== undefined && !opaque(data.code))) return finish("CALLBACK_INVALID");
            if (data.failure) return finish("SILENT_AUTH_UNAVAILABLE");
            finish(undefined, data.code);
          };
          const finish = (error?: string, value?: string) => {
            if (settled) return;
            settled = true;
            remove("message", listener);
            remove("securitypolicyviolation", csp);
            clear(timer);
            error ? reject(new Error(error)) : resolve(value!);
          };
          add("message", listener);
          add("securitypolicyviolation", csp);
          timer = later(() => finish("SILENT_AUTH_UNAVAILABLE"), 10000);
          frame.src = url.toString();
          document.body.appendChild(frame);
        });
        check(ticket);
        const token = await exchange(code, verifier, resource, ticket, abort.signal);
        installToken(resource, token);
      } finally {
        abort.abort();
        clear(timer);
        frame.remove();
      }
    };
    const running = (async () => {
      try {
        if (incoming) {
          const token = await exchange(incoming.code, incoming.verifier,
            "acquisition", ticket, new AbortController().signal);
          installToken("acquisition", token);
          try { sessionStorage.removeItem(REDIRECT_ATTEMPT_KEY); } catch { /* denied */ }
        } else {
          await restoreOne("acquisition");
        }
        if (ticket !== generation) return getState();
        try { await restoreOne("content"); } catch { /* workspace remains usable */ }
        if (executiveResource && ticket === generation) {
          try { await restoreOne("executive"); } catch { /* optional privilege */ }
        }
      } catch {
        if (!incoming && ticket === generation) await redirectFallback(ticket);
        // The one-attempt guard also protects unattended post-expiry recovery.
      }
      return getState();
    })();
    restoring = running;
    try { return await running; }
    finally { if (restoring === running) restoring = null; }
  }

  async function signIn() {
    if (!configured) return getState();
    // A failed popup must not undo the user's explicit persistent logout.
    try {
      sessionStorage.removeItem(REDIRECT_ATTEMPT_KEY);
      sessionStorage.removeItem(REDIRECT_PENDING_KEY);
    } catch { /* policy restricted */ }
    cancel();
    tokens.acquisition = null;
    tokens.content = null;
    lastError = null;
    // Must happen in the click call stack, before crypto or any other await.
    let popup: WebPopup | null = null;
    try {
      popup = open("about:blank", "_blank", POPUP_FEATURES);
    } catch {
      /* blocked */
    }
    if (!popup) {
      lastError = "POPUP_BLOCKED";
      emit();
      return getState();
    }
    const current = { generation, popup, cancel: () => {} };
    flow = current;
    emit();
    try {
      await transaction("acquisition", current);
      check(current.generation);
      const acquired = ((): Token | null => tokens.acquisition)();
      if (acquired && acquired.expires > now()) {
        // Only a new interactive grant can clear an explicit same-tab logout.
        explicitlySignedOut = false;
        try { localStorage.removeItem(logoutKey); } catch { /* denied */ }
        rememberSignedIn();
      }
      await transaction("content", current);
      check(current.generation);
      if (executiveResource) {
        try { await transaction("executive", current); check(current.generation); }
        catch {
          if (current.generation === generation) {
            tokens.executive = null;
            advanceExecutive();
          }
          // Optional Executive authorization cannot erase valid workspace access.
        }
      }
    } catch (error) {
      if (current.generation === generation) lastError = reason(error);
    } finally {
      if (flow === current) {
        flow = null;
        try {
          popup.close();
        } catch {
          /* closed */
        }
        emit();
      }
    }
    return getState();
  }
  async function signInResearch() {
    if (!configured || !researchResource) throw new Error("RESEARCH_UNAVAILABLE");
    cancel();
    tokens.acquisition = null;
    tokens.content = null;
    lastError = null;
    let popup: WebPopup | null = null;
    try { popup = open("about:blank", "_blank", POPUP_FEATURES); } catch { /* blocked */ }
    if (!popup) throw new Error("POPUP_BLOCKED");
    const current = { generation, popup, cancel: () => {} };
    flow = current; emit();
    try {
      await transaction("research", current);
      check(current.generation);
      const acquiredResearch = ((): Token | null => tokens.research)();
      if (acquiredResearch && acquiredResearch.expires > now()) {
        // Research is a user-initiated separate grant, not automatic SSO.
        explicitlySignedOut = false;
        try { localStorage.removeItem(logoutKey); } catch { /* denied */ }
      }
    } catch (error) {
      throw new Error(reason(error));
    } finally {
      if (flow === current) {
        flow = null;
        try { popup.close(); } catch { /* closed */ }
        emit();
      }
    }
  }
  async function signOut() {
    // Apply the local privacy boundary before any storage operations. A quota
    // refusal may reject setItem while read operations still succeed.
    explicitlySignedOut = true;
    try { logoutBroadcast?.postMessage("USER_SIGNED_OUT"); } catch { /* unavailable */ }
    try { localStorage.setItem(logoutKey, "1"); } catch { /* unavailable */ }
    try { localStorage.removeItem(priorKey); } catch { /* unavailable */ }
    try { sessionStorage.removeItem(REDIRECT_PENDING_KEY); } catch { /* unavailable */ }
    try { sessionStorage.removeItem(REDIRECT_ATTEMPT_KEY); } catch { /* unavailable */ }
    redirectGrant = null;
    cancel();
    tokens.acquisition = null;
    tokens.content = null;
    lastError = null;
    emit();
    return getState();
  }
  /**
   * Fixed-route read. The default policy keeps the established behavior:
   * any non-OK status (including 401/403 auth refusal and 503) fails closed
   * with READ_FAILED before a body is read. Work and Result opt into
   * schema-specific typed 503 bodies only on their fixed routes: Work uses
   * the full public cap and the closed Work queue schema; Result uses the
   * exact 16KiB result cap and the closed result envelope schema. Nothing
   * else may surface error JSON, and full closed-body validation stays in
   * the host decoder.
   */
  async function read(
    resource: Resource,
    url: string,
    signal: AbortSignal,
    policy: { cap: number; typedUnavailableSchema: string | null } = {
      cap: MAX_RESPONSE_BYTES,
      typedUnavailableSchema: null,
    },
  ) {
    const ticket = generation,
      token = tokens[resource];
    if (!token || !valid(resource)) {
      emit();
      throw new Error("TOKEN_REQUIRED");
    }
    const controller = new AbortController(),
      onAbort = () => controller.abort();
    signal.addEventListener("abort", onAbort, { once: true });
    if (signal.aborted) onAbort();
    const timer = later(() => controller.abort(), READ_TIMEOUT_MS);
    if (resource === "research") researchRequests.add(controller);
    try {
      const response = await fetchFn(url, {
        method: "GET",
        redirect: "error",
        credentials: "omit",
        cache: "no-store",
        headers: {
          Accept: "application/json",
          Authorization: `Bearer ${token.value}`,
        },
        signal: controller.signal,
      });
      if (response.status === 503 && policy.typedUnavailableSchema) {
        const body = await boundedJson(response, policy.cap);
        if (
          body === null ||
          typeof body !== "object" ||
          Array.isArray(body) ||
          (body as Record<string, unknown>).schema !==
            policy.typedUnavailableSchema ||
          (body as Record<string, unknown>).availability !== "UNAVAILABLE"
        )
          throw new Error("RESPONSE_INVALID");
        if (
          signal.aborted ||
          controller.signal.aborted ||
          ticket !== generation ||
          !valid(resource)
        )
          throw new Error("READ_CANCELLED");
        return body;
      }
      if (!response.ok) throw new Error("READ_FAILED");
      const result = await boundedJson(response, policy.cap);
      if (
        signal.aborted ||
        controller.signal.aborted ||
        ticket !== generation ||
        !valid(resource)
      )
        throw new Error("READ_CANCELLED");
      return result;
    } finally {
      clear(timer);
      signal.removeEventListener("abort", onAbort);
      researchRequests.delete(controller);
    }
  }
  /** One fixed mutation on the original command; failures never trigger retry. */
  async function projectAdmissionAction(mode:"pause"|"resume",request:ProjectAdmissionPauseRequest|ProjectAdmissionResumeRequest):Promise<unknown>{
    const payload=projectAdmissionPublicRequest(mode,request),ticket=generation,token=tokens.acquisition;
    if(!payload || !token || !valid("acquisition"))throw new Error("PROJECT_ADMISSION_UNAUTHORIZED");
    const signal=request.signal,controller=new AbortController();let timeout:ReturnType<typeof setTimeout>|undefined;
    let fail!:(reason:Error)=>void;
    const interrupted=new Promise<never>((_,reject)=>{fail=reject;});
    void interrupted.catch(()=>{});
    const cancel=()=>{controller.abort();fail(new Error("PROJECT_ADMISSION_OUTCOME_UNCONFIRMED"));};
    try {
      signal.addEventListener("abort",cancel,{once:true});
      timeout=later(cancel,60_000);if(signal.aborted)cancel();
      const body=JSON.stringify(payload);if(new TextEncoder().encode(body).length>16_384)throw new Error("PROJECT_ADMISSION_REQUEST_INVALID");
      const exchange=async()=>{
        if(signal.aborted || controller.signal.aborted || ticket!==generation || !valid("acquisition"))throw new Error("PROJECT_ADMISSION_UNAUTHORIZED");
        const response=await fetchFn(`${ORIGIN}/workspace/project-admission/${mode}`,{method:"POST",redirect:"error",credentials:"omit",cache:"no-store",
          headers:{Accept:"application/json","Content-Type":"application/json",Authorization:`Bearer ${token.value}`},body,signal:controller.signal});
        if(!response.ok)throw new Error("PROJECT_ADMISSION_REQUEST_FAILED");
        const result=await boundedJson(response,32_768);
        if(signal.aborted || controller.signal.aborted || ticket!==generation || tokens.acquisition!==token || !valid("acquisition"))throw new Error("PROJECT_ADMISSION_OUTCOME_UNCONFIRMED");
        return result;
      };
      return await Promise.race([exchange(),interrupted]);
    } finally {if(timeout!==undefined)clear(timeout);signal.removeEventListener("abort",cancel);controller.abort();}
  }

  async function sourcePost(
    path: string,
    body: Record<string, unknown>,
    signal: AbortSignal,
  ) {
    const ticket = generation,
      token = tokens.acquisition;
    if (!token || !valid("acquisition")) throw new Error("TOKEN_REQUIRED");
    const controller = new AbortController(),
      onAbort = () => controller.abort();
    signal.addEventListener("abort", onAbort, { once: true });
    if (signal.aborted) onAbort();
    const timer = later(() => controller.abort(), READ_TIMEOUT_MS);
    try {
      if (controller.signal.aborted) throw new Error("READ_CANCELLED");
      const response = await fetchFn(ORIGIN + path, {
        method: "POST",
        redirect: "error",
        credentials: "omit",
        cache: "no-store",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
          Authorization: `Bearer ${token.value}`,
        },
        body: JSON.stringify(body),
        signal: controller.signal,
      });
      if (!response.ok) throw new Error("SOURCE_OPERATION_FAILED");
      const result = await boundedJson(response, SOURCE_OPERATION_CAP);
      if (
        signal.aborted ||
        controller.signal.aborted ||
        ticket !== generation ||
        !valid("acquisition")
      )
        throw new Error("READ_CANCELLED");
      return result;
    } finally {
      clear(timer);
      signal.removeEventListener("abort", onAbort);
    }
  }
  /** One explicit original instruction pause; no replay or alternate destination. */
  async function instructionAdmissionAction(request:InstructionPauseRequest):Promise<unknown>{
    const payload=instructionPublicRequest("pause",request),ticket=generation,token=tokens.acquisition;
    if(!payload || !token || !valid("acquisition"))throw new Error("INSTRUCTION_UNAUTHORIZED");
    const signal=request.signal,controller=new AbortController();let timeout:ReturnType<typeof setTimeout>|undefined;
    let fail!:(reason:Error)=>void;
    const interrupted=new Promise<never>((_,reject)=>{fail=reject;});
    void interrupted.catch(()=>{});
    const cancel=()=>{controller.abort();fail(new Error("INSTRUCTION_OUTCOME_UNCONFIRMED"));};
    try {
      signal.addEventListener("abort",cancel,{once:true});
      timeout=later(cancel,60_000);if(signal.aborted)cancel();
      const body=JSON.stringify(payload);if(new TextEncoder().encode(body).length>16_384)throw new Error("INSTRUCTION_REQUEST_INVALID");
      const exchange=async()=>{
        if(signal.aborted || controller.signal.aborted || ticket!==generation || !valid("acquisition"))throw new Error("INSTRUCTION_UNAUTHORIZED");
        const response=await fetchFn(`${ORIGIN}/workspace/instruction-admission/pause`,{method:"POST",redirect:"error",credentials:"omit",cache:"no-store",
          headers:{Accept:"application/json","Content-Type":"application/json",Authorization:`Bearer ${token.value}`},body,signal:controller.signal});
        if(!response.ok)throw new Error("INSTRUCTION_REQUEST_FAILED");
        const result=await boundedJson(response,32_768);
        if(signal.aborted || controller.signal.aborted || ticket!==generation || tokens.acquisition!==token || !valid("acquisition"))throw new Error("INSTRUCTION_OUTCOME_UNCONFIRMED");
        return result;
      };
      return await Promise.race([exchange(),interrupted]);
    } finally {if(timeout!==undefined)clear(timeout);signal.removeEventListener("abort",cancel);controller.abort();}
  }

  /**
   * One acquisition-authenticated attempt at a fixed Control Room route.
   * The server owns each action grant. A post-dispatch auth change cannot
   * turn an original result into a claim that the request was never sent.
   */
  function controlRoomAction(
    operation: ControlRoomOperation,
    input: unknown,
    signal: AbortSignal,
  ): Promise<ControlRoomActionResult> {
    const ticket = generation, token = tokens.acquisition;
    const controller = new AbortController();
    const byteBrand = Object.getOwnPropertyDescriptor(
      Object.getPrototypeOf(Uint8Array.prototype), Symbol.toStringTag,
    )?.get;
    let dispatched = false, settled = false;
    let response: Response | null = null;
    let reader: ReadableStreamDefaultReader<Uint8Array> | null = null;
    let readerReleased = false, bodyReleased = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    return new Promise((resolve, reject) => {
      const releaseBody = () => {
        if (reader && !readerReleased) {
          readerReleased = true;
          try { void Promise.resolve(reader.cancel()).catch(() => {}); } catch { /* lost cleanup */ }
          try { reader.releaseLock(); } catch { /* a pending read may retain the lock */ }
        } else if (!reader && response && !bodyReleased) {
          bodyReleased = true;
          try { void Promise.resolve(response.body?.cancel()).catch(() => {}); } catch { /* lost cleanup */ }
        }
      };
      const finish = (result?: ControlRoomActionResult) => {
        if (settled) return;
        settled = true;
        // Settle before any cleanup callback can move auth or abort again.
        if (result) resolve(result);
        else reject(new ControlRoomActionTransportError(
          operation, dispatched ? "EFFECT_UNKNOWN" : "NOT_DISPATCHED",
        ));
        try { if (timer !== undefined) clear(timer); } catch { /* cleanup only */ }
        try { signal.removeEventListener("abort", onAbort); } catch { /* invalid signal */ }
        try { controller.abort(); } catch { /* cleanup only */ }
        releaseBody();
      };
      const onAbort = () => finish();
      void (async () => {
        try {
          const started = now();
          if (!Number.isFinite(started)) throw new Error("ACTION_CLOCK_INVALID");
          const deadline = started + 490_000;
          // One total deadline, installed before payload preflight; never reset
          // at response headers or while consuming the body.
          timer = later(onAbort, 490_000);
          signal.addEventListener("abort", onAbort, { once: true });
          if (signal.aborted) { finish(); return; }
          const payload = decodeControlRoomActionPayload(input, operation);
          const body = JSON.stringify(payload) + "\n";
          if (new TextEncoder().encode(body).length > CONTROL_ROOM_REQUEST_BYTES)
            throw new Error("ACTION_INPUT_TOO_LARGE");
          const options: RequestInit = {
            method: "POST", redirect: "error", credentials: "omit", cache: "no-store",
            headers: {
              Accept: "application/json", "Content-Type": "application/json",
              Authorization: "Bearer " + (token?.value ?? ""),
            },
            body, signal: controller.signal,
          };
          const aborted = signal.aborted || controller.signal.aborted;
          const current = now();
          if (!configured || !token || aborted || settled
              || !Number.isFinite(current) || current >= deadline || token.expires <= current
              || ticket !== generation || tokens.acquisition !== token)
            throw new Error("ACTION_NOT_ADMITTED");
          dispatched = true;
          response = await fetchFn(ORIGIN + "/workspace/control-room/" + operation, options);
          if (settled) { releaseBody(); return; }
          const withinDeadline = () => {
            const observed = now();
            return Number.isFinite(observed) && observed < deadline;
          };
          if (!withinDeadline()) { finish(); return; }
          const contentType = response.headers.get("content-type")?.split(";")[0]?.trim().toLowerCase();
          const declared = response.headers.get("content-length");
          if (contentType !== "application/json"
              || (declared !== null && (!/^[0-9]+$/.test(declared)
                || Number(declared) > CONTROL_ROOM_RESPONSE_BYTES))
              || !response.body)
            throw new Error("ACTION_RESPONSE_INVALID");
          if (settled) { releaseBody(); return; }
          reader = response.body.getReader();
          const chunks: Uint8Array[] = [];
          let size = 0;
          while (true) {
            const part = await reader.read();
            if (settled) return;
            if (!withinDeadline()) { finish(); return; }
            if (part.done) break;
            if (!ArrayBuffer.isView(part.value) || byteBrand?.call(part.value) !== "Uint8Array"
                || part.value.byteLength > CONTROL_ROOM_RESPONSE_BYTES - size)
              throw new Error("ACTION_RESPONSE_TOO_LARGE");
            // The source reader may reuse its buffer on the following read.
            const owned = new Uint8Array(part.value);
            size += owned.byteLength;
            chunks.push(owned);
          }
          const bytes = new Uint8Array(size);
          let offset = 0;
          for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength; }
          if (settled) return;
          if (!withinDeadline()) { finish(); return; }
          const result = decodeControlRoomActionJson(bytes, operation, response.status);
          // A qualified result is settled immediately, before any clock or cleanup
          // callback can overwrite it. No post-dispatch READ/auth rewrite.
          finish(result);
        } catch {
          // Never trust a dependency's claimed operation or NOT_DISPATCHED error.
          // Only a decoded original-owner envelope can supply that proof here.
          finish();
        }
      })();
    });
  }
  async function executivePost(
    route: "company-priorities" | "context" | "submit" | "status" | "session/context" | "session/history-context" | "session/send" | "session/reply" | "session/references" | "direct-native/result" | "direct-native/consume" | "direct-native/correction" | `project-planning/${PlanningOperation}` | `project-execution/${ProjectExecutionOperation}` | typeof FRESH_CONVERSATION_PATHS[keyof typeof FRESH_CONVERSATION_PATHS] | typeof PROJECT_CONVERSATION_READ_PATHS[keyof typeof PROJECT_CONVERSATION_READ_PATHS],
    arguments_: unknown,
    signal: AbortSignal,
  ) {
    const token = tokens.executive, ticket = executiveGeneration;
    const planning=route.startsWith("project-planning/"), execution=route.startsWith("project-execution/"), fresh=route.startsWith("conversation/");
    const dual=planning || execution || route==="conversation/preview" || route==="conversation/create" || route==='conversation/consume' || route==='conversation/turn' || route==='conversation/turn/preview';
    const workspace=dual ? tokens.acquisition : null, workspaceGeneration=generation;
    if (!configured || !executiveResource || !token || !valid("executive"))
      throw new Error("EXECUTIVE_AUTH_REQUIRED");
    if (dual && (!workspace || !valid("acquisition"))) throw new Error("WORKSPACE_AUTH_REQUIRED");
    // READ-only may observe but must never originate a SEND or Event ACK effect.
    if ((planning || execution || fresh || route === "submit" || route === "session/send" || route === "direct-native/consume" || (route === "direct-native/correction" && (arguments_ as Record<string,unknown>)?.operation === "request")) &&
      token.executiveSend !== true)
      throw new Error("EXECUTIVE_SEND_SCOPE_REQUIRED");
    const direct = route.startsWith("direct-native/");
    const body = JSON.stringify((route === "context" || route === "company-priorities") ? {} : (route === "session/context" || route === "session/history-context" || direct) ? arguments_ : { arguments: arguments_ });
    if (new TextEncoder().encode(body).length > (direct ? 4096 : 65_536)) throw new Error("EXECUTIVE_INPUT_TOO_LARGE");
    const controller = new AbortController();
    const abort = () => controller.abort();
    signal.addEventListener("abort", abort, { once: true });
    if (signal.aborted) abort();
    // This one effect may first prepare its source (at most 120s), then owns
    // the existing finite 300s foreground call. Reads and direct-native H2
    // keep their incumbent deadline. No timeout can authorize a retry.
    const foregroundResearch = route === "submit" && arguments_ !== null &&
      typeof arguments_ === "object" && !Array.isArray(arguments_) &&
      Reflect.get(arguments_, "execution_profile") === "research_only";
    const timer = later(abort, (planning || execution || fresh) ? Math.max(0,Math.min(300_000,token.expires-now(),dual ? workspace!.expires-now() : Infinity)) : foregroundResearch ? 430_000 : READ_TIMEOUT_MS);
    executiveRequests.add(controller);
    const current = () => !controller.signal.aborted && ticket === executiveGeneration &&
      tokens.executive === token && valid("executive") && (!dual ||
        (generation===workspaceGeneration && tokens.acquisition===workspace && valid("acquisition")));
    let rejectAbort!: (error: Error) => void;
    const cancelled = new Promise<never>((_resolve, reject) => { rejectAbort = reject; });
    const rejectCancelled = () => rejectAbort(new Error("EXECUTIVE_REQUEST_CANCELLED"));
    controller.signal.addEventListener("abort", rejectCancelled, { once: true });
    try {
      if (!current()) throw new Error("EXECUTIVE_REQUEST_CANCELLED");
      const result = (async () => {
        const response = await fetchFn(`${ORIGIN}/os/executive/${route}`, {
          method: "POST", redirect: "error", credentials: "omit", cache: "no-store",
          headers: { Accept: "application/json", "Content-Type": "application/json",
            Authorization: `Bearer ${token.value}`, ...(dual ? {"X-Mastermind-Workspace-Authorization":`Bearer ${workspace!.value}`} : {}) },
          body, signal: controller.signal,
        });
        if (!current()) throw new Error("EXECUTIVE_REQUEST_CANCELLED");
        if (!response.ok && !direct && !execution) throw new Error("EXECUTIVE_REQUEST_FAILED");
        const decoded = await boundedJson(response, direct ? DIRECT_RESULT_BYTES : 262_144, direct ? parseDirectNativeJson : JSON.parse);
        if (!response.ok) {
          const errorStatuses = execution ? [400, 401, 403, 409, 503] : [401, 403, 409, 503];
          if (!errorStatuses.includes(response.status)) throw new Error("EXECUTIVE_REQUEST_FAILED");
          if (execution) {
            if (projectExecutionResult(decoded, route.slice("project-execution/".length) as ProjectExecutionOperation).ok !== false)
              throw new Error("EXECUTIVE_REQUEST_FAILED");
          } else if (decodeDirectNativeResult(decoded)?.availability !== "UNAVAILABLE") throw new Error("EXECUTIVE_REQUEST_FAILED");
        }
        if (!current()) throw new Error("EXECUTIVE_REQUEST_CANCELLED");
        return decoded;
      })();
      return await Promise.race([result, cancelled]);
    } finally {
      clear(timer);
      signal.removeEventListener("abort", abort);
      controller.signal.removeEventListener("abort", rejectCancelled);
      executiveRequests.delete(controller);
      controller.abort();
    }
  }
  return {
    ...hostObservationWebMethods(read),
    research: {
      authGeneration: () => generation,
      available: () => configured && researchResource !== null && valid("research"),
      subscribe(listener) { researchListeners.add(listener); return () => { researchListeners.delete(listener); }; },
      signIn: signInResearch,
      readEvidenceItem: (itemId, signal) => {
        if (!configured || !researchResource) return Promise.reject(new Error("RESEARCH_UNAVAILABLE"));
        const url = evidenceUrl(itemId); // validates before any fetch
        return read("research", url, signal, { cap: EVIDENCE_BODY_BYTES, typedUnavailableSchema: null });
      },
    },
    executive: {
      authGeneration: () => executiveGeneration,
      available: () => configured && executiveResource !== null && valid("executive"),
      subscribe(listener) { executiveListeners.add(listener); return () => { executiveListeners.delete(listener); }; },
      context: (signal) => executivePost("context", null, signal),
      companyPriorities: (signal) => executivePost("company-priorities", null, signal),
      submit: (arguments_, signal) => executivePost("submit", arguments_, signal),
      status: (arguments_, signal) => executivePost("status", { intent_id: arguments_.intent_id }, signal),
      projectPlanning: { request: (operation,arguments_,signal) =>
        executivePost(`project-planning/${operation}`,planningArguments(operation,arguments_),signal) },
      projectExecution: { request: (operation,arguments_,signal) =>
        executivePost(`project-execution/${operation}`,projectExecutionArguments(operation,arguments_),signal) },
      freshConversation: {request:(operation,arguments_,signal)=>
        executivePost(FRESH_CONVERSATION_PATHS[operation],freshConversationArguments(operation,arguments_),signal)},
      directNative: {
        correction: (request,signal)=>executivePost('direct-native/correction',request,signal),
        read: (selection, signal) => {
          const normalized=normalizeDirectSelection(selection);
          if(!normalized)return Promise.reject(new Error("DIRECT_SELECTION_INVALID"));
          return executivePost("direct-native/result",normalized,signal);
        },
        consume: (request, signal) => {
          const {result_digest,operation_key,...selected}=request;
          const normalized=normalizeDirectSelection(selected);
          if(!normalized||normalized.attempt_id===null||typeof result_digest!=="string"||!/^[a-f0-9]{64}$/.test(result_digest)||
            typeof operation_key!=="string"||!/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(operation_key))return Promise.reject(new Error("DIRECT_SELECTION_INVALID"));
          return executivePost("direct-native/consume",{...normalized,result_digest,operation_key},signal);
        },
      },
    },
    /**
     * Fixed selected-session continuation transport over the same private
     * Executive bearer. Three fixed POST routes only; the selection is
     * normalized before any call and the exact argument shapes are passed
     * through verbatim. Without Executive configuration or a valid Executive
     * token this reports unavailable and executivePost sends no request.
     */
    executiveSession: {
      projectConversations: {request: (operation,arguments_,signal) => {
        const closed=projectConversationArguments(operation,arguments_);
        return closed ? executivePost(PROJECT_CONVERSATION_READ_PATHS[operation],closed,signal)
          : Promise.reject(new Error('PROJECT_CONVERSATION_SELECTION_INVALID'));
      }},
      authGeneration: () => executiveGeneration,
      available: () => configured && executiveResource !== null && valid("executive"),
      subscribe(listener) { executiveListeners.add(listener); return () => { executiveListeners.delete(listener); }; },
      historyContext: (selection, signal) => {
        const closed = projectHistorySelection(selection);
        return closed ? executivePost("session/history-context", {selection: {work_ref: closed.workRef}}, signal)
          : Promise.reject(new Error("SESSION_HISTORY_SELECTION_INVALID"));
      },
      context: (selection, signal) => {
        const normalized = normalizeExecutiveSessionSelection(selection);
        if (!normalized) return Promise.reject(new Error("SELECTION_INVALID"));
        return executivePost(
          "session/context",
          { selection: sessionSelectionWire(normalized) },
          signal,
        );
      },
      send: (arguments_, signal) => executivePost("session/send", arguments_, signal),
      reply: (arguments_, signal) => executivePost("session/reply", arguments_, signal),
      references: (arguments_, signal) => executivePost("session/references", arguments_, signal),
      projectReferences: (arguments_, signal) => {
        const closed = projectHistoryArguments(arguments_);
        return closed ? executivePost("session/references", closed, signal)
          : Promise.reject(new Error("SESSION_REFERENCES_INVALID"));
      },
    } satisfies ProjectConversationHistoryTransport,
    // Same existing OAuth generation used by every bounded acquisition read.
    // The MissionHost requires this proof before it mounts the plan port.
    invalidationGeneration: () => generation,
    getState,
    subscribe(listener) {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    signIn,
    signOut,
    restore,
    readPrograms: ({ signal }) =>
      read("acquisition", `${ORIGIN}/workspace/programs/current`, signal),
    readByokRoles: ({ signal }) =>
      read("acquisition", `${ORIGIN}/workspace/byok/roles/current`, signal, { cap: BYOK_ROLES_RESPONSE_CAP, typedUnavailableSchema: null }),
    readControlRoomState: ({ signal }) =>
      read("acquisition", `${ORIGIN}/workspace/control-room/state/current`, signal),
    readControlRoomDiscovery: ({ signal }) =>
      read("acquisition", `${ORIGIN}/workspace/control-room/discover/current`, signal),
    openControlRoomSurface: ({ payload, signal }) => controlRoomAction("open", payload, signal),
    bindControlRoomSurface: ({ payload, signal }) => controlRoomAction("bind", payload, signal),
    unbindControlRoomSurface: ({ payload, signal }) => controlRoomAction("unbind", payload, signal),
    refreshControlRoomBuilds: ({ signal }) => controlRoomAction("refresh-builds", {}, signal),
    readWork: ({ signal }) =>
      read(
        "acquisition",
        `${ORIGIN}/workspace/work/current`,
        signal,
        {
          cap: MAX_RESPONSE_BYTES,
          typedUnavailableSchema: "mastermind.workspace_work_queue.v1",
        },
      ),
    readAttendedFabricCatalog: ({ signal }) =>
      read("acquisition", `${ORIGIN}/workspace/fabric/catalog/current`, signal,
        { cap: 65_536, typedUnavailableSchema: null }),
    readAttendedFabric: ({ rootId, runId, signal }) => {
      const selected = attendedSelection({ rootId, runId });
      if (!selected) return Promise.reject(new Error("FABRIC_SELECTION_INVALID"));
      return read("acquisition", `${ORIGIN}/workspace/fabric/status/current?${new URLSearchParams({
        root_id: selected.rootId, run_id: selected.runId,
      })}`, signal, { cap: 16_384, typedUnavailableSchema: null });
    },
    readProjectAccess: request => {
      const selection=projectAccessPublicSelection(request);
      if(!selection)return Promise.reject(Error("PROJECT_ACCESS_REQUEST_INVALID"));
      return read("acquisition",`${ORIGIN}/workspace/project-access/current?${new URLSearchParams({work_ref:selection.work_ref})}`,request.signal,
        {cap:16_384,typedUnavailableSchema:"mastermind.workspace_project_access.v1"});
    },
    readProjectInstructions: request => {
      const payload=instructionPublicRequest("content",request);
      if(!payload)return Promise.reject(Error("INSTRUCTION_REQUEST_INVALID"));
      return read("acquisition",`${ORIGIN}/workspace/project-instructions/current?${instructionQuery(payload)}`,request.signal,
        {cap:32_768,typedUnavailableSchema:"mastermind.workspace_project_instructions.v2"});
    },
    readInstructionAdmissionControl: request => {
      const payload=instructionPublicRequest("current",request);
      if(!payload)return Promise.reject(Error("INSTRUCTION_REQUEST_INVALID"));
      return read("acquisition",`${ORIGIN}/workspace/instruction-admission/current?${instructionQuery(payload)}`,request.signal,
        {cap:32_768,typedUnavailableSchema:"mastermind.workspace_instruction_admission_control.v1"});
    },
    pauseInstructionAdmission: request => instructionAdmissionAction(request),
    readInstructionAdmissionOperation: request => {
      const payload=instructionPublicRequest("status",request);
      if(!payload)return Promise.reject(Error("INSTRUCTION_REQUEST_INVALID"));
      return read("acquisition",`${ORIGIN}/workspace/instruction-admission/operation?${instructionQuery(payload)}`,request.signal,
        {cap:32_768,typedUnavailableSchema:null});
    },
    readProjectAdmissionControl: request => {
      const payload=projectAdmissionPublicRequest("current",request);
      if(!payload)return Promise.reject(new Error("PROJECT_ADMISSION_REQUEST_INVALID"));
      return read("acquisition",`${ORIGIN}/workspace/project-admission/current?${projectAdmissionQuery(payload)}`,request.signal,
        {cap:32_768,typedUnavailableSchema:"mastermind.workspace_project_admission_control.v1"});
    },
    pauseProjectAdmission: request => projectAdmissionAction("pause",request),
    resumeProjectAdmission: request => projectAdmissionAction("resume",request),
    readProjectAdmissionOperation: request => {
      const payload=projectAdmissionPublicRequest("status",request);
      if(!payload)return Promise.reject(new Error("PROJECT_ADMISSION_REQUEST_INVALID"));
      return read("acquisition",`${ORIGIN}/workspace/project-admission/operation?${projectAdmissionQuery(payload)}`,request.signal,
        {cap:32_768,typedUnavailableSchema:null});
    },
    readAutonomyPolicy: (request) => {
      const { signal, ...selected } = request;
      if (!isAutonomySelection(selected))
        return Promise.reject(new Error("AUTONOMY_SELECTION_INVALID"));
      return read("acquisition", `${ORIGIN}/workspace/autonomy/current?${new URLSearchParams({
        work_ref: selected.work_ref, root_job_id: selected.root_job_id,
      })}`, signal, { cap: 32_768, typedUnavailableSchema: AUTONOMY_READ_BODY_SCHEMA });
    },
    sourceOperations:createSourceOperationTransport((method,path,body,signal)=>(method==='read'||method==='options')
      ?read('acquisition',ORIGIN+path,signal,{cap:SOURCE_OPERATION_CAP,typedUnavailableSchema:null})
      :sourcePost(path,body,signal)),
    readSourceOperationContext: (request) => {
      const { signal, ...selected } = request;
      if (!validSourceOperationContextSelection(selected)) return Promise.reject(new Error("SOURCE_OPERATION_CONTEXT_SELECTION_INVALID"));
      const query = new URLSearchParams({ action: selected.action });
      if (selected.workRef !== null) query.set('work_ref', selected.workRef);
      return read("acquisition", `${ORIGIN}/workspace/source-operation/context?${query}`, signal, { cap: 4096, typedUnavailableSchema: null });
    },
    readProjectPlan: (request) => {
      const { signal, ...selected } = request;
      if (!validProjectPlanSelection(selected))
        return Promise.reject(new Error("PROJECT_PLAN_SELECTION_INVALID"));
      return read("acquisition", `${ORIGIN}/workspace/project-plan/current?${new URLSearchParams({ work_ref: selected.work_ref })}`,
        signal, { cap: 131_072, typedUnavailableSchema: "mastermind.workspace_project_plan.v1" });
    },
    readProjectSessionAssociation: (request) => {
      const { signal, ...value } = request;
      const selected = normalizeProjectAssociationSelection(value);
      if (!selected) return Promise.reject(new Error("PROJECT_SESSION_SELECTION_INVALID"));
      return read("acquisition", `${ORIGIN}/workspace/project-session/current?${new URLSearchParams({ work_ref: selected.workRef, root_job_id: selected.rootJobId })}`,
        signal, { cap: 16_384, typedUnavailableSchema: "mastermind.workspace_project_session_association.v1" });
    },
    readProjectArchivePage: (request) => {
      const { signal, ...cursor } = request;
      if (!validArchiveCursor(cursor)) return Promise.reject(new Error("PROJECT_ARCHIVE_REQUEST_INVALID"));
      return read("acquisition", `${ORIGIN}/workspace/projects/archive/current?${new URLSearchParams({ after_work_ref: cursor.after_work_ref, catalogue_digest: cursor.catalogue_digest })}`,
        signal, { cap: 262_144, typedUnavailableSchema: "mastermind.workspace_project_archive.v1" });
    },
    readProjectArchive: ({ signal }) => read("acquisition", `${ORIGIN}/workspace/projects/archive/current`,
      signal, { cap: 262_144, typedUnavailableSchema: "mastermind.workspace_project_archive.v1" }),
    readProjectDirection: (request) => {
      const { signal, ...selected } = request;
      if (!validDirectionSelection(selected))
        return Promise.reject(new Error("DIRECTION_SELECTION_INVALID"));
      return read("acquisition", `${ORIGIN}/workspace/project-direction/current?${new URLSearchParams({ work_ref: selected.work_ref })}`,
        signal, { cap: 65_536, typedUnavailableSchema: "mastermind.workspace_project_direction.v1" });
    },
    readProjectKnowledgeCatalogue: (request) => {
      const {signal,...value}=request, selected=knowledgeReadSelection(value,"catalogue");
      if(!selected) return Promise.reject(new Error("PROJECT_KNOWLEDGE_SELECTION_INVALID"));
      return read("acquisition", `${ORIGIN}/workspace/project-knowledge/current?${new URLSearchParams({...selected})}`,
        signal,{cap:131_072,typedUnavailableSchema:"mastermind.workspace_project_knowledge.v1"});
    },
    readProjectKnowledgeMemory: (request) => {
      const {signal,...value}=request, selected=knowledgeReadSelection(value,"memory");
      if(!selected) return Promise.reject(new Error("PROJECT_KNOWLEDGE_SELECTION_INVALID"));
      return read("acquisition", `${ORIGIN}/workspace/project-memory/current?${new URLSearchParams({...selected})}`,
        signal,{cap:131_072,typedUnavailableSchema:"mastermind.workspace_project_preference.v1"});
    },
    readProjectKnowledgeSource: (request) => {
      const {signal,...value}=request, selected=knowledgeReadSelection(value,"source");
      if(!selected) return Promise.reject(new Error("PROJECT_KNOWLEDGE_SELECTION_INVALID"));
      return read("acquisition", `${ORIGIN}/workspace/project-source/current?${new URLSearchParams({...selected})}`,
        signal,{cap:131_072,typedUnavailableSchema:"mastermind.workspace_project_source.v1"});
    },
    readProjectJournal: (request) => {
      const { signal, ...selected } = request;
      if (!validJournalSelection(selected))
        return Promise.reject(new Error("PROJECT_JOURNAL_SELECTION_INVALID"));
      return read("acquisition", `${ORIGIN}/workspace/project-journal/current?${new URLSearchParams({ work_ref: selected.work_ref })}`,
        signal, { cap: 131_072, typedUnavailableSchema: "mastermind.workspace_project_journal.v1" });
    },
    readAdmittedPlan: ({ work_ref, root_job_id, signal }) => {
      if (!/^WS:[A-Z0-9][A-Za-z0-9._-]{1,63}$/.test(work_ref) || !/^JOB-[0-9]{1,9}$/.test(root_job_id))
        return Promise.reject(new Error("PLAN_SELECTION_INVALID"));
      return read("acquisition", `${ORIGIN}/workspace/plan/current?${new URLSearchParams({ work_ref, root_job_id })}`,
        signal, { cap: 16_384, typedUnavailableSchema: "mastermind.workspace_admitted_execution_plan.v1" });
    },
    readModelConfiguration: ({ signal }) => read("acquisition", `${ORIGIN}/workspace/resources/models/current`,
      signal, { cap: 278_528, typedUnavailableSchema: "mastermind.workspace_model_configuration.v1" }),
    readCapacityFabric: ({ signal }) => read("acquisition", `${ORIGIN}/workspace/resources/fabric/current`,
      signal, { cap: 262_144, typedUnavailableSchema: "mastermind.workspace_capacity_fabric.v1" }),
    readT3AttemptFleet: ({ attemptId, signal }) => {
      if (!validT3AttemptId(attemptId))
        return Promise.reject(new Error("T3_ATTEMPT_SELECTION_INVALID"));
      return read("acquisition", `${ORIGIN}/workspace/resources/t3/attempts/current?${new URLSearchParams({ attempt_id: attemptId })}`,
        signal, { cap: 16_384, typedUnavailableSchema: null });
    },
    readResourceCapacity: ({ work_ref, root_job_id, job_id, attempt_id, signal }) => {
      const selected = { work_ref, root_job_id, job_id, attempt_id };
      if (!validResourceCapacitySelection(selected))
        return Promise.reject(new Error("RESOURCE_CAPACITY_SELECTION_INVALID"));
      return read("acquisition", `${ORIGIN}/workspace/resources/capacity/current?${new URLSearchParams(selected)}`,
        signal, { cap: 16_384, typedUnavailableSchema: "mastermind.workspace_resource_capacity_result.v1" });
    },
    readRetainedActivity: ({ work_ref, root_job_id, job_id, attempt_id, signal }) => {
      const selected = { work_ref, root_job_id, job_id, attempt_id };
      if (!validActivitySelection(selected))
        return Promise.reject(new Error("ACTIVITY_SELECTION_INVALID"));
      return read("acquisition", `${ORIGIN}/workspace/operator/activity/current?${new URLSearchParams(selected)}`,
        signal, { cap: 16_384, typedUnavailableSchema: "mastermind.workspace_retained_activity.v1" });
    },
    readMission: ({ work_ref, root_job_id, signal }) => {
      if (!normalizeSelection({ workRef: work_ref, rootJobId: root_job_id }))
        return Promise.reject(new Error("SELECTION_INVALID"));
      return read(
        "acquisition",
        `${ORIGIN}/workspace/mission/current?${new URLSearchParams({ work_ref, root_job_id })}`,
        signal,
      );
    },
    async readOriginalMissionV4(request: MissionSelection & { signal: AbortSignal }) {
      const { signal, ...input } = request;
      const selected = normalizeWorkspaceSelection(input);
      if (!selected) throw new Error("SELECTION_INVALID");
      return read("acquisition", `${ORIGIN}/workspace/mission/v4/current?${new URLSearchParams({
        work_ref: selected.workRef, root_job_id: selected.rootJobId, read_mode: "original_owner",
      })}`, signal);
    },
    ...(deps.productAcceptanceOwner ? {
      productAcceptanceOwner: deps.productAcceptanceOwner,
      async readMissionV4(request: MissionV4Selection & { signal: AbortSignal }) {
        const { signal, ...input } = request;
        const selected = missionV4Selection(input);
        if (!selected) throw new Error("SELECTION_INVALID");
        const started = generation, owner = deps.productAcceptanceOwner;
        const authorized = () => !signal.aborted && generation === started && owner === deps.productAcceptanceOwner
          && getState().status === "signed_in" && getState().acquisition;
        const guard = guardAcceptanceRead(owner, selected, authorized);
        try {
          guard.check();
          const raw = await read("acquisition", `${ORIGIN}/workspace/mission/v4/current?${new URLSearchParams({
            work_ref: selected.workRef, root_job_id: selected.rootJobId, request_message_key: selected.requestMessageKey,
          })}`, signal);
          guard.check();
          return raw;
        } finally { guard.dispose(); }
      },
    } : {}),
    readMissionV3: ({ workRef, rootJobId, signal }) => {
      if (!normalizeWorkspaceSelection({ workRef, rootJobId }))
        return Promise.reject(new Error("SELECTION_INVALID"));
      return read(
        "acquisition",
        `${ORIGIN}/workspace/mission/v3/current?${new URLSearchParams({ work_ref: workRef, root_job_id: rootJobId })}`,
        signal,
      );
    },
    readResult: ({
      workRef,
      rootJobId,
      jobId,
      attemptId,
      resultEnvelopeDigest,
      signal,
    }) => {
      if (
        !normalizeSelection({ workRef, rootJobId }) ||
        !normalizeResultSelection({
          workRef,
          rootJobId,
          jobId,
          attemptId,
          resultEnvelopeDigest,
        })
      )
        return Promise.reject(new Error("SELECTION_INVALID"));
      // Web and native emit the canonical selection keys in the order the
      // contract table prescribes. No additional selectors, no cursor, no
      // arbitrary URL — the path is the fixed /workspace/result/current. The
      // route reads under the exact 16KiB result body cap and is the one
      // route allowed to surface the typed 503 unavailable envelope.
      return read(
        "acquisition",
        `${ORIGIN}/workspace/result/current?${new URLSearchParams({
          work_ref: workRef,
          root_job_id: rootJobId,
          job_id: jobId,
          attempt_id: attemptId,
          result_envelope_digest: resultEnvelopeDigest,
        })}`,
        signal,
        {
          cap: RESULT_HTTP_BODY_BYTES,
          typedUnavailableSchema: "mastermind.workspace_role_result.v1",
        },
      );
    },
    readMissionResult: (request) => {
      const { signal, ...input } = request;
      const normalized = normalizeResultSelection(input);
      if (!normalized) return Promise.reject(new Error("SELECTION_INVALID"));
      // Fixed acquisition GET. The compound cap is the incumbent 2_000_000
      // stream ceiling; the nested 16KiB ceiling stays in the result decoder.
      // Typed 503 is the closed compound body, not a nested Result document.
      return read(
        "acquisition",
        `${ORIGIN}/workspace/mission-result/current?${new URLSearchParams({
          work_ref: normalized.workRef,
          root_job_id: normalized.rootJobId,
          job_id: normalized.jobId,
          attempt_id: normalized.attemptId,
          result_envelope_digest: normalized.resultEnvelopeDigest,
        })}`,
        signal,
        {
          cap: MAX_RESPONSE_BYTES,
          typedUnavailableSchema: "mastermind.workspace_mission_result.v1",
        },
      );
    },
    readResultReferences: ({ workRef, rootJobId, signal }) => {
      if (!normalizeWorkspaceSelection({ workRef, rootJobId }))
        return Promise.reject(new Error("SELECTION_INVALID"));
      // Fixed retained-result reference read: the same Acquisition READ
      // token, origin, permission and 16KiB cap as the retained Result
      // route; the typed allowed 503 unavailable body carries this route's
      // own closed schema. No extra selector, cursor or arbitrary URL.
      return read(
        "acquisition",
        `${ORIGIN}/workspace/result-references/current?${new URLSearchParams({
          work_ref: workRef,
          root_job_id: rootJobId,
        })}`,
        signal,
        {
          cap: 16_384,
          typedUnavailableSchema: "mastermind.workspace_result_references.v1",
        },
      );
    },
    readCurrentWindow: ({ signal }) =>
      read("content", `${ORIGIN}/workspace/window/current`, signal),
  };
}
function base64(b: Uint8Array) {
  return btoa(String.fromCharCode(...b))
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "");
}
async function boundedJson(response: Response, max: number, parse: (raw: string) => unknown = JSON.parse): Promise<unknown> {
  if (
    response.headers
      .get("content-type")
      ?.split(";", 1)[0]
      .trim()
      .toLowerCase() !== "application/json"
  )
    throw new Error("RESPONSE_TYPE_INVALID");
  const declared = response.headers.get("content-length");
  if (declared !== null && (!/^\d+$/.test(declared) || Number(declared) > max))
    throw new Error("RESPONSE_TOO_LARGE");
  const reader = response.body?.getReader();
  if (!reader) throw new Error("RESPONSE_BODY_MISSING");
  const chunks: Uint8Array[] = [];
  let size = 0;
  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > max) throw new Error("RESPONSE_TOO_LARGE");
      chunks.push(value);
    }
  } catch (error) {
    try {
      await reader.cancel();
    } catch {
      /* transport gone */
    }
    throw error;
  } finally {
    reader.releaseLock();
  }
  const all = new Uint8Array(size);
  let offset = 0;
  for (const chunk of chunks) {
    all.set(chunk, offset);
    offset += chunk.length;
  }
  try {
    return parse(new TextDecoder("utf-8", { fatal: true }).decode(all));
  } catch {
    throw new Error("RESPONSE_INVALID_JSON");
  }
}
