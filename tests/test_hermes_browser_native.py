"""Native registration, invocation identity, uncertainty and image presentation."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
from types import SimpleNamespace

import pytest

from test_hermes_omh_native import framework

ROOT=Path(__file__).resolve().parents[1]


def load(tmp_path):
    dest=tmp_path/"plugin";dest.mkdir()
    shutil.copyfile(ROOT/"integrations/hermes_harness/browser_plugin/__init__.py",dest/"__init__.py")
    spec=importlib.util.spec_from_file_location("browser_native_test_"+tmp_path.name,dest/"__init__.py")
    module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
    descriptor=dict(schema=module.RUNTIME_SCHEMA,release_commit="a"*40,source_root=str(ROOT),
        python_executable=sys.executable,profile_home=str(tmp_path/"profile"),bindings_path=str(tmp_path/"bindings.json"),
        source_files={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in module.SOURCE_FILES})
    (dest/"_runtime.json").write_text(json.dumps(descriptor));(dest/"_runtime.json").chmod(0o600)
    return module,descriptor,dest


def reply(raw,profile,*,image=False):
    envelope=json.loads(raw);arguments=envelope["arguments"]
    receipt=dict(schema="mastermind.web_sol_browser_receipt.v1",adapter_instance_id=arguments["browser_id"],
        session_id=hashlib.sha256((profile+"\0"+envelope["session_id"]).encode()).hexdigest(),
        operation_key=envelope["operation_key"],nonce=envelope["nonce"],action=arguments["action"],
        transport_boot_nonce=arguments.get("connection_id","connection-generation"),status="OK",effect="NOT_APPLIED",
        observed_at="2026-11-08T00:00:00Z",data={"mime_type":"image/jpeg","base64":"/9j/2Q=="} if image else {})
    return SimpleNamespace(returncode=0,stdout=json.dumps({"state":"RECEIPT","receipt":receipt,"retry_allowed":False}).encode(),stderr=b"")


def test_native_invocation_uses_exact_profile_and_existing_registry(tmp_path,monkeypatch):
    module,d,_=load(tmp_path);ctx,entries,calls,disposed,_=framework(monkeypatch,d["profile_home"])
    observed=[]
    def run(argv,**kwargs):
        observed.append((argv,kwargs));return reply(kwargs["input"],d["profile_home"])
    monkeypatch.setattr(module.subprocess,"run",run);monkeypatch.setenv("PROVIDER_API_KEY","SECRET_SENTINEL")
    handle=module.register(ctx);handler=calls[0]["handler"]
    arguments={"action":"status","browser_id":"a"*64}
    assert json.loads(handler(arguments))["reason"]=="NATIVE_SESSION_UNBOUND"
    assert observed==[]
    result=json.loads(handler(arguments,session_id="native-session"));assert result["state"]=="RECEIPT"
    argv,kwargs=observed[0];assert argv[:3]==[sys.executable,"-I","-B"]
    assert "SECRET_SENTINEL" not in str(kwargs["env"]) and "PYTHONPATH" not in kwargs["env"]
    assert not kwargs.get("shell") and kwargs["timeout"]==35
    assert json.loads(kwargs["input"])["session_id"]=="native-session"
    assert arguments=={"action":"status","browser_id":"a"*64}
    handle.dispose();assert json.loads(handler(arguments,session_id="native-session"))["reason"]=="NATIVE_REGISTRATION_STALE"
    assert len(observed)==1


@pytest.mark.parametrize("action,state",[("open","EFFECT_UNKNOWN"),("snapshot","UNAVAILABLE")])
def test_timeout_never_retries_and_keeps_parent_request_identity(tmp_path,monkeypatch,action,state):
    module,d,_=load(tmp_path);ctx,_,calls,_,_=framework(monkeypatch,d["profile_home"]);observed=[]
    def run(argv,**kwargs):
        observed.append(json.loads(kwargs["input"]));raise subprocess.TimeoutExpired(argv,28)
    monkeypatch.setattr(module.subprocess,"run",run);module.register(ctx)
    result=json.loads(calls[0]["handler"]({"action":action,"browser_id":"a"*64},session_id="native-session"))
    assert result["state"]==state and result["retry_allowed"] is False and len(observed)==1
    assert result["request_ref"]["nonce"]==observed[0]["nonce"]
    assert result["request_ref"]["operation_key"]==observed[0]["operation_key"]


@pytest.mark.parametrize("change",["profile","registration","source"])
def test_currentness_change_after_send_does_not_claim_no_effect(tmp_path,monkeypatch,change):
    module,d,where=load(tmp_path);ctx,entries,calls,_,constants=framework(monkeypatch,d["profile_home"])
    def run(argv,**kwargs):
        if change=="profile":constants.get_hermes_home=lambda:tmp_path/"different"
        elif change=="registration":entries.clear()
        else:(where/"_runtime.json").write_text("{}")
        return reply(kwargs["input"],d["profile_home"])
    monkeypatch.setattr(module.subprocess,"run",run);module.register(ctx)
    result=json.loads(calls[0]["handler"]({"action":"open","browser_id":"a"*64},session_id="native-session"))
    assert result["state"]=="EFFECT_UNKNOWN" and result["reason"]=="NATIVE_REGISTRATION_CHANGED"


def test_screenshot_is_presented_as_hermes_multimodal_content(tmp_path,monkeypatch):
    module,d,_=load(tmp_path);ctx,_,calls,_,_=framework(monkeypatch,d["profile_home"])
    monkeypatch.setattr(module.subprocess,"run",lambda argv,**kwargs:reply(kwargs["input"],d["profile_home"],image=True))
    module.register(ctx);result=calls[0]["handler"]({"action":"screenshot","browser_id":"a"*64},session_id="native-session")
    assert result["_multimodal"] is True and result["content"][1]["type"]=="image_url"
    assert result["content"][1]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    assert "base64" not in result["text_summary"]


def test_wrong_receipt_identity_after_send_is_uncertain(tmp_path,monkeypatch):
    module,d,_=load(tmp_path);ctx,_,calls,_,_=framework(monkeypatch,d["profile_home"])
    def run(argv,**kwargs):
        response=reply(kwargs["input"],d["profile_home"]);data=json.loads(response.stdout)
        data["receipt"]["session_id"]="wrong-session";response.stdout=json.dumps(data).encode();return response
    monkeypatch.setattr(module.subprocess,"run",run);module.register(ctx)
    result=json.loads(calls[0]["handler"]({"action":"open","browser_id":"a"*64},session_id="native-session"))
    assert result["state"]=="EFFECT_UNKNOWN" and result["reason"]=="NATIVE_LOCAL_OUTPUT_INVALID"


def test_descriptor_closure_and_profile_collision_fail_closed(tmp_path,monkeypatch):
    module,d,where=load(tmp_path);ctx,_,calls,_,_=framework(monkeypatch,d["profile_home"])
    module.register(ctx)
    with pytest.raises(module.NativeBrowserError,match="NATIVE_TOOL_COLLISION"):module.register(ctx)
    assert len(calls)==1
    d["source_files"].pop("integrations/chairman_surfaces/web_sol_client.py")
    (where/"_runtime.json").write_text(json.dumps(d))
    with pytest.raises(module.NativeBrowserError,match="NATIVE_DESCRIPTOR_INVALID"):module.load_runtime()

