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


NODE_HARNESS = r'''
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
  nativeHost: scenario === "mismatched-host"
    ? `com.mastermind.web_sol_surface.${"b".repeat(24)}`
    : EXPECTED_HOST,
  protocolMajor: 1,
  clientPackageVersion: "0.1.0",
  nativePackageVersion: "0.1.0",
  extensionPackageVersion: "0.1.0",
  capabilityDigest,
};

let runtimeMessageListener = null;
let portMessageListener = null;
let nativeConnectNames = [];
let nativeMessages = [];
let disconnected = false;

const event = (capture) => ({
  addListener(callback) { capture(callback); },
});
const port = {
  onDisconnect: event(() => undefined),
  onMessage: event((callback) => { portMessageListener = callback; }),
  postMessage(value) { nativeMessages.push(value); },
  disconnect() { disconnected = true; },
};

const probe = () => ({
  kind: "MMX_WEB_SOL_PROBE",
  conversation_fingerprint: "c".repeat(64),
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
});

const chrome = {
  runtime: {
    id: "kmpbpccecbofdnhpcmjogofgmdodpnko",
    onMessage: event((callback) => { runtimeMessageListener = callback; }),
    connectNative(name) {
      nativeConnectNames.push(name);
      return port;
    },
  },
  tabs: {
    onRemoved: event(() => undefined),
    async sendMessage() { return probe(); },
    async get(id) { return {id, windowId: 10, active: true}; },
    async update(id) { return {id, windowId: 10, active: true}; },
  },
  windows: {
    async get(id) { return {id, focused: true}; },
    async update(id) { return {id, focused: true}; },
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
context.importScripts = () => {
  context.MMX_WEB_SOL_INSTANCE = Object.freeze({...config});
};
vm.createContext(context);
vm.runInContext(source, context, {filename: "background.js"});

(async () => {
  assert.equal(typeof runtimeMessageListener, "function");
  runtimeMessageListener(
    probe(),
    {
      id: chrome.runtime.id,
      frameId: 0,
      tab: {id: 7, windowId: 10},
    },
  );

  if (scenario === "mismatched-host") {
    assert.deepEqual(nativeConnectNames, []);
    assert.deepEqual(nativeMessages, []);
    return;
  }

  assert.deepEqual(nativeConnectNames, [EXPECTED_HOST]);
  assert.equal(nativeMessages.length, 1);
  const firstHello = nativeMessages[0];
  assert.equal(firstHello.schema, "mastermind.web_sol_transport_hello.v1");
  assert.equal(firstHello.role, "extension");
  assert.equal(firstHello.adapter_instance_id, INSTANCE);
  assert.equal(firstHello.boot_nonce, null);

  portMessageListener({
    ...firstHello,
    schema: "mastermind.web_sol_transport_hello_ack.v1",
    boot_nonce: BOOT,
  });
  assert.equal(disconnected, false);
  assert.equal(nativeMessages.length, 2);
  const secondHello = nativeMessages[1];
  assert.equal(secondHello.boot_nonce, BOOT);
  assert.notEqual(secondHello.challenge_nonce, firstHello.challenge_nonce);

  portMessageListener({
    ...secondHello,
    schema: "mastermind.web_sol_transport_hello_ack.v1",
  });
  assert.equal(disconnected, false);
  assert.equal(vm.runInContext("transportHandshakeReady", context), true);

  portMessageListener({
    schema: "mastermind.web_sol_surface_action.v1",
    binding_id: "12345678-1234-4234-8234-123456789abc",
    conversation_fingerprint: "c".repeat(64),
    binding_fingerprint: "d".repeat(64),
    action: "INSPECT",
    operation_key: "wsx-f2-extension-handshake-test",
    issued_at: new Date().toISOString(),
    expires_at: new Date(Date.now() + 30000).toISOString(),
    nonce: "fixture-nonce-0123456789",
  });
  await new Promise((resolve) => setImmediate(resolve));

  const receipt = nativeMessages.at(-1);
  assert.equal(receipt.schema, "mastermind.web_sol_surface_receipt.v1");
  assert.equal(receipt.status, "INSPECTED");
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
'''


def run_scenario(scenario: str) -> subprocess.CompletedProcess[str]:
    node = shutil.which("node")
    assert node is not None, "Node is required for extension handshake behavior"
    return subprocess.run(
        [
            node,
            "-e",
            NODE_HARNESS,
            str(BACKGROUND),
            scenario,
            wsp.transport_capability_digest(),
        ],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )


def test_background_capability_and_package_constants_match_python_contract():
    source = BACKGROUND.read_text(encoding="utf-8")
    assert (
        f'EXPECTED_CAPABILITY_DIGEST = "{wsp.transport_capability_digest()}"'
        in source
    )
    assert f'PACKAGE_VERSION = "{wsp.WEB_SOL_PACKAGE_VERSION}"' in source


@pytest.mark.parametrize("scenario", ["valid", "mismatched-host"])
def test_extension_handshake_is_behavioral_and_rejects_host_instance_drift(
    scenario,
):
    completed = run_scenario(scenario)
    assert completed.returncode == 0, completed.stdout + completed.stderr
