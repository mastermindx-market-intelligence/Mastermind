"""The original Worker factory composes DSH without dispatching a provider."""
import asyncio
import dataclasses
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from control_plane.executive_agent_capabilities import ExecutionCapabilityRegistry
from control_plane.executive_worker_broker import BrokerStateError
from control_plane.operator_harness_contract import RequestedExecutionProfile, WorkspaceIdentity
from integrations.deepseek_harness.operator_adapter import NativeOperatorAdapter
from scripts import executive_os_phase1c_worker as worker
from test_native_deepseek_attestation import deepseek_installation
from test_native_worker_factory import native_config
from test_subscription_worker_config import _write_config


def config(i):
    value=native_config(i.root)
    value.update(native_provider="deepseek",operator_harness_armed=True,
        control_uid=os.geteuid()+1000,allowed_supplementary_gids=[12,61,100],
        deepseek_node_binary=str(i.binary),deepseek_release=str(i.release),
        deepseek_attestation_receipt=str(i.receipt),allowed_node_versions=["v26.5.0"])
    for field in ("codex_binary","codex_attestation_receipt","allowed_codex_versions","required_team_identifier"):
        del value[field]
    value["native_realm_enrollment"]["provider_binary_sha256"]=i.document["node"]["sha256"]
    return value


@pytest.fixture
def prepared(deepseek_installation,monkeypatch):
    i=deepseek_installation;value=config(i)
    for field in ("workspace_root","run_root","provider_home"):
        Path(value[field]).mkdir(mode=0o700)
    monkeypatch.setattr(worker,"_ROOT",i.root/("a"*40))
    monkeypatch.setattr(worker,"_build_autonomy_canary_factory",lambda c:lambda p:{})
    # Construction fixture only. The installed -I -S -B SDK/profile consumer
    # has separate real-wheel and original-interpreter qualification.
    i.dependency_checks=[]
    monkeypatch.setattr(worker,"_activate_native_deepseek_dependencies",
        lambda installed,uid:SimpleNamespace(require_current=lambda:i.dependency_checks.append(uid)))
    # The production default registry is the same owner used by Runtime and
    # Supervisor. Only physical installation/dependency observations are inert.
    registry=ExecutionCapabilityRegistry.load()
    profile=registry.resolve("operator.dsh.native-conversation.v1")
    profiles=registry.profiles
    workspace=Path(value["workspace_root"]);info=workspace.stat()
    identity=WorkspaceIdentity(str(workspace),"b"*40,info.st_dev,info.st_ino,info.st_uid,info.st_gid)
    requested=RequestedExecutionProfile(value["worker_id"],"acp","deepseek-chat","dsh-native-web-acp",
        i.document["node"]["sha256"],"v26.5.0",identity,profile.sandbox_policy,profile.approval_policy,
        profile.network_policy,profile.capability_manifest(harness_binary_digest=i.document["node"]["sha256"]),
        profile.native_helper_policy,"c"*64,expected_config_digest=profile.expected_config_digest)
    return i,value,profiles,profile,requested


def test_closed_native_config_is_a_distinct_provider(deepseek_installation):
    value=config(deepseek_installation)
    assert worker._load_config(_write_config(deepseek_installation.root,value),
                              require_root_owner=False)==value


@pytest.mark.parametrize("change",["argv","environment","codex","account","relative-release","node-version"])
def test_no_caller_launch_or_borrowed_provider_fields(deepseek_installation,change):
    i=deepseek_installation;value=config(i)
    if change=="argv":value["argv"]=["node","unqualified"]
    elif change=="environment":value["environment"]={"TOKEN":"untrusted"}
    elif change=="codex":value["codex_binary"]=str(i.binary)
    elif change=="account":value["provider_account_id"]="caller"
    elif change=="relative-release":value["deepseek_release"]="relative"
    else:value["allowed_node_versions"]=["26.5.0"]
    with pytest.raises(worker.WorkerConfigError):
        worker._load_config(_write_config(i.root,value),require_root_owner=False)


def test_actual_broker_and_adapter_use_only_original_loop_and_owner(prepared,monkeypatch):
    i,value,_,_,requested=prepared
    monkeypatch.setenv("NODE_OPTIONS","--import /untrusted")
    monkeypatch.setenv("CODEX_HOME","/other/provider")
    before=list(i.calls)
    async def exercise():
        broker=worker._build_broker(value,autonomy_guard=lambda:None)
        assert broker.adapter is None and broker.validation_adapter is None
        loader=lambda turn:"one original input"
        adapter=broker.operator_adapter_factory(Path(value["workspace_root"]),loader,requested)
        assert type(adapter) is NativeOperatorAdapter
        assert adapter.loop is asyncio.get_running_loop() and adapter.turn_input_loader is loader
        assert adapter.native is None and adapter.pending_calls==set()
        assert i.dependency_checks==[value["worker_uid"]]
        adapter.binding.verify_source()
        assert i.dependency_checks==[value["worker_uid"]]*2
        assert adapter.binding.argv==(str(i.binary),str(i.entry))
        assert adapter.binding.binary.sha256==requested.harness_binary_digest
        assert adapter.binding.environment["DSH_HOME"]==value["provider_home"]
        assert "NODE_OPTIONS" not in adapter.binding.environment and "CODEX_HOME" not in adapter.binding.environment
        assert adapter.binding.protocol_profile.agent_version=="0.0.1"
        assert adapter.binding.protocol_profile.model_option_value("deepseek-chat")=='["deepseek-account","deepseek-chat"]'
        assert adapter.binding.protocol_profile.auth_method is None
        assert adapter.validate_requested_profile(requested).accepted
        with pytest.raises(BrokerStateError,match="original native effect owner"):
            adapter.binding.require_current_effect(None,None,None,"session/new",None)
        calls=[]
        monkeypatch.setattr(broker,"require_native_operator_effect",lambda *args:calls.append(args))
        adapter.binding.require_current_effect("op","epoch","generation","session/prompt","session")
        assert calls==[(adapter,"op","epoch","generation","session/prompt","session")]
        marker=object()
        class OriginalNative:
            async def observe(self):return marker
        with pytest.raises(worker.WorkerConfigError,match="original process"):
            await adapter.binding.observe_attestation(OriginalNative())
        payload=json.loads(adapter.binding.environment["MMX_NATIVE_EXECUTION_POLICY"])
        assert payload["profile_id"]=="operator.dsh.native-conversation.v1"
        assert payload["config"]==prepared[3].dsh_native_config_projection()
        assert payload["expected_config_digest"]==requested.expected_config_digest
        assert set(payload)=={"schema","profile_id","profile_digest","policy_digest","expected_config_digest","config","model"}
        assert not any(key in payload for key in ("worker_id","account","workspace","attestation"))
    asyncio.run(exercise())
    assert i.calls==before


@pytest.mark.parametrize("change",["disabled","duplicate","worker","provider","binary","version",
                                    "write-path","configuration","capabilities","network"])
def test_factory_refuses_before_constructing_or_sending(prepared,monkeypatch,change):
    _,value,profiles,profile,requested=prepared
    if change in {"disabled","duplicate"}:
        policy_digest=ExecutionCapabilityRegistry.load().policy_digest
        monkeypatch.setattr(worker.ExecutionCapabilityRegistry,"load",
            lambda:SimpleNamespace(profiles=profiles,policy_digest=policy_digest))
    if change=="disabled":profiles[profile.profile_id]=dataclasses.replace(profile,enabled=False)
    elif change=="duplicate":profiles["duplicate"]=profile
    else:
        changes={"worker":{"worker_id":"foreign"},"provider":{"provider":"openai-codex"},
            "binary":{"harness_binary_digest":"f"*64},"version":{"harness_version":"v0.0.0"},
            "write-path":{"allowed_write_paths":("/other",)},
            "configuration":{"expected_config_digest":"f"*64},
            "capabilities":{"capabilities":None},"network":{"network_policy":"enabled"}}
        requested=dataclasses.replace(requested,**changes[change])
    async def exercise():
        broker=worker._build_broker(value,autonomy_guard=lambda:None)
        with pytest.raises(worker.WorkerConfigError):
            broker.operator_adapter_factory(Path(value["workspace_root"]),lambda t:"",requested)
        assert broker._operator_run is None
    asyncio.run(exercise())


@pytest.mark.parametrize("change",["source","node-enrollment","retained-package"])
def test_installed_source_and_realm_join_is_current(prepared,monkeypatch,change):
    i,value,*_=prepared
    if change=="source":monkeypatch.setattr(worker,"_ROOT",i.root/("d"*40))
    elif change=="node-enrollment":value["native_realm_enrollment"]["provider_binary_sha256"]="e"*64
    else:(i.release/"unqualified.js").write_text("changed")
    with pytest.raises(worker.WorkerConfigError,match="Node/package attestation refused"):
        worker._load_native_deepseek_installation(value)


def test_deepseek_never_opens_a_codex_account_scope(prepared,monkeypatch):
    _,value,*_=prepared;marker=object();calls=[]
    monkeypatch.setattr(worker,"native_codex_account_scope",
                        lambda *a,**kw:pytest.fail("DeepSeek borrowed Codex account"))
    monkeypatch.setattr(worker,"_build_broker",lambda c,**kw:marker)
    async def serve(broker,name):
        assert broker is marker and name==value["launchd_socket_name"];calls.append(name)
    monkeypatch.setattr(worker,"_serve_broker",serve)
    asyncio.run(worker._serve(value));assert len(calls)==1


def test_deepseek_refuses_a_borrowed_codex_lifetime(prepared):
    _,value,*_=prepared
    with pytest.raises(worker.WorkerConfigError,match="cannot borrow a Codex"):
        worker._build_broker(value,native_account=object())


def node_owner(prepared, adapter, monkeypatch, *, change=None):
    import hashlib
    from control_plane import codex_operator_adapter as implementation
    from integrations.deepseek_harness.native_protocol import native_observation
    from test_dsh_native_protocol import owner_facts_wire
    i,value,_,_,requested=prepared
    wire=owner_facts_wire();facts=wire["facts"]
    facts["session_cwd"]=requested.workspace.workspace_path
    facts["workspace"]={key:getattr(requested.workspace,key) for key in ("workspace_path","device","inode","uid","gid")}
    facts["process"].update(uid=value["worker_uid"],gid=value["worker_gid"],exec_path=str(i.binary),
        binary_sha256=requested.harness_binary_digest)
    facts["source"].update(entry_path=str(i.entry),entry_sha256=hashlib.sha256(i.entry.read_bytes()).hexdigest())
    identities=[requested.workspace,requested.workspace]
    monkeypatch.setattr(implementation,"_default_base_sha",lambda path:identities.pop(0).base_sha)
    identity=SimpleNamespace(pid=123,effective_uid=value["worker_uid"],effective_gid=value["worker_gid"])
    resource=SimpleNamespace(identity=identity,identity_matches=lambda:True)
    async def observe():
        if change=="resource":resource.identity=SimpleNamespace(**vars(identity))
        if change=="closed":adapter.close_operation=object()
        return native_observation(wire,"original-native")
    native=SimpleNamespace(resource=resource,provider_session_id="original-native",observe=observe)
    adapter.native=native
    return native,wire,identities

def test_factory_joins_actual_node_facts_to_original_worker_and_observed_git(prepared,monkeypatch):
    _,value,_,_,requested=prepared
    async def exercise():
        broker=worker._build_broker(value,autonomy_guard=lambda:None)
        adapter=broker.operator_adapter_factory(Path(value["workspace_root"]),lambda t:"",requested)
        native,wire,_=node_owner(prepared,adapter,monkeypatch)
        observed=await adapter.binding.observe_attestation(native)
        assert observed.auth.worker_id==value["worker_id"] and observed.auth.provider=="acp"
        assert observed.auth.identity_confidence.value=="SLOT_ONLY"
        assert observed.auth.nonsecret_provider_account_id is None
        assert observed.workspace == requested.workspace
        assert observed.served_model=="deepseek-chat"
        assert not any(key in wire["facts"] for key in ("worker_id","base_sha","principal"))
    asyncio.run(exercise())

@pytest.mark.parametrize("change",["pid","uid","gid","binary","source","workspace","git","account","inventory","provider","resource","closed"])
def test_factory_refuses_mismatched_or_retired_original_facts(prepared,monkeypatch,change):
    _,value,_,_,requested=prepared
    async def exercise():
        broker=worker._build_broker(value,autonomy_guard=lambda:None)
        adapter=broker.operator_adapter_factory(Path(value["workspace_root"]),lambda t:"",requested)
        native,wire,identities=node_owner(prepared,adapter,monkeypatch,change=change)
        facts=wire["facts"]
        if change in ("pid","uid","gid"):facts["process"][change]+=1
        elif change=="binary":facts["process"]["binary_sha256"]="f"*64
        elif change=="source":facts["source"]["entry_sha256"]="f"*64
        elif change=="workspace":facts["workspace"]["inode"]+=1
        elif change=="git":identities[1]=dataclasses.replace(requested.workspace,base_sha="e"*40)
        elif change=="account":facts["account"]=None
        elif change=="inventory":facts["effective_mcp"]=None
        elif change=="provider":facts["selection"]["provider"]="foreign"
        with pytest.raises(worker.WorkerConfigError):
            await adapter.binding.observe_attestation(native)
    asyncio.run(exercise())

def test_factory_policy_currentness_uses_original_registry_digest(prepared,monkeypatch):
    _,value,profiles,_,requested=prepared
    async def exercise():
        broker=worker._build_broker(value,autonomy_guard=lambda:None)
        adapter=broker.operator_adapter_factory(Path(value["workspace_root"]),lambda t:"",requested)
        monkeypatch.setattr(worker.ExecutionCapabilityRegistry,"load",
            lambda:SimpleNamespace(profiles=profiles,policy_digest="f"*64))
        with pytest.raises(worker.WorkerConfigError,match="policy changed"):
            adapter.binding.verify_source()
    asyncio.run(exercise())
