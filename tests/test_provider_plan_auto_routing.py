"""Original request/picker AUTO join; controlled owner observations, no provider calls."""
from __future__ import annotations
import copy
import hashlib
import importlib
import json
import os
from pathlib import Path
import shutil
import socket
import sqlite3
import sys
import time
from types import SimpleNamespace
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]

@pytest.fixture(scope="module")
def source_stage(tmp_path_factory):
    target = tmp_path_factory.mktemp("provider-auto-source")
    candidate = os.environ.get("MMX_PROVIDER_AUTO_TEST_STAGE")
    if candidate:
        shutil.copytree(Path(candidate)/"ext", target/"ext")
    else:
        # The source-linked predecessor fixture is materialized and every
        # input hash checked before applying the actual production composer.
        import base64, zlib
        from ops.native_fabric.provider_plans import compose
        fixture = json.loads((ROOT/"tests/fixtures/provider-plan-auto-predecessor.json").read_text())
        profile = json.loads((compose.HERE/"profile.json").read_text())
        assert fixture["schema"] == "mastermind.provider_plan_test_predecessor.v1"
        assert fixture["files"] == profile["base_files"]
        base = target/"base"
        for relative, spec in fixture["sources"].items():
            raw = ((ROOT/spec["source"]).read_bytes() if "source" in spec
                   else zlib.decompress(base64.b64decode(spec["zlib_base64"], validate=True)))
            assert hashlib.sha256(raw).hexdigest() == fixture["files"][relative]
            path = base/relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        (base/"RELEASE.json").write_text(json.dumps({
            "digest":profile["base_selection"]["generation"], "files":profile["base_files"]}))
        built=target/"composed"
        compose.compose(base,built)
        shutil.copytree(built/"ext",target/"ext")
    return target/"ext"

@pytest.fixture
def runtime(source_stage,tmp_path,monkeypatch):
    stage=tmp_path/"ext"
    shutil.copytree(source_stage,stage)
    names={p.stem for p in stage.glob("*.py")}
    before={name:sys.modules.get(name) for name in names}
    for name in names:sys.modules.pop(name,None)
    monkeypatch.syspath_prepend(str(stage))
    try:
        pick=importlib.import_module("pick")
        task=importlib.import_module("fabric_task")
        bp=importlib.import_module("byteplus_coding_plan")
        worker=importlib.import_module("native_plan_worker")
        broker=importlib.import_module("lease_broker")
        bridge=importlib.import_module("experiential_bridge")
        pin=importlib.import_module("experiential_pin")
        transport=importlib.import_module("experiential_transport")
        owner=importlib.import_module("experiential_host_context")
        policy=importlib.import_module("experiential_plan_policy")
        lane=importlib.import_module("lane_runtime")
        slot=importlib.import_module("slot")
        for key in ("FABRIC_OPERATOR_CHILD_ID","POOL_OPERATOR_CHILD_BUDGET","LANE_LEASED",
                    "POOL_LEASE_ID","POOL_ORCHESTRATOR_ID","POOL_TASK_COMPLEXITY",
                    "POOL_ESCALATION_REASON","POOL_ACCOUNTS_YAML","POOL_BROKER_DB"):
            monkeypatch.delenv(key,raising=False)
        host={"m2":{"local":True,"hostnames":[socket.gethostname().split(".",1)[0]],
                    "roles":["seat"],"local_only_engines":["byteplus","experiential"]}}
        (stage/"hosts.json").write_text(json.dumps(host))
        scope="subscription-"+"1"*64
        bp_row={"name":"byteplus-fixture","enabled":True,"per_account_cap":1,
                "quota_scope":"byteplus:"+scope,"coding_plan":{
            "schema":bp.ACCOUNT_SCHEMA,"subscription_ref":scope,"binding_id":bp.BINDING_ID,
            "base_url":bp.BASE_URL,"models":sorted(bp.MODELS),
            "scope":"individual_supported_coding_tools","quota_enforcement":"provider_hard_stop_no_payg",
            "entitlement_source":"chairman_declared_plan","plan_price_usd_per_month":50,
            "concurrency_source":"operator_limit_not_provider_entitlement",
            "launcher_sha256":hashlib.sha256(Path(bp.__file__).read_bytes()).hexdigest(),
            "credential_ref":"provider-home:byteplus-fixture","provider_home":str(tmp_path/"private"),
            "owner_uid":os.getuid(),"owner_gid":os.getgid(),"quota_observation":None}}
        org="fixture-org";org_sha=hashlib.sha256(org.encode()).hexdigest()
        exp_account=policy.PLAN_ACCOUNT_PREFIX+org_sha
        exp_row={"name":exp_account,"enabled":True,"per_account_cap":1,
            "quota_scope":"experiential:"+org_sha,"plan":{
                "schema":policy.PLAN_ACCOUNT_SCHEMA,"account":exp_account,"organization_sha256":org_sha,
                "plan_policy":"free_and_uncensored","policy_digest":policy.plan_policy_digest("free_and_uncensored"),
                "free_credits_per_day":7000,"paid_allowance_usd_per_month":200,
                "entitlement_source":"chairman_declared_plan","funding":"provider_prepaid_wallet"}}
        exp_provider={"enabled":True,"accounts":[exp_row],"plan_gateway":{
            "account":exp_account,"host":"127.0.0.1","port":8311,"route_host":"m2","route_id":"fixture-plan"}}
        accounts=tmp_path/"accounts.yaml"
        accounts.write_text(yaml.safe_dump({"schema":"mastermind.provider_accounts.v1","providers":{
            "byteplus":{"enabled":True,"native_host":"m2","accounts":[bp_row]},
            "experiential":exp_provider}}))
        monkeypatch.setattr(broker,"DEFAULT_ACCOUNTS",str(accounts))
        br=broker.Broker(db_path=str(tmp_path/"leases.sqlite"),lock_path=str(tmp_path/"leases.lock"),
                         accounts_path=str(accounts),external_gates=False,hosts_path=str(stage/"hosts.json"),
                         status_json=str(tmp_path/"status.json"),this_host="m2")
        monkeypatch.setattr(broker,"default_broker",lambda:br)
        replies={
            "/statusz":{"plan_policy":"free_and_uncensored",
                "plan_policy_digest":policy.plan_policy_digest("free_and_uncensored"),"account_metadata_enabled":True},
            "/api/whoami":{"org_id":org},
            "/api/v1/credits":{"data":{"total_credits":200,"total_usage":168}},
            "/v1/models":{"data":[{"id":m} for m in policy.PLAN_MODELS]},
        }
        included_evidence = [True]  # fixture-only; production readback is absent
        def context():
            value = owner._observed_context(exp_provider,read=replies.__getitem__,
                token="fixture-proxy-token-32-characters",base="http://127.0.0.1:8311")
            if included_evidence[0]:
                value["quota_readback"]["included_funding"] = {
                    "schema":"mastermind.experiential_included_funding/v1",
                    "source":"authenticated_provider_account","organization_sha256":org_sha,
                    "plan_tier":"max","plan_active":True,"daily_credits":7000,
                    "continue_on_credits":False,"provider_enforces_included_stop":True,
                    "paid_uncensored_remains_available":True,"observed_at_unix":time.time(),
                    "included_models":list(policy.FREE_CHAT_MODELS)+list(policy.FREE_NATIVE_MODELS)}
            return value
        adapter=bridge.HostAdapter(pin,transport,SimpleNamespace(host_owned_context=context),stage)
        monkeypatch.setattr(bridge,"resolve_host_adapter",lambda *_:adapter)
        real_occupancy_reader = lane.read_lane_occupancy
        physical=SimpleNamespace(status="known",active_count=0)
        monkeypatch.setattr(lane,"enforce_remote_first_lane_launch",
                            lambda *a,**kw:{"max_active":2,"load_ratio_limit":2/3})
        monkeypatch.setattr(lane,"read_lane_occupancy",lambda *_:physical)
        monkeypatch.setattr(slot,"_local_host_admission_refusal",lambda _:None)
        monkeypatch.setattr(pick,"load_pools",lambda *a:{"pools":{},"routing":{}})
        monkeypatch.setattr(pick,"_ledger_records",lambda:[])
        fallback=[]
        def old_route(*args,**kwargs):
            fallback.append(kwargs)
            return "NONE reason=no_pool_available"
        monkeypatch.setattr(pick,"_format_pick_host",old_route)
        sent=[]
        returncode=[0]
        def dispatch(argv,*,env):
            sent.append((argv,env))
            return SimpleNamespace(returncode=returncode[0])
        monkeypatch.setattr(task.subprocess,"run",dispatch)
        def request(rid="auto-fixture",**options):
            values=dict(cwd=str(tmp_path),packet=None,stdin_bytes=b"Write a pure addition function.",
                root_id="fixture-root",parent_run_id="fixture-root",task_complexity="C1_ROUTINE_BOUNDED")
            values.update(options)
            return task.request(rid,"mechanical",**values)
        yield SimpleNamespace(task=task,pick=pick,bp=bp,worker=worker,broker=br,bridge=bridge,
            policy=policy,replies=replies,accounts=accounts,stage=stage,physical=physical,
            sent=sent,returncode=returncode,fallback=fallback,request=request,adapter=adapter,
            lane=lane,real_occupancy_reader=real_occupancy_reader,included_evidence=included_evidence)
    finally:
        for name in names:
            if before[name] is None:sys.modules.pop(name,None)
            else:sys.modules[name]=before[name]

def receipt(rt,suffix,rid="auto-fixture"):
    return json.loads((rt.stage/"state/remote_sub"/(rid+suffix)).read_text())

def free_options():
    return {"experiential_response_only":True,"experiential_retention_acknowledged":True,
            "experiential_sensitive_data_opt_in":True}

def test_unpinned_coding_request_consumes_actual_picker_and_freezes_route(runtime):
    r=runtime
    assert r.request(max_turns=2)==0
    assert len(r.sent)==1 and not r.fallback
    launch=receipt(r,".request-launch.json")
    assert launch["route"]["POOL"]=="byteplus" and launch["route"]["MODEL"]=="glm-5.3-flash"
    assert launch["selection_mode"]=="AUTO" and launch["execution_cwd"]==str(r.stage.parent.resolve())
    argv,env=r.sent[0]
    assert argv[2:4]==["m2","byteplus"] and argv[6]=="glm-5.3-flash"
    assert env["POOL_REQUEST_MAX_TURNS"]=="2" and env["POOL_RUN_ID"]=="auto-fixture"

def test_consented_response_selects_only_free_chat_and_preserves_facts(runtime):
    r=runtime
    assert r.request(**free_options())==0
    launch=receipt(r,".request-launch.json");request=receipt(r,".request.json")
    assert launch["route"]["POOL"]=="experiential"
    assert launch["route"]["MODEL"]=="deepseek-v4.1-flash"
    assert launch["selection_mode"]=="AUTO"
    assert request["provider_plan_context"]["response_only"] is True
    argv,env=r.sent[0]
    assert argv[6] in r.policy.FREE_CHAT_MODELS and ":" not in argv[6]
    assert env["EXPERIENTIAL_STRICT_MANUAL_PIN"]=="1"
    packet=r.stage/"state/remote_sub/auto-fixture.request.packet"
    assert r.worker.original_request("experiential",argv[6],argv[5],str(packet),env)[0]=="auto-fixture"

@pytest.mark.parametrize("missing",["experiential_response_only","experiential_retention_acknowledged",
                                    "experiential_sensitive_data_opt_in"])
def test_missing_task_consent_or_response_capability_excludes_free_auto(runtime,missing):
    options=free_options();options.pop(missing)
    assert runtime.request(**options)==0
    assert runtime.sent[0][0][3]=="byteplus"

def test_proprietary_response_requires_separate_code_exposure_opt_in(runtime):
    r=runtime
    assert r.request(**free_options(),experiential_proprietary_code=True)==0
    assert r.sent[0][0][3]=="byteplus"

def test_paid_only_catalog_never_becomes_free_auto(runtime):
    r=runtime
    r.replies["/v1/models"]={"data":[{"id":m} for m in r.policy.PAID_UNCENSORED_MODELS]}
    assert r.request(**free_options())==0
    assert r.sent[0][0][3]=="byteplus"

def test_unavailable_metadata_removes_free_candidate(runtime):
    r=runtime
    r.replies["/statusz"]["plan_policy_digest"]="0"*64
    assert r.request(**free_options())==0
    assert r.sent[0][0][3]=="byteplus"

def test_existing_physical_reconciliation_hold_excludes_both_plans(runtime):
    r=runtime;r.physical.status="held"
    with pytest.raises(r.task.FabricTaskError,match="NONE"):
        r.request(**free_options())
    assert not r.sent and len(r.fallback)==1

def test_existing_account_shared_cap_removes_plan(runtime):
    r=runtime
    now=time.time()
    with r.broker._conn() as conn:
        conn.execute("INSERT INTO leases (id,orchestrator_id,pool,account,task_class,model,host,pid,granted_at,ttl,last_heartbeat,state,purpose) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("held-one","other-root","byteplus","byteplus-fixture","mechanical","deepseek-v4.1-flash","m2",1,now,300,now,"held","WORKER"))
    with pytest.raises(r.task.FabricTaskError,match="NONE"):
        r.request()
    assert not r.sent

@pytest.mark.parametrize("field,value",[
    ("FABRIC_OPERATOR_CHILD_ID","operator-child"),
    ("POOL_OPERATOR_CHILD_BUDGET","1"),
])
def test_operator_child_contract_remains_outside_local_plan_auto(runtime,monkeypatch,field,value):
    r=runtime;monkeypatch.setenv(field,value)
    with pytest.raises(r.task.FabricTaskError,match="NONE"):
        r.request(**free_options())
    assert not r.sent
    assert r.fallback and "provider_plan_context" not in r.fallback[0]

def test_tool_dependent_turn_fuse_does_not_select_response_transport(runtime):
    r=runtime
    assert r.request(**free_options(),max_turns=2)==0
    assert r.sent[0][0][3]=="byteplus"

def test_original_tilde_workdir_is_retained_and_resolved_at_local_adapter(runtime):
    r=runtime
    assert r.request(cwd="~")==0
    request=receipt(r,".request.json");launch=receipt(r,".request-launch.json")
    assert request["cwd"]=="~"
    assert launch["execution_cwd"]==str(Path("~").expanduser().resolve())
    argv,env=r.sent[0]
    assert argv[5]==launch["execution_cwd"]
    packet=r.stage/"state/remote_sub/auto-fixture.request.packet"
    assert r.worker.original_request("byteplus",argv[6],argv[5],str(packet),env)[0]=="auto-fixture"

def test_possible_send_failure_has_one_dispatch_and_no_replay_or_paid_fallback(runtime):
    r=runtime;r.returncode[0]=75
    assert r.request(**free_options())==75
    with pytest.raises(r.task.FabricTaskError,match="REQUEST_RUN_ALREADY_EXISTS"):
        r.request(**free_options())
    assert len(r.sent)==1 and r.sent[0][0][6]=="deepseek-v4.1-flash"

def test_mutated_auto_consent_facts_refuse_at_original_send_binding(runtime):
    r=runtime
    assert r.request(**free_options())==0
    argv,env=r.sent[0];env=dict(env);env["EXPERIENTIAL_SENSITIVE_DATA_OPT_IN"]="0"
    packet=r.stage/"state/remote_sub/auto-fixture.request.packet"
    with pytest.raises(ValueError,match="AUTO_FREE_RESPONSE_FACTS"):
        r.worker.original_request("experiential",argv[6],argv[5],str(packet),env)

def test_mutated_execution_workdir_refuses_original_binding(runtime):
    r=runtime
    assert r.request(cwd="~")==0
    argv,env=r.sent[0]
    packet=r.stage/"state/remote_sub/auto-fixture.request.packet"
    with pytest.raises(ValueError,match="ORIGINAL_REQUEST_BINDING"):
        r.worker.original_request("byteplus",argv[6],str(r.stage),str(packet),env)

def test_non_plan_preference_preserves_incumbent_selection(runtime):
    r=runtime
    with pytest.raises(r.task.FabricTaskError,match="NONE"):
        r.request(prefer="minimax")
    assert not r.sent and len(r.fallback)==1

def test_incompatible_deadline_excludes_local_plans_before_selection(runtime,monkeypatch):
    r=runtime;seen=[]
    def deadline_route(task_class,options,*args):
        seen.append(options);return "NONE reason=no_pool_available"
    monkeypatch.setattr(r.task,"_route_with_deadline",deadline_route)
    with pytest.raises(r.task.FabricTaskError,match="NONE"):
        r.request(request_deadline_ns=time.monotonic_ns()+30_000_000_000)
    assert not r.sent and seen[0]["excluded_hosts"]==["m2"]
    assert "provider_plan_context" not in seen[0]


@pytest.mark.parametrize("binding_valid",[True,False])
def test_published_shared_active_binding_uses_real_read_only_occupancy(runtime,monkeypatch,binding_valid):
    r=runtime
    stable=r.stage.parent/"stable/ext"
    active=stable/"active"
    active.mkdir(parents=True)
    (active/".admission.lock").touch(mode=0o600)
    (r.stage/"active").symlink_to(active)
    (r.stage.parent/"RELEASE.json").write_text(json.dumps({
        "stable_ext":str(stable),
        "links":{"ext/active":str(active) if binding_valid else str(stable/"wrong-active")}}))
    monkeypatch.setattr(r.lane,"read_lane_occupancy",r.real_occupancy_reader)
    if binding_valid:
        assert r.request()==0 and r.sent[0][0][3]=="byteplus"
    else:
        with pytest.raises(r.task.FabricTaskError,match="NONE"):
            r.request()
        assert not r.sent


def test_unverified_max_funding_excludes_included_auto(runtime):
    r = runtime
    r.included_evidence[0] = False
    assert r.request(**free_options()) == 0
    assert receipt(r, ".request-launch.json")["route"]["POOL"] == "byteplus"
    assert all(item[0][6] not in r.policy.FREE_CHAT_MODELS for item in r.sent)
