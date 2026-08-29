"use strict";

const PROBE_KIND = "MMX_WEB_SOL_PROBE";
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

async function buildProbe() {
  const targetPresent = CHAT_PATH.test(location.pathname);
  const composerAvailable = firstMatch(COMPOSER_SELECTORS);
  const generationActive = firstMatch(ACTIVE_SELECTORS);
  const providerErrorPresent = firstMatch(ERROR_SELECTORS);
  const conversationFingerprint = targetPresent
    ? await sha256Hex(`${location.origin}${location.pathname}`)
    : null;

  return {
    kind: PROBE_KIND,
    conversation_fingerprint: conversationFingerprint,
    observation: {
      schema: PROBE_SCHEMA,
      target_present: targetPresent,
      exact_conversation_loaded: false,
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

buildProbe()
  .then((probe) => chrome.runtime.sendMessage(probe))
  .catch(() => undefined);
