from __future__ import annotations
import copy, hashlib, json, subprocess, sys
from pathlib import Path
import pytest
from integrations.slack_agent_dialogue.source_continuity import *
S=lambda c:c*40

def probe(n):return {"name":n,"ok":True,"result_sha256":hashlib.sha256(n.encode()).hexdigest()}
def obs(**x):
    v={"operation_key":"source-continuity-rchp0-rch1-20260903-sol-001","carrier":"github:mastermindx-market-intelligence/Mastermind#346","repository":"mastermindx-market-intelligence/Mastermind","pr_number":400,"branch":"sol/source-continuity-rchp0-rch1-20260903","pinned_base_sha":S("a"),"expected_remote_head_sha":S("b"),"remote_head_sha":S("b"),"remote_tree_sha":S("c"),"remote_merge_base_sha":S("a"),"remote_changed_paths":["integrations/slack_agent_dialogue/source_continuity.py","tests/test_source_continuity.py"],"owned_paths":["docs/runbooks/SOURCE_CONTINUITY.md","integrations/slack_agent_dialogue/source_continuity.py","scripts/verify_source_continuity.py","tests/test_source_continuity.py"],"sealed_changed_paths":["integrations/slack_agent_dialogue/source_continuity.py","tests/test_source_continuity.py"],"local_branch":"sol/source-continuity-rchp0-rch1-20260903","local_head_sha":S("b"),"local_tree_sha":S("c"),"unpushed_commit_count":0,"uncommitted_in_scope_paths":[],"untracked_in_scope_paths":[],"unowned_dirty_paths":[],"unsafe_paths":[],"external_effect_state":"NONE","external_effect_evidence_ref":"github:mastermindx-market-intelligence/Mastermind#346:comment-5520453190","local_only_effect":False,"index_lock":False,"collision_state":"CLEAR","current_main_sha":S("d"),"pr_open":True,"pr_draft":True,"verified_at":"2026-09-03T04:30:00Z","probe_results":sorted([probe(n) for n in {"LOCAL_BRANCH","LOCAL_HEAD","LOCAL_TREE","LOCAL_STATUS","REMOTE_BRANCH","REMOTE_PR","REMOTE_TREE","REMOTE_MERGE_BASE","REMOTE_CHANGED_PATHS","CURRENT_MAIN"}],key=lambda r:r["name"]),"last_completed_task":"pure receipt contract","remaining_tasks":["hosted CI"],"checks_started_or_pending":["repository-test"],"ended_because":"ONGOING","exact_next_action":"Publish the Draft checkpoint."};v.update(x);return v

def release(r,**x):
    v={"source_receipt":r,"builder_result_state":"SOL_ACCEPTED_BUILDER_RESULT","terminal_stop_verified":True,"stop_operation_key":r["operation_key"],"stop_carrier":r["carrier"],"child_source_state":"REMOVED","stale_child_source_suppressed":False,"branch_writer_state":"BRANCH_WRITER_RELEASED","release_operation_key":"source-continuity-release-20260903-sol-001","repository":r["repository"],"pr_number":r["pr_number"],"branch":r["branch"],"current_remote_head_sha":r["remote_head_sha"],"current_remote_tree_sha":r["remote_tree_sha"],"current_remote_merge_base_sha":r["remote_merge_base_sha"],"current_changed_paths":r["changed_paths"],"current_main_sha":r["current_main_sha"],"requested_actions":["CHECKS","REVIEW"],"verified_at":"2026-09-03T04:45:00Z"};v.update(x);return v

def test_remote_complete_is_content_addressed_and_non_authoritative():
    r=verify_source_continuity(obs());assert r["decision"]=="REMOTE_COMPLETE_VERIFIED";q=r["receipt"];assert validate_receipt(q)==q;assert not q["transfer_safe"] and not q["grants_merge_authority"]

def test_checkpoint_preserves_sticky_local_and_effect_truth():
    r=verify_source_continuity(obs(local_head_sha=S("e"),local_tree_sha=S("f"),unpushed_commit_count=2,uncommitted_in_scope_paths=["scripts/verify_source_continuity.py"],external_effect_state="EFFECT_UNKNOWN",local_only_effect=True,index_lock=True));assert r["decision"]=="CHECKPOINT_VERIFIED";assert set(r["receipt"]["sticky_reasons"])=={"EXTERNAL_EFFECT_UNKNOWN","INDEX_LOCK_PRESENT","LOCAL_HEAD_DIFFERS","LOCAL_ONLY_EFFECT","LOCAL_TREE_DIFFERS","UNCOMMITTED_IN_SCOPE","UNPUSHED_COMMITS"}

@pytest.mark.parametrize("change,reason",[(dict(expected_remote_head_sha=S("e")),"EXPECTED_REMOTE_HEAD_MISMATCH"),(dict(remote_merge_base_sha=S("e")),"MERGE_BASE_MISMATCH"),(dict(collision_state="CONFLICT"),"COLLISION_UNRESOLVED"),(dict(pr_open=False),"PR_NOT_OPEN"),(dict(pr_draft=False),"PR_NOT_DRAFT"),(dict(remote_changed_paths=["outside.py"]),"REMOTE_PATH_OUTSIDE_OWNERSHIP")])
def test_identity_and_collision_fail_closed(change,reason):
    r=verify_source_continuity(obs(**change));assert not r["ok"] and reason in r["reason_codes"]

def test_context_budget_requires_actionable_handoff():
    r=verify_source_continuity(obs(ended_because="CONTEXT_BUDGET",remaining_tasks=[],exact_next_action=""));assert "CONTEXT_BUDGET_HANDOFF_INCOMPLETE" in r["reason_codes"]

def test_receipt_drift_bool_counts_and_secret_paths_refuse_without_echo():
    q=verify_source_continuity(obs())["receipt"];d=copy.deepcopy(q);d["current_main_sha"]=S("e")
    with pytest.raises(ContinuityContractError,match="RECEIPT_INVALID"):validate_receipt(d)
    assert not verify_source_continuity(obs(unpushed_commit_count=True))["ok"]
    bad="safe-"+"gh"+"p_"+"abcdefghijklmnopqrstuvwxyz123456.py";r=verify_source_continuity(obs(owned_paths=[bad]));assert not r["ok"] and bad not in json.dumps(r)

def test_release_requires_remote_complete_stop_release_and_fresh_same_pr_evidence():
    q=verify_source_continuity(obs())["receipt"];ok=evaluate_release_transfer(release(q));assert ok["decision"]=="RELEASE_RESPONSIBILITY_ELIGIBLE" and not ok["grants_release_authority"]
    cases=[(dict(terminal_stop_verified=False),"TERMINAL_STOP_REQUIRED"),(dict(branch_writer_state="BOUND"),"BRANCH_WRITER_NOT_RELEASED"),(dict(release_operation_key=q["operation_key"]),"FRESH_RELEASE_OPERATION_REQUIRED"),(dict(current_remote_head_sha=S("e")),"RECEIPT_STALE"),(dict(requested_actions=["EDIT_FEATURE"]),"RELEASE_SCOPE_VIOLATION")]
    for change,reason in cases:assert reason in evaluate_release_transfer(release(q,**change))["reason_codes"]

def test_watch_stop_failed_requires_suppression():
    q=verify_source_continuity(obs())["receipt"];assert "CHILD_SOURCE_NOT_SUPPRESSED" in evaluate_release_transfer(release(q,child_source_state="WATCH_STOP_FAILED"))["reason_codes"];assert evaluate_release_transfer(release(q,child_source_state="WATCH_STOP_FAILED",stale_child_source_suppressed=True))["ok"]

def test_canonical_json_and_core_import_fences():
    for bad in ({"x":{1}}, {"x":float("nan")}, {1:"x"}):
        with pytest.raises(ContinuityContractError):canonical_json(bad)
    text=(Path(__file__).parents[1]/"integrations/slack_agent_dialogue/source_continuity.py").read_text();assert all(x not in text for x in ("subprocess","urllib","sqlite3","open(","write_text("))

def test_cli_duplicate_json_is_fixed_error(tmp_path):
    p=tmp_path/"bad.json";p.write_text('{"operation_key":"one","operation_key":"two"}');r=subprocess.run([sys.executable,"-m","scripts.verify_source_continuity","--config",str(p)],cwd=Path(__file__).parents[1],capture_output=True,text=True);assert r.returncode==2 and not r.stdout and "Traceback" not in r.stderr
