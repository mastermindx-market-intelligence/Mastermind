from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess

import pytest

from integrations.chairman_surfaces import web_sol_protocol as wsp


ROOT = Path(__file__).resolve().parents[1]
EXTENSION = ROOT / "integrations" / "chairman_surfaces" / "web_sol_extension"
BACKGROUND = EXTENSION / "background.js"
CONTENT = EXTENSION / "content.js"
MANIFEST = EXTENSION / "manifest.json"


BACKGROUND_HARNESS = r'''
const fs = require("node:fs");
const vm = require("node:vm");
const assert = require("node:assert/strict");
const { webcrypto } = require("node:crypto");

const source = fs.readFileSync(process.argv[1], "utf8");
const scenario = process.argv[2];
const capabilityDigest = process.argv[3];
const INSTANCE = "a".repeat(64);
const EXPECTED_HOST = `com.mastermind.web_sol_surface.${INSTANCE.slice(0, 24)}`;
const BOOT = "boot-nonce-0000000000000001";
const HOST_PATTERNS = ["https://chat.openai.com/*", "https://chatgpt.com/*"];
const RECONNECT_NAMES = [
  "mmx-web-sol-native-reconnect-v1-0",
  "mmx-web-sol-native-reconnect-v1-1",
  "mmx-web-sol-native-reconnect-v1-2",
];

const config = {
  schema: "mastermind.web_sol_instance_config.v1",
  instanceId: INSTANCE,
  nativeHost: EXPECTED_HOST,
  protocolMajor: 1,
  clientPackageVersion: "0.1.0",
  nativePackageVersion: "0.1.0",
  extensionPackageVersion: "0.1.0",
  capabilityDigest,
};

const fingerprints = new Map([
  [1, "1".repeat(64)],
  [2, "2".repeat(64)],
  [3, "3".repeat(64)],
]);
const tabs = new Map([
  [1, {id: 1, windowId: 10, active: false, url: "https://chatgpt.com/c/alpha"}],
  [2, {id: 2, windowId: 20, active: false, url: "https://chat.openai.com/c/beta"}],
]);
if (scenario === "no-tabs") tabs.clear();

let runtimeMessageListener = null;
let alarmListener = null;
let updatedListener = null;
let movedListener = null;
let attachedListener = null;
let detachedListener = null;
let removedListener = null;
let replacedListener = null;
let queryCalls = [];
let sendCalls = [];
let nativeConnectNames = [];
let nativePorts = [];
let alarmCreates = [];
let alarmClears = [];
let connectFailuresRemaining = 0;

function event(capture) {
  return { addListener(callback) { capture(callback); } };
}

function makePort() {
  let messageListener = null;
  let disconnectListener = null;
  const messages = [];
  const port = {
    messages,
    onDisconnect: event((callback) => { disconnectListener = callback; }),
    onMessage: event((callback) => { messageListener = callback; }),
    postMessage(value) { messages.push(value); },
    disconnect() { if (disconnectListener) disconnectListener(); },
    emit(value) { assert.equal(typeof messageListener, "function"); messageListener(value); },
    nativeDisconnect() { assert.equal(typeof disconnectListener, "function"); disconnectListener(); },
  };
  return port;
}

function probeFor(tabId, expectedFingerprint) {
  if (scenario === "content-unavailable" && tabId === 2) {
    throw new Error("content unavailable");
  }
  const fingerprint = fingerprints.get(tabId) || null;
  const targetPresent = fingerprint !== null;
  return {
    kind: "MMX_WEB_SOL_PROBE",
    conversation_fingerprint: fingerprint,
    observation: {
      schema: "mastermind.web_sol_surface_probe.v1",
      target_present: targetPresent,
      exact_conversation_loaded:
        targetPresent && typeof expectedFingerprint === "string" && fingerprint === expectedFingerprint,
      page_responsive: true,
      document_ready_state: "complete",
      visibility: "visible",
      composer_available: true,
      generation_state: "idle",
      auth_required: false,
      provider_error_present: false,
    },
  };
}

const chrome = {
  runtime: {
    id: "kmpbpccecbofdnhpcmjogofgmdodpnko",
    onMessage: event((callback) => { runtimeMessageListener = callback; }),
    connectNative(name) {
      nativeConnectNames.push(name);
      if (connectFailuresRemaining > 0) {
        connectFailuresRemaining -= 1;
        throw new Error("native host unavailable");
      }
      const port = makePort();
      nativePorts.push(port);
      return port;
    },
  },
  alarms: {
    onAlarm: event((callback) => { alarmListener = callback; }),
    create(name, options) { alarmCreates.push({name, ...options}); },
    async clear(name) { alarmClears.push(name); return true; },
  },
  tabs: {
    onUpdated: event((callback) => { updatedListener = callback; }),
    onMoved: event((callback) => { movedListener = callback; }),
    onAttached: event((callback) => { attachedListener = callback; }),
    onDetached: event((callback) => { detachedListener = callback; }),
    onRemoved: event((callback) => { removedListener = callback; }),
    onReplaced: event((callback) => { replacedListener = callback; }),
    async query(query) {
      queryCalls.push(JSON.parse(JSON.stringify(query)));
      return Array.from(tabs.values()).map((tab) => ({...tab}));
    },
    async sendMessage(tabId, request) {
      sendCalls.push({tabId, request: {...request}});
      return probeFor(tabId, request.expected_conversation_fingerprint);
    },
    async get(tabId) {
      const tab = tabs.get(tabId);
      if (!tab) throw new Error("missing tab");
      return {...tab};
    },
    async update(tabId) {
      const tab = tabs.get(tabId);
      if (!tab) throw new Error("missing tab");
      tab.active = true;
      return {...tab};
    },
  },
  windows: {
    async get(windowId) { return {id: windowId, focused: true}; },
    async update(windowId) { return {id: windowId, focused: true}; },
  },
};

const context = {
  chrome,
  Date,
  Map,
  Set,
  Number,
  Array,
  Object,
  String,
  Promise,
  URL,
  Uint8Array,
  TextEncoder,
  crypto: webcrypto,
  console,
};
context.globalThis = context;
context.importScripts = () => {
  context.MMX_WEB_SOL_INSTANCE = Object.freeze({...config});
};
vm.createContext(context);
vm.runInContext(source, context, {filename: "background.js"});

async function flush() {
  for (let index = 0; index < 8; index += 1) {
    await new Promise((resolve) => setImmediate(resolve));
  }
}

function targetSnapshot() {
  return JSON.parse(vm.runInContext(
    "JSON.stringify(Array.from(targets.entries(), ([fingerprint, entries]) => [fingerprint, Array.from(entries.entries())]))",
    context,
  ));
}

function completeHandshake(port) {
  assert.equal(port.messages.length, 1);
  const first = port.messages[0];
  port.emit({...first, schema: "mastermind.web_sol_transport_hello_ack.v1", boot_nonce: BOOT});
  assert.equal(port.messages.length, 2);
  const second = port.messages[1];
  port.emit({...second, schema: "mastermind.web_sol_transport_hello_ack.v1"});
  assert.equal(vm.runInContext("transportHandshakeReady", context), true);
}

(async () => {
  await flush();

  if (scenario === "boot-hydrates-two-tabs") {
    assert.deepEqual(queryCalls, [{url: HOST_PATTERNS}]);
    assert.deepEqual(sendCalls.map((item) => item.tabId), [1, 2]);
    for (const item of sendCalls) {
      assert.equal(item.request.kind, "MMX_WEB_SOL_REPROBE");
      assert.equal(item.request.expected_conversation_fingerprint, null);
    }
    assert.equal(nativeConnectNames.length, 1);
    assert.equal(nativeConnectNames[0], EXPECTED_HOST);
    assert.deepEqual(targetSnapshot(), [
      ["1".repeat(64), [[1, 10]]],
      ["2".repeat(64), [[2, 20]]],
    ]);
    return;
  }

  if (scenario === "no-tabs") {
    assert.deepEqual(queryCalls, [{url: HOST_PATTERNS}]);
    assert.deepEqual(sendCalls, []);
    assert.deepEqual(targetSnapshot(), []);
    assert.deepEqual(nativeConnectNames, [EXPECTED_HOST]);
    return;
  }

  if (scenario === "content-unavailable") {
    assert.deepEqual(queryCalls, [{url: HOST_PATTERNS}]);
    assert.deepEqual(sendCalls.map((item) => item.tabId), [1, 2]);
    assert.deepEqual(targetSnapshot(), [["1".repeat(64), [[1, 10]]]]);
    return;
  }

  if (scenario === "route-events") {
    assert.equal(typeof updatedListener, "function");
    assert.equal(typeof movedListener, "function");
    assert.equal(typeof attachedListener, "function");
    assert.equal(typeof detachedListener, "function");
    assert.equal(typeof replacedListener, "function");
    assert.equal(typeof removedListener, "function");

    fingerprints.set(1, "3".repeat(64));
    tabs.get(1).url = "https://chatgpt.com/c/gamma";
    updatedListener(1, {url: tabs.get(1).url, status: "complete"}, {...tabs.get(1)});
    await flush();
    assert.deepEqual(targetSnapshot(), [
      ["2".repeat(64), [[2, 20]]],
      ["3".repeat(64), [[1, 10]]],
    ]);

    tabs.get(1).windowId = 11;
    attachedListener(1, {newWindowId: 11, newPosition: 0});
    await flush();
    assert.deepEqual(targetSnapshot(), [
      ["2".repeat(64), [[2, 20]]],
      ["3".repeat(64), [[1, 11]]],
    ]);

    detachedListener(1, {oldWindowId: 11, oldPosition: 0});
    assert.deepEqual(targetSnapshot(), [["2".repeat(64), [[2, 20]]]]);
    movedListener(2, {fromIndex: 0, toIndex: 1, windowId: 20});
    await flush();
    assert.deepEqual(targetSnapshot(), [["2".repeat(64), [[2, 20]]]]);

    tabs.set(3, {id: 3, windowId: 30, active: false, url: "https://chatgpt.com/c/replacement"});
    tabs.delete(2);
    replacedListener(3, 2);
    await flush();
    assert.deepEqual(targetSnapshot(), [["3".repeat(64), [[3, 30]]]]);
    removedListener(3);
    assert.deepEqual(targetSnapshot(), []);
    return;
  }

  if (scenario === "bounded-reconnect") {
    assert.equal(typeof alarmListener, "function");
    assert.equal(nativePorts.length, 1);
    const firstPort = nativePorts[0];
    completeHandshake(firstPort);
    await flush();
    assert.deepEqual(alarmClears.sort(), [...RECONNECT_NAMES].sort());

    connectFailuresRemaining = 3;
    firstPort.nativeDisconnect();
    assert.deepEqual(alarmCreates.at(-1), {
      name: RECONNECT_NAMES[0],
      delayInMinutes: 1,
    });

    alarmListener({name: RECONNECT_NAMES[0]});
    await flush();
    assert.deepEqual(alarmCreates.at(-1), {
      name: RECONNECT_NAMES[1],
      delayInMinutes: 5,
    });

    alarmListener({name: RECONNECT_NAMES[1]});
    await flush();
    assert.deepEqual(alarmCreates.at(-1), {
      name: RECONNECT_NAMES[2],
      delayInMinutes: 15,
    });

    const beforeFinal = alarmCreates.length;
    alarmListener({name: RECONNECT_NAMES[2]});
    await flush();
    assert.equal(alarmCreates.length, beforeFinal);
    assert.equal(nativePorts.length, 1);
    assert.equal(
      nativePorts.some((port) => port.messages.some((message) => message.schema === "mastermind.web_sol_surface_action.v1")),
      false,
    );
    return;
  }

  throw new Error(`unknown scenario: ${scenario}`);
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
'''


CONTENT_HARNESS = r'''
const fs = require("node:fs");
const vm = require("node:vm");
const assert = require("node:assert/strict");
const { webcrypto } = require("node:crypto");

const source = fs.readFileSync(process.argv[1], "utf8");
let listener = null;
let initialProbe = null;
const chrome = {
  runtime: {
    onMessage: {addListener(callback) { listener = callback; }},
    async sendMessage(value) { initialProbe = value; },
  },
};
const context = {
  chrome,
  location: {
    origin: "https://chat.openai.com",
    pathname: "/c/alpha",
  },
  document: {
    visibilityState: "visible",
    readyState: "complete",
    querySelector(selector) {
      return selector === "#prompt-textarea" ? {} : null;
    },
  },
  TextEncoder,
  Uint8Array,
  crypto: webcrypto,
  Promise,
  console,
};
vm.createContext(context);
vm.runInContext(source, context, {filename: "content.js"});

(async () => {
  await new Promise((resolve) => setTimeout(resolve, 25));
  assert.equal(typeof listener, "function");
  assert.equal(initialProbe.kind, "MMX_WEB_SOL_PROBE");

  let response;
  const accepted = listener(
    {
      kind: "MMX_WEB_SOL_REPROBE",
      expected_conversation_fingerprint: null,
    },
    {},
    (value) => { response = value; },
  );
  assert.equal(accepted, true);
  await new Promise((resolve) => setTimeout(resolve, 25));
  assert.equal(response.kind, "MMX_WEB_SOL_PROBE");
  assert.equal(response.observation.target_present, true);
  assert.equal(response.observation.exact_conversation_loaded, false);
  assert.equal(typeof response.conversation_fingerprint, "string");
  assert.equal(response.conversation_fingerprint.length, 64);
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
'''


def _node() -> str:
    node = shutil.which("node")
    assert node is not None, "Node is required for Web-Sol MV3 behavior tests"
    return node


def _run_background(scenario: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            _node(),
            "-e",
            BACKGROUND_HARNESS,
            str(BACKGROUND),
            scenario,
            wsp.transport_capability_digest(),
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


@pytest.mark.parametrize(
    "scenario",
    [
        "boot-hydrates-two-tabs",
        "no-tabs",
        "content-unavailable",
        "route-events",
        "bounded-reconnect",
    ],
)
def test_mv3_worker_reconstitutes_exact_profile_state_without_replaying_actions(
    scenario: str,
):
    completed = _run_background(scenario)
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_content_probe_supports_nullable_expected_fingerprint_for_hydration():
    completed = subprocess.run(
        [_node(), "-e", CONTENT_HARNESS, str(CONTENT)],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_manifest_grants_only_native_messaging_and_bounded_alarm_reconnect():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert set(manifest["permissions"]) == {"nativeMessaging", "alarms"}
    assert set(manifest["host_permissions"]) == {
        "https://chat.openai.com/*",
        "https://chatgpt.com/*",
    }
