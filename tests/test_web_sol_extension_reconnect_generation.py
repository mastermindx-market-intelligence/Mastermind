from __future__ import annotations

from pathlib import Path
import shutil
import subprocess

import pytest

from integrations.chairman_surfaces import web_sol_protocol as wsp


ROOT = Path(__file__).resolve().parents[1]
BACKGROUND = (
    ROOT
    / "integrations"
    / "chairman_surfaces"
    / "web_sol_extension"
    / "background.js"
)


HARNESS = r'''
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

let runtimeMessageListener = null;
let alarmListener = null;
let connectFailuresRemaining = 0;
const nativeConnectNames = [];
const nativePorts = [];
const alarmCreates = [];
const alarmClears = [];

function event(capture) {
  return {addListener(callback) { capture(callback); }};
}

function makePort() {
  let messageListener = null;
  let disconnectListener = null;
  const messages = [];
  let disconnectCount = 0;
  return {
    messages,
    get disconnectCount() { return disconnectCount; },
    onDisconnect: event((callback) => { disconnectListener = callback; }),
    onMessage: event((callback) => { messageListener = callback; }),
    postMessage(value) { messages.push(value); },
    disconnect() {
      disconnectCount += 1;
      if (disconnectListener) disconnectListener();
    },
    emit(value) {
      assert.equal(typeof messageListener, "function");
      messageListener(value);
    },
    nativeDisconnect() {
      assert.equal(typeof disconnectListener, "function");
      disconnectListener();
    },
  };
}

function validProbe() {
  return {
    kind: "MMX_WEB_SOL_PROBE",
    conversation_fingerprint: "1".repeat(64),
    observation: {
      schema: "mastermind.web_sol_surface_probe.v1",
      target_present: true,
      exact_conversation_loaded: true,
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
    onUpdated: event(() => {}),
    onMoved: event(() => {}),
    onAttached: event(() => {}),
    onDetached: event(() => {}),
    onRemoved: event(() => {}),
    onReplaced: event(() => {}),
    async query() { return []; },
    async sendMessage() { return null; },
    async get(tabId) { return {id: tabId, windowId: 10, active: false}; },
    async update(tabId) { return {id: tabId, windowId: 10, active: true}; },
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

function completeHandshake(port) {
  assert.equal(port.messages.length, 1);
  const first = port.messages[0];
  port.emit({...first, schema: "mastermind.web_sol_transport_hello_ack.v1", boot_nonce: BOOT});
  assert.equal(port.messages.length, 2);
  const second = port.messages[1];
  port.emit({...second, schema: "mastermind.web_sol_transport_hello_ack.v1"});
  assert.equal(vm.runInContext("transportHandshakeReady", context), true);
}

function reconnectAlarms() {
  return alarmCreates.filter((item) => item.name.startsWith("mmx-web-sol-native-reconnect-"));
}

function handshakeAlarms() {
  return alarmCreates.filter((item) => item.name.startsWith("mmx-web-sol-native-handshake-"));
}

(async () => {
  await flush();
  assert.equal(typeof runtimeMessageListener, "function");
  assert.equal(typeof alarmListener, "function");
  assert.equal(nativePorts.length, 1);
  const firstPort = nativePorts[0];

  if (scenario === "probe-cannot-reset-exhausted-generation") {
    completeHandshake(firstPort);
    connectFailuresRemaining = 3;
    firstPort.nativeDisconnect();

    for (const delay of [1, 5, 15]) {
      const scheduled = reconnectAlarms().at(-1);
      assert.equal(scheduled.delayInMinutes, delay);
      alarmListener({name: scheduled.name});
      await flush();
    }

    const connectsAfterExhaustion = nativeConnectNames.length;
    runtimeMessageListener(
      validProbe(),
      {
        id: chrome.runtime.id,
        frameId: 0,
        tab: {id: 1, windowId: 10},
      },
    );
    await flush();
    assert.equal(nativeConnectNames.length, connectsAfterExhaustion);
    assert.equal(nativePorts.length, 1);
    return;
  }

  if (scenario === "silent-handshake-times-out-within-generation") {
    const timeout = handshakeAlarms().at(-1);
    assert.ok(timeout, "connected-but-silent native port needs a handshake timeout");
    assert.equal(timeout.delayInMinutes, 0.5);
    alarmListener({name: timeout.name});
    await flush();
    assert.equal(firstPort.disconnectCount, 1);
    assert.equal(vm.runInContext("nativePort", context), null);
    const reconnect = reconnectAlarms().at(-1);
    assert.ok(reconnect);
    assert.equal(reconnect.delayInMinutes, 1);
    return;
  }

  if (scenario === "completed-handshake-cancels-stale-timeout") {
    const timeout = handshakeAlarms().at(-1);
    assert.ok(timeout, "handshake timeout must be armed before ACK");
    completeHandshake(firstPort);
    await flush();
    assert.ok(alarmClears.includes(timeout.name));

    const reconnectCount = reconnectAlarms().length;
    alarmListener({name: timeout.name});
    await flush();
    assert.equal(firstPort.disconnectCount, 0);
    assert.equal(reconnectAlarms().length, reconnectCount);
    assert.equal(vm.runInContext("transportHandshakeReady", context), true);
    return;
  }

  throw new Error(`unknown scenario: ${scenario}`);
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
'''


def _node() -> str:
    node = shutil.which("node")
    assert node is not None, "Node is required for Web-Sol MV3 behavior tests"
    return node


@pytest.mark.parametrize(
    "scenario",
    [
        "probe-cannot-reset-exhausted-generation",
        "silent-handshake-times-out-within-generation",
        "completed-handshake-cancels-stale-timeout",
    ],
)
def test_reconnect_generation_and_handshake_timeout_are_bounded(scenario: str):
    completed = subprocess.run(
        [
            _node(),
            "-e",
            HARNESS,
            str(BACKGROUND),
            scenario,
            wsp.transport_capability_digest(),
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
