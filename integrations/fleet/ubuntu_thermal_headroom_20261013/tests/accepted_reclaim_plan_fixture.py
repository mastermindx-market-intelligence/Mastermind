#!/usr/bin/env python3
"""Original Fabric accepted-result -> read-only exact host/worktree plan.

Uses fixture status/log only; neither Git nor an external host is touched.
"""
import copy
import importlib.util
import os
from pathlib import Path
import sys
from unittest.mock import patch
import pytest

STAGE = Path(__file__).resolve().parent
EXT = Path.home()/".claude/projects/-Users-chriswong-Documents-Cluade-Macro-Dashboard/handoff_kits/meta-ceo-b-2026-09-08/ext"
sys.path.insert(0,str(EXT))
spec=importlib.util.spec_from_file_location("original_fabric_accepted_reclaim_plan", STAGE/"fabric_task.py")
controller=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=controller
spec.loader.exec_module(controller)

RID="new-macro-run-42"
ROOT="original-root"
PARENT="original-parent"
COMMIT="ab"*20
PREFIX="2026-10-15T04:42Z [remote_sub id=new-macro-run-42 host=ubuntu0]"
INTENT=(
    PREFIX+" FABRIC_NEW_MACRO_WORKTREE run="+RID+
    " commit="+COMMIT+" root="+ROOT+" parent="+PARENT+"\n"
)
LOG=(INTENT+PREFIX+" LAUNCH stdout=lanes/new-macro-run-42.remote.stdout "
     "rc_file=ext/foo cwd=~/lanes/repos/macro\n"
     +PREFIX+" DONE rc=0 signal=ok\n").encode()
GOOD={
 "state":"TERMINAL","rc":0,"signal":"ok","result_available":True,
 "accepted":True,"accepted_by":"reviewer","acceptance_state":"ACCEPTED",
 "root_id":ROOT,"parent_run_id":PARENT,
}

def call(status=None,log=LOG,**kw):
    s=status if status is not None else GOOD
    with patch.object(controller,"inspect_run",side_effect=[copy.deepcopy(s),copy.deepcopy(s)]),\
         patch.object(controller,"_paths",return_value=(Path("/safe/owner.log"),Path("/safe/owner.result"))),\
         patch.object(controller,"_bounded_regular",return_value=log):
        return controller.plan_accepted_macro_worktree_release(
            RID,root_id=ROOT,parent_run_id=PARENT,pinned_sha=COMMIT,**kw)

def test_exact_success_still_not_approved_for_deletion():
    plan=call()
    assert plan["host"]=="ubuntu0"
    assert plan["checkout_path"]=="~/lanes/wt/"+RID
    assert plan["expected_branch"]=="lane/"+RID
    assert plan["execution_accepted_by"]=="reviewer"
    assert plan["cleanup_authorized"] is False
    assert plan["state"]=="HOST_WORKTREE_SOURCE_AND_LIVENESS_PROOF_REQUIRED"

@pytest.mark.parametrize("field,value",[
 ("state","ACTIVE_OR_WAITING"),("rc",76),("signal","effect_unknown"),
 ("accepted",False),("accepted",None),
 ("accepted_by","none"),("acceptance_state","UNVERIFIED"),
 ("root_id","foreign-root"),("parent_run_id","foreign-parent"),
 ("result_available",False),
])
def test_all_ineligible_terminal_or_custody_conditions_refused(field,value):
    s={**GOOD,field:value}
    with pytest.raises(controller.FabricTaskError, match="ACCEPTANCE_OR_CUSTODY"):
        call(status=s)

@pytest.mark.parametrize("bad",[
 LOG.replace(b"FABRIC_NEW_MACRO_WORKTREE",b"LEGACY_SOURCE_WORKER"),
 LOG+INTENT.encode(),
 LOG.replace(b"host=ubuntu0",b"host=unknown"),
 LOG.replace(COMMIT.encode(),b"c"*40),
 LOG.replace(b"root=original-root",b"root=foreign-root"),
 LOG.replace(b"parent=original-parent",b"parent=foreign-parent"),
 LOG.replace(b"run=new-macro-run-42",b"run=other-run"),
])
def test_no_unique_exact_launch_provenance_refused(bad):
    with pytest.raises(controller.FabricTaskError,match="LAUNCH_PROOF_UNVERIFIED"):
        call(log=bad)

def test_second_owner_status_drift_refused():
    altered={**GOOD,"accepted":False}
    with patch.object(controller,"inspect_run",side_effect=[GOOD,altered]),\
         patch.object(controller,"_paths",return_value=(Path("/safe/log"),Path("/safe/result"))),\
         patch.object(controller,"_bounded_regular",return_value=LOG):
        with pytest.raises(controller.FabricTaskError,match="ACCEPTANCE_CHANGED"):
            controller.plan_accepted_macro_worktree_release(
                RID,root_id=ROOT,parent_run_id=PARENT,pinned_sha=COMMIT)

def test_log_changes_during_consistency_check_refused():
    with patch.object(controller,"inspect_run",side_effect=[GOOD,GOOD]),\
         patch.object(controller,"_paths",return_value=(Path("/safe/log"),Path("/safe/result"))),\
         patch.object(controller,"_bounded_regular",side_effect=[LOG,LOG+b"changed\n"]):
        with pytest.raises(controller.FabricTaskError,match="LOG_CHANGED"):
            controller.plan_accepted_macro_worktree_release(
                RID,root_id=ROOT,parent_run_id=PARENT,pinned_sha=COMMIT)

def test_no_runtime_ssh_or_gc_side_effect(monkeypatch):
    def refuse(*args,**kwargs):
        raise AssertionError("reclaim-plan may not spawn commands")
    monkeypatch.setattr(controller.subprocess,"run",refuse)
    assert call()["cleanup_authorized"] is False
