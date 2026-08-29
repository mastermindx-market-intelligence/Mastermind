"use strict";

const NATIVE_HOST = "com.mastermind.web_sol_surface";
const PROBE_KIND = "MMX_WEB_SOL_PROBE";
const REPROBE_KIND = "MMX_WEB_SOL_REPROBE";
const ACTION_SCHEMA = "mastermind.web_sol_surface_action.v1";
const RECEIPT_SCHEMA = "mastermind.web_sol_surface_receipt.v1";
const PROBE_SCHEMA = "mastermind.web_sol_surface_probe.v1";

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
const ACTION_KEYS = new Set([
  "schema",
  "binding_id",
  "conversation_fingerprint",
  "binding_fingerprint",
  "binding_revision",
  "action",
  "operation_key",
  "issued_at",
  "expires_at",
  "nonce",
]);

const targets = new Map();
const tabFingerprints = new Map();
let nativePort = null;

function exactKeys(object, allowed) {
  if (!object || typeof object !== "object" || Array.isArray(object)) {
    return false;
  }
  const keys = Object.keys(object);
  return keys.length === allowed.size && keys.every((key) => allowed.has(key));
}

function isHex64(value) {
  return typeof value === "string" && /^[0-9a-f]{64}$/.test(value);
}

function validProbeObservation(observation) {
  if (!exactKeys(observation, OBSERVATION_KEYS)) {
    return false;
  }
  if (observation.schema !== PROBE_SCHEMA) {
    return false;
  }
  if (
    typeof observation.target_present !== "boolean" ||
    typeof observation.exact_conversation_loaded !== "boolean" ||
    typeof observation.page_responsive !== "boolean"
  ) {
    return false;
  }
  if (!["loading", "interactive", "complete"].includes(observation.document_ready_state)) {
    return false;
  }
  if (!["visible", "hidden"].includes(observation.visibility)) {
    return false;
  }
  if (!["active", "idle", "unknown"].includes(observation.generation_state)) {
    return false;
  }
  for (const field of ["composer_available", "auth_required", "provider_error_present"]) {
    if (observation[field] !== null && typeof observation[field] !== "boolean") {
      return false;
    }
  }
  return true;
}

function validProbeEvent(event) {
  if (!event || typeof event !== "object" || Array.isArray(event)) {
    return false;
  }
  if (event.kind !== PROBE_KIND) {
    return false;
  }
  if (event.conversation_fingerprint !== null && !isHex64(event.conversation_fingerprint)) {
    return false;
  }
  return validProbeObservation(event.observation);
}

function validActionRequest(request) {
  if (!exactKeys(request, ACTION_KEYS) || request.schema !== ACTION_SCHEMA) {
    return false;
  }
  if (request.action !== "INSPECT" && request.action !== "FOREGROUND") {
    return false;
  }
  if (!isHex64(request.conversation_fingerprint) || !isHex64(request.binding_fingerprint)) {
    return false;
  }
  if (
    typeof request.binding_id !== "string" ||
    typeof request.operation_key !== "string" ||
    !request.operation_key ||
    typeof request.nonce !== "string" ||
    request.nonce.length < 16
  ) {
    return false;
  }
  if (!Number.isSafeInteger(request.binding_revision) || request.binding_revision < 0) {
    return false;
  }
  if (typeof request.issued_at !== "string" || typeof request.expires_at !== "string") {
    return false;
  }
  return true;
}

function removeTabMapping(tabId) {
  const previous = tabFingerprints.get(tabId);
  if (!previous) {
    return;
  }
  tabFingerprints.delete(tabId);
  const entries = targets.get(previous);
  if (!entries) {
    return;
  }
  entries.delete(tabId);
  if (entries.size === 0) {
    targets.delete(previous);
  }
}

function recordProbe(event, sender) {
  if (!validProbeEvent(event) || !sender || !sender.tab) {
    return false;
  }
  const tabId = sender.tab.id;
  const windowId = sender.tab.windowId;
  if (!Number.isInteger(tabId) || !Number.isInteger(windowId)) {
    return false;
  }
  removeTabMapping(tabId);
  if (!event.conversation_fingerprint || !event.observation.target_present) {
    return true;
  }
  let entries = targets.get(event.conversation_fingerprint);
  if (!entries) {
    entries = new Map();
    targets.set(event.conversation_fingerprint, entries);
  }
  entries.set(tabId, windowId);
  tabFingerprints.set(tabId, event.conversation_fingerprint);
  return true;
}

function unknownObservation() {
  return {
    schema: PROBE_SCHEMA,
    target_present: false,
    exact_conversation_loaded: false,
    page_responsive: false,
    document_ready_state: "loading",
    visibility: "hidden",
    composer_available: null,
    generation_state: "unknown",
    auth_required: null,
    provider_error_present: null,
  };
}

function receipt(request, status, observation) {
  return {
    schema: RECEIPT_SCHEMA,
    binding_id: request.binding_id,
    conversation_fingerprint: request.conversation_fingerprint,
    binding_fingerprint: request.binding_fingerprint,
    binding_revision: request.binding_revision,
    action: request.action,
    operation_key: request.operation_key,
    nonce: request.nonce,
    status,
    observed_at: new Date().toISOString(),
    observation,
  };
}

function resolveExactTarget(conversationFingerprint) {
  const entries = targets.get(conversationFingerprint);
  if (!entries || entries.size === 0) {
    return { status: "TARGET_NOT_FOUND" };
  }
  if (entries.size !== 1) {
    return { status: "AMBIGUOUS_TARGET" };
  }
  const [entry] = entries.entries();
  const [tabId, windowId] = entry;
  return { status: null, tabId, windowId };
}

async function freshProbe(tabId, expectedConversationFingerprint) {
  let event;
  try {
    event = await chrome.tabs.sendMessage(tabId, {
      kind: "MMX_WEB_SOL_REPROBE",
      expected_conversation_fingerprint: expectedConversationFingerprint,
    });
  } catch (_error) {
    return null;
  }
  if (!validProbeEvent(event)) {
    return null;
  }
  return event;
}

function classifyProbe(request, event, successStatus) {
  if (!event || event.conversation_fingerprint !== request.conversation_fingerprint) {
    return receipt(request, "TARGET_CHANGED", event ? event.observation : unknownObservation());
  }
  if (!event.observation.exact_conversation_loaded) {
    return receipt(request, "TARGET_CHANGED", event.observation);
  }
  if (event.observation.auth_required === true) {
    return receipt(request, "AUTH_REQUIRED", event.observation);
  }
  if (event.observation.provider_error_present === true) {
    return receipt(request, "PROVIDER_ERROR", event.observation);
  }
  return receipt(request, successStatus, event.observation);
}

async function handleInspect(request) {
  const resolved = resolveExactTarget(request.conversation_fingerprint);
  if (resolved.status) {
    return receipt(request, resolved.status, unknownObservation());
  }
  const { tabId } = resolved;
  const event = await freshProbe(tabId, request.conversation_fingerprint);
  return classifyProbe(request, event, "INSPECTED");
}

async function handleForeground(request) {
  const resolved = resolveExactTarget(request.conversation_fingerprint);
  if (resolved.status) {
    return receipt(request, resolved.status, unknownObservation());
  }
  const { tabId, windowId } = resolved;

  const before = await freshProbe(tabId, request.conversation_fingerprint);
  const beforeReceipt = classifyProbe(request, before, "INSPECTED");
  if (beforeReceipt.status !== "INSPECTED") {
    return beforeReceipt;
  }

  try {
    await chrome.tabs.update(tabId, { active: true });
    await chrome.windows.update(windowId, { focused: true });
  } catch (_error) {
    return receipt(request, "UNKNOWN", before.observation);
  }

  const after = await freshProbe(tabId, request.conversation_fingerprint);
  return classifyProbe(request, after, "FOREGROUNDED_VERIFIED");
}

async function handleNativeRequest(request, port) {
  if (!validActionRequest(request)) {
    return;
  }
  const result = request.action === "INSPECT"
    ? await handleInspect(request)
    : request.action === "FOREGROUND"
      ? await handleForeground(request)
      : null;
  if (result) {
    port.postMessage(result);
  }
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
  const port = nativePort;
  port.onDisconnect.addListener(() => {
    if (nativePort === port) {
      nativePort = null;
    }
  });
  port.onMessage.addListener((request) => {
    handleNativeRequest(request, port).catch(() => undefined);
  });
  return nativePort;
}

chrome.runtime.onMessage.addListener((event, sender) => {
  if (!recordProbe(event, sender)) {
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

if (chrome.tabs && chrome.tabs.onRemoved) {
  chrome.tabs.onRemoved.addListener((tabId) => removeTabMapping(tabId));
}
