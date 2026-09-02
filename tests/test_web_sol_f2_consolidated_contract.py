from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

import pytest

from control_plane import surface_bindings as sb
from integrations.chairman_surfaces import web_sol_client as client
from integrations.chairman_surfaces import web_sol_protocol as wsp


ROOT = Path(__file__).resolve().parents[1]
BACKGROUND = (
    ROOT
    / "integrations"
    / "chairman_surfaces"
    / "web_sol_extension"
    / "background.js"
)
CONTENT = (
    ROOT
    / "integrations"
    / "chairman_surfaces"
    / "web_sol_extension"
    / "content.js"
)
ISSUED = datetime(2026, 8, 30, 19, 0, tzinfo=timezone.utc)
NONCE = "f2-consolidated-nonce-000001"


def _zulu(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def binding(
    *,
    host: str = "chatgpt.com",
    conversation: str = "session-alpha",
) -> dict:
    return sb.new_binding(
        work_ref="WS:CHAIRMAN-CONTROL-ROOM",
        role="ceo",
        provider="chatgpt",
        locator_kind="chatgpt_managed_env",
        locator={
            "env_manager": "gologin",
            "profile_id": "aaaaaaaaaaaaaaaaaaaaaaaa",
            "url": f"https://{host}/c/{conversation}",
        },
        observed_at="2026-08-30T18:59:00Z",
        seat_ref="chatgpt1",
        binding_id="11111111-1111-4111-8111-111111111111",
    )


def request(
    *,
    action: str = "INSPECT",
    ttl_seconds: int = 30,
) -> dict:
    document = {
        "schema": wsp.ACTION_SCHEMA,
        "binding_id": "11111111-1111-4111-8111-111111111111",
        "conversation_fingerprint": "a" * 64,
        "binding_fingerprint": "b" * 64,
        "action": action,
        "operation_key": "web-sol-f2-consolidated-contract",
        "issued_at": _zulu(ISSUED),
        "expires_at": _zulu(ISSUED + timedelta(seconds=ttl_seconds)),
        "nonce": NONCE,
    }
    # Transitional compatibility only so non-revision tests can reach their
    # intended old implementation branch during RED. The final closed wire
    # test below requires this legacy field to disappear.
    if "binding_revision" in getattr(wsp, "_REQUEST_KEYS", frozenset()):
        document["binding_revision"] = 0
    return document


def observation(**overrides) -> dict:
    value = {
        "schema": wsp.PROBE_SCHEMA,
        "target_present": True,
        "exact_conversation_loaded": True,
        "page_responsive": True,
        "document_ready_state": "complete",
        "visibility": "visible",
        "composer_available": True,
        "generation_state": "idle",
        "auth_required": False,
        "provider_error_present": False,
    }
    value.update(overrides)
    return value


def receipt(
    *,
    action: str = "INSPECT",
    status: str = "INSPECTED",
    observed: dict | None = None,
    **overrides,
) -> dict:
    source = request(action=action)
    value = {
        "schema": wsp.RECEIPT_SCHEMA,
        "binding_id": source["binding_id"],
        "conversation_fingerprint": source["conversation_fingerprint"],
        "binding_fingerprint": source["binding_fingerprint"],
        "action": action,
        "operation_key": source["operation_key"],
        "nonce": source["nonce"],
        "status": status,
        "observed_at": "2026-08-30T19:00:01Z",
        "observation": observed or observation(),
    }
    if "binding_revision" in source:
        value["binding_revision"] = source["binding_revision"]
    value.update(overrides)
    return value


def test_action_and_receipt_wire_do_not_mint_a_fictitious_binding_revision():
    clean_request = request()
    clean_request.pop("binding_revision", None)
    assert wsp.validate_request(clean_request) == clean_request
    with pytest.raises(wsp.WebSolProtocolError):
        wsp.validate_request({**clean_request, "binding_revision": 0})

    clean_receipt = receipt()
    clean_receipt.pop("binding_revision", None)
    assert wsp.validate_receipt(clean_receipt) == clean_receipt
    with pytest.raises(wsp.WebSolProtocolError):
        wsp.validate_receipt({**clean_receipt, "binding_revision": 0})


def test_transport_capability_digest_binds_probe_and_instance_config_contracts():
    document = {
        "schema": wsp.TRANSPORT_CAPABILITY_SCHEMA,
        "protocol_major": wsp.TRANSPORT_PROTOCOL_MAJOR,
        "package_version": wsp.WEB_SOL_PACKAGE_VERSION,
        "roles": ["client", "extension"],
        "actions": sorted(action.value for action in wsp.SurfaceAction),
        "schemas": sorted(
            [
                wsp.ACTION_SCHEMA,
                wsp.HELLO_ACK_SCHEMA,
                wsp.HELLO_SCHEMA,
                wsp.INSTANCE_CONFIG_SCHEMA,
                wsp.PROBE_SCHEMA,
                wsp.RECEIPT_SCHEMA,
            ]
        ),
    }
    payload = json.dumps(
        document,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    assert wsp.transport_capability_digest() == hashlib.sha256(payload).hexdigest()


def test_structural_request_validation_enforces_the_sixty_second_ttl_ceiling():
    assert wsp.validate_request(request(ttl_seconds=60))["expires_at"].endswith("Z")
    with pytest.raises(wsp.WebSolProtocolError, match="ttl"):
        wsp.validate_request(request(ttl_seconds=61))


@pytest.mark.parametrize(
    ("action", "status", "observed"),
    [
        ("FOREGROUND", "INSPECTED", observation()),
        (
            "FOREGROUND",
            "FOREGROUNDED_VERIFIED",
            observation(target_present=False),
        ),
        (
            "INSPECT",
            "TARGET_CHANGED",
            observation(exact_conversation_loaded=True),
        ),
        ("INSPECT", "AUTH_REQUIRED", observation(auth_required=False)),
        (
            "INSPECT",
            "PROVIDER_ERROR",
            observation(provider_error_present=False),
        ),
    ],
)
def test_receipt_status_semantics_reject_contradictory_probe_evidence(
    action,
    status,
    observed,
):
    with pytest.raises(wsp.WebSolProtocolError):
        wsp.validate_receipt(
            receipt(action=action, status=status, observed=observed)
        )


def test_foreground_effect_unknown_is_a_closed_observation_agnostic_receipt():
    accepted = wsp.validate_receipt(
        receipt(
            action="FOREGROUND",
            status="FOREGROUND_EFFECT_UNKNOWN",
            observed=observation(
                target_present=False,
                exact_conversation_loaded=False,
                page_responsive=False,
                document_ready_state="loading",
                visibility="hidden",
                composer_available=None,
                generation_state="unknown",
                auth_required=None,
                provider_error_present=None,
            ),
        )
    )
    assert accepted["status"] == "FOREGROUND_EFFECT_UNKNOWN"


def test_chat_openai_and_chatgpt_aliases_share_one_exact_conversation_identity():
    canonical = binding(host="chatgpt.com")
    legacy = binding(host="chat.openai.com")
    different = binding(host="chatgpt.com", conversation="session-beta")

    assert client.conversation_fingerprint(legacy) == client.conversation_fingerprint(
        canonical
    )
    assert client.conversation_fingerprint(canonical) != client.conversation_fingerprint(
        different
    )


CONTENT_HARNESS = r"""
const fs = require("node:fs");
const vm = require("node:vm");
const { webcrypto, pbkdf2 } = require("node:crypto");

const source = fs.readFileSync(process.argv[1], "utf8");
const host = process.argv[2];
const saturate = process.argv[3] === "saturate";
if (saturate) {
  for (let index = 0; index < 4; index += 1) {
    pbkdf2("a", "b", 200000, 32, "sha256", () => {});
  }
}
let resolveProbe;
const probeReceived = new Promise((resolve) => {
  resolveProbe = resolve;
});
const context = {
  chrome: {
    runtime: {
      onMessage: { addListener() {} },
      sendMessage(value) {
        resolveProbe(value);
        return Promise.resolve();
      },
    },
  },
  crypto: webcrypto,
  document: {
    readyState: "complete",
    visibilityState: "visible",
    querySelector() { return null; },
  },
  location: {
    origin: `https://${host}`,
    pathname: "/c/session-alpha",
  },
  TextEncoder,
  Promise,
  Array,
  Object,
  String,
  RegExp,
  console,
};
vm.createContext(context);
vm.runInContext(source, context, {filename: "content.js"});

(async () => {
  const observed = await Promise.race([
    probeReceived,
    new Promise((_, reject) =>
      setTimeout(
        () => reject(new Error("probe fingerprint not emitted")),
        5000,
      ),
    ),
  ]);
  if (!observed || typeof observed.conversation_fingerprint !== "string") {
    throw new Error("probe fingerprint not emitted");
  }
  process.stdout.write(observed.conversation_fingerprint);
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
"""


def _content_fingerprint(host: str, *, saturate_crypto: bool = False) -> str:
    node = shutil.which("node")
    assert node is not None, "Node is required for cross-language identity proof"
    completed = subprocess.run(
        [
            node,
            "-e",
            CONTENT_HARNESS,
            str(CONTENT),
            host,
            "saturate" if saturate_crypto else "normal",
        ],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    return completed.stdout.strip()


def test_content_script_alias_canonicalization_matches_python_exactly():
    python_value = client.conversation_fingerprint(binding(host="chatgpt.com"))
    assert _content_fingerprint("chatgpt.com") == python_value
    assert _content_fingerprint("chat.openai.com") == python_value


@pytest.mark.parametrize("host", ["chatgpt.com", "chat.openai.com"])
def test_content_script_probe_waits_for_crypto_completion_under_saturation(host):
    python_value = client.conversation_fingerprint(binding(host="chatgpt.com"))
    assert _content_fingerprint(host, saturate_crypto=True) == python_value


@pytest.mark.parametrize("mode", ["malformed", "wrong_nonce", "wrong_action"])
def test_foreground_post_send_untrusted_receipt_is_effect_unknown_without_retry(
    monkeypatch,
    mode,
):
    calls = 0

    def exchange(source, *, path, expected_instance_id):
        nonlocal calls
        calls += 1
        assert path.is_absolute()
        assert len(expected_instance_id) == 64
        if mode == "malformed":
            return {"schema": wsp.RECEIPT_SCHEMA}
        value = receipt(
            action=source["action"],
            status="FOREGROUNDED_VERIFIED",
            observed=observation(),
        )
        for field in (
            "binding_id",
            "conversation_fingerprint",
            "binding_fingerprint",
            "action",
            "operation_key",
            "nonce",
        ):
            value[field] = source[field]
        if "binding_revision" in source:
            value["binding_revision"] = source["binding_revision"]
        if mode == "wrong_nonce":
            value["nonce"] = "different-receipt-nonce-0001"
        else:
            value["action"] = "INSPECT"
            value["status"] = "INSPECTED"
        return value

    monkeypatch.setattr(client, "_exchange_web_sol_socket", exchange)
    with pytest.raises(client.WebSolExtensionError) as caught:
        client.foreground_via_extension(
            binding(),
            operation_key="web-sol-f2-receipt-effect-safety",
            issued_at="2026-08-30T19:00:00Z",
            expires_at="2026-08-30T19:00:30Z",
            nonce="foreground-receipt-nonce-0001",
        )

    assert caught.value.code == "foreground_effect_unknown"
    assert calls == 1


BACKGROUND_HARNESS = r"""
const fs = require("node:fs");
const vm = require("node:vm");
const assert = require("node:assert/strict");
const { webcrypto } = require("node:crypto");

const source = fs.readFileSync(process.argv[1], "utf8");
const scenario = process.argv[2];
const capabilityDigest = process.argv[3];
const INSTANCE = "a".repeat(64);
const CONVERSATION = "c".repeat(64);
const BOOT = "boot-nonce-0000000000000001";
const config = {
  schema: "mastermind.web_sol_instance_config.v1",
  instanceId: INSTANCE,
  nativeHost: `com.mastermind.web_sol_surface.${INSTANCE.slice(0, 24)}`,
  protocolMajor: 1,
  clientPackageVersion: "0.1.0",
  nativePackageVersion: "0.1.0",
  extensionPackageVersion: "0.1.0",
  capabilityDigest,
};

let runtimeMessageListener = null;
let portMessageListener = null;
const nativeMessages = [];
let tabUpdates = 0;
let tabGets = 0;
let probeReads = 0;
let windowUpdates = 0;

const event = (capture) => ({
  addListener(callback) { capture(callback); },
});
const port = {
  onDisconnect: event(() => undefined),
  onMessage: event((callback) => { portMessageListener = callback; }),
  postMessage(value) { nativeMessages.push(value); },
  disconnect() {},
};

function probe(fingerprint = CONVERSATION, exact = true) {
  return {
    kind: "MMX_WEB_SOL_PROBE",
    conversation_fingerprint: fingerprint,
    observation: {
      schema: "mastermind.web_sol_surface_probe.v1",
      target_present: true,
      exact_conversation_loaded: exact,
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
    connectNative() { return port; },
  },
  tabs: {
    onRemoved: event(() => undefined),
    async sendMessage() {
      probeReads += 1;
      if (scenario === "post-probe-changed" && probeReads === 2) {
        return probe("d".repeat(64), false);
      }
      if (scenario === "post-probe-fails" && probeReads === 2) {
        throw new Error("post probe failed");
      }
      return probe();
    },
    async get(id) {
      tabGets += 1;
      if (scenario === "tab-get-after-activation-fails" && tabUpdates === 1 && tabGets === 2) {
        throw new Error("tab readback failed");
      }
      return {id, windowId: 10, active: true};
    },
    async update(id) {
      tabUpdates += 1;
      return {id, windowId: 10, active: true};
    },
  },
  windows: {
    async get(id) {
      if (scenario === "final-window-readback-fails") {
        throw new Error("window readback failed");
      }
      return {id, focused: true};
    },
    async update(id) {
      windowUpdates += 1;
      if (scenario === "window-update-fails") {
        throw new Error("window update failed");
      }
      return {id, focused: true};
    },
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
  runtimeMessageListener(
    probe(),
    {
      id: chrome.runtime.id,
      frameId: 0,
      tab: {id: 7, windowId: 10},
    },
  );

  const firstHello = nativeMessages[0];
  portMessageListener({
    ...firstHello,
    schema: "mastermind.web_sol_transport_hello_ack.v1",
    boot_nonce: BOOT,
  });
  const secondHello = nativeMessages[1];
  portMessageListener({
    ...secondHello,
    schema: "mastermind.web_sol_transport_hello_ack.v1",
  });
  assert.equal(vm.runInContext("transportHandshakeReady", context), true);

  const now = Date.now();
  const action = {
    schema: "mastermind.web_sol_surface_action.v1",
    binding_id: "12345678-1234-4234-8234-123456789abc",
    conversation_fingerprint: CONVERSATION,
    binding_fingerprint: "d".repeat(64),
    action: "FOREGROUND",
    operation_key: "web-sol-f2-post-actuation-effect-safety",
    issued_at: new Date(now).toISOString(),
    expires_at: new Date(now + 30000).toISOString(),
    nonce: "foreground-effect-nonce-0001",
  };
  if (source.includes('"binding_revision"')) {
    action.binding_revision = 0;
  }
  portMessageListener(action);
  for (let index = 0; index < 20; index += 1) {
    await new Promise((resolve) => setImmediate(resolve));
  }

  const result = nativeMessages.at(-1);
  assert.equal(result.schema, "mastermind.web_sol_surface_receipt.v1");
  assert.equal(result.status, "FOREGROUND_EFFECT_UNKNOWN");
  assert.equal(tabUpdates, 1);
  assert.ok(windowUpdates <= 1);
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
"""


def _run_background_scenario(scenario: str) -> subprocess.CompletedProcess[str]:
    node = shutil.which("node")
    assert node is not None, "Node is required for foreground effect-safety proof"
    return subprocess.run(
        [
            node,
            "-e",
            BACKGROUND_HARNESS,
            str(BACKGROUND),
            scenario,
            wsp.transport_capability_digest(),
        ],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )


@pytest.mark.parametrize(
    "scenario",
    [
        "tab-get-after-activation-fails",
        "window-update-fails",
        "post-probe-changed",
        "post-probe-fails",
        "final-window-readback-fails",
    ],
)
def test_every_post_actuation_foreground_failure_is_effect_unknown_without_replay(
    scenario,
):
    completed = _run_background_scenario(scenario)
    assert completed.returncode == 0, completed.stdout + completed.stderr
