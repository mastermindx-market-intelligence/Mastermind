"use strict";

importScripts("instance_config.js");
importScripts("census_core.js");
importScripts("continuation_core.js");

const K = globalThis.MMXWebSolContinuation;
const PROBE_KIND = "MMX_WEB_SOL_PROBE";
const REPROBE_KIND = "MMX_WEB_SOL_REPROBE";
const ACTION_SCHEMA = "mastermind.web_sol_surface_action.v1";
const RECEIPT_SCHEMA = "mastermind.web_sol_surface_receipt.v1";
const PROBE_SCHEMA = "mastermind.web_sol_surface_probe.v1";
const HELLO_SCHEMA = "mastermind.web_sol_transport_hello.v1";
const HELLO_ACK_SCHEMA = "mastermind.web_sol_transport_hello_ack.v1";
const INSTANCE_CONFIG_SCHEMA = "mastermind.web_sol_instance_config.v1";
const TRANSPORT_PROTOCOL_MAJOR = 1;
const PACKAGE_VERSION = "0.5.0";
const EXPECTED_CAPABILITY_DIGEST = "f82f3a7d3e6b85771348df5f422dc5a0c0a8a9fd19835415516fc66e03c51a5f";
const MAX_ACTION_TTL_MS = 60000;
const ALLOWED_FUTURE_SKEW_MS = 5000;
const CHATGPT_TAB_PATTERNS = Object.freeze([
  "https://chat.openai.com/*",
  "https://chatgpt.com/*",
]);
const RECONNECT_ALARM_PREFIX = "mmx-web-sol-native-reconnect-v1-";
const HANDSHAKE_ALARM_PREFIX = "mmx-web-sol-native-handshake-v1-";
const RECONNECT_DELAYS_MINUTES = Object.freeze([1, 5, 15]);
const HANDSHAKE_TIMEOUT_MINUTES = 0.5;
const CONTINUATION_ACK_RESULT_SCHEMA = "mastermind.web_sol_continuation_ack_result.v1";
const CONTINUATION_ACK_OBSERVE_KIND = "MMX_WEB_SOL_OBSERVE_CONTINUATION_ACK";

const OBSERVATION_KEYS = new Set([
  "schema", "target_present", "exact_conversation_loaded", "page_responsive",
  "document_ready_state", "visibility", "composer_available", "generation_state",
  "auth_required", "provider_error_present",
]);
const ACTION_KEYS = new Set([
  "schema", "binding_id", "conversation_fingerprint", "binding_fingerprint",
  "action", "operation_key", "issued_at", "expires_at", "nonce",
]);
const TYPED_REENTRY_KEYS = new Set([...ACTION_KEYS, "operation_id", "result_digest", "obligation_digest"]);
const SEMANTIC_CONTENT_RESULT_KEYS = new Set([
  "schema", "conversation_fingerprint", "turn_id", "directive_digest",
  "session_alias", "runtime_binding_id", "runtime_binding_generation",
  "runtime_binding_fingerprint", "wake_obligation_ids",
  "wake_obligation_digest", "provider_native_turn_id",
  "acknowledged_obligation_ids", "terminal_ack_trailer",
  "document_epoch", "status",
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
let reconnectEpoch = null;
let reconnectGenerationOpen = false;
let nativePortEpoch = null;
let nativePortReconnectAttempt = null;
let nativePortToken = null;
let nextNativePortToken = 0;
let activeHandshakeAlarmName = null;

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

function validTurnId(value) {
  return typeof value === "string" && /^[A-Za-z0-9][A-Za-z0-9._:/-]{2,255}$/.test(value);
}

function validDocumentEpoch(value) {
  return typeof value === "string" && /^[0-9a-f]{32}$/.test(value);
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
  if (event.document_epoch !== undefined && !validDocumentEpoch(event.document_epoch)) return false;
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

function validTypedReentryRequest(request) {
  if (!exactKeys(request, TYPED_REENTRY_KEYS) || request.schema !== ACTION_SCHEMA) return false;
  if (request.action !== "TYPED_REENTRY") return false;
  const foreground = {};
  for (const key of ["schema", "binding_id", "conversation_fingerprint", "binding_fingerprint",
    "operation_key", "issued_at", "expires_at", "nonce"]) foreground[key] = request[key];
  foreground.action = "FOREGROUND";
  if (!validActionRequest(foreground)) return false;
  return isHex64(request.operation_id) && isHex64(request.result_digest) &&
    isHex64(request.obligation_digest);
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

function removeTabMapping(tabId, dropState = true) {
  const previous = tabFingerprints.get(tabId);
  if (!previous) return;
  if (previous.fingerprint) {
    const entries = targets.get(previous.fingerprint);
    if (entries) {
      entries.delete(tabId);
      if (entries.size === 0) targets.delete(previous.fingerprint);
    }
  }
  if (dropState) {
    tabFingerprints.delete(tabId);
  } else {
    tabFingerprints.set(tabId, {
      fingerprint: null,
      navigationGeneration: previous.navigationGeneration,
      documentEpoch: null,
      window: null,
    });
  }
}

function advanceTabNavigationGeneration(tabId) {
  if (!Number.isInteger(tabId)) return null;
  const previous = tabFingerprints.get(tabId) || {
    fingerprint: null,
    navigationGeneration: 0,
    documentEpoch: null,
    window: null,
  };
  removeTabMapping(tabId, false);
  const navigationGeneration = previous.navigationGeneration + 1;
  tabFingerprints.set(tabId, {
    fingerprint: null,
    navigationGeneration,
    documentEpoch: null,
    window: null,
  });
  return navigationGeneration;
}

function recordProbe(event, sender) {
  if (!validProbeEvent(event) || !sender || !sender.tab) return false;
  if (sender.frameId !== undefined && sender.frameId !== 0) return false;
  if (sender.id !== undefined && sender.id !== chrome.runtime.id) return false;
  const tabId = sender.tab.id;
  const windowId = sender.tab.windowId;
  if (!Number.isInteger(tabId) || !Number.isInteger(windowId)) return false;
  const previous = tabFingerprints.get(tabId) || {
    fingerprint: null,
    navigationGeneration: 0,
    documentEpoch: null,
    window: null,
  };
  removeTabMapping(tabId, false);
  const documentEpoch = validDocumentEpoch(event.document_epoch)
    ? event.document_epoch
    : null;
  const state = {
    fingerprint: null,
    navigationGeneration: previous.navigationGeneration,
    documentEpoch,
    window: windowId,
  };
  if (!event.conversation_fingerprint || !event.observation.target_present) {
    tabFingerprints.set(tabId, state);
    return true;
  }
  state.fingerprint = event.conversation_fingerprint;
  let entries = targets.get(event.conversation_fingerprint);
  if (!entries) {
    entries = new Map();
    targets.set(event.conversation_fingerprint, entries);
  }
  entries.set(tabId, windowId);
  tabFingerprints.set(tabId, state);
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

function receipt(request, status, observation, semantic = null) {
  const result = {
    schema: RECEIPT_SCHEMA, binding_id: request.binding_id,
    conversation_fingerprint: request.conversation_fingerprint,
    binding_fingerprint: request.binding_fingerprint,
    action: request.action, operation_key: request.operation_key, nonce: request.nonce,
    status, observed_at: new Date().toISOString(), observation,
  };
  if (request.action === "TYPED_REENTRY") {
    result.operation_id = request.operation_id;
    result.result_digest = request.result_digest;
    result.obligation_digest = request.obligation_digest;
  }
  if (["SUBMIT_CONTINUATION", "OBSERVE_CONTINUATION_ACK"].includes(request.action)) {
    for (const key of K.correlationKeys) {
      result[key] = key === "wake_obligation_ids" ? [...request[key]] : request[key];
    }
  }
  if (request.action === "OBSERVE_CONTINUATION_ACK") {
    result.provider_native_turn_id = semantic?.provider_native_turn_id ?? null;
    result.acknowledged_obligation_ids = semantic?.acknowledged_obligation_ids
      ? [...semantic.acknowledged_obligation_ids] : [];
    result.terminal_ack_trailer = semantic?.terminal_ack_trailer === true;
  }
  return result;
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
  const state = tabFingerprints.get(tabId);
  if (!Number.isInteger(windowId) || !state ||
      state.fingerprint !== conversationFingerprint || state.window !== windowId ||
      !Number.isSafeInteger(state.navigationGeneration) ||
      state.navigationGeneration < 0) return {status: "TARGET_NOT_FOUND"};
  const navigationGeneration = state.navigationGeneration;
  const documentEpoch = state.documentEpoch;
  return {status: null, tabId, windowId, navigationGeneration, documentEpoch};
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
    removeTabMapping(tabId, false);
    return null;
  }
  return event;
}

async function refreshTabMapping(tabId) {
  if (!Number.isInteger(tabId)) return;
  removeTabMapping(tabId, false);
  await freshProbe(tabId, null);
}

async function hydrateTargets() {
  targets.clear();
  tabFingerprints.clear();
  if (!chrome.tabs || typeof chrome.tabs.query !== "function") return;
  let openTabs;
  try {
    openTabs = await chrome.tabs.query({url: CHATGPT_TAB_PATTERNS});
  } catch (_error) {
    return;
  }
  if (!Array.isArray(openTabs)) return;
  openTabs
    .filter((tab) => tab && Number.isInteger(tab.id))
    .sort((left, right) => left.id - right.id);
  for (const tab of openTabs) {
    if (!tab || !Number.isInteger(tab.id)) continue;
    await refreshTabMapping(tab.id);
  }
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

const typedReentryEffects = [];

function typedReentryBlocker(request, status = "TYPED_REENTRY_BLOCKED") {
  return receipt(request, status, unknownObservation());
}

async function handleTypedReentry(request) {
  if (typedReentryEffects.some((effect) => effect.nonce === request.nonce)) {
    return typedReentryBlocker(request);
  }
  const resolved = resolveExactTarget(request.conversation_fingerprint);
  if (resolved.status) return typedReentryBlocker(request, resolved.status);
  const before = await freshProbe(resolved.tabId, request.conversation_fingerprint);
  if (!before || before.conversation_fingerprint !== request.conversation_fingerprint) {
    return receipt(request, "CONVERSATION_CLOSED", unknownObservation());
  }
  if (before.observation.composer_available !== true || before.observation.generation_state !== "idle") {
    return receipt(request, "NOT_CONSUMED", before.observation);
  }
  const result = await handleForeground(request);
  if (result.status !== "FOREGROUNDED_VERIFIED") return typedReentryBlocker(request);
  typedReentryEffects.push({
    conversation_fingerprint: request.conversation_fingerprint,
    operation_id: request.operation_id,
    nonce: request.nonce,
  });
  return receipt(request, "CONSUMED", result.observation);
}

function validSubmitContinuationRequest(request) {
  return request?.action === "SUBMIT_CONTINUATION" && K?.validRequest(request) === true;
}
function validObserveContinuationAckRequest(request) {
  return request?.action === "OBSERVE_CONTINUATION_ACK" && K?.validRequest(request) === true;
}
async function handleSubmitContinuation(request) {
  const outcome = await K.handle(request, {resolveExactTarget, freshProbe,
    requestWindowStatus, unknownObservation, sendMessage: (i, v) => chrome.tabs.sendMessage(i, v, {frameId: 0})});
  return receipt(request, outcome.status, outcome.observation || unknownObservation());
}

function semanticContentRequest(request) {
  return {
    kind: CONTINUATION_ACK_OBSERVE_KIND,
    expected_conversation_fingerprint: request.conversation_fingerprint,
    turn_id: request.turn_id,
    directive_digest: request.directive_digest,
    session_alias: request.session_alias,
    runtime_binding_id: request.runtime_binding_id,
    runtime_binding_generation: request.runtime_binding_generation,
    runtime_binding_fingerprint: request.runtime_binding_fingerprint,
    wake_obligation_ids: [...request.wake_obligation_ids],
    wake_obligation_digest: request.wake_obligation_digest,
  };
}


function sameStringArray(left, right) {
  return Array.isArray(left) && Array.isArray(right) &&
    left.length === right.length && left.every((value, index) => value === right[index]);
}

function validSemanticContentResult(value, request) {
  if (!exactKeys(value, SEMANTIC_CONTENT_RESULT_KEYS) ||
      value.schema !== CONTINUATION_ACK_RESULT_SCHEMA ||
      !["CONTINUATION_ACKNOWLEDGED", "CONTINUATION_ACK_PENDING",
        "CONTINUATION_ACK_REFUSED"].includes(value.status)) return false;
  for (const key of [
    "conversation_fingerprint", "turn_id", "directive_digest", "session_alias",
    "runtime_binding_id", "runtime_binding_generation", "runtime_binding_fingerprint",
    "wake_obligation_digest",
  ]) {
    if (value[key] !== request[key]) return false;
  }
  if (!sameStringArray(value.wake_obligation_ids, request.wake_obligation_ids) ||
      typeof value.document_epoch !== "string" || !/^[0-9a-f]{32}$/.test(value.document_epoch) ||
      typeof value.terminal_ack_trailer !== "boolean") return false;
  if (value.status === "CONTINUATION_ACKNOWLEDGED") {
    return validTurnId(value.provider_native_turn_id) &&
      sameStringArray(value.acknowledged_obligation_ids, request.wake_obligation_ids) &&
      value.terminal_ack_trailer === true;
  }
  return value.provider_native_turn_id === null &&
    sameStringArray(value.acknowledged_obligation_ids, []) &&
    value.terminal_ack_trailer === false;
}

function semanticProbeEligible(event, request) {
  return event && event.conversation_fingerprint === request.conversation_fingerprint &&
    validDocumentEpoch(event.document_epoch) &&
    event.observation.target_present && event.observation.exact_conversation_loaded &&
    event.observation.auth_required !== true &&
    event.observation.provider_error_present !== true;
}

function sameSemanticTarget(left, right) {
  return left && right && !left.status && !right.status &&
    left.tabId === right.tabId &&
    left.navigationGeneration === right.navigationGeneration &&
    left.documentEpoch === right.documentEpoch;
}

async function handleObserveContinuationAck(request) {
  const resolved = resolveExactTarget(request.conversation_fingerprint);
  if (resolved.status) return receipt(request, resolved.status, unknownObservation());
  const before = await freshProbe(resolved.tabId, request.conversation_fingerprint);
  const bound = resolveExactTarget(request.conversation_fingerprint);
  if (!semanticProbeEligible(before, request) ||
      bound.status || bound.tabId !== resolved.tabId ||
      bound.documentEpoch !== before.document_epoch) {
    return receipt(
      request,
      "CONTINUATION_ACK_REFUSED",
      before ? before.observation : unknownObservation(),
    );
  }
  let semantic;
  try {
    semantic = await chrome.tabs.sendMessage(
      bound.tabId,
      semanticContentRequest(request),
      {frameId: 0},
    );
  } catch (_error) {
    return receipt(request, "CONTINUATION_ACK_REFUSED", before.observation);
  }
  if (!validSemanticContentResult(semantic, request) ||
      semantic.document_epoch !== bound.documentEpoch) {
    return receipt(request, "CONTINUATION_ACK_REFUSED", before.observation);
  }
  const current = resolveExactTarget(request.conversation_fingerprint);
  if (!sameSemanticTarget(current, bound) || requestWindowStatus(request)) {
    return receipt(request, "CONTINUATION_ACK_REFUSED", before.observation);
  }
  const after = await freshProbe(bound.tabId, request.conversation_fingerprint);
  const finalTarget = resolveExactTarget(request.conversation_fingerprint);
  if (!semanticProbeEligible(after, request) ||
      after.document_epoch !== bound.documentEpoch ||
      !sameSemanticTarget(finalTarget, bound)) {
    return receipt(
      request,
      "CONTINUATION_ACK_REFUSED",
      after ? after.observation : unknownObservation(),
    );
  }
  return receipt(request, semantic.status, after.observation, semantic);
}

const CENSUS_REQUEST_SCHEMA = "mastermind.web_sol_census_request.v1";
const CENSUS_RECEIPT_SCHEMA = "mastermind.web_sol_census_receipt.v1";
const CENSUS_HEADERS = Object.freeze(["schema", "scope", "adapter_instance_id", "started_at", "completed_at",
  "duration_ms", "inventory_coverage", "consistency", "reason", "initial_tab_count", "final_tab_count",
  "excluded_private_count", "omitted_tab_count", "unobserved_added_count", "unique_conversation_count",
  "duplicate_tab_count", "probed_tab_count", "generation_cue_count", "unknown_cue_count", "probe_coverage"]);
const CENSUS_ROWS = Object.freeze(["slot", "conversation_fingerprint", "identity_evidence", "document_binding",
  "status", "generation_cue", "selected_in_window", "discarded", "frozen", "visibility", "auth_required",
  "provider_error_present", "duplicate_count", "duplicate_cue_disagreement", "observed_at",
  "selected_model", "selected_effort", "served_model", "model_evidence"]);
const CENSUS_KEYS = new Set(["schema", "adapter_instance_id", "operation_key", "nonce", "issued_at", "expires_at"]);
function validCensusCorrelation(value, minimum, maximum) {
  // Match Python str length/isspace exactly for this sibling protocol. Legacy
  // handshake/action nonce grammar remains with isNonce above.
  return typeof value === "string" && Array.from(value).length >= minimum &&
    Array.from(value).length <= maximum &&
    !/[\u0009-\u000d\u001c-\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]/.test(value);
}
function validCensusRequest(request) {
  return exactKeys(request, CENSUS_KEYS) && request.schema === CENSUS_REQUEST_SCHEMA && INSTANCE_CONFIG &&
    request.adapter_instance_id === INSTANCE_CONFIG.instanceId && validCensusCorrelation(request.nonce, 16, 128) &&
    validCensusCorrelation(request.operation_key, 1, 256) &&
    [request.issued_at, request.expires_at].every(v => typeof v === "string" &&
      /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{3})?Z$/.test(v)) &&
    Number.isFinite(Date.parse(request.issued_at)) && Number.isFinite(Date.parse(request.expires_at)) &&
    Date.parse(request.expires_at) > Date.parse(request.issued_at) &&
    Date.parse(request.expires_at) - Date.parse(request.issued_at) <= 10000;
}
function packCensus(snapshot) {
  if (!exactKeys(snapshot, new Set([...CENSUS_HEADERS, "rows"])) ||
      snapshot.schema !== "mastermind.web_sol_local_census.v1" ||
      snapshot.adapter_instance_id !== INSTANCE_CONFIG.instanceId ||
      !Array.isArray(snapshot.rows) || snapshot.rows.length > 128 ||
      !snapshot.rows.every(r => exactKeys(r, new Set(CENSUS_ROWS)) &&
        r.selected_model === null && r.selected_effort === null && r.served_model === null &&
        r.document_binding === "UNVERIFIED" && r.model_evidence === "UNVERIFIED")) throw Error("INVALID_OBSERVATION");
  return {schema: "mastermind.web_sol_census_table.v1",
    header: CENSUS_HEADERS.map(k => snapshot[k]), rows: snapshot.rows.map(r => CENSUS_ROWS.map(k => r[k]))};
}
function censusReceipt(request, status, snapshot = null) {
  return {schema: CENSUS_RECEIPT_SCHEMA, adapter_instance_id: request.adapter_instance_id,
    operation_key: request.operation_key, nonce: request.nonce, status, snapshot};
}
async function handleCensusRequest(request, port) {
  if (!validCensusRequest(request)) return;
  const accepted = Object.freeze({...request});
  const token = nativePortToken, boot = transportBootNonce;
  if (nativePort !== port || !transportHandshakeReady || !boot) return;
  const ms = Math.min(10000, Date.parse(accepted.expires_at) - Date.now());
  if (ms <= 0 || Date.parse(accepted.issued_at) > Date.now()+5000) {
    port.postMessage(censusReceipt(accepted, "READ_DEADLINE_EXCEEDED")); return;
  }
  const deadline = performance.now()+ms;
  let result;
  try {
    // One stable API object and collector realm own pending-read backpressure.
    const snapshot = await globalThis.MMXWebSolCensus.collect(
      chrome.tabs, INSTANCE_CONFIG.instanceId, deadline);
    result = snapshot.reason === "ADAPTER_UNCONFIGURED" ? censusReceipt(accepted, "COLLECTOR_UNAVAILABLE") :
      censusReceipt(accepted, "COLLECTED", packCensus(snapshot));
    if (new TextEncoder().encode(JSON.stringify(result)).length > 61440)
      result = censusReceipt(accepted, "RESULT_TOO_LARGE");
  } catch (_) { result = censusReceipt(accepted, "INVALID_OBSERVATION"); }
  // A completed or timed-out old operation cannot write to either port generation.
  if (nativePort !== port || nativePortToken !== token || transportBootNonce !== boot ||
      !transportHandshakeReady || performance.now() >= deadline) return;
  port.postMessage(result);
}
function validCensusPopup(event, sender) {
  return INSTANCE_CONFIG && exactKeys(event, new Set(["kind"])) && event.kind === "MMX_WEB_SOL_CENSUS_REFRESH" &&
    sender && sender.id === chrome.runtime.id && !Object.prototype.hasOwnProperty.call(sender, "tab") &&
    sender.url === chrome.runtime.getURL("census.html") &&
    sender.origin === `chrome-extension://${chrome.runtime.id}`;
}

async function handleNativeRequest(request, port) {
  if (request && request.schema === CENSUS_REQUEST_SCHEMA) return handleCensusRequest(request, port);
  const typedReentry = validTypedReentryRequest(request);
  const submitContinuation = validSubmitContinuationRequest(request);
  const observeContinuationAck = validObserveContinuationAckRequest(request);
  if (!typedReentry && !submitContinuation && !observeContinuationAck &&
      !validActionRequest(request)) return;
  const accepted = Object.freeze({...request});
  const windowStatus = requestWindowStatus(accepted);
  if (windowStatus) {
    port.postMessage(receipt(accepted, windowStatus, unknownObservation()));
    return;
  }
  const result = accepted.action === "INSPECT"
    ? await handleInspect(accepted)
    : accepted.action === "FOREGROUND" ? await handleForeground(accepted)
    : typedReentry ? await handleTypedReentry(accepted)
    : submitContinuation ? await handleSubmitContinuation(accepted)
    : observeContinuationAck ? await handleObserveContinuationAck(accepted) : null;
  if (result) port.postMessage(result);
  return result;
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

function validReconnectEpoch(value) {
  return typeof value === "string" && /^[0-9a-f]{48}$/.test(value);
}

function beginReconnectGeneration() {
  reconnectEpoch = randomChallengeNonce();
  reconnectGenerationOpen = true;
  return reconnectEpoch;
}

function reconnectAlarmName(epoch, index) {
  return `${RECONNECT_ALARM_PREFIX}${epoch}-${index}`;
}

function reconnectAlarmIdentity(name) {
  if (typeof name !== "string" || !name.startsWith(RECONNECT_ALARM_PREFIX)) return null;
  const suffix = name.slice(RECONNECT_ALARM_PREFIX.length);
  const match = /^([0-9a-f]{48})-([0-9]+)$/.exec(suffix);
  if (!match) return null;
  const index = Number(match[2]);
  if (!validReconnectEpoch(match[1]) || !Number.isSafeInteger(index) ||
      index < 0 || index >= RECONNECT_DELAYS_MINUTES.length) return null;
  return {epoch: match[1], index};
}

function handshakeAlarmName(epoch, token) {
  return `${HANDSHAKE_ALARM_PREFIX}${epoch}-${token}`;
}

function handshakeAlarmIdentity(name) {
  if (typeof name !== "string" || !name.startsWith(HANDSHAKE_ALARM_PREFIX)) return null;
  const suffix = name.slice(HANDSHAKE_ALARM_PREFIX.length);
  const match = /^([0-9a-f]{48})-([0-9]+)$/.exec(suffix);
  if (!match) return null;
  const token = Number(match[2]);
  if (!validReconnectEpoch(match[1]) || !Number.isSafeInteger(token) || token < 1) return null;
  return {epoch: match[1], token};
}

function scheduleReconnect(epoch, index) {
  if (!INSTANCE_CONFIG || !chrome.alarms || typeof chrome.alarms.create !== "function") return;
  if (epoch !== reconnectEpoch || !reconnectGenerationOpen) return;
  if (!Number.isSafeInteger(index) || index < 0) return;
  if (index >= RECONNECT_DELAYS_MINUTES.length) {
    reconnectGenerationOpen = false;
    return;
  }
  chrome.alarms.create(reconnectAlarmName(epoch, index), {
    delayInMinutes: RECONNECT_DELAYS_MINUTES[index],
  });
}

async function clearReconnectAlarms(epoch) {
  if (!chrome.alarms || typeof chrome.alarms.clear !== "function") return;
  await Promise.all(
    RECONNECT_DELAYS_MINUTES.map((_delay, index) =>
      chrome.alarms.clear(reconnectAlarmName(epoch, index)).catch(() => false),
    ),
  );
}

function armHandshakeTimeout(epoch, token) {
  if (!chrome.alarms || typeof chrome.alarms.create !== "function") return;
  const name = handshakeAlarmName(epoch, token);
  activeHandshakeAlarmName = name;
  chrome.alarms.create(name, {delayInMinutes: HANDSHAKE_TIMEOUT_MINUTES});
}

function clearHandshakeTimeout(epoch, token) {
  const name = handshakeAlarmName(epoch, token);
  if (activeHandshakeAlarmName === name) activeHandshakeAlarmName = null;
  if (!chrome.alarms || typeof chrome.alarms.clear !== "function") return;
  chrome.alarms.clear(name).catch(() => false);
}

function resetTransport(port) {
  if (nativePort !== port) return false;
  const epoch = nativePortEpoch;
  const token = nativePortToken;
  nativePort = null;
  transportHandshakeReady = false;
  transportBootNonce = null;
  transportChallengeNonce = null;
  transportStage = "DISCONNECTED";
  nativePortEpoch = null;
  nativePortReconnectAttempt = null;
  nativePortToken = null;
  if (validReconnectEpoch(epoch) && Number.isSafeInteger(token)) {
    clearHandshakeTimeout(epoch, token);
  } else {
    activeHandshakeAlarmName = null;
  }
  return true;
}

function rejectTransport(port, epoch, reconnectAttempt) {
  const wasCurrent = nativePort === port && nativePortEpoch === epoch;
  if (!wasCurrent || !resetTransport(port)) return;
  try {
    port.disconnect();
  } catch (_error) {
    // The state is already reset; reconnect remains bounded below.
  }
  scheduleReconnect(epoch, reconnectAttempt + 1);
}

function handleTransportAck(message, port, epoch, reconnectAttempt, token) {
  if (nativePort !== port || nativePortEpoch !== epoch || nativePortToken !== token) return;
  if (!validTransportAck(message) || message.challenge_nonce !== transportChallengeNonce) {
    rejectTransport(port, epoch, reconnectAttempt);
    return;
  }
  if (transportStage === "AWAITING_FIRST_ACK") {
    transportBootNonce = message.boot_nonce;
    const secondChallenge = randomChallengeNonce();
    if (secondChallenge === transportChallengeNonce) {
      rejectTransport(port, epoch, reconnectAttempt);
      return;
    }
    transportChallengeNonce = secondChallenge;
    transportStage = "AWAITING_FINAL_ACK";
    port.postMessage(transportHello(transportBootNonce, secondChallenge));
    return;
  }
  if (transportStage !== "AWAITING_FINAL_ACK" || message.boot_nonce !== transportBootNonce) {
    rejectTransport(port, epoch, reconnectAttempt);
    return;
  }
  clearHandshakeTimeout(epoch, token);
  transportStage = "READY";
  transportChallengeNonce = null;
  transportHandshakeReady = true;
  reconnectGenerationOpen = false;
  clearReconnectAlarms(epoch).catch(() => undefined);
}

function getNativePort(epoch, reconnectAttempt = -1) {
  if (!INSTANCE_CONFIG) return null;
  if (nativePort) return nativePort;
  if (epoch !== reconnectEpoch || !reconnectGenerationOpen) return null;
  try {
    nativePort = chrome.runtime.connectNative(INSTANCE_CONFIG.nativeHost);
  } catch (_error) {
    nativePort = null;
    scheduleReconnect(epoch, reconnectAttempt + 1);
    return null;
  }
  const port = nativePort;
  const token = ++nextNativePortToken;
  nativePortEpoch = epoch;
  nativePortReconnectAttempt = reconnectAttempt;
  nativePortToken = token;
  transportHandshakeReady = false;
  transportBootNonce = null;
  transportChallengeNonce = randomChallengeNonce();
  transportStage = "AWAITING_FIRST_ACK";
  port.onDisconnect.addListener(() => {
    const wasReady = nativePort === port && nativePortEpoch === epoch && transportHandshakeReady;
    if (!resetTransport(port)) return;
    if (wasReady) {
      const nextEpoch = beginReconnectGeneration();
      scheduleReconnect(nextEpoch, 0);
    } else {
      scheduleReconnect(epoch, reconnectAttempt + 1);
    }
  });
  port.onMessage.addListener((request) => {
    if (nativePort !== port || nativePortEpoch !== epoch || nativePortToken !== token) return;
    if (!transportHandshakeReady) {
      handleTransportAck(request, port, epoch, reconnectAttempt, token);
      return;
    }
    handleNativeRequest(request, port).catch(() => undefined);
  });
  armHandshakeTimeout(epoch, token);
  try {
    port.postMessage(transportHello(null, transportChallengeNonce));
  } catch (_error) {
    rejectTransport(port, epoch, reconnectAttempt);
    return null;
  }
  return nativePort;
}

chrome.runtime.onMessage.addListener((event, sender, sendResponse) => {
  if (validCensusPopup(event, sender)) {
    globalThis.MMXWebSolCensus.collect(chrome.tabs, INSTANCE_CONFIG.instanceId)
      .then(sendResponse, () => sendResponse(null));
    return true;
  }
  if (!recordProbe(event, sender)) return;
  const port = nativePort;
  if (!port || !transportHandshakeReady) return;
  port.postMessage({
    kind: PROBE_KIND,
    conversation_fingerprint: event.conversation_fingerprint,
    observation: event.observation,
  });
});

function refreshFromTabEvent(tabId) {
  refreshTabMapping(tabId).catch(() => removeTabMapping(tabId, false));
}

if (chrome.tabs) {
  if (chrome.tabs.onUpdated) {
    chrome.tabs.onUpdated.addListener((tabId, changeInfo) => {
      if (!changeInfo) return;
      if (typeof changeInfo.url === "string") {
        advanceTabNavigationGeneration(tabId);
        refreshFromTabEvent(tabId);
      } else if (changeInfo.status === "complete") {
        refreshFromTabEvent(tabId);
      }
    });
  }
  if (chrome.tabs.onMoved) {
    chrome.tabs.onMoved.addListener((tabId) => refreshFromTabEvent(tabId));
  }
  if (chrome.tabs.onAttached) {
    chrome.tabs.onAttached.addListener((tabId) => refreshFromTabEvent(tabId));
  }
  if (chrome.tabs.onDetached) {
    chrome.tabs.onDetached.addListener((tabId) => advanceTabNavigationGeneration(tabId));
  }
  if (chrome.tabs.onReplaced) {
    chrome.tabs.onReplaced.addListener((addedTabId, removedTabId) => {
      removeTabMapping(removedTabId);
      refreshFromTabEvent(addedTabId);
    });
  }
  if (chrome.tabs.onRemoved) {
    chrome.tabs.onRemoved.addListener((tabId) => removeTabMapping(tabId));
  }
}

if (chrome.alarms && chrome.alarms.onAlarm) {
  chrome.alarms.onAlarm.addListener((alarm) => {
    const name = alarm && alarm.name;
    const handshake = handshakeAlarmIdentity(name);
    if (handshake) {
      if (name !== activeHandshakeAlarmName || !nativePort || transportHandshakeReady ||
          handshake.epoch !== nativePortEpoch || handshake.token !== nativePortToken) return;
      const port = nativePort;
      const epoch = nativePortEpoch;
      const reconnectAttempt = nativePortReconnectAttempt;
      rejectTransport(port, epoch, reconnectAttempt);
      return;
    }

    const reconnect = reconnectAlarmIdentity(name);
    if (!reconnect || nativePort || !reconnectGenerationOpen ||
        reconnect.epoch !== reconnectEpoch) return;
    getNativePort(reconnect.epoch, reconnect.index);
  });
}

const initialReconnectEpoch = beginReconnectGeneration();
getNativePort(initialReconnectEpoch, -1);
hydrateTargets().catch(() => {
  targets.clear();
  tabFingerprints.clear();
});
