"use strict";

const PROBE_KIND = "MMX_WEB_SOL_PROBE";
const REPROBE_KIND = "MMX_WEB_SOL_REPROBE";
const CONTINUATION_SUBMIT_KIND = "MMX_WEB_SOL_SUBMIT_CONTINUATION";
const CONTINUATION_RESULT_SCHEMA = "mastermind.web_sol_continuation_submit_result.v1";
const PROBE_SCHEMA = "mastermind.web_sol_surface_probe.v1";
const CONTINUATION_DIRECTIVE_TEXT = [
  "SOL CONTINUE",
  "",
  "Continue the same logical responsibility.",
  "Recover current canonical state before acting; Project/chat history is advisory only.",
  "Do not restart completed work.",
  "Recover any open reciprocal worker dialogue before creating replacement work.",
  "Advance the highest-leverage unfinished critical-path capability within the existing authorized scope.",
].join("\n");
const CONTINUATION_DIRECTIVE_DIGEST = "cde0de54629786dcd6c0ee3b169558cf050de48b828a4da15cbd2d881c66afd9";
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

function validSubmitContinuationRequest(request) {
  const keys = [
    "kind", "expected_conversation_fingerprint", "turn_id", "directive_digest",
    "session_alias", "runtime_binding_id", "runtime_binding_generation",
    "runtime_binding_fingerprint",
  ];
  return exactKeys(request, keys) && request.kind === CONTINUATION_SUBMIT_KIND &&
    typeof request.expected_conversation_fingerprint === "string" &&
    /^[0-9a-f]{64}$/.test(request.expected_conversation_fingerprint) &&
    validTurnId(request.turn_id) && validTurnId(request.session_alias) &&
    typeof request.runtime_binding_id === "string" &&
    /^bind-wsx-[0-9a-f]{48}$/.test(request.runtime_binding_id) &&
    Number.isSafeInteger(request.runtime_binding_generation) &&
    request.runtime_binding_generation >= 1 &&
    typeof request.runtime_binding_fingerprint === "string" &&
    /^[0-9a-f]{64}$/.test(request.runtime_binding_fingerprint) &&
    request.directive_digest === CONTINUATION_DIRECTIVE_DIGEST;
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
    if (!writeComposer(composer, CONTINUATION_DIRECTIVE_TEXT)) {
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

chrome.runtime.onMessage.addListener((request, _sender, sendResponse) => {
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
