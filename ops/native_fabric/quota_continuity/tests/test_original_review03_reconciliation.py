"""Hermetic, no-provider tests for the fixed original #1127 reviewer recovery."""
from __future__ import annotations
import copy
import json
import os
from pathlib import Path
import sys
import tempfile

import pytest

HERE = Path(__file__).resolve().parents[1] / "source"
sys.path.insert(0, str(HERE))
import native_watchlist_review03_reconcile as r


@pytest.fixture
def private_root():
    # The production artifact owner's DirectoryChain intentionally rejects
    # world-writable /tmp. Use a temporary owner-only directory under HOME so
    # tests exercise actual ancestry checks rather than mocking them.
    with tempfile.TemporaryDirectory(prefix=".review03-chain-test-",dir=Path.home()) as value:
        yield Path(value)


@pytest.fixture
def original(private_root, monkeypatch):
    here = private_root / "owner"
    (here / "state" / "remote_sub").mkdir(parents=True)
    monkeypatch.setattr(r, "HERE", here)
    material = {
        "schema":r.SCHEMA, "run_id":r.RUN, "root_id":r.ROOT, "lease_id":r.LEASE,
        "local":{"broker_lease_state":"expired","local_source_sha256":{"log":"fixed"}},
        "remote":{
            "schema":"mastermind.original-review03-host-observation.v1",
            "run_id":r.RUN,"host":"ubuntu1","returncode":1,
            "review_produced":False,"worker_cleanup_proven":True,
            "files_sha256":r.HOST_EXPECTED.copy()},
        "review_performed":False, "lease_released_by_this_operation":False,
        "retry_permitted":False,
    }
    proof = {**material, "proof_sha256":r.digest(r.canonical(material))}
    monkeypatch.setattr(r,"qualification", lambda:copy.deepcopy(proof))
    return here,proof


def test_complete_receipt_preserves_original_failure_and_refuses_acceptance(original):
    here,proof=original
    assert r.status_from_receipt() is None
    output=r.reconcile_original(r.RUN,r.ROOT,proof["proof_sha256"])
    assert output["state"]=="TERMINAL_FAILURE"
    assert output["rc"]==1 and output["signal"]=="other"
    assert output["root_id"]==r.ROOT
    assert output["parent_run_id"]==r.ROOT
    assert output["acceptance_reason"]=="REVIEW_NOT_PERFORMED"
    assert output["accepted"] is None and output["result_available"] is False
    assert output["original_reconciliation"]["worker_terminated"] is True
    assert output["original_reconciliation"]["broker_lease_expired"] is True
    assert output["original_reconciliation"]["retry_allowed"] is False
    saved=r.receipt_path()
    assert saved.exists() and saved.stat().st_mode & 0o777 == 0o600
    assert r._saved()["proof"]==proof


def test_second_reconcile_is_idempotent_and_preserves_bytes(original):
    _,proof=original
    a=r.reconcile_original(r.RUN,r.ROOT,proof["proof_sha256"])
    before=r.receipt_path().read_bytes()
    b=r.reconcile_original(r.RUN,r.ROOT,proof["proof_sha256"])
    assert a==b and before==r.receipt_path().read_bytes()


@pytest.mark.parametrize("run,root",[
    ("another-run","terminal-colw-20261022-pr1127"),
    ("terminal-colw-pr1127-independent-review-03","another-root")
])
def test_wrong_run_or_root_refused_before_mutation(original,run,root):
    _,proof=original
    with pytest.raises(r.NotQualified, match="original_operation_only"):
        r.reconcile_original(run,root,proof["proof_sha256"])
    assert not r.receipt_path().exists()


def test_stale_read_only_proof_refused_without_receipt(original):
    _,proof=original
    with pytest.raises(r.NotQualified, match="stale_qualification"):
        r.reconcile_original(r.RUN,r.ROOT,"0"*64)
    assert not r.receipt_path().exists()


def test_existing_receipt_tamper_fails_closed_and_is_not_rewritten(original):
    _,proof=original
    r.reconcile_original(r.RUN,r.ROOT,proof["proof_sha256"])
    path=r.receipt_path()
    altered=path.read_bytes().replace(b"review_performed",b"review_completed")
    path.write_bytes(altered)
    assert r.status_from_receipt() is None
    with pytest.raises(r.NotQualified):
        r.reconcile_original(r.RUN,r.ROOT,proof["proof_sha256"])
    assert path.read_bytes()==altered


def test_valid_self_hash_but_wrong_root_rejected(original):
    _,proof=original
    path=r.receipt_path()
    payload={"schema":r.SCHEMA,"created_at":123.0,
             "proof":{**proof,"root_id":"forged-root"}}
    payload["receipt_sha256"]=r.digest(r.canonical(payload))
    path.write_bytes(r.canonical(payload)+b"\n")
    os.chmod(path,0o600)
    assert r.status_from_receipt() is None


def test_existing_symlink_cannot_be_followed_or_overwritten(original):
    here,proof=original
    path=r.receipt_path()
    target=here/"arbitrary-target"
    target.write_text("original")
    path.symlink_to(target)
    assert r.status_from_receipt() is None
    with pytest.raises(OSError):
        r.reconcile_original(r.RUN,r.ROOT,proof["proof_sha256"])
    assert target.read_text()=="original"


def test_host_observation_binds_identity_and_original_file_digests():
    correct={"schema":"mastermind.original-review03-host-observation.v1",
             "run_id":r.RUN,"host":r.HOST,"returncode":1,
             "review_produced":False,"worker_cleanup_proven":True,
             "files_sha256":r.HOST_EXPECTED.copy()}
    assert r.validate_host_observation(r.canonical(correct))==correct
    for key,value in [
        ("returncode",0),("review_produced",True),
        ("worker_cleanup_proven",False),("host","another-host"),
        ("run_id","different-run"),("files_sha256",{}),
    ]:
        altered={**correct,key:value}
        with pytest.raises(r.NotQualified):
            r.validate_host_observation(r.canonical(altered))


def test_duplicate_json_keys_and_nonfinite_numbers_are_rejected():
    with pytest.raises(r.NotQualified, match="duplicate_json_key"):
        r.strict_json(b'{"root_id":"a","root_id":"b"}')
    with pytest.raises(r.NotQualified, match="nonfinite_json"):
        r.strict_json(b'{"x":NaN}')


def test_owned_file_rejects_symlink_and_digest_mismatch(private_root):
    good=private_root/"good"
    good.write_bytes(b"owned")
    os.chmod(good,0o600)
    assert r.read_bound(good,r.digest(b"owned"))==b"owned"
    with pytest.raises(r.NotQualified,match="source_digest_changed"):
        r.read_bound(good,r.digest(b"changed"))
    link=private_root/"link"
    link.symlink_to(good)
    with pytest.raises(OSError):
        r.read_bound(link,r.digest(b"owned"))


def test_qualification_rechecks_controller_after_remote_observation(monkeypatch):
    evidence={"local_source_sha256":{"x":"bound"},"broker_lease_state":"expired"}
    calls=[]
    def local():
        calls.append("local")
        return dict(evidence)
    def remote():
        calls.append("remote")
        return {"host":"ubuntu1","returncode":1}
    monkeypatch.setattr(r,"source_snapshot",local)
    monkeypatch.setattr(r,"observe_original_host",remote)
    proof=r.qualification()
    assert calls==["local","remote","local"]
    assert proof["run_id"]==r.RUN and proof["root_id"]==r.ROOT
    assert proof["review_performed"] is False and proof["retry_permitted"] is False
    assert proof["proof_sha256"]==r.digest(r.canonical({k:v for k,v in proof.items() if k!="proof_sha256"}))


def test_qualification_drift_rejected(monkeypatch):
    reads=iter([{"x":1},{"x":2}])
    monkeypatch.setattr(r,"source_snapshot",lambda: next(reads))
    monkeypatch.setattr(r,"observe_original_host",lambda: {"host":"ubuntu1"})
    with pytest.raises(r.NotQualified,match="original_evidence_changed"):
        r.qualification()


def test_no_provider_dispatch_or_lease_mutation_in_reconciliation_source():
    source=Path(r.__file__).read_text()
    assert "fabric_request" not in source
    assert "broker.release(" not in source
    assert "subprocess.Popen" not in source
    assert "os.O_CREAT|os.O_EXCL" in source
    assert "StrictHostKeyChecking=yes" in source
    assert "status_from_receipt" in source

def test_host_inspector_is_explicit_not_optimization_removable():
    import ast
    parsed=ast.parse(r.HOST_SOURCE)
    assert not any(isinstance(node,ast.Assert) for node in ast.walk(parsed))
    assert "os.O_NOFOLLOW" in r.HOST_SOURCE
    assert "residual_count" in r.HOST_SOURCE


def test_intermediate_symlink_rejected_for_read_and_publish(original):
    here,proof=original
    outside=here.parent/"other"
    outside.mkdir()
    state=here/"state"
    state.rename(here/"state_saved")
    state.symlink_to(outside,target_is_directory=True)
    assert r.status_from_receipt() is None
    with pytest.raises((OSError,ValueError)):
        r.reconcile_original(r.RUN,r.ROOT,proof["proof_sha256"])
    assert not (outside/"remote_sub"/r.receipt_path().name).exists()


def test_symlink_after_receipt_publish_disqualifies_readback(original):
    here,proof=original
    r.reconcile_original(r.RUN,r.ROOT,proof["proof_sha256"])
    state=here/"state"
    moved=here/"state_saved"
    state.rename(moved)
    state.symlink_to(moved,target_is_directory=True)
    assert r.status_from_receipt() is None


def test_concurrent_owner_receipt_create_converges_by_digest_readback(original,monkeypatch):
    _,proof=original
    owner_open=os.open
    seen=[]
    def writer(name,flags,mode=0o777,*,dir_fd=None):
        if name==r.receipt_path().name and flags & os.O_EXCL and not seen:
            seen.append(True)
            material={"schema":r.SCHEMA,"created_at":123.0,"proof":proof}
            material["receipt_sha256"]=r.digest(r.canonical(material))
            fd=owner_open(name,flags,0o600,dir_fd=dir_fd)
            with os.fdopen(fd,"wb") as stream:
                stream.write(r.canonical(material)+b"\n")
                stream.flush()
                os.fsync(stream.fileno())
            raise FileExistsError(17,"other original writer won O_EXCL")
        return owner_open(name,flags,mode,dir_fd=dir_fd)
    monkeypatch.setattr(os,"open",writer)
    result=r.reconcile_original(r.RUN,r.ROOT,proof["proof_sha256"])
    assert seen==[True] and result["state"]=="TERMINAL_FAILURE"
    assert r._saved()["proof"]==proof


def test_remote_observer_validates_fixed_host_and_output(monkeypatch):
    from types import SimpleNamespace
    good={"schema":"mastermind.original-review03-host-observation.v1",
          "run_id":r.RUN,"host":r.HOST,"returncode":1,
          "review_produced":False,"worker_cleanup_proven":True,
          "files_sha256":r.HOST_EXPECTED.copy()}
    calls=[]
    def fake(argv,**kw):
        calls.append((argv,kw))
        return SimpleNamespace(returncode=0,stdout=r.canonical(good))
    monkeypatch.setattr(r.subprocess,"run",fake)
    assert r.observe_original_host()==good
    assert calls[0][0][0]=="ssh" and calls[0][0][-2]==r.HOST
    assert "python3 -I -S -c" in calls[0][0][-1]
    assert calls[0][1]["timeout"]==25
    monkeypatch.setattr(r.subprocess,"run",lambda *a,**kw:SimpleNamespace(returncode=0,stdout=r.canonical({**good,"returncode":0})))
    with pytest.raises(r.NotQualified):
        r.observe_original_host()


def test_cli_wrong_root_and_reconcile_requires_digest(monkeypatch,capsys):
    proof={"run_id":r.RUN,"root_id":r.ROOT,"proof_sha256":"a"*64}
    monkeypatch.setattr(r,"qualification",lambda:dict(proof))
    assert r.main(["check",r.RUN,"--root",r.ROOT])==0
    assert r.strict_json(capsys.readouterr().out.encode())==proof
    assert r.main(["check","wrong-run","--root",r.ROOT])==78
    assert r.main(["reconcile",r.RUN,"--root",r.ROOT])==78
    assert "REFUSED" in capsys.readouterr().out


def _original_local_source(private_root,monkeypatch):
    import sqlite3
    here=private_root/"native_owner"/"ext"
    (here/"state"/"remote_sub").mkdir(parents=True)
    (here.parent/"orch"/"fabric").mkdir(parents=True)
    (here/"broker").mkdir()
    monkeypatch.setattr(r,"HERE",here)
    request={"run_id":r.RUN,"root_id":r.ROOT,"parent_run_id":r.ROOT,
             "task_class":"review","packet_sha256":r.PACKET_SHA,"packet_bytes":2971}
    launch={"run_id":r.RUN,"root_id":r.ROOT,"parent_run_id":r.ROOT,
            "packet_sha256":r.PACKET_SHA,"state":"LAUNCH_ATTEMPT_RESERVED",
            "route":{"HOST":r.HOST,"KEY":"-","MODE":"qwen","MODEL":r.MODEL,
                     "POOL":"bailian","REASON":"execute_order_bailian"}}
    transport={"run_id":r.RUN,"host":r.HOST,"lease_id":r.LEASE,"mode":"qwen",
               "packet_sha256":r.PACKET_SHA,
               "support_digest":"558b4875ba6dda4f0a48e23692945c4c0317389deae673e84da45296e217c580"}
    continuation={"origin_run_id":r.RUN,"root_id":r.ROOT,"parent_run_id":r.ROOT,
                  "effective_run_id":r.RUN,"controller_rc":124,"background_execution":False,
                  "reason":"continuation_evidence_unqualified"}
    log=("RUN_RESERVED explicit=1\nLAUNCH_ATTEMPT attempt=1\n"
         "LEASE_PRESERVED effect_unknown=1 lease="+r.LEASE+"\n"
         "DONE rc=124 signal=effect_unknown reason=transport_deadline_without_rc\n").encode()
    data={
        ".log":log,
        ".request.json":r.canonical(request),
        ".transport-verified.json":r.canonical(transport),
        ".continuation-finished.json":r.canonical(continuation),
        ".controller-process.jsonl":b'{"process":"simulated"}\n',
        ".routing-process.jsonl":b'{"route":"simulated"}\n',
    }
    launch["request_sha256"]=r.digest(data[".request.json"])
    data[".request-launch.json"]=r.canonical(launch)
    returned={"run_id":r.RUN,"root_id":r.ROOT,"parent_run_id":r.ROOT,
              "controller_rc":124,"state":"NATIVE_CONTROLLER_RETURNED",
              "log_sha256":r.digest(log),
              "launch_sha256":r.digest(data[".request-launch.json"])}
    data[".request-return.json"]=r.canonical(returned)
    monkeypatch.setattr(r,"EXPECTED",{s:r.digest(raw) for s,raw in data.items()})
    for suffix,raw in data.items():
        p=here/"state"/"remote_sub"/(r.RUN+suffix)
        p.write_bytes(raw)
        os.chmod(p,0o600)
    outcome={"run_id":r.RUN,"root_id":r.ROOT,"rc":124,
             "signal":"effect_unknown","reason":"transport_deadline_without_rc"}
    ledger=here.parent/"orch"/"fabric"/"ledger.jsonl"
    ledger.write_bytes(r.canonical(outcome)+b"\n")
    os.chmod(ledger,0o600)
    broker=here/"broker"/"leases.sqlite"
    with sqlite3.connect(broker) as db:
        db.execute("CREATE TABLE leases (id TEXT,orchestrator_id TEXT,pool TEXT,"
                   "account TEXT,host TEXT,state TEXT,model TEXT)")
        db.execute("INSERT INTO leases VALUES (?,?,?,?,?,?,?)",
                   (r.LEASE,r.ROOT,"bailian","Ryan",r.HOST,"expired",r.MODEL))
        db.commit()
    return here,data


def test_source_snapshot_checks_all_original_controller_and_broker_evidence(private_root,monkeypatch):
    here,_=_original_local_source(private_root,monkeypatch)
    proof=r.source_snapshot()
    assert len(proof["local_source_sha256"])==8
    assert proof["broker_lease_state"]=="expired"
    assert len(proof["ledger_row_sha256"])==64
    import sqlite3
    with sqlite3.connect(here/"broker"/"leases.sqlite") as db:
        db.execute("UPDATE leases SET state='held' WHERE id=?",(r.LEASE,))
        db.commit()
    with pytest.raises(r.NotQualified,match="original_lease_not_expired"):
        r.source_snapshot()


def test_source_snapshot_rejects_wrong_original_identity(private_root,monkeypatch):
    here,_=_original_local_source(private_root,monkeypatch)
    path=here/"state"/"remote_sub"/(r.RUN+".request.json")
    payload=r.strict_json(path.read_bytes())
    payload["root_id"]="forged"
    forged=r.canonical(payload)
    path.write_bytes(forged)
    monkeypatch.setitem(r.EXPECTED,".request.json",r.digest(forged))
    with pytest.raises(r.NotQualified,match="original_binding"):
        r.source_snapshot()


def test_source_snapshot_rejects_duplicate_outcome_ledger_record(private_root,monkeypatch):
    here,_=_original_local_source(private_root,monkeypatch)
    ledger=here.parent/"orch"/"fabric"/"ledger.jsonl"
    ledger.write_bytes(ledger.read_bytes()*2)
    with pytest.raises(r.NotQualified,match="controller_ledger_unique"):
        r.source_snapshot()


def test_source_snapshot_refuses_intermediate_symlink_even_when_final_files_valid(private_root,monkeypatch):
    here,_=_original_local_source(private_root,monkeypatch)
    state=here/"state"
    move=here/"state_saved"
    state.rename(move)
    state.symlink_to(move,target_is_directory=True)
    with pytest.raises((OSError,ValueError)):
        r.source_snapshot()



def test_broker_db_symlink_is_refused_before_sqlite_can_follow_it(private_root,monkeypatch):
    here,_=_original_local_source(private_root,monkeypatch)
    db=here/"broker"/"leases.sqlite"
    original=here/"broker"/"saved_lease.sqlite"
    db.rename(original)
    db.symlink_to(original)
    with pytest.raises((OSError,ValueError)):
        r.source_snapshot()
    assert original.exists()


def test_broker_parent_symlink_is_refused_even_when_database_is_valid(private_root,monkeypatch):
    here,_=_original_local_source(private_root,monkeypatch)
    parent=here/"broker"
    original=here/"broker_original"
    parent.rename(original)
    parent.symlink_to(original,target_is_directory=True)
    with pytest.raises((OSError,ValueError)):
        r.source_snapshot()
    assert (original/"leases.sqlite").exists()


def test_incomplete_competing_exclusive_receipt_remains_untouched(original,monkeypatch):
    _,proof=original
    real_open=os.open
    once=[]
    def competing(name,flags,mode=0o777,*,dir_fd=None):
        if (name==r.receipt_path().name and flags & os.O_CREAT
                and flags & os.O_EXCL and not once):
            once.append(True)
            fd=real_open(name,flags,0o600,dir_fd=dir_fd)
            os.close(fd)
            raise FileExistsError(17,"other original writer reserved the receipt")
        return real_open(name,flags,mode,dir_fd=dir_fd)
    monkeypatch.setattr(os,"open",competing)
    with pytest.raises(r.NotQualified,match="original_receipt_incomplete"):
        r.reconcile_original(r.RUN,r.ROOT,proof["proof_sha256"])
    assert once==[True]
    assert r.receipt_path().read_bytes()==b""
