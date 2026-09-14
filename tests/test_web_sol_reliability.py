"""Behavioral regressions for the production reliability amendment.

These tests execute the actual extension service-worker source in Node, rather
than accepting selector/source-string presence as proof of browser behavior.
They do not connect to ChatGPT, extract content, or mutate any real profile.
"""
from __future__ import annotations

import io
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import shutil
import subprocess

import pytest

from integrations.chairman_surfaces import web_sol_native_host as native
from integrations.chairman_surfaces import web_sol_protocol as wsp

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 8, 30, 8, 0, 0, tzinfo=timezone.utc)


def request(
    *,
    issued: datetime | None = None,
    expires: datetime | None = None,
):
    issued = NOW if issued is None else issued
    expires = NOW + timedelta(seconds=30) if expires is None else expires
    return {
        "schema": wsp.ACTION_SCHEMA,
        "binding_id": "12345678-1234-4234-8234-123456789abc",
        "conversation_fingerprint": "a" * 64,
        "binding_fingerprint": "b" * 64,
        "action": "FOREGROUND",
        "operation_key": "wsx-reliability-fixture",
        "issued_at": issued.isoformat().replace("+00:00", "Z"),
        "expires_at": expires.isoformat().replace("+00:00", "Z"),
        "nonce": "fixture-nonce-0123456789",
    }


def test_action_window_accepts_fresh_bounded_request_and_detaches_it():
    original = request()
    accepted = wsp.validate_action_window(original, now=NOW)
    assert accepted == original
    assert accepted is not original


@pytest.mark.parametrize(
    ("issued", "expires", "now", "reason"),
    [
        (
            NOW - timedelta(seconds=31),
            NOW - timedelta(seconds=1),
            NOW,
            "expired",
        ),
        (NOW - timedelta(seconds=30), NOW, NOW, "expired"),
        (
            NOW + timedelta(seconds=6),
            NOW + timedelta(seconds=30),
            NOW,
            "future",
        ),
        (NOW, NOW + timedelta(seconds=61), NOW, "ttl"),
    ],
)
def test_action_window_refuses_expiry_future_and_excessive_ttl(
    issued,
    expires,
    now,
    reason,
):
    with pytest.raises(wsp.WebSolProtocolError, match=reason):
        wsp.validate_action_window(
            request(issued=issued, expires=expires),
            now=now,
        )


def test_action_window_rejects_a_naive_clock_instead_of_guessing_timezone():
    with pytest.raises(wsp.WebSolProtocolError, match="clock"):
        wsp.validate_action_window(request(), now=NOW.replace(tzinfo=None))


class PartialWriter(io.BytesIO):
    def write(self, payload):
        return super().write(payload[:2])


def test_native_frame_write_handles_short_writes_without_truncation():
    stream = PartialWriter()
    document = {"fixture": "closed-frame"}
    native.write_frame(stream, document)
    stream.seek(0)
    assert native.read_frame(stream) == document


class StalledWriter(io.BytesIO):
    def write(self, payload):
        return 0


def test_native_frame_write_refuses_zero_progress():
    with pytest.raises(native.NativeHostError, match="frame_write_failed"):
        native.write_frame(StalledWriter(), {"fixture": "closed-frame"})


NODE_HARNESS = r'''
const fs = require("node:fs");
const vm = require("node:vm");
const assert = require("node:assert/strict");
const { webcrypto } = require("node:crypto");
const scenario = process.argv[1];
const source = fs.readFileSync(process.argv[2], "utf8");
const A = "a".repeat(64), B = "b".repeat(64);
let actualFingerprint = A;
let currentWindow = 10;
let active = false;
let focused = false;
let composerAvailable = true;
let activationCount = 0;
let activatedWindows = [];
let results = [];
const event = () => ({addListener() {}});
const port = { onDisconnect: event(), onMessage: event(), postMessage(value) { results.push(value); } };
function probe() {
  return {
    kind: "MMX_WEB_SOL_PROBE",
    conversation_fingerprint: actualFingerprint,
    observation: {
      schema: "mastermind.web_sol_surface_probe.v1",
      target_present: true, exact_conversation_loaded: true,
      page_responsive: true, document_ready_state: "complete", visibility: "visible",
      composer_available: composerAvailable, generation_state: "idle", auth_required: false,
      provider_error_present: false,
    },
  };
}
const chrome = {
  runtime: { id: "kmpbpccecbofdnhpcmjogofgmdodpnko", onMessage: event(),
             onStartup: event(), onInstalled: event(), connectNative() {return port;} },
  tabs: {
    onRemoved: event(), onUpdated: event(), onAttached: event(), onReplaced: event(),
    async get(id) { return {id, windowId: currentWindow, active}; },
    async sendMessage() { return probe(); },
    async query() { return []; },
    async update(id, change) { activationCount++; active = true; return {id, windowId: currentWindow, active}; },
  },
  windows: {
    async get(id) { return {id, focused}; },
    async update(id, change) {
      activatedWindows.push(id);
      focused = scenario !== "false-focus" && scenario !== "typed-reentry-false-focus-blocker";
      return {id, focused};
    },
  },
  alarms: {onAlarm: event(), create() {}, async clear() {}},
};
const context = vm.createContext({chrome, Date, Map, Set, Number, Array, Object, String,
  Boolean, RegExp, Promise, URL, TextEncoder, crypto: webcrypto, console, setTimeout, clearTimeout,
  importScripts() {}});
vm.runInContext(source, context, {filename: "background.js"});
const request = {
  schema: "mastermind.web_sol_surface_action.v1",
  binding_id: "12345678-1234-4234-8234-123456789abc",
  conversation_fingerprint: A, binding_fingerprint: B,
  action: "FOREGROUND", operation_key: "wsx-js-reliability-fixture",
  issued_at: new Date().toISOString(),
  expires_at: new Date(Date.now() + 30000).toISOString(),
  nonce: "fixture-nonce-0123456789",
};
const typedReentry = Object.assign({}, request, {
  action: "TYPED_REENTRY",
  operation_id: "e".repeat(64),
  result_digest: "f".repeat(64),
  obligation_digest: "1".repeat(64),
});
(async () => {
  context.recordProbe(probe(), {tab: {id: 7, windowId: 10}});
  if (scenario === "false-focus") {
    const result = await context.handleForeground(request);
    assert.notEqual(result.status, "FOREGROUNDED_VERIFIED", "unfocused window was falsely verified");
  } else if (scenario === "moved-window") {
    currentWindow = 22;
    const result = await context.handleForeground(request);
    assert.deepEqual(activatedWindows, [22], "foreground used stale cached window identity");
    assert.equal(result.status, "FOREGROUNDED_VERIFIED");
  } else if (scenario === "route-change") {
    actualFingerprint = B;
    const changed = await context.handleInspect(request);
    assert.equal(changed.status, "TARGET_CHANGED");
    const current = await context.handleInspect({...request, conversation_fingerprint: B, action: "INSPECT"});
    assert.equal(current.status, "INSPECTED", "SPA route was stranded under old fingerprint");
  } else if (scenario === "expired-action") {
    request.issued_at = "2000-01-01T00:00:00Z";
    request.expires_at = "2000-01-01T00:00:30Z";
    await context.handleNativeRequest(request, port);
    assert.equal(activationCount, 0, "expired foreground performed a browser effect");
    assert.equal(results.at(-1).status, "REQUEST_EXPIRED");
  } else if (scenario === "typed-reentry-consumed-once") {
    const first = await context.handleNativeRequest(typedReentry, port);
    assert.equal(first.status, "CONSUMED");
    assert.equal(first.conversation_fingerprint, A);
    const second = await context.handleNativeRequest(typedReentry, port);
    assert.equal(second.status, "TYPED_REENTRY_BLOCKED");
    assert.equal(second.conversation_fingerprint, A);
    assert.equal(activationCount, 1);
    const documents = results.filter((document) => document.schema === "mastermind.web_sol_surface_receipt.v1");
    console.log(JSON.stringify(documents));
  } else if (scenario === "typed-reentry-closed-conversation-blocker") {
    actualFingerprint = B;
    const blocked = await context.handleNativeRequest(typedReentry, port);
    assert.equal(blocked.status, "CONVERSATION_CLOSED");
    assert.equal(blocked.conversation_fingerprint, A);
    assert.equal(activationCount, 0);
    console.log(JSON.stringify(blocked));
  } else if (scenario === "typed-reentry-composer-unavailable") {
    composerAvailable = false;
    const blocked = await context.handleNativeRequest(typedReentry, port);
    assert.equal(blocked.status, "NOT_CONSUMED");
    assert.equal(blocked.conversation_fingerprint, A);
    assert.equal(activationCount, 0);
    console.log(JSON.stringify(blocked));
  } else if (scenario === "typed-reentry-false-focus-blocker") {
    const blocked = await context.handleNativeRequest(typedReentry, port);
    assert.notEqual(blocked.status, "FOREGROUNDED_VERIFIED");
    assert.equal(blocked.conversation_fingerprint, A);
    console.log(JSON.stringify(blocked));
  } else if (scenario === "typed-reentry-unknown-schema") {
    const changed = {...typedReentry, extra: "forbidden"};
    const result = await context.handleNativeRequest(changed, port);
    assert.equal(result, undefined);
    assert.equal(results.length, 0);
  } else {
    throw new Error("unknown test scenario");
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
'''


@pytest.mark.parametrize(
    "scenario",
    [
        "false-focus",
        "moved-window",
        "route-change",
        "expired-action",
        "typed-reentry-consumed-once",
        "typed-reentry-closed-conversation-blocker",
        "typed-reentry-composer-unavailable",
        "typed-reentry-false-focus-blocker",
        "typed-reentry-unknown-schema",
    ],
)
def test_actual_extension_reliability_behaviors(scenario):
    node = shutil.which("node")
    assert (
        node is not None
    ), "Node is required for real extension behavior tests; do not skip this gate"
    background = (
        ROOT
        / "integrations/chairman_surfaces/web_sol_extension/background.js"
    )
    completed = subprocess.run(
        [node, "-e", NODE_HARNESS, scenario, str(background)],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


DIGEST_FIELDS = ("operation_id", "result_digest", "obligation_digest")


def _run_extension_scenario(scenario: str) -> subprocess.CompletedProcess:
    node = shutil.which("node")
    assert (
        node is not None
    ), "Node is required for real extension behavior tests; do not skip this gate"
    background = (
        ROOT
        / "integrations/chairman_surfaces/web_sol_extension/background.js"
    )
    return subprocess.run(
        [node, "-e", NODE_HARNESS, scenario, str(background)],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )


def _extension_built_document(scenario: str):
    completed = _run_extension_scenario(scenario)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    return json.loads(completed.stdout)


def test_typed_reentry_extension_receipts_pass_host_validate_receipt():
    consumed_docs = _extension_built_document("typed-reentry-consumed-once")
    by_kind = {
        "CONSUMED": consumed_docs[0],
        "TYPED_REENTRY_BLOCKED": consumed_docs[1],
        "CONVERSATION_CLOSED": _extension_built_document(
            "typed-reentry-closed-conversation-blocker"
        ),
        "NOT_CONSUMED": _extension_built_document(
            "typed-reentry-composer-unavailable"
        ),
    }
    for kind, document in by_kind.items():
        assert document["status"] == kind
        accepted = wsp.validate_receipt(document)
        for field in DIGEST_FIELDS:
            assert field in accepted
            assert accepted[field] == document[field]


def test_typed_reentry_failed_foreground_receipt_is_host_legal():
    document = _extension_built_document("typed-reentry-false-focus-blocker")
    accepted = wsp.validate_receipt(document)
    assert accepted["status"] in {"TYPED_REENTRY_BLOCKED", "NOT_CONSUMED"}
    for field in DIGEST_FIELDS:
        assert field in accepted
        assert accepted[field] == document[field]
