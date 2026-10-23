"""Hermetic, no-provider tests for the fixed original #1127 reviewer recovery."""
from __future__ import annotations
import copy
import json
import os
from pathlib import Path
import sys

import pytest

HERE = Path(__file__).resolve().parents[1] / "source"
sys.path.insert(0, str(HERE))
import native_watchlist_review03_reconcile as r


@pytest.fixture
def original(tmp_path, monkeypatch):
    here = tmp_path / "owner"
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


def test_owned_file_rejects_symlink_and_digest_mismatch(tmp_path):
    good=tmp_path/"good"
    good.write_bytes(b"owned")
    os.chmod(good,0o600)
    assert r.read_bound(good,r.digest(b"owned"))==b"owned"
    with pytest.raises(r.NotQualified,match="source_digest_changed"):
        r.read_bound(good,r.digest(b"changed"))
    link=tmp_path/"link"
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
