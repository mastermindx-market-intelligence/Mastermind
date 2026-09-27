import {
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
import { normalizeSelection, normalizeWorkspaceSelection } from "./mission";
import { normalizeResultSelection, RESULT_HTTP_BODY_BYTES } from "./result";
import type { AuthState, RawClient } from "./host";
export type { AuthState } from "./host";
export interface WebPopup {
  close(): void;
  closed?: boolean;
  set location(value: string);
}
export interface WebAuthDeps {
  config?: Partial<WebAuthConfig>;
  crypto?: Crypto;
  fetchFn?: typeof fetch;
  openPopup?: (
    url: string,
    target: string,
    features: string,
  ) => WebPopup | null;
  addEventListener?: typeof window.addEventListener;
  removeEventListener?: typeof window.removeEventListener;
  setTimeout?: typeof setTimeout;
  clearTimeout?: typeof clearTimeout;
  now?: () => number;
}
type Resource = "acquisition" | "content";
type Token = { value: string; expires: number };
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
  document.title = failure || error ? "Sign-in failed" : "Completing sign-in";
  const main = document.createElement("main");
  main.setAttribute("role", "status");
  main.textContent =
    failure || error
      ? "Sign-in failed. Close this window and try again."
      : "Completing sign-in. This window will close automatically.";
  document.body.replaceChildren(main);
  if (origin === ORIGIN && window.opener && !window.opener.closed) {
    try {
      window.opener.postMessage(payload, ORIGIN);
    } catch {
      /* opener is gone */
    }
  }
  return true;
}

/** Private memory owns two exact-audience tokens. Only fixed reads cross this boundary. */
export function createWebAuth(deps: WebAuthDeps = {}): RawClient {
  const config = { ...readWebAuthConfig(), ...deps.config };
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
  const cryptoApi = deps.crypto ?? crypto,
    fetchFn = deps.fetchFn ?? fetch.bind(globalThis),
    now = deps.now ?? Date.now;
  const open =
    deps.openPopup ??
    ((url, target, features) =>
      window.open(url, target, features) as unknown as WebPopup | null);
  const add = deps.addEventListener ?? window.addEventListener.bind(window),
    remove =
      deps.removeEventListener ?? window.removeEventListener.bind(window);
  const later = deps.setTimeout ?? setTimeout,
    clear = deps.clearTimeout ?? clearTimeout;
  let generation = 0,
    flow: { generation: number; popup: WebPopup; cancel: () => void } | null =
      null,
    lastError: string | null = null;
  const tokens: Record<Resource, Token | null> = {
    acquisition: null,
    content: null,
  };
  const listeners = new Set<(s: AuthState) => void>();
  const valid = (resource: Resource) =>
    Boolean(tokens[resource] && tokens[resource]!.expires > now());
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
      reason: !configured ? "CLIENT_NOT_REGISTERED" : lastError,
      acquisition: valid("acquisition"),
      content: valid("content"),
    };
  }
  function emit() {
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
    const scope =
      resource === "acquisition" ? ACQUISITION_SCOPE : CONTENT_SCOPE;
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
        (t.scope !== undefined && t.scope !== scope)
      )
        throw new Error("TOKEN_INVALID");
      return {
        value: t.access_token,
        expires: now() + Number(t.expires_in) * 1000,
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
    const scope =
      resource === "acquisition" ? ACQUISITION_SCOPE : CONTENT_SCOPE;
    const audience =
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
      later(
        () => {
          if (ticket === generation && tokens[resource] === token) {
            tokens[resource] = null;
            emit();
          }
        },
        Math.max(0, token.expires - now()),
      );
      emit();
    } finally {
      remove("message", listener);
      clear(timer);
      clear(poll);
      abort.abort();
      current.cancel = () => {};
    }
  }
  async function signIn() {
    if (!configured) return getState();
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
      await transaction("content", current);
      check(current.generation);
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
  async function signOut() {
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
   * with READ_FAILED before a body is read. Only the result route opts into
   * the single allowed typed error body: a 503 whose body parses under the
   * exact 16KiB result cap and presents the closed unavailable envelope
   * shape. Nothing else may surface error JSON, and the full closed-body
   * validation stays in the host decoder.
   */
  async function read(
    resource: Resource,
    url: string,
    signal: AbortSignal,
    policy: { cap: number; allowTypedUnavailable: boolean } = {
      cap: MAX_RESPONSE_BYTES,
      allowTypedUnavailable: false,
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
      if (response.status === 503 && policy.allowTypedUnavailable) {
        const body = await boundedJson(response, policy.cap);
        if (
          body === null ||
          typeof body !== "object" ||
          Array.isArray(body) ||
          (body as Record<string, unknown>).schema !==
            "mastermind.workspace_role_result.v1" ||
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
    }
  }
  return {
    getState,
    subscribe(listener) {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    signIn,
    signOut,
    readPrograms: ({ signal }) =>
      read("acquisition", `${ORIGIN}/workspace/programs/current`, signal),
    readMission: ({ work_ref, root_job_id, signal }) => {
      if (!normalizeSelection({ workRef: work_ref, rootJobId: root_job_id }))
        return Promise.reject(new Error("SELECTION_INVALID"));
      return read(
        "acquisition",
        `${ORIGIN}/workspace/mission/current?${new URLSearchParams({ work_ref, root_job_id })}`,
        signal,
      );
    },
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
        { cap: RESULT_HTTP_BODY_BYTES, allowTypedUnavailable: true },
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
async function boundedJson(response: Response, max: number): Promise<unknown> {
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
    return JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(all));
  } catch {
    throw new Error("RESPONSE_INVALID_JSON");
  }
}
