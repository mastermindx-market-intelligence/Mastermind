from __future__ import annotations

from datetime import datetime, timedelta, timezone
import inspect
import json
from pathlib import Path
import shutil
import subprocess

import pytest

from control_plane import surface_bindings as sb
from control_plane.session_targets import SessionTarget
from integrations.chairman_surfaces import web_sol_client as client
from integrations.chairman_surfaces import web_sol_instance as wsi
from integrations.chairman_surfaces import web_sol_protocol as wsp
from integrations.chairman_surfaces import web_sol_runtime_binding as wrb


ROOT = Path(__file__).resolve().parents[1]
CONTENT = ROOT / "integrations/chairman_surfaces/web_sol_extension/content.js"
BACKGROUND = ROOT / "integrations/chairman_surfaces/web_sol_extension/background.js"
HEX_A = "a" * 64
HEX_B = "b" * 64
TURN_ID = "ohf-turn-r2-0001"
NONCE = "continuation-nonce-00000001"
OPERATION = "web-sol-session-runtime-r2-20260916-sol-001"


def binding() -> dict:
    return sb.new_binding(
        work_ref="WS:CHAIRMAN-CONTROL-ROOM",
        role="ceo",
        provider="chatgpt",
        locator_kind="chatgpt_managed_env",
        locator={
            "env_manager": "gologin",
            "profile_id": "aaaaaaaaaaaaaaaaaaaaaaaa",
            "url": "https://chatgpt.com/c/session-alpha",
        },
        observed_at="2026-09-16T20:00:00Z",
        seat_ref="chatgpt-seat-1",
        binding_id="11111111-1111-4111-8111-111111111111",
    )


RUNTIME_BOOT = "runtime-boot-nonce-r2-fixture-0001"
SESSION_ALIAS = "EXECUTIVE-CEO-A"


def runtime_lease(
    row: dict | None = None,
    *,
    boot_nonce: str = RUNTIME_BOOT,
) -> wrb.WebSolRuntimeBindingLease:
    navigation = row or binding()
    target = wrb.ExactWebSolTarget(
        adapter_instance_id=wsi.adapter_instance_id(navigation),
        seat_ref=navigation["seat_ref"],
        env_manager=navigation["locator"]["env_manager"],
        folder_id=navigation["locator"].get("folder_id"),
        profile_id=navigation["locator"]["profile_id"],
        conversation_fingerprint=HEX_A,
        census_digest="c" * 64,
    )
    logical = SessionTarget(
        session_alias=SESSION_ALIAS,
        target_seat="ceo",
        reasoning_surface="chatgpt-sol",
        wake_transport="chatgpt-gui",
        allowed_transports=("chatgpt-gui",),
        workstream="executive",
        target_enabled=True,
    )
    projected = wrb.project_runtime_binding(
        target,
        logical,
        boot_nonce=boot_nonce,
    )
    return wrb.WebSolRuntimeBindingLease(
        target=target,
        runtime_binding=projected,
        runtime_binding_fingerprint=wrb.runtime_binding_fingerprint(
            projected,
            target,
        ),
    )


def request(**overrides) -> dict:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    lease = runtime_lease()
    value = {
        "schema": wsp.ACTION_SCHEMA,
        "binding_id": "11111111-1111-4111-8111-111111111111",
        "conversation_fingerprint": HEX_A,
        "binding_fingerprint": HEX_B,
        "action": "SUBMIT_CONTINUATION",
        "operation_key": OPERATION,
        "issued_at": now.isoformat().replace("+00:00", "Z"),
        "expires_at": (now + timedelta(seconds=30)).isoformat().replace("+00:00", "Z"),
        "nonce": NONCE,
        "turn_id": TURN_ID,
        "directive_digest": wsp.CONTINUATION_DIRECTIVE_DIGEST,
        "session_alias": lease.runtime_binding.session_alias,
        "runtime_binding_id": lease.runtime_binding.binding_id,
        "runtime_binding_generation": lease.runtime_binding.binding_generation,
        "runtime_binding_fingerprint": lease.runtime_binding_fingerprint,
    }
    value.update(overrides)
    return value


def observation(*, generation_state: str = "idle", exact: bool = True) -> dict:
    return {
        "schema": wsp.PROBE_SCHEMA,
        "target_present": exact,
        "exact_conversation_loaded": exact,
        "page_responsive": True,
        "document_ready_state": "complete",
        "visibility": "hidden",
        "composer_available": True,
        "generation_state": generation_state,
        "auth_required": False,
        "provider_error_present": False,
    }


def receipt(req: dict, status: str, *, generation_state: str = "idle") -> dict:
    return {
        "schema": wsp.RECEIPT_SCHEMA,
        "binding_id": req["binding_id"],
        "conversation_fingerprint": req["conversation_fingerprint"],
        "binding_fingerprint": req["binding_fingerprint"],
        "action": req["action"],
        "operation_key": req["operation_key"],
        "nonce": req["nonce"],
        "status": status,
        "observed_at": "2026-09-16T20:00:01Z",
        "observation": observation(generation_state=generation_state),
        "turn_id": req["turn_id"],
        "directive_digest": req["directive_digest"],
        "session_alias": req["session_alias"],
        "runtime_binding_id": req["runtime_binding_id"],
        "runtime_binding_generation": req["runtime_binding_generation"],
        "runtime_binding_fingerprint": req["runtime_binding_fingerprint"],
    }


def test_continuation_action_is_a_new_advertised_package_generation():
    assert wsp.WEB_SOL_PACKAGE_VERSION == "0.4.0"
    assert "SUBMIT_CONTINUATION" in {item.value for item in wsp.SurfaceAction}
    assert len(wsp.CONTINUATION_DIRECTIVE_DIGEST) == 64
    assert "Continue the same logical responsibility." in wsp.CONTINUATION_DIRECTIVE_TEXT


def test_fixed_directive_is_identical_across_protocol_and_extension_layers():
    import hashlib
    import re

    content = CONTENT.read_text(encoding="utf-8")
    match = re.search(
        r'const CONTINUATION_DIRECTIVE_TEXT = \[(.*?)\]\.join\("\\n"\);',
        content,
        re.DOTALL,
    )
    assert match is not None
    array_body = re.sub(r",\s*$", "", match.group(1))
    lines = json.loads("[" + array_body + "]")
    rendered = "\n".join(lines)
    assert rendered == wsp.CONTINUATION_DIRECTIVE_TEXT
    assert hashlib.sha256(rendered.encode("utf-8")).hexdigest() == wsp.CONTINUATION_DIRECTIVE_DIGEST
    assert wsp.CONTINUATION_DIRECTIVE_DIGEST in content
    helper = (
        ROOT / "integrations/chairman_surfaces/web_sol_extension/continuation_core.js"
    ).read_text(encoding="utf-8")
    assert wsp.CONTINUATION_DIRECTIVE_DIGEST in helper


def test_continuation_request_is_closed_and_cannot_carry_caller_text():
    accepted = wsp.validate_request(request())
    assert accepted["turn_id"] == TURN_ID
    assert accepted["directive_digest"] == wsp.CONTINUATION_DIRECTIVE_DIGEST
    for forbidden in ("prompt", "message", "text", "body", "instruction"):
        with pytest.raises(wsp.WebSolProtocolError):
            wsp.validate_request({**request(), forbidden: "caller-controlled"})
    with pytest.raises(wsp.WebSolProtocolError, match="directive_digest"):
        wsp.validate_request(request(directive_digest="f" * 64))
    with pytest.raises(wsp.WebSolProtocolError, match="turn_id"):
        wsp.validate_request(request(turn_id="bad turn id"))


def test_continuation_receipts_distinguish_none_possible_and_started():
    req = request()
    assert wsp.validate_receipt(
        receipt(req, "CONTINUATION_NOT_SUBMITTED")
    )["status"] == "CONTINUATION_NOT_SUBMITTED"
    assert wsp.validate_receipt(
        receipt(req, "CONTINUATION_SUBMIT_EFFECT_UNKNOWN")
    )["status"] == "CONTINUATION_SUBMIT_EFFECT_UNKNOWN"
    started = receipt(req, "CONTINUATION_STARTED", generation_state="active")
    assert wsp.validate_receipt(started)["status"] == "CONTINUATION_STARTED"
    with pytest.raises(wsp.WebSolProtocolError, match="generation_state"):
        wsp.validate_receipt(receipt(req, "CONTINUATION_STARTED", generation_state="idle"))


def test_client_exposes_only_fixed_semantic_continuation_not_generic_text(monkeypatch):
    row = binding()
    signature = inspect.signature(client.submit_continuation_via_extension)
    assert list(signature.parameters) == [
        "binding",
        "runtime_binding_lease",
        "operation_key",
        "turn_id",
        "issued_at",
        "expires_at",
        "nonce",
    ]
    for forbidden in ("prompt", "message", "text", "instruction", "selector", "url", "retry"):
        assert forbidden not in signature.parameters

    seen = []

    def exchange(
        req,
        *,
        path,
        expected_instance_id,
        on_handshake=None,
        before_action=None,
    ):
        handshake = {"boot_nonce": RUNTIME_BOOT}
        if on_handshake is not None:
            on_handshake(handshake)
        if before_action is not None:
            before_action(handshake)
        seen.append(req)
        return receipt(req, "CONTINUATION_STARTED", generation_state="active")

    monkeypatch.setattr(client, "_exchange_web_sol_socket", exchange)
    result = client.submit_continuation_via_extension(
        row,
        runtime_lease(row),
        operation_key=OPERATION,
        turn_id=TURN_ID,
        issued_at="2026-09-16T20:00:00Z",
        expires_at="2026-09-16T20:00:30Z",
        nonce=NONCE,
    )
    assert result["status"] == "CONTINUATION_STARTED"
    assert len(seen) == 1
    assert seen[0]["action"] == "SUBMIT_CONTINUATION"
    assert seen[0]["turn_id"] == TURN_ID
    assert seen[0]["directive_digest"] == wsp.CONTINUATION_DIRECTIVE_DIGEST
    assert not any(key in seen[0] for key in ("prompt", "message", "text", "instruction"))


def test_native_host_fences_same_turn_even_if_caller_changes_nonce():
    import importlib

    host = importlib.import_module("integrations.chairman_surfaces.web_sol_native_host")
    host._SUBMIT_CONTINUATION_NONCES.clear()
    host._SUBMIT_CONTINUATION_TURNS.clear()
    first = request()
    writes: list[dict] = []
    result = host.forward_request(
        first,
        write_chrome=writes.append,
        read_chrome=lambda _timeout: receipt(
            first, "CONTINUATION_STARTED", generation_state="active"
        ),
        timeout_seconds=1.0,
        expected_instance_id=runtime_lease().target.adapter_instance_id,
        boot_nonce=RUNTIME_BOOT,
    )
    assert result["status"] == "CONTINUATION_STARTED"
    second = request(nonce="continuation-nonce-00000002")
    with pytest.raises(host.NativeHostError, match="continuation_turn_reused"):
        host.forward_request(
            second,
            write_chrome=writes.append,
            read_chrome=lambda _timeout: None,
            timeout_seconds=1.0,
            expected_instance_id=runtime_lease().target.adapter_instance_id,
            boot_nonce=RUNTIME_BOOT,
        )
    assert writes == [first]


CONTENT_HARNESS = r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const {webcrypto, createHash} = require('node:crypto');
(async () => {
  const source = fs.readFileSync(process.argv[1], 'utf8');
  const scenario = process.argv[2];
  const url = 'https://chatgpt.com/c/session-alpha';
  const fp = createHash('sha256').update(url).digest('hex');
  let clicks = 0, dispatched = 0, text = '';
  const composer = {
    isContentEditable:true, childNodes:[],
    getAttribute:name => name === 'contenteditable' ? 'true' : null,
    replaceChildren(...nodes){text=nodes.map(x=>x.data||'').join('');composer.childNodes=nodes;},
    dispatchEvent(){dispatched++;return true;}, focus(){},
  };
  const send = {disabled:false,getAttribute:()=>null,click(){clicks++;if(scenario==='click-throws')throw Error('boom');}};
  const document = {
    visibilityState:'visible', readyState:'complete',
    createTextNode:value=>({data:value}),
    querySelector(selector){
      if(selector==='#prompt-textarea'||selector==="[data-testid='prompt-textarea']")
        return scenario==='no-composer'?null:composer;
      if(selector==="button[data-testid='send-button']"||selector==="button[data-testid='composer-submit-button']")
        return scenario==='no-send'?null:send;
      return null;
    },
  };
  const listeners=[];
  const context=vm.createContext({TextEncoder,Uint8Array,location:{origin:'https://chatgpt.com',pathname:'/c/session-alpha'},document,
    crypto:webcrypto,InputEvent:function(){},Event:function(){},setTimeout,clearTimeout,
    chrome:{runtime:{onMessage:{addListener:f=>listeners.push(f)},sendMessage:()=>{}}}});
  vm.runInContext(source,context,{filename:'content.js'});
  const request={kind:'MMX_WEB_SOL_SUBMIT_CONTINUATION',expected_conversation_fingerprint:fp,
    turn_id:'ohf-turn-r2-0001',directive_digest:vm.runInContext('CONTINUATION_DIRECTIVE_DIGEST',context),
    session_alias:'EXECUTIVE-CEO-A',runtime_binding_id:'bind-wsx-'+ 'c'.repeat(48),
    runtime_binding_generation:1,runtime_binding_fingerprint:'d'.repeat(64)};
  const result=await context.submitContinuation(request);
  if(scenario==='success'){
    assert.equal(result.effect,'SUBMIT_TRIGGERED');assert.equal(clicks,1);assert.equal(dispatched>0,true);
    assert.equal(text,vm.runInContext('CONTINUATION_DIRECTIVE_TEXT',context));
  } else if(scenario==='no-composer'||scenario==='no-send') {
    assert.equal(result.effect,'NOT_SUBMITTED');assert.equal(clicks,0);assert.equal(text,'');
  } else if(scenario==='click-throws') {
    assert.equal(result.effect,'SUBMIT_EFFECT_UNKNOWN');assert.equal(clicks,1);
  } else throw Error('unknown scenario');
})().catch(error=>{console.error(error.stack||error.message);process.exitCode=1;});
"""


@pytest.mark.parametrize("scenario", ["success", "no-composer", "no-send", "click-throws"])
def test_real_content_script_has_fixed_fill_only_submission_contract(scenario):
    node = shutil.which("node")
    assert node is not None
    completed = subprocess.run(
        [node, "-e", CONTENT_HARNESS, str(CONTENT), scenario],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


BACKGROUND_HARNESS = r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const {webcrypto} = require('node:crypto');
(async()=>{
 const source=fs.readFileSync(process.argv[1],'utf8'); const scenario=process.argv[2];
 const helper=fs.readFileSync(process.argv[4],'utf8');
 const A='a'.repeat(64),B='b'.repeat(64),D=process.argv[3]; let generation='idle',submitCalls=0;
 const event=()=>({addListener(){}});
 const probe=()=>({kind:'MMX_WEB_SOL_PROBE',conversation_fingerprint:A,observation:{schema:'mastermind.web_sol_surface_probe.v1',
  target_present:true,exact_conversation_loaded:true,page_responsive:true,document_ready_state:'complete',visibility:'hidden',
  composer_available:true,generation_state:generation,auth_required:false,provider_error_present:false}});
 const tabs={query:async()=>[],get:async id=>({id,windowId:10,active:false,url:'https://chatgpt.com/c/session-alpha'}),
  sendMessage:async(id,message)=>{
   if(message.kind==='MMX_WEB_SOL_REPROBE')return probe();
   if(message.kind==='MMX_WEB_SOL_SUBMIT_CONTINUATION'){
    submitCalls++; if(scenario==='started')generation='active';
    return {schema:'mastermind.web_sol_continuation_submit_result.v1',conversation_fingerprint:A,
      turn_id:message.turn_id,directive_digest:message.directive_digest,
      session_alias:message.session_alias,runtime_binding_id:message.runtime_binding_id,
      runtime_binding_generation:message.runtime_binding_generation,
      runtime_binding_fingerprint:message.runtime_binding_fingerprint,effect:'SUBMIT_TRIGGERED'};
   }
   throw Error('unexpected message');
  },update:async()=>({id:7,windowId:10,active:true}),onUpdated:event(),onMoved:event(),onAttached:event(),onDetached:event(),onReplaced:event(),onRemoved:event()};
 const context=vm.createContext({chrome:{runtime:{id:'ext',onMessage:event(),connectNative(){throw Error('no native');},getURL:x=>'chrome-extension://ext/'+x},
  tabs,windows:{get:async()=>({focused:false}),update:async()=>({focused:true})},alarms:{create(){},clear:async()=>true,getAll:async()=>[],onAlarm:event()}},
  MMX_WEB_SOL_INSTANCE:null,MMXWebSolCensus:{collect:async()=>null},crypto:webcrypto,TextEncoder,TextDecoder,URL,Date,Map,Set,Number,Array,Object,String,Boolean,RegExp,Promise,
  performance,setTimeout,clearTimeout,importScripts(name){if(name==='continuation_core.js')vm.runInContext(helper,context,{filename:name});},console});
 vm.runInContext(source,context,{filename:'background.js'});
 context.recordProbe(probe(),{id:'ext',frameId:0,tab:{id:7,windowId:10}});
 const req={schema:'mastermind.web_sol_surface_action.v1',binding_id:'11111111-1111-4111-8111-111111111111',conversation_fingerprint:A,
  binding_fingerprint:B,action:'SUBMIT_CONTINUATION',operation_key:'web-sol-r2-fixture',issued_at:new Date().toISOString(),
  expires_at:new Date(Date.now()+30000).toISOString(),nonce:'continuation-nonce-00000001',turn_id:'ohf-turn-r2-0001',directive_digest:D,
  session_alias:'EXECUTIVE-CEO-A',runtime_binding_id:'bind-wsx-'+ 'c'.repeat(48),runtime_binding_generation:1,
  runtime_binding_fingerprint:'d'.repeat(64)};
 const first=await context.handleSubmitContinuation(req);
 if(scenario==='started')assert.equal(first.status,'CONTINUATION_STARTED');
 else assert.equal(first.status,'CONTINUATION_SUBMIT_EFFECT_UNKNOWN');
 const second=await context.handleSubmitContinuation({...req,nonce:'continuation-nonce-00000002'});
 assert.equal(second.status,'CONTINUATION_NOT_SUBMITTED');
 assert.equal(submitCalls,1,'same turn must never submit twice');
})().catch(error=>{console.error(error.stack||error.message);process.exitCode=1;});
"""


@pytest.mark.parametrize("scenario", ["started", "not-observed"])
def test_real_background_fences_one_turn_and_observes_start_or_unknown(scenario):
    node = shutil.which("node")
    assert node is not None
    completed = subprocess.run(
        [
            node,
            "-e",
            BACKGROUND_HARNESS,
            str(BACKGROUND),
            scenario,
            wsp.CONTINUATION_DIRECTIVE_DIGEST,
            str(ROOT / "integrations/chairman_surfaces/web_sol_extension/continuation_core.js"),
        ],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
