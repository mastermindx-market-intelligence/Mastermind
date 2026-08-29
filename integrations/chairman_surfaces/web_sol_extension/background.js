"use strict";

const NATIVE_HOST = "com.mastermind.web_sol_surface";
const PROBE_KIND = "MMX_WEB_SOL_PROBE";

const OBSERVATION_KEYS = new Set([
  "schema",
  "target_present",
  "exact_conversation_loaded",
  "page_responsive",
  "document_ready_state",
  "visibility",
  "composer_available",
  "generation_state",
  "auth_required",
  "provider_error_present",
]);

let nativePort = null;

function exactKeys(object, allowed) {
  if (!object || typeof object !== "object" || Array.isArray(object)) {
    return false;
  }
  const keys = Object.keys(object);
  return keys.length === allowed.size && keys.every((key) => allowed.has(key));
}

function validProbeEvent(event) {
  if (!event || typeof event !== "object" || Array.isArray(event)) {
    return false;
  }
  if (event.kind !== PROBE_KIND) {
    return false;
  }
  if (
    event.conversation_fingerprint !== null &&
    (typeof event.conversation_fingerprint !== "string" ||
      !/^[0-9a-f]{64}$/.test(event.conversation_fingerprint))
  ) {
    return false;
  }
  return exactKeys(event.observation, OBSERVATION_KEYS);
}

function getNativePort() {
  if (nativePort) {
    return nativePort;
  }
  try {
    nativePort = chrome.runtime.connectNative(NATIVE_HOST);
  } catch (_error) {
    nativePort = null;
    return null;
  }
  nativePort.onDisconnect.addListener(() => {
    nativePort = null;
  });
  return nativePort;
}

chrome.runtime.onMessage.addListener((event) => {
  if (!validProbeEvent(event)) {
    return;
  }
  const port = getNativePort();
  if (!port) {
    return;
  }
  port.postMessage({
    kind: PROBE_KIND,
    conversation_fingerprint: event.conversation_fingerprint,
    observation: event.observation,
  });
});
