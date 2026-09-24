from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import shutil
import subprocess

from integrations.chairman_surfaces import web_sol_protocol as wsp


ROOT = Path(__file__).resolve().parents[1]
EXTENSION = ROOT / "integrations/chairman_surfaces/web_sol_extension"
CORE = EXTENSION / "semantic_ack_core.js"
CONTENT = EXTENSION / "content.js"
BACKGROUND = EXTENSION / "background.js"
WAKE_A = "WAKE-" + "a" * 32
WAKE_B = "WAKE-" + "b" * 32
NUDGE = "NUDGE-" + "c" * 32
CONVERSATION_ID = "synthetic-semantic-ack-001"
IDENTITY = f"https://chatgpt.com/c/{CONVERSATION_ID}"
FINGERPRINT = hashlib.sha256(IDENTITY.encode()).hexdigest()


def _request() -> dict:
    ids = [WAKE_A, WAKE_B]
    return {
        "kind": "MMX_WEB_SOL_OBSERVE_CONTINUATION_ACK",
        "expected_conversation_fingerprint": FINGERPRINT,
        "turn_id": NUDGE,
        "directive_digest": wsp.CONTINUATION_DIRECTIVE_DIGEST,
        "session_alias": "SOL-WEB-3",
        "runtime_binding_id": "bind-wsx-" + "d" * 48,
        "runtime_binding_generation": 4,
        "runtime_binding_fingerprint": "e" * 64,
        "wake_obligation_ids": ids,
        "wake_obligation_digest": wsp.wake_obligation_digest(ids),
    }


def _run(
    *,
    assistant_text: str,
    assistant_status: str = "finished_successfully",
    assistant_end_turn: bool = True,
    fetch_status: int = 200,
    fetch_raises: bool = False,
    snapshot_conversation_id: str = CONVERSATION_ID,
    declared_length: int | None = None,
    body_missing: bool = False,
) -> dict:
    node = shutil.which("node")
    assert node is not None
    payload = {
        "request": _request(),
        "assistant_text": assistant_text,
        "assistant_status": assistant_status,
        "assistant_end_turn": assistant_end_turn,
        "fetch_status": fetch_status,
        "fetch_raises": fetch_raises,
        "snapshot_conversation_id": snapshot_conversation_id,
        "declared_length": declared_length,
        "body_missing": body_missing,
    }
    harness = r"""
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const vm = require('node:vm');
const input = JSON.parse(process.argv[3]);
const request = input.request;
let providerSnapshot = null;
const document = {
  visibilityState:'visible', readyState:'complete',
  querySelector:(selector) => selector === '#prompt-textarea' ? {} : null,
};
const context = vm.createContext({
  TextEncoder, TextDecoder, Uint8Array, ArrayBuffer, URL,
  Object, Array, Set, RegExp, JSON, String, Number, Boolean,
  location:{origin:'https://chatgpt.com', pathname:'/c/synthetic-semantic-ack-001'},
  document, Event:function(){}, InputEvent:function(){},
  crypto:{subtle:crypto.webcrypto.subtle,getRandomValues:(value) => crypto.webcrypto.getRandomValues(value)},
  fetch:async (url, options) => {
    if (input.fetch_raises) throw new Error('network unavailable');
    assert.equal(url, 'https://chatgpt.com/backend-api/conversation/synthetic-semantic-ack-001');
    assert.equal(options.method, 'GET');
    assert.equal(options.credentials, 'include');
    assert.equal(options.cache, 'no-store');
    assert.equal(options.redirect, 'error');
    assert.equal(options.headers.Accept, 'application/json');
    assert.deepEqual(Object.keys(options).sort(), ['cache','credentials','headers','method','redirect']);
    assert.deepEqual(Object.keys(options.headers), ['Accept']);
    const encoded = new TextEncoder().encode(JSON.stringify(providerSnapshot));
    let emitted = false;
    const body = input.body_missing ? null : {getReader:() => ({
      read:async () => emitted ? {done:true} : (emitted = true, {done:false,value:encoded}),
      cancel:async () => {},
    })};
    return {
      status:input.fetch_status,
      ok:input.fetch_status >= 200 && input.fetch_status < 300,
      headers:{get:(name) => name.toLowerCase() === 'content-type'
        ? 'application/json; charset=utf-8'
        : name.toLowerCase() === 'content-length'
          ? String(input.declared_length ?? encoded.byteLength) : null},
      body,
    };
  },
  chrome:{runtime:{onMessage:{addListener:() => {}},sendMessage:() => {}}},
});
context.globalThis = context;
vm.runInContext(fs.readFileSync(process.argv[1], 'utf8'), context, {filename:'semantic_ack_core.js'});
vm.runInContext(fs.readFileSync(process.argv[2], 'utf8'), context, {filename:'content.js'});
(async () => {
  const directive = vm.runInContext(`continuationDirective(${JSON.stringify(request)})`, context);
  assert.ok(directive.endsWith(`MASTERMIND_WAKE_NUDGE ${request.turn_id}\nMASTERMIND_WAKE_SET ${request.wake_obligation_digest}`));
  const userId = 'user-turn-current-001';
  const assistantId = 'assistant-turn-current-001';
  providerSnapshot = {
    conversation_id:input.snapshot_conversation_id,
    current_node:assistantId,
    mapping:{
      [userId]:{id:userId,parent:null,children:[assistantId],message:{
        id:userId,author:{role:'user'},status:'finished_successfully',end_turn:false,
        content:{content_type:'text',parts:[directive]},
      }},
      [assistantId]:{id:assistantId,parent:userId,children:[],message:{
        id:assistantId,author:{role:'assistant'},status:input.assistant_status,
        end_turn:input.assistant_end_turn,
        content:{content_type:'text',parts:[input.assistant_text]},
      }},
    },
  };
  const result = await context.observeSemanticAck(request);
  process.stdout.write(JSON.stringify({directive, result}));
})().catch(error => {console.error(error.stack || error.message); process.exitCode = 1;});
"""
    completed = subprocess.run(
        [node, "-e", harness, str(CORE), str(CONTENT), json.dumps(payload)],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    return json.loads(completed.stdout)


def _ack_text() -> str:
    return "\n".join(
        [
            "Canonical state consumed.",
            f"MASTERMIND_WAKE_ACK {WAKE_B}",
            f"MASTERMIND_WAKE_ACK {WAKE_A}",
        ]
    )


def test_content_producer_returns_only_closed_provider_projection() -> None:
    result = _run(assistant_text=_ack_text())
    projection = result["result"]
    assert projection["status"] == "CONTINUATION_ACKNOWLEDGED"
    assert projection["provider_native_turn_id"] == "assistant-turn-current-001"
    assert projection["acknowledged_obligation_ids"] == [WAKE_A, WAKE_B]
    rendered = json.dumps(projection, sort_keys=True)
    assert "Canonical state consumed" not in rendered
    assert "SOL CONTINUE" not in rendered
    assert "/backend-api/" not in rendered


def test_content_producer_requires_provider_terminal_status_and_end_turn() -> None:
    pending = _run(
        assistant_text=_ack_text(),
        assistant_status="in_progress",
        assistant_end_turn=False,
    )["result"]
    assert pending["status"] == "CONTINUATION_ACK_PENDING"
    assert pending["provider_native_turn_id"] is None

    not_terminal = _run(
        assistant_text=_ack_text(),
        assistant_status="finished_successfully",
        assistant_end_turn=False,
    )["result"]
    assert not_terminal["status"] == "CONTINUATION_ACK_PENDING"


def test_provider_snapshot_transport_unavailable_is_pending_not_ack() -> None:
    projection = _run(assistant_text=_ack_text(), fetch_raises=True)["result"]
    assert projection["status"] == "CONTINUATION_ACK_PENDING"
    assert projection["acknowledged_obligation_ids"] == []


def test_provider_snapshot_auth_or_identity_refusal_fails_closed() -> None:
    projection = _run(assistant_text=_ack_text(), fetch_status=403)["result"]
    assert projection["status"] == "CONTINUATION_ACK_REFUSED"
    assert projection["provider_native_turn_id"] is None


def test_provider_snapshot_must_self_identify_exact_conversation() -> None:
    projection = _run(
        assistant_text=_ack_text(),
        snapshot_conversation_id="different-conversation-001",
    )["result"]
    assert projection["status"] == "CONTINUATION_ACK_REFUSED"
    assert projection["acknowledged_obligation_ids"] == []


def test_provider_snapshot_read_is_stream_bounded_and_requires_a_body() -> None:
    oversized = _run(
        assistant_text=_ack_text(),
        declared_length=8 * 1024 * 1024 + 1,
    )["result"]
    assert oversized["status"] == "CONTINUATION_ACK_REFUSED"

    missing = _run(assistant_text=_ack_text(), body_missing=True)["result"]
    assert missing["status"] == "CONTINUATION_ACK_REFUSED"


def test_background_uses_one_provider_observation_without_time_or_idle_semantics() -> None:
    source = BACKGROUND.read_text(encoding="utf-8")
    start = source.index("async function handleObserveContinuationAck")
    end = source.index("\nconst CENSUS_REQUEST_SCHEMA", start)
    handler = source[start:end]
    assert handler.count("semanticContentRequest(request)") == 1
    assert handler.count("freshProbe(") == 2
    assert "setTimeout" not in handler
    assert "SEMANTIC_STABILITY_MS" not in source
    assert 'generation_state === "active"' not in handler
    assert 'generation_state !== "idle"' not in handler
    assert "validSemanticContentResult(semantic, request)" in handler
    assert "bound.tabId !== resolved.tabId" in handler
    assert "sameSemanticTarget(current, bound)" in handler
    assert "sameSemanticTarget(finalTarget, bound)" in handler


BACKGROUND_SEMANTIC_EPOCH_HARNESS = r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const {webcrypto} = require('node:crypto');
(async () => {
  const background = fs.readFileSync(process.argv[1], 'utf8');
  const continuation = fs.readFileSync(process.argv[2], 'utf8');
  const input = JSON.parse(process.argv[3]);
  const A = input.request.conversation_fingerprint;
  const B = 'b'.repeat(64);
  const EPOCH_ONE = '1'.repeat(32);
  const EPOCH_TWO = '2'.repeat(32);
  let context;
  let actualFingerprint = A;
  let currentEpoch = EPOCH_ONE;
  const listeners = {};
  const event = (name) => ({addListener(fn) { listeners[name] = fn; }});
  const probe = () => ({
    kind:'MMX_WEB_SOL_PROBE',
    conversation_fingerprint:actualFingerprint,
    document_epoch:currentEpoch,
    observation:{
      schema:'mastermind.web_sol_surface_probe.v1',
      target_present:true, exact_conversation_loaded:actualFingerprint === A,
      page_responsive:true, document_ready_state:'complete', visibility:'visible',
      composer_available:true, generation_state:'idle', auth_required:false,
      provider_error_present:false,
    },
  });
  const semantic = (message) => ({
    schema:'mastermind.web_sol_continuation_ack_result.v1',
    conversation_fingerprint:A,
    turn_id:message.turn_id,
    directive_digest:message.directive_digest,
    session_alias:message.session_alias,
    runtime_binding_id:message.runtime_binding_id,
    runtime_binding_generation:message.runtime_binding_generation,
    runtime_binding_fingerprint:message.runtime_binding_fingerprint,
    wake_obligation_ids:[...message.wake_obligation_ids],
    wake_obligation_digest:message.wake_obligation_digest,
    provider_native_turn_id:'assistant-turn-current-001',
    acknowledged_obligation_ids:[...message.wake_obligation_ids],
    terminal_ack_trailer:true,
    document_epoch:input.scenario === 'document-rotated' ? EPOCH_TWO : EPOCH_ONE,
    status:'CONTINUATION_ACKNOWLEDGED',
  });
  const tabs = {
    query:async () => [],
    get:async (id) => ({id, windowId:10, active:false}),
    sendMessage:async (_id, message) => {
      if (message.kind === 'MMX_WEB_SOL_REPROBE') return probe();
      if (message.kind === 'MMX_WEB_SOL_OBSERVE_CONTINUATION_ACK') {
        if (input.scenario === 'aba') {
          context.advanceTabNavigationGeneration(7);
          actualFingerprint = B;
          context.recordProbe(probe(), {id:'ext', frameId:0, tab:{id:7, windowId:10}});
          context.advanceTabNavigationGeneration(7);
          actualFingerprint = A;
          context.recordProbe(probe(), {id:'ext', frameId:0, tab:{id:7, windowId:10}});
        }
        return semantic(message);
      }
      throw new Error('unexpected message kind: ' + message.kind);
    },
    update:async () => ({id:7, windowId:10, active:true}),
    onUpdated:event('updated'), onMoved:event('moved'), onAttached:event('attached'),
    onDetached:event('detached'), onReplaced:event('replaced'), onRemoved:event('removed'),
  };
  context = vm.createContext({
    chrome:{
      runtime:{id:'ext', onMessage:event('runtime'), connectNative(){throw new Error('no native');},
        getURL:(value) => 'chrome-extension://ext/' + value},
      tabs,
      windows:{get:async () => ({focused:false}), update:async () => ({focused:true})},
      alarms:{create(){}, clear:async () => true, getAll:async () => [], onAlarm:event('alarm')},
    },
    MMX_WEB_SOL_INSTANCE:null,
    MMXWebSolCensus:{collect:async () => null},
    crypto:webcrypto, TextEncoder, TextDecoder, URL, Date, Map, Set, Number, Array,
    Object, String, Boolean, RegExp, Promise, performance, setTimeout, clearTimeout,
    importScripts(name) {
      if (name === 'continuation_core.js') {
        vm.runInContext(continuation, context, {filename:name});
      }
    },
    console,
  });
  vm.runInContext(background, context, {filename:'background.js'});
  if (input.scenario === 'aba') {
    assert.equal(typeof context.advanceTabNavigationGeneration, 'function');
  }
  context.recordProbe(probe(), {id:'ext', frameId:0, tab:{id:7, windowId:10}});
  const result = await context.handleObserveContinuationAck(input.request);
  process.stdout.write(JSON.stringify(result));
})().catch((error) => { console.error(error.stack || error.message); process.exitCode = 1; });
"""


def _run_background_semantic_epoch(scenario: str) -> dict:
    node = shutil.which("node")
    assert node is not None
    request = _request()
    now = datetime.now(timezone.utc).replace(microsecond=0)
    request = {
        "schema": wsp.ACTION_SCHEMA,
        "binding_id": "11111111-1111-4111-8111-111111111111",
        "conversation_fingerprint": request.pop("expected_conversation_fingerprint"),
        "binding_fingerprint": "f" * 64,
        "action": "OBSERVE_CONTINUATION_ACK",
        "operation_key": f"web-sol-semantic-epoch:{scenario}",
        "issued_at": now.isoformat().replace("+00:00", "Z"),
        "expires_at": (now + timedelta(seconds=30)).isoformat().replace("+00:00", "Z"),
        "nonce": f"semantic-epoch-{scenario}-000001",
        **{key: value for key, value in request.items() if key != "kind"},
    }
    completed = subprocess.run(
        [
            node,
            "-e",
            BACKGROUND_SEMANTIC_EPOCH_HARNESS,
            str(BACKGROUND),
            str(EXTENSION / "continuation_core.js"),
            json.dumps({"scenario": scenario, "request": request}),
        ],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    return json.loads(completed.stdout)


def test_background_accepts_one_stable_document_and_navigation_generation() -> None:
    assert _run_background_semantic_epoch("stable")["status"] == "CONTINUATION_ACKNOWLEDGED"


def test_background_refuses_same_tab_a_to_b_to_a_navigation() -> None:
    assert _run_background_semantic_epoch("aba")["status"] == "CONTINUATION_ACK_REFUSED"


def test_background_refuses_rotated_document_epoch() -> None:
    assert _run_background_semantic_epoch("document-rotated")["status"] == "CONTINUATION_ACK_REFUSED"
