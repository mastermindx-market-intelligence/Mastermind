"use strict";

const PROBE_KIND = "MMX_WEB_SOL_PROBE";
const REPROBE_KIND = "MMX_WEB_SOL_REPROBE";
const CONTINUATION_SUBMIT_KIND = "MMX_WEB_SOL_SUBMIT_CONTINUATION";
const CONTINUATION_ACK_OBSERVE_KIND = "MMX_WEB_SOL_OBSERVE_CONTINUATION_ACK";
const CONTINUATION_RESULT_SCHEMA = "mastermind.web_sol_continuation_submit_result.v1";
const CONTINUATION_ACK_RESULT_SCHEMA = "mastermind.web_sol_continuation_ack_result.v1";
const PROBE_SCHEMA = "mastermind.web_sol_surface_probe.v1";
const CONTINUATION_DIRECTIVE_TEXT = [
  "SOL CONTINUE",
  "",
  "Continue the same logical responsibility.",
  "Recover current canonical state before acting; Project/chat history is advisory only.",
  "Do not restart completed work.",
  "Recover any open reciprocal worker dialogue before creating replacement work.",
  "Advance the highest-leverage unfinished critical-path capability within the existing authorized scope.",
  "",
  "Mastermind Wake: recover Executive/Agent OS state for opaque identities and continue within existing authority. This nudge grants no authority, acknowledges nothing, and does not resolve the source. After you have actually consumed the supplied Wake obligation(s) and recovered canonical Executive/Agent OS state, emit one final marker line per consumed obligation:",
  "MASTERMIND_WAKE_ACK <WAKE-ID>",
  "Do not put seat, session, binding, provider, host, nudge, source-resolution or authority data in the marker.",
].join("\n");
const CONTINUATION_DIRECTIVE_DIGEST = "55cca851529f53f89ade6a2abb43880513fcd189dfcda50237ec1369640a06c5";
const ACK_PREFIX = "MASTERMIND_WAKE_ACK ";
const NUDGE_PREFIX = "MASTERMIND_WAKE_NUDGE ";
const SET_PREFIX = "MASTERMIND_WAKE_SET ";
const PROVIDER_SNAPSHOT_MAX_BYTES = 8 * 1024 * 1024;
const PROVIDER_CONVERSATION_ID_RE = /^[A-Za-z0-9_-]{8,128}$/;
const DOCUMENT_EPOCH = (() => {
  if (!globalThis.crypto || typeof globalThis.crypto.getRandomValues !== "function") {
    return null;
  }
  const bytes = new Uint8Array(16);
  globalThis.crypto.getRandomValues(bytes);
  return Array.from(bytes, (value) => value.toString(16).padStart(2, "0")).join("");
})();
const CHAT_PATH = /^(?:\/c\/[^/]+|\/g\/g-p-[A-Za-z0-9_-]+\/c\/[^/]+)\/?$/;

const COMPOSER_SELECTORS = [
  "#prompt-textarea",
  "[data-testid='prompt-textarea']",
];
const ACTIVE_SELECTORS = [
  "[data-testid='stop-button']",
];
const SEND_SELECTORS = [
  "button[data-testid='send-button']",
  "button[data-testid='composer-submit-button']",
];
const ERROR_SELECTORS = [
  "[data-testid='conversation-turn-error']",
  "[data-testid='error-message']",
];

function firstElement(selectors) {
  for (const selector of selectors) {
    const element = document.querySelector(selector);
    if (element) return element;
  }
  return null;
}

function firstMatch(selectors) {
  return firstElement(selectors) !== null;
}

function normalizeVisibility() {
  return document.visibilityState === "hidden" ? "hidden" : "visible";
}

function normalizedReadyState() {
  if (document.readyState === "loading" || document.readyState === "interactive") {
    return document.readyState;
  }
  return "complete";
}

function canonicalConversationIdentity() {
  const path = location.pathname.endsWith("/") ? location.pathname.slice(0, -1) : location.pathname;
  const origin = location.origin.toLowerCase() === "https://chat.openai.com"
    ? "https://chatgpt.com"
    : location.origin.toLowerCase();
  return `${origin}${path}`;
}

function authState(targetPresent, composerAvailable) {
  if (location.pathname.startsWith("/auth/") || location.pathname === "/login") {
    return true;
  }
  if (targetPresent && composerAvailable) {
    return false;
  }
  return null;
}

async function sha256Hex(value) {
  const encoded = new TextEncoder().encode(value);
  const digest = await crypto.subtle.digest("SHA-256", encoded);
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

async function buildProbe(expectedConversationFingerprint = null) {
  const observationIdentity = canonicalConversationIdentity();
  const targetPresent = CHAT_PATH.test(location.pathname);
  const composerAvailable = firstMatch(COMPOSER_SELECTORS);
  const generationActive = firstMatch(ACTIVE_SELECTORS);
  const providerErrorPresent = firstMatch(ERROR_SELECTORS);
  const documentReadyState = normalizedReadyState();
  const visibility = normalizeVisibility();
  const authRequired = authState(targetPresent, composerAvailable);
  const conversationFingerprint = targetPresent
    ? await sha256Hex(observationIdentity)
    : null;
  if (canonicalConversationIdentity() !== observationIdentity) {
    throw new Error("OBSERVATION_INVALIDATED");
  }
  const exactConversationLoaded =
    targetPresent &&
    typeof expectedConversationFingerprint === "string" &&
    conversationFingerprint === expectedConversationFingerprint;

  return {
    kind: PROBE_KIND,
    conversation_fingerprint: conversationFingerprint,
    document_epoch: DOCUMENT_EPOCH,
    observation: {
      schema: PROBE_SCHEMA,
      target_present: targetPresent,
      exact_conversation_loaded: exactConversationLoaded,
      page_responsive: true,
      document_ready_state: documentReadyState,
      visibility,
      composer_available: composerAvailable,
      generation_state: generationActive ? "active" : composerAvailable ? "idle" : "unknown",
      auth_required: authRequired,
      provider_error_present: providerErrorPresent,
    },
  };
}

function exactKeys(object, expected) {
  if (!object || typeof object !== "object" || Array.isArray(object)) return false;
  const keys = Object.keys(object);
  return keys.length === expected.length && keys.every((key) => expected.includes(key));
}

function validTurnId(value) {
  return typeof value === "string" && /^[A-Za-z0-9][A-Za-z0-9._:/-]{2,255}$/.test(value);
}

function validWakeObligationSet(request) {
  const ids = request.wake_obligation_ids;
  return Array.isArray(ids) && ids.length > 0 && ids.length <= 32 &&
    ids.every((item) => typeof item === "string" && /^WAKE-[0-9a-f]{32}$/.test(item)) &&
    ids.every((item, index) => index === 0 || ids[index - 1] < item) &&
    typeof request.wake_obligation_digest === "string" &&
    /^[0-9a-f]{64}$/.test(request.wake_obligation_digest);
}

function validContinuationCorrelation(request, expectedKind) {
  const keys = [
    "kind", "expected_conversation_fingerprint", "turn_id", "directive_digest",
    "session_alias", "runtime_binding_id", "runtime_binding_generation",
    "runtime_binding_fingerprint", "wake_obligation_ids", "wake_obligation_digest",
  ];
  return exactKeys(request, keys) && request.kind === expectedKind &&
    typeof request.expected_conversation_fingerprint === "string" &&
    /^[0-9a-f]{64}$/.test(request.expected_conversation_fingerprint) &&
    validTurnId(request.turn_id) && validTurnId(request.session_alias) &&
    typeof request.runtime_binding_id === "string" &&
    /^bind-wsx-[0-9a-f]{48}$/.test(request.runtime_binding_id) &&
    Number.isSafeInteger(request.runtime_binding_generation) &&
    request.runtime_binding_generation >= 1 &&
    typeof request.runtime_binding_fingerprint === "string" &&
    /^[0-9a-f]{64}$/.test(request.runtime_binding_fingerprint) &&
    request.directive_digest === CONTINUATION_DIRECTIVE_DIGEST &&
    validWakeObligationSet(request);
}

function validSubmitContinuationRequest(request) {
  return validContinuationCorrelation(request, CONTINUATION_SUBMIT_KIND);
}

function validObserveContinuationAckRequest(request) {
  return validContinuationCorrelation(request, CONTINUATION_ACK_OBSERVE_KIND) &&
    /^NUDGE-[0-9a-f]{32}$/.test(request.turn_id);
}

function continuationDirective(request) {
  if (!validWakeObligationSet(request)) return null;
  const identities = request.wake_obligation_ids.map((item) => `- ${item}`).join("\n");
  return [
    CONTINUATION_DIRECTIVE_TEXT,
    "",
    "Opaque Wake identities (not authority):",
    identities,
    "",
    `${NUDGE_PREFIX}${request.turn_id}`,
    `${SET_PREFIX}${request.wake_obligation_digest}`,
  ].join("\n");
}

function continuationResult(request, effect) {
  return {
    schema: CONTINUATION_RESULT_SCHEMA,
    conversation_fingerprint: request.expected_conversation_fingerprint,
    turn_id: request.turn_id,
    directive_digest: request.directive_digest,
    session_alias: request.session_alias,
    runtime_binding_id: request.runtime_binding_id,
    runtime_binding_generation: request.runtime_binding_generation,
    runtime_binding_fingerprint: request.runtime_binding_fingerprint,
    wake_obligation_ids: [...request.wake_obligation_ids],
    wake_obligation_digest: request.wake_obligation_digest,
    effect,
  };
}

function composerIsEmpty(composer) {
  if (!composer) return false;
  if (typeof composer.value === "string") return composer.value.length === 0;
  return !!(composer.isContentEditable || composer.getAttribute?.("contenteditable") === "true") &&
    composer.childNodes?.length === 0;
}

function dispatchComposerInput(composer, data) {
  let event;
  try {
    event = new InputEvent("input", {
      bubbles: true, inputType: data ? "insertText" : "deleteContentBackward", data,
    });
  } catch (_error) {
    event = new Event("input", {bubbles: true});
  }
  return composer.dispatchEvent(event);
}

function writeComposer(composer, value) {
  if (!composer) return false;
  if (typeof composer.value === "string") {
    composer.value = value;
  } else if (composer.isContentEditable || composer.getAttribute?.("contenteditable") === "true") {
    if (typeof composer.replaceChildren === "function") {
      if (value) composer.replaceChildren(document.createTextNode(value));
      else composer.replaceChildren();
    } else {
      return false;
    }
  } else {
    return false;
  }
  dispatchComposerInput(composer, value || null);
  return true;
}

function clearComposer(composer) {
  try {
    return writeComposer(composer, "") && composerIsEmpty(composer);
  } catch (_error) {
    return false;
  }
}

function submitButtonReady(button) {
  return !!button && button.disabled !== true && button.getAttribute?.("aria-disabled") !== "true";
}

async function submitContinuation(request) {
  if (!validSubmitContinuationRequest(request)) return null;
  const expected = request.expected_conversation_fingerprint;
  let identity;
  try {
    identity = canonicalConversationIdentity();
    if (!CHAT_PATH.test(location.pathname) || await sha256Hex(identity) !== expected) {
      return continuationResult(request, "NOT_SUBMITTED");
    }
  } catch (_error) {
    return continuationResult(request, "NOT_SUBMITTED");
  }

  const composer = firstElement(COMPOSER_SELECTORS);
  if (!composer || !composerIsEmpty(composer)) {
    return continuationResult(request, "NOT_SUBMITTED");
  }
  let composerMutated = false;
  let submitPossible = false;
  try {
    composer.focus?.();
    const directive = continuationDirective(request);
    if (!directive || !writeComposer(composer, directive)) {
      return continuationResult(request, "NOT_SUBMITTED");
    }
    composerMutated = true;
    await Promise.resolve();
    if (canonicalConversationIdentity() !== identity || await sha256Hex(canonicalConversationIdentity()) !== expected) {
      return continuationResult(
        request,
        clearComposer(composer) ? "NOT_SUBMITTED" : "SUBMIT_EFFECT_UNKNOWN",
      );
    }
    const sendButton = firstElement(SEND_SELECTORS);
    if (!submitButtonReady(sendButton)) {
      return continuationResult(
        request,
        clearComposer(composer) ? "NOT_SUBMITTED" : "SUBMIT_EFFECT_UNKNOWN",
      );
    }
    submitPossible = true;
    sendButton.click();
    return continuationResult(request, "SUBMIT_TRIGGERED");
  } catch (_error) {
    if (!submitPossible && composerMutated && clearComposer(composer)) {
      return continuationResult(request, "NOT_SUBMITTED");
    }
    return continuationResult(request, "SUBMIT_EFFECT_UNKNOWN");
  }
}


function emptySemanticReduction(status) {
  return {
    status,
    provider_native_turn_id: null,
    obligation_ids: [],
    terminal_ack_trailer: false,
  };
}

function semanticAckResult(request, reduced) {
  const statuses = {
    ACKNOWLEDGED: "CONTINUATION_ACKNOWLEDGED",
    PENDING: "CONTINUATION_ACK_PENDING",
    REFUSED: "CONTINUATION_ACK_REFUSED",
  };
  const status = statuses[reduced.status] || "CONTINUATION_ACK_REFUSED";
  const acknowledged = status === "CONTINUATION_ACKNOWLEDGED";
  return {
    schema: CONTINUATION_ACK_RESULT_SCHEMA,
    conversation_fingerprint: request.expected_conversation_fingerprint,
    turn_id: request.turn_id,
    directive_digest: request.directive_digest,
    session_alias: request.session_alias,
    runtime_binding_id: request.runtime_binding_id,
    runtime_binding_generation: request.runtime_binding_generation,
    runtime_binding_fingerprint: request.runtime_binding_fingerprint,
    wake_obligation_ids: [...request.wake_obligation_ids],
    wake_obligation_digest: request.wake_obligation_digest,
    provider_native_turn_id: acknowledged ? reduced.provider_native_turn_id : null,
    acknowledged_obligation_ids: acknowledged ? [...reduced.obligation_ids] : [],
    terminal_ack_trailer: acknowledged && reduced.terminal_ack_trailer === true,
    document_epoch: DOCUMENT_EPOCH,
    status,
  };
}

function providerConversationId() {
  const path = location.pathname.endsWith("/")
    ? location.pathname.slice(0, -1)
    : location.pathname;
  const match = /^(?:\/c\/([^/]+)|\/g\/g-p-[A-Za-z0-9_-]+\/c\/([^/]+))$/.exec(path);
  if (!match) return null;
  const value = match[1] || match[2];
  return PROVIDER_CONVERSATION_ID_RE.test(value) ? value : null;
}

async function boundedProviderJson(response) {
  const declaredHeader = response.headers?.get?.("content-length");
  if (declaredHeader !== null && declaredHeader !== undefined) {
    const declared = Number(declaredHeader);
    if (!Number.isSafeInteger(declared) || declared < 0 ||
        declared > PROVIDER_SNAPSHOT_MAX_BYTES) return null;
  }
  const reader = response.body?.getReader?.();
  if (!reader) return null;
  const chunks = [];
  let total = 0;
  try {
    while (true) {
      const result = await reader.read();
      if (!result || typeof result.done !== "boolean") return null;
      if (result.done) break;
      if (!(result.value instanceof Uint8Array)) return null;
      total += result.value.byteLength;
      if (total > PROVIDER_SNAPSHOT_MAX_BYTES) {
        await reader.cancel?.();
        return null;
      }
      chunks.push(result.value);
    }
  } catch (_error) {
    try { await reader.cancel?.(); } catch (_ignored) {}
    return null;
  }
  const buffer = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    buffer.set(chunk, offset);
    offset += chunk.byteLength;
  }
  try {
    return JSON.parse(new TextDecoder("utf-8", {fatal: true}).decode(buffer));
  } catch (_error) {
    return null;
  }
}

async function fetchProviderSnapshot() {
  const conversationId = providerConversationId();
  if (!conversationId) return {status: "REFUSED", snapshot: null};
  let response;
  try {
    const endpoint = new URL(
      `/backend-api/conversation/${encodeURIComponent(conversationId)}`,
      location.origin,
    );
    if (endpoint.origin !== location.origin ||
        endpoint.pathname !== `/backend-api/conversation/${encodeURIComponent(conversationId)}` ||
        endpoint.search || endpoint.hash) {
      return {status: "REFUSED", snapshot: null};
    }
    response = await fetch(endpoint.href, {
      method: "GET",
      credentials: "include",
      cache: "no-store",
      redirect: "error",
      headers: {Accept: "application/json"},
    });
  } catch (_error) {
    return {status: "PENDING", snapshot: null};
  }
  if ([401, 403, 404].includes(response.status)) {
    return {status: "REFUSED", snapshot: null};
  }
  if (!response.ok) return {status: "PENDING", snapshot: null};
  const contentType = response.headers?.get?.("content-type") || "";
  if (!contentType.toLowerCase().includes("application/json")) {
    return {status: "REFUSED", snapshot: null};
  }
  const snapshot = await boundedProviderJson(response);
  if (!snapshot || typeof snapshot !== "object" || Array.isArray(snapshot) ||
      snapshot.conversation_id !== conversationId) {
    return {status: "REFUSED", snapshot: null};
  }
  return {status: "SNAPSHOT", snapshot};
}

async function observeSemanticAck(request) {
  if (!validObserveContinuationAckRequest(request) ||
      !globalThis.MMXWebSolSemanticAck?.reduceConversation) {
    return semanticAckResult(request, emptySemanticReduction("REFUSED"));
  }
  const identity = canonicalConversationIdentity();
  let probe;
  try {
    if (!CHAT_PATH.test(location.pathname) ||
        await sha256Hex(identity) !== request.expected_conversation_fingerprint) {
      return semanticAckResult(request, emptySemanticReduction("REFUSED"));
    }
    probe = await buildProbe(request.expected_conversation_fingerprint);
  } catch (_error) {
    return semanticAckResult(request, emptySemanticReduction("REFUSED"));
  }
  if (canonicalConversationIdentity() !== identity ||
      probe.conversation_fingerprint !== request.expected_conversation_fingerprint ||
      !probe.observation.target_present || !probe.observation.exact_conversation_loaded ||
      probe.observation.auth_required === true ||
      probe.observation.provider_error_present === true) {
    return semanticAckResult(request, emptySemanticReduction("REFUSED"));
  }
  const provider = await fetchProviderSnapshot();
  if (provider.status !== "SNAPSHOT") {
    return semanticAckResult(
      request,
      emptySemanticReduction(provider.status === "PENDING" ? "PENDING" : "REFUSED"),
    );
  }
  if (canonicalConversationIdentity() !== identity ||
      await sha256Hex(identity) !== request.expected_conversation_fingerprint) {
    return semanticAckResult(request, emptySemanticReduction("REFUSED"));
  }
  const reduced = globalThis.MMXWebSolSemanticAck.reduceConversation(
    provider.snapshot,
    {
      nudge_id: request.turn_id,
      wake_obligation_ids: request.wake_obligation_ids,
      wake_obligation_digest: request.wake_obligation_digest,
    },
  );
  return semanticAckResult(request, reduced);
}

chrome.runtime.onMessage.addListener((request, _sender, sendResponse) => {
  if (validObserveContinuationAckRequest(request)) {
    observeSemanticAck(request)
      .then((result) => sendResponse(result))
      .catch(() => sendResponse(semanticAckResult(
        request, emptySemanticReduction("REFUSED")
      )));
    return true;
  }
  if (validSubmitContinuationRequest(request)) {
    submitContinuation(request)
      .then((result) => sendResponse(result))
      .catch(() => sendResponse(continuationResult(request, "SUBMIT_EFFECT_UNKNOWN")));
    return true;
  }
  if (
    !request ||
    request.kind !== REPROBE_KIND ||
    (request.expected_conversation_fingerprint !== null &&
      (typeof request.expected_conversation_fingerprint !== "string" ||
        !/^[0-9a-f]{64}$/.test(request.expected_conversation_fingerprint)))
  ) {
    return false;
  }
  buildProbe(request.expected_conversation_fingerprint)
    .then((probe) => sendResponse(probe))
    .catch(() => sendResponse(null));
  return true;
});

buildProbe()
  .then((probe) => chrome.runtime.sendMessage(probe))
  .catch(() => undefined);
