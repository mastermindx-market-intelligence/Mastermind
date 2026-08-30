"use strict";

const NATIVE_HOST = "com.mastermind.web_sol_surface";
const PROBE_KIND = "MMX_WEB_SOL_PROBE";
const REPROBE_KIND = "MMX_WEB_SOL_REPROBE";
const ACTION_SCHEMA = "mastermind.web_sol_surface_action.v1";
const RECEIPT_SCHEMA = "mastermind.web_sol_surface_receipt.v1";
const PROBE_SCHEMA = "mastermind.web_sol_surface_probe.v1";
const MAX_ACTION_TTL_MS = 60000;
const ALLOWED_FUTURE_SKEW_MS = 5000;

const OBSERVATION_KEYS = new Set([
  "schema", "target_present", "exact_conversation_loaded", "page_responsive",
  "document_ready_state", "visibility", "composer_available", "generation_state",
  "auth_required", "provider_error_present",
]);
const ACTION_KEYS = new Set([
  "schema", "binding_id", "conversation_fingerprint", "binding_fingerprint",
  "binding_revision", "action", "operation_key", "issued_at", "expires_at", "nonce",
]);

const targets = new Map();
const tabFingerprints = new Map();
let nativePort = null;

function exactKeys(object, allowed) {
  if (!object || typeof object !== "object" || Array.isArray(object)) return false;
  const keys = Object.keys(object);
  return keys.length === allowed.size && keys.every((key) => allowed.has(key));
}

function isHex64(value) {
  return typeof value === "string" && /^[0-9a-f]{64}$/.test(value);
}

function validProbeObservation(observation) {
  if (!exactKeys(observation, OBSERVATION_KEYS) || observation.schema !== PROBE_SCHEMA) return false;
  for (const field of ["target_present", "exact_conversation_loaded", "page_responsive"]) {
    if (typeof observation[field] !== "boolean") return false;
  }
  if (!["loading", "interactive", "complete"].includes(observation.document_ready_state)) return false;
  if (!["visible", "hidden"].includes(observation.visibility)) return false;
  if (!["active", "idle", "unknown"].includes(observation.generation_state)) return false;
  for (const field of ["composer_available", "auth_required", "provider_error_present"]) {
    if (observation[field] !== null && typeof observation[field] !== "boolean") return false;
  }
  return true;
}

function validProbeEvent(event) {
  if (!event || typeof event !== "object" || Array.isArray(event)) return false;
  if (event.kind !== PROBE_KIND) return false;
  if (event.conversation_fingerprint !== null && !isHex64(event.conversation_fingerprint)) return false;
  return validProbeObservation(event.observation);
}

function validActionRequest(request) {
  if (!exactKeys(request, ACTION_KEYS) || request.schema !== ACTION_SCHEMA) return false;
  if (request.action !== "INSPECT" && request.action !== "FOREGROUND") return false;
  if (!isHex64(request.conversation_fingerprint) || !isHex64(request.binding_fingerprint)) return false;
  if (typeof request.binding_id !== "string" ||
      !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(request.binding_id)) return false;
  if (typeof request.operation_key !== "string" || !request.operation_key ||
      request.operation_key.length > 256 || /\s/.test(request.operation_key)) return false;
  if (typeof request.nonce !== "string" || request.nonce.length < 16 ||
      request.nonce.length > 128 || /\s/.test(request.nonce)) return false;
  if (!Number.isSafeInteger(request.binding_revision) || request.binding_revision < 0) return false;
  return typeof request.issued_at === "string" && typeof request.expires_at === "string";
}

function requestWindowStatus(request, nowMs = Date.now()) {
  if (!request.issued_at.endsWith("Z") || !request.expires_at.endsWith("Z")) return "REQUEST_WINDOW_INVALID";
  const issued = Date.parse(request.issued_at);
  const expires = Date.parse(request.expires_at);
  if (!Number.isFinite(nowMs) || !Number.isFinite(issued) || !Number.isFinite(expires) || expires <= issued) {
    return "REQUEST_WINDOW_INVALID";
  }
  if (expires <= nowMs) return "REQUEST_EXPIRED";
  if (issued > nowMs + ALLOWED_FUTURE_SKEW_MS) return "REQUEST_NOT_YET_VALID";
  if (expires - issued > MAX_ACTION_TTL_MS) return "REQUEST_WINDOW_INVALID";
  return null;
}

function removeTabMapping(tabId) {
  const previous = tabFingerprints.get(tabId);
  if (!previous) return;
  tabFingerprints.delete(tabId);
  const entries = targets.get(previous);
  if (!entries) return;
  entries.delete(tabId);
  if (entries.size === 0) targets.delete(previous);
}

function recordProbe(event, sender) {
  if (!validProbeEvent(event) || !sender || !sender.tab) return false;
  if (sender.frameId !== undefined && sender.frameId !== 0) return false;
  if (sender.id !== undefined && sender.id !== chrome.runtime.id) return false;
  const tabId = sender.tab.id;
  const windowId = sender.tab.windowId;
  if (!Number.isInteger(tabId) || !Number.isInteger(windowId)) return false;
  removeTabMapping(tabId);
  if (!event.conversation_fingerprint || !event.observation.target_present) return true;
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
    schema: PROBE_SCHEMA, target_present: false, exact_conversation_loaded: false,
    page_responsive: false, document_ready_state: "loading", visibility: "hidden",
    composer_available: null, generation_state: "unknown", auth_required: null,
    provider_error_present: null,
  };
}

function receipt(request, status, observation) {
  return {
    schema: RECEIPT_SCHEMA, binding_id: request.binding_id,
    conversation_fingerprint: request.conversation_fingerprint,
    binding_fingerprint: request.binding_fingerprint, binding_revision: request.binding_revision,
    action: request.action, operation_key: request.operation_key, nonce: request.nonce,
    status, observed_at: new Date().toISOString(), observation,
  };
}

function resolveExactTarget(conversationFingerprint) {
  const entries = targets.get(conversationFingerprint);
  if (!entries || entries.size === 0) return {status: "TARGET_NOT_FOUND"};
  if (entries.size !== 1) return {status: "AMBIGUOUS_TARGET"};
  const [entry] = entries.entries();
  const [tabId, windowId] = entry;
  return {status: null, tabId, windowId};
}

async function freshProbe(tabId, expectedConversationFingerprint) {
  let event;
  try {
    event = await chrome.tabs.sendMessage(tabId, {
      kind: "MMX_WEB_SOL_REPROBE",
      expected_conversation_fingerprint: expectedConversationFingerprint,
    });
    if (!validProbeEvent(event)) return null;
    // A route change is new navigation evidence, not a reason to strand this
    // tab forever under its previous conversation fingerprint.
    const tab = await chrome.tabs.get(tabId);
    if (!recordProbe(event, {tab})) return null;
  } catch (_error) {
    removeTabMapping(tabId);
    return null;
  }
  return event;
}

function classifyProbe(request, event, successStatus) {
  if (!event || event.conversation_fingerprint !== request.conversation_fingerprint) {
    return receipt(request, "TARGET_CHANGED", event ? event.observation : unknownObservation());
  }
  if (!event.observation.exact_conversation_loaded) return receipt(request, "TARGET_CHANGED", event.observation);
  if (event.observation.auth_required === true) return receipt(request, "AUTH_REQUIRED", event.observation);
  if (event.observation.provider_error_present === true) return receipt(request, "PROVIDER_ERROR", event.observation);
  return receipt(request, successStatus, event.observation);
}

async function handleInspect(request) {
  const windowStatus = requestWindowStatus(request);
  if (windowStatus) return receipt(request, windowStatus, unknownObservation());
  const resolved = resolveExactTarget(request.conversation_fingerprint);
  if (resolved.status) return receipt(request, resolved.status, unknownObservation());
  const {tabId} = resolved;
  const event = await freshProbe(tabId, request.conversation_fingerprint);
  return classifyProbe(request, event, "INSPECTED");
}

async function handleForeground(request) {
  let windowStatus = requestWindowStatus(request);
  if (windowStatus) return receipt(request, windowStatus, unknownObservation());
  const resolved = resolveExactTarget(request.conversation_fingerprint);
  if (resolved.status) return receipt(request, resolved.status, unknownObservation());
  const {tabId} = resolved;

  const before = await freshProbe(tabId, request.conversation_fingerprint);
  const beforeReceipt = classifyProbe(request, before, "INSPECTED");
  if (beforeReceipt.status !== "INSPECTED") return beforeReceipt;
  const currentTarget = resolveExactTarget(request.conversation_fingerprint);
  if (currentTarget.status || currentTarget.tabId !== tabId) {
    return receipt(request, currentTarget.status || "TARGET_CHANGED", before.observation);
  }
  // Admission is checked again after asynchronous observation, immediately
  // before the first browser effect. A valid request can expire while probing.
  windowStatus = requestWindowStatus(request);
  if (windowStatus) return receipt(request, windowStatus, before.observation);

  let windowId;
  try {
    await chrome.tabs.update(tabId, {active: true});
    const currentTab = await chrome.tabs.get(tabId);
    windowId = currentTab.windowId;
    if (!Number.isInteger(windowId)) return receipt(request, "UNKNOWN", before.observation);
    await chrome.windows.update(windowId, {focused: true});
  } catch (_error) {
    return receipt(request, "UNKNOWN", before.observation);
  }

  const after = await freshProbe(tabId, request.conversation_fingerprint);
  const afterReceipt = classifyProbe(request, after, "INSPECTED");
  if (afterReceipt.status !== "INSPECTED") return afterReceipt;
  try {
    const verifiedTab = await chrome.tabs.get(tabId);
    const verifiedWindow = await chrome.windows.get(windowId);
    const current = resolveExactTarget(request.conversation_fingerprint);
    if (current.status || current.tabId !== tabId || verifiedTab.active !== true ||
        verifiedTab.windowId !== windowId || verifiedWindow.id !== windowId ||
        verifiedWindow.focused !== true || after.observation.visibility !== "visible") {
      return receipt(request, "UNKNOWN", after.observation);
    }
  } catch (_error) {
    return receipt(request, "UNKNOWN", after.observation);
  }
  return receipt(request, "FOREGROUNDED_VERIFIED", after.observation);
}

async function handleNativeRequest(request, port) {
  if (!validActionRequest(request)) return;
  const accepted = Object.freeze({...request});
  const windowStatus = requestWindowStatus(accepted);
  if (windowStatus) {
    port.postMessage(receipt(accepted, windowStatus, unknownObservation()));
    return;
  }
  const result = accepted.action === "INSPECT"
    ? await handleInspect(accepted)
    : accepted.action === "FOREGROUND" ? await handleForeground(accepted) : null;
  if (result) port.postMessage(result);
}

function getNativePort() {
  if (nativePort) return nativePort;
  try {
    nativePort = chrome.runtime.connectNative(NATIVE_HOST);
  } catch (_error) {
    nativePort = null;
    return null;
  }
  const port = nativePort;
  port.onDisconnect.addListener(() => {
    if (nativePort === port) nativePort = null;
  });
  port.onMessage.addListener((request) => {
    handleNativeRequest(request, port).catch(() => undefined);
  });
  return nativePort;
}

chrome.runtime.onMessage.addListener((event, sender) => {
  if (!recordProbe(event, sender)) return;
  const port = getNativePort();
  if (!port) return;
  port.postMessage({kind: PROBE_KIND, conversation_fingerprint: event.conversation_fingerprint,
                    observation: event.observation});
});

if (chrome.tabs && chrome.tabs.onRemoved) {
  chrome.tabs.onRemoved.addListener((tabId) => removeTabMapping(tabId));
}
