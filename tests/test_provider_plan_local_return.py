"""Original request -> local shell -> slot -> controlled CLI -> result/acceptance.

Only the provider executable and the physical load observation are controlled.
No external service, production account, or production state is used.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
from subprocess import run as real_run
import sys
import tempfile
from types import SimpleNamespace
import pytest
import yaml

from tests.test_provider_plan_auto_routing import source_stage, runtime, receipt


@pytest.fixture
def tmp_path():
    # The production artifact reader rejects writable ancestor directories,
    # including /tmp. Exercise it under a new private owned home directory.
    with tempfile.TemporaryDirectory(prefix=".mmx-plan-local-test-",dir=Path.home()) as directory:
        yield Path(directory).resolve()


@pytest.fixture
def local_runtime(runtime, monkeypatch):
    r = runtime
    root = r.stage.parent
    fabric = root/"orch/fabric"
    fabric.mkdir(parents=True)
    accounts = yaml.safe_load(r.accounts.read_text())
    provider = accounts["providers"]["byteplus"]
    home = root/"private"
    home.mkdir(mode=0o700, exist_ok=True)
    home.chmod(0o700)
    (home/"claude").mkdir(mode=0o700)
    credential=home/"provider-credential"
    credential.write_text("fixture-not-a-provider-credential")
    credential.chmod(0o600)
    provider["accounts"][0]["coding_plan"]["provider_home"] = str(home.resolve())
    (fabric/"accounts.yaml").write_text(yaml.safe_dump(accounts))
    host = {"m2":{"local":True,"hostnames":[socket.gethostname().split(".",1)[0]],
        "roles":["seat"],"local_only_engines":["byteplus","experiential"],
        "cores":max(2,os.cpu_count() or 2),"max_active":1,"load_gate":1,
        "min_free_gb":0,"worktree_root":str(root)}}
    (r.stage/"hosts.json").write_text(json.dumps(host))
    support = root/"controlled-boundaries"
    support.mkdir()
    # Measurement fixture: admission code and policy remain the real source.
    (support/"sitecustomize.py").write_text("import os\nos.getloadavg=lambda:(0.,0.,0.)\n")
    binaries = root/"bin"
    binaries.mkdir()
    calls = root/"provider-calls.jsonl"
    fake = binaries/"claude"
    fake.write_text("#!"+sys.executable+"\n"+r'''
import json, os, sys
from pathlib import Path
with Path(os.environ["FIXTURE_PROVIDER_CALLS"]).open("a") as stream:
    stream.write(json.dumps({"model":os.environ["ANTHROPIC_MODEL"]})+"\n")
if os.environ.get("FIXTURE_PROVIDER_REPLY") == "malformed":
    print("unqualified provider response")
    raise SystemExit(0)
print(json.dumps({"type":"system","subtype":"init","session_id":"fixture-session"}))
print(json.dumps({"type":"result","subtype":"success","is_error":False,
    "result":"def add(a, b):\n    return a + b",
    "usage":{"input_tokens":12,"output_tokens":9},"session_id":"fixture-session"}))
''')
    fake.chmod(0o700)
    monkeypatch.setenv("PATH",str(binaries)+os.pathsep+str(Path(sys.executable).parent)+os.pathsep+os.environ["PATH"])
    monkeypatch.setenv("PYTHONPATH",str(support)+os.pathsep+str(r.stage))
    monkeypatch.setenv("POOL_BROKER_HOST","m2")
    monkeypatch.setenv("POOL_CHILD_TIMEOUT_SECONDS","20")
    monkeypatch.setenv("FIXTURE_PROVIDER_CALLS",str(calls))
    for key in ("REMOTE_SUB_HERE","REMOTE_SUB_LOG_DIR","REMOTE_SUB_LOCAL_CMD",
                "REMOTE_SUB_LEDGER_CMD","POOL_LEDGER_PATH","LANE_REMOTE_HOST",
                "POOL_PRELEASE_HANDOFF","POOL_COMMISSION_DEADLINE_NS",
                "POOL_COMMISSION_REMAINING_SECONDS","POOL_CAPACITY_PREFLIGHT"):
        monkeypatch.delenv(key,raising=False)
    processes=[]
    invocations=[]
    def dispatch(argv,*,env):
        invocations.append((list(argv),dict(env)))
        result=real_run(argv,env=env,capture_output=True,text=True,timeout=40)
        processes.append(result)
        return result
    monkeypatch.setattr(r.task.subprocess,"run",dispatch)
    r.calls=calls
    r.processes=processes
    r.invocations=invocations
    r.fixture_fabric=fabric
    r.fixture_host=host
    yield r


def terminal_rows(r,rid="auto-fixture"):
    path=r.fixture_fabric/"ledger.jsonl"
    if not path.is_file():return []
    return [json.loads(line) for line in path.read_text().splitlines()
            if json.loads(line).get("run_id")==rid and json.loads(line).get("kind")!="outcome"]


def diagnostics(r):
    state=r.stage/"state/remote_sub"
    path=state/"auto-fixture.local-stderr.txt"
    return (r.processes[-1].stderr if r.processes else "")+(path.read_text() if path.exists() else "")


def test_actual_local_auto_request_retains_answer_and_single_original_terminal(local_runtime):
    r=local_runtime
    assert r.request(max_turns=2)==0, diagnostics(r)
    status=r.task.inspect_run("auto-fixture")
    assert status["state"]=="TERMINAL" and status["rc"]==0 and status["signal"]=="ok"
    assert status["result_available"] is True and status["root_id"]=="fixture-root"
    assert status["accepted"] is False
    assert (r.stage/"lanes/auto-fixture.remote.stdout").read_text()=="def add(a, b):\n    return a + b\n"
    returned=receipt(r,".request-return.json")
    assert returned["controller_rc"]==0 and returned["state"]=="NATIVE_CONTROLLER_RETURNED"
    rows=terminal_rows(r)
    assert len(rows)==1 and rows[0]["job_class"]=="mechanical"
    assert rows[0]["input_tokens"]==12 and rows[0]["output_tokens"]==9
    assert rows[0]["root_id"]==rows[0]["parent_run_id"]=="fixture-root"
    assert len(r.calls.read_text().splitlines())==1
    accepted=real_run([sys.executable,str(r.stage/"fabric_task.py"),"accept",
        "auto-fixture","--by","deterministic"],capture_output=True,text=True,timeout=15)
    assert accepted.returncode==0,accepted.stderr
    assert r.task.inspect_run("auto-fixture")["accepted"] is True
    with pytest.raises(r.task.FabricTaskError):
        r.request(max_turns=2)
    log=r.stage/"state/remote_sub/auto-fixture.log"
    prior=log.read_bytes()
    repeated=real_run([sys.executable,str(r.stage/"native_plan_worker.py"),"local-controller",
        "byteplus","glm-5.3-flash",str(r.stage.parent),
        str(r.stage/"state/remote_sub/auto-fixture.request.packet"),
        str(r.stage/"lanes/auto-fixture.remote.stdout"),str(log),"bash"],
        env=r.invocations[0][1],capture_output=True,text=True,timeout=15)
    assert repeated.returncode==76 and log.read_bytes()==prior
    assert r.task.inspect_run("auto-fixture")["accepted"] is True
    assert len(r.calls.read_text().splitlines())==1


def test_actual_slot_host_refusal_has_positive_no_send_witness_and_lineage(local_runtime):
    r=local_runtime
    r.fixture_host["m2"]["load_gate"]=0
    (r.stage/"hosts.json").write_text(json.dumps(r.fixture_host))
    assert r.request(max_turns=2)==78,diagnostics(r)
    assert not r.calls.exists()
    proof=receipt(r,".plan-admission-refused.json")
    assert proof["phase"]=="before_provider_acquire" and proof["reason"]=="host_admission"
    status=r.task.inspect_run("auto-fixture")
    assert status["state"]=="TERMINAL" and status["rc"]==78 and status["signal"]=="admission"
    assert status["accepted"] is None and status["root_id"]=="fixture-root"
    assert len(terminal_rows(r))==1
    assert not (r.stage/"state/remote_sub/auto-fixture.task-cli-started.json").exists()


def test_unqualified_provider_result_preserves_unknown_without_terminal(local_runtime,monkeypatch):
    r=local_runtime
    monkeypatch.setenv("FIXTURE_PROVIDER_REPLY","malformed")
    assert r.request(max_turns=2)==76,diagnostics(r)
    assert len(r.calls.read_text().splitlines())==1
    assert r.task.inspect_run("auto-fixture")["state"]=="EFFECT_UNKNOWN"
    assert terminal_rows(r)==[]
    assert receipt(r,".request-return.json")["controller_rc"]==76


def test_raw_prestart_return_without_slot_witness_is_not_invented_no_send(local_runtime,monkeypatch):
    r=local_runtime
    refusal=r.stage.parent/"unqualified-refusal"
    refusal.write_text("#!/bin/sh\nexit 78\n")
    refusal.chmod(0o700)
    monkeypatch.setenv("REMOTE_SUB_LOCAL_CMD",str(refusal))
    assert r.request(max_turns=2)==76,diagnostics(r)
    assert not r.calls.exists()
    assert r.task.inspect_run("auto-fixture")["state"]=="EFFECT_UNKNOWN"
    assert terminal_rows(r)==[]


def test_actual_terminal_publication_failure_is_settling_not_active(local_runtime,monkeypatch):
    r=local_runtime
    blocked=r.stage.parent/"ledger-is-directory"
    blocked.mkdir()
    monkeypatch.setenv("POOL_LEDGER_PATH",str(blocked))
    assert r.request(max_turns=2)==74,diagnostics(r)
    assert len(r.calls.read_text().splitlines())==1
    status=r.task.inspect_run("auto-fixture")
    assert status["state"]=="SETTLING" and status["accepted"] is None
    assert terminal_rows(r)==[]
    assert receipt(r,".request-return.json")["controller_rc"]==74


def test_result_changed_after_worker_completion_does_not_publish_success(local_runtime,monkeypatch):
    r=local_runtime
    changed=r.stage.parent/"changed-return"
    changed.write_text('#!/bin/sh\n/bin/bash "$@"\nrc=$?\nprintf "changed answer\\n"\nexit "$rc"\n')
    changed.chmod(0o700)
    monkeypatch.setenv("REMOTE_SUB_LOCAL_CMD",str(changed))
    assert r.request(max_turns=2)==76,diagnostics(r)
    assert len(r.calls.read_text().splitlines())==1
    assert r.task.inspect_run("auto-fixture")["state"]=="EFFECT_UNKNOWN"
    assert terminal_rows(r)==[]
