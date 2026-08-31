"use strict";

importScripts("instance_config.js");

const PROBE_KIND = "MMX_WEB_SOL_PROBE";
const REPROBE_KIND = "MMX_WEB_SOL_REPROBE";
const ACTION_SCHEMA = "mastermind.web_sol_surface_action.v1";
const RECEIPT_SCHEMA = "mastermind.web_sol_surface_receipt.v1";
const PROBE_SCHEMA = "mastermind.web_sol_surface_probe.v1";
const HELLO_SCHEMA = "mastermind.web_sol_transport_hello.v1";
const HELLO_ACK_SCHEMA = "mastermind.web_sol_transport_hello_ack.v1";
const INSTANCE_CONFIG_SCHEMA = "mastermind.web_sol_instance_config.v1";
const TRANSPORT_PROTOCOL_MAJOR = 1;
const PACKAGE_VERSION = "0.1.0";
const EXPECTED_CAPABILITY_DIGEST = "87276c884840bf14e3717a7249c07e6fff5ae09c591782dadadb05f9affa2d26";
const MAX_ACTION_TTL_MS = 60000;
const ALLOWED_FUTURE_SKEW_MS = 5000;

const OBSERVATION_KEYS = new Set([
  "schema", "target_present", "exact_conversation_loaded", "page_responsive",
  "document_ready_state", "visibility", "composer_available", "generation_state",
  "auth_required", "provider_error_present",
]);
const ACTION_KEYS = new Set([
  "schema", "binding_id", "conversation_fingerprint", "binding_fingerprint",
  "action", "operation_key", "issued_at", "expires_at", "nonce",
]);
const INSTANCE_CONFIG_KEYS = new Set([
  "schema", "instanceId", "nativeHost", "protocolMajor",
  "clientPackageVersion", "nativePackageVersion", "extensionPackageVersion",
  "capabilityDigest",
]);
const TRANSPORT_KEYS = new Set([
  "schema", "protocol_major", "role", "adapter_instance_id",
  "client_package_version", "native_package_version", "extension_package_version",
  "capability_digest", "boot_nonce", "challenge_nonce",
]);

const targets = new Map();
const tabFingerprints = new Map();
let nativePort = null;
let transportHandshakeReady = false;
let transportBootNonce = null;
let transportChallengeNonce = null;
let transportStage = "DISCONNECTED";

function exactKeys(object, allowed) {
  if (!object || typeof object !== "object" || Array.isArray(object)) return false;
  const keys = Object.keys(object);
  return keys.length === allowed.size && keys.every((key) => allowed.has(key));
}

function isHex64(value) {
  return typeof value === "string" && /^[0-9a-f]{64}$/.test(value);
}

function isNonce(value) {
  return typeof value === "string" && value.length >= 16 && value.length <= 128 && !/\s/.test(value);
}

function validInstanceConfig(value) {
  if (!exactKeys(value, INSTANCE_CONFIG_KEYS)) return false;
  if (value.schema !== INSTANCE_CONFIG_SCHEMA || value.protocolMajor !== TRANSPORT_PROTOCOL_MAJOR) return false;
  if (!isHex64(value.instanceId)) return false;
  const expectedNativeHost = `com.mastermind.web_sol_surface.${value.instanceId.slice(0, 24)}`;
  if (value.nativeHost !== expectedNativeHost) return false;
  for (const field of ["clientPackageVersion", "nativePackageVersion", "extensionPackageVersion"]) {
    if (value[field] !== PACKAGE_VERSION) return false;
  }
  return value.capabilityDigest === EXPECTED_CAPABILITY_DIGEST;
}

const rawInstanceConfig = globalThis.MMX_WEB_SOL_INSTANCE;
const INSTANCE_CONFIG = validInstanceConfig(rawInstanceConfig)
  ? Object.freeze({...rawInstanceConfig})
  : null;

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
    binding_fingerprint: request.binding_fingerprint,
    action: request.action, operation_key: request.operation_key, nonce: request.nonce,
    status, observed_at: new Date().toISOString(), observation,
  };
}

function foregroundEffectUnknown(request, observation) {
  return receipt(request, "FOREGROUND_EFFECT_UNKNOWN", observation || unknownObservation());
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
      kind: REPROBE_KIND,
      expected_conversation_fingerprint: expectedConversationFingerprint,
    });
    if (!validProbeEvent(event)) return null;
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
  if (!event.observation.target_present || !event.observation.exact_conversation_loaded) {
    return receipt(request, "TARGET_CHANGED", event.observation);
  }
  if (event.observation.auth_required === true) return receipt(request, "AUTH_REQUIRED", event.observation);
  if (event.observation.provider_error_present === true) return receipt(request, "PROVIDER_ERROR", event.observation);
  return receipt(request, successStatus, event.observation);
}

async function handleInspect(request) {
  const windowStatus = requestWindowStatus(request);
  if (windowStatus) return receipt(request, windowStatus, unknownObservation());
  const resolved = resolveExactTarget(request.conversation_fingerprint);
  if (resolved.status) return receipt(request, resolved.status, unknownObservation());
  const event = await freshProbe(resolved.tabId, request.conversation_fingerprint);
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
  windowStatus = requestWindowStatus(request);
  if (windowStatus) return receipt(request, windowStatus, before.observation);

  let windowId;
  try {
    await chrome.tabs.update(tabId, {active: true});
    const currentTab = await chrome.tabs.get(tabId);
    windowId = currentTab.windowId;
    if (!Number.isInteger(windowId)) return foregroundEffectUnknown(request, before.observation);
    await chrome.windows.update(windowId, {focused: true});
  } catch (_error) {
    return foregroundEffectUnknown(request, before.observation);
  }

  const after = await freshProbe(tabId, request.conversation_fingerprint);
  const afterReceipt = classifyProbe(request, after, "INSPECTED");
  if (afterReceipt.status !== "INSPECTED") {
    return foregroundEffectUnknown(request, after ? after.observation : before.observation);
  }
  try {
    const verifiedTab = await chrome.tabs.get(tabId);
    const verifiedWindow = await chrome.windows.get(windowId);
    const current = resolveExactTarget(request.conversation_fingerprint);
    if (current.status || current.tabId !== tabId || verifiedTab.active !== true ||
        verifiedTab.windowId !== windowId || verifiedWindow.id !== windowId ||
        verifiedWindow.focused !== true || after.observation.visibility !== "visible") {
      return foregroundEffectUnknown(request, after.observation);
    }
  } catch (_error) {
    return foregroundEffectUnknown(request, after.observation);
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

function randomChallengeNonce() {
  const bytes = new Uint8Array(24);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (value) => value.toString(16).padStart(2, "0")).join("");
}

function transportHello(bootNonce, challengeNonce) {
  return {
    schema: HELLO_SCHEMA,
    protocol_major: TRANSPORT_PROTOCOL_MAJOR,
    role: "extension",
    adapter_instance_id: INSTANCE_CONFIG.adapterInstanceId || INSTANCE_CONFIG.instanceId,
    client_package_version: INSTANCE_CONFIG.clientPackageVersion,
    native_package_version: INSTANCE_CONFIG.nativePackageVersion,
    extension_package_version: INSTANCE_CONFIG.extensionPackageVersion,
    capability_digest: INSTANCE_CONFIG.capabilityDigest,
    boot_nonce: bootNonce,
    challenge_nonce: challengeNonce,
  };
}

function validTransportAck(message) {
  if (!exactKeys(message, TRANSPORT_KEYS) || message.schema !== HELLO_ACK_SCHEMA) return false;
  if (message.protocol_major !== TRANSPORT_PROTOCOL_MAJOR || message.role !== "extension") return false;
  if (message.adapter_instance_id !== INSTANCE_CONFIG.instanceId) return false;
  if (message.client_package_version !== PACKAGE_VERSION ||
      message.native_package_version !== PACKAGE_VERSION ||
      message.extension_package_version !== PACKAGE_VERSION) return false;
  if (message.capability_digest !== INSTANCE_CONFIG.capabilityDigest) return false;
  return isNonce(message.boot_nonce) && isNonce(message.challenge_nonce);
}

function resetTransport(port) {
  if (nativePort === port) nativePort = null;
  transportHandshakeReady = false;
  transportBootNonce = null;
  transportChallengeNonce = null;
  transportStage = "DISCONNECTED";
}

function rejectTransport(port) {
  resetTransport(port);
  try {
    port.disconnect();
  } catch (_error) {
    return;
  }
}

function handleTransportAck(message, port) {
  if (!validTransportAck(message) || message.challenge_nonce !== transportChallengeNonce) {
    rejectTransport(port);
    return;
  }
  if (transportStage === "AWAITING_FIRST_ACK") {
    transportBootNonce = message.boot_nonce;
    const secondChallenge = randomChallengeNonce();
    if (secondChallenge === transportChallengeNonce) {
      rejectTransport(port);
      return;
    }
    transportChallengeNonce = secondChallenge;
    transportStage = "AWAITING_FINAL_ACK";
    port.postMessage(transportHello(transportBootNonce, secondChallenge));
    return;
  }
  if (transportStage !== "AWAITING_FINAL_ACK" || message.boot_nonce !== transportBootNonce) {
    rejectTransport(port);
    return;
  }
  transportStage = "READY";
  transportChallengeNonce = null;
  transportHandshakeReady = true;
}

function getNativePort() {
  if (!INSTANCE_CONFIG) return null;
  if (nativePort) return nativePort;
  try {
    nativePort = chrome.runtime.connectNative(INSTANCE_CONFIG.nativeHost);
  } catch (_error) {
    nativePort = null;
    return null;
  }
  const port = nativePort;
  transportHandshakeReady = false;
  transportBootNonce = null;
  transportChallengeNonce = randomChallengeNonce();
  transportStage = "AWAITING_FIRST_ACK";
  port.onDisconnect.addListener(() => resetTransport(port));
  port.onMessage.addListener((request) => {
    if (!transportHandshakeReady) {
      handleTransportAck(request, port);
      return;
    }
    handleNativeRequest(request, port).catch(() => undefined);
  });
  port.postMessage(transportHello(null, transportChallengeNonce));
  return nativePort;
}

chrome.runtime.onMessage.addListener((event, sender) => {
  if (!recordProbe(event, sender)) return;
  const port = getNativePort();
  if (!port || !transportHandshakeReady) return;
  port.postMessage({
    kind: PROBE_KIND,
    conversation_fingerprint: event.conversation_fingerprint,
    observation: event.observation,
  });
});

if (chrome.tabs && chrome.tabs.onRemoved) {
  chrome.tabs.onRemoved.addListener((tabId) => removeTabMapping(tabId));
}
