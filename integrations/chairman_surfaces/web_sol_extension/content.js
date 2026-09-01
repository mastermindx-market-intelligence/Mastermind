"use strict";

const PROBE_KIND = "MMX_WEB_SOL_PROBE";
const REPROBE_KIND = "MMX_WEB_SOL_REPROBE";
const PROBE_SCHEMA = "mastermind.web_sol_surface_probe.v1";
const CHAT_PATH = /^(?:\/c\/[^/]+|\/g\/g-p-[A-Za-z0-9_-]+\/c\/[^/]+)\/?$/;

const COMPOSER_SELECTORS = [
  "#prompt-textarea",
  "[data-testid='prompt-textarea']",
];
const ACTIVE_SELECTORS = [
  "[data-testid='stop-button']",
];
const ERROR_SELECTORS = [
  "[data-testid='conversation-turn-error']",
  "[data-testid='error-message']",
];

function firstMatch(selectors) {
  for (const selector of selectors) {
    if (document.querySelector(selector)) {
      return true;
    }
  }
  return false;
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
  const targetPresent = CHAT_PATH.test(location.pathname);
  const composerAvailable = firstMatch(COMPOSER_SELECTORS);
  const generationActive = firstMatch(ACTIVE_SELECTORS);
  const providerErrorPresent = firstMatch(ERROR_SELECTORS);
  const conversationFingerprint = targetPresent
    ? await sha256Hex(canonicalConversationIdentity())
    : null;
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
      document_ready_state: normalizedReadyState(),
      visibility: normalizeVisibility(),
      composer_available: composerAvailable,
      generation_state: generationActive ? "active" : composerAvailable ? "idle" : "unknown",
      auth_required: authState(targetPresent, composerAvailable),
      provider_error_present: providerErrorPresent,
    },
  };
}

chrome.runtime.onMessage.addListener((request, _sender, sendResponse) => {
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
