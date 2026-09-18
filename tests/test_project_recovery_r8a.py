import copy, json, subprocess, sys
from pathlib import Path
import pytest
from control_plane.project_recovery import assess_recovery
from control_plane.project_recovery_contract import ProjectRecoveryContractError, validate_inputs
from control_plane.project_recovery_rules import detect_recovery_findings, wait_state

def session(findings=None, workstreams=None, repositories=None):
    return {"schema":"mastermind.session_truth_receipt.v1","scope":{"workstreams":workstreams or ["WS:ALPHA"],"linear":[],"repositories":repositories or ["o/r"],"operation_key":None,"requires_executive":True},"skillpack":{},"observation":{},"observations":{"agentos":{"available":True,"source_sha":"1"*40},"github":{"available":True,"pull_requests":[]},"executive":{"available":True,"fresh":True,"operations":[]}},"findings":findings or [],"admission":{},"semantic_hash":"sha256:"+"a"*64}
def agent(workstreams=None, programs=None, available=True):
    return {"schema":"agent_os_state.v1","workstreams":workstreams or [],"program_registry":{"schema":"agentos.program_registry.v1","available":available,**({"programs":programs or []} if available else {"reason":"unavailable","programs":[]})}}
def ws(key="WS:ALPHA",**kw):
    row={"key":key.removeprefix("WS:"),"status":"active","program":"alpha"}; row.update(kw); return row

def test_contract_rejects_duplicate_workstreams():
    with pytest.raises(ProjectRecoveryContractError,match="duplicate workstream"): validate_inputs(session(),agent([ws(),ws()],[{"key":"alpha","lifecycle_state":"building"}]),as_of="2026-09-14")
def test_wait_expiry_is_explicit():
    assert wait_state({"kind":"natural_evidence","review_after":"2026-09-25","condition":"wait for evidence"},as_of="2026-09-14")=="VALID"; assert wait_state({"kind":"natural_evidence","review_after":"2026-09-01","condition":"wait for evidence"},as_of="2026-09-14")=="OVERDUE"
def test_orphan_program_is_recovery_required():
    out=detect_recovery_findings(session(),agent([], [{"key":"alpha","lifecycle_state":"building"}]),as_of="2026-09-14"); assert out[0]["code"]=="ORPHAN_BUILDING_PROGRAM"; assert out[0]["disposition"]=="RECOVERY_REQUIRED"
def test_terminal_bindings_force_reconcile_not_recovery():
    out=detect_recovery_findings(session(),agent([ws(status="done")],[{"key":"alpha","lifecycle_state":"building"}]),as_of="2026-09-14"); assert out[0]["code"]=="PROGRAM_LIFECYCLE_DISAGREEMENT"; assert out[0]["disposition"]=="UNKNOWN_RECONCILE"
def test_runtime_unknown_blocks_recovery():
    st=session([{"code":"RUNTIME_STATE_UNAVAILABLE","subject":"WS:ALPHA"}]); out=detect_recovery_findings(st,agent([ws()],[{"key":"alpha","lifecycle_state":"building"}]),as_of="2026-09-14"); assert {x["code"] for x in out}=={"RUNTIME_OWNERSHIP_UNKNOWN"}
def test_valid_wait_is_not_recovery():
    a=assess_recovery(session(),agent([ws(wait={"kind":"natural_evidence","review_after":"2026-09-25","condition":"wait for evidence"})],[{"key":"alpha","lifecycle_state":"building"}]),as_of="2026-09-14",observed_at="2026-09-14T12:00:00Z"); assert a["summary"]["VALID_INTENTIONAL_WAIT"]==1; assert not a["findings"]
def test_semantic_hash_ignores_observation_time():
    ao=agent([ws(wait={"kind":"natural_evidence","review_after":"2026-09-25","condition":"wait for evidence"})],[{"key":"alpha","lifecycle_state":"building"}]); one=assess_recovery(session(),ao,as_of="2026-09-14",observed_at="2026-09-14T12:00:00Z"); two=assess_recovery(session(),ao,as_of="2026-09-14",observed_at="2026-09-14T12:05:00Z"); assert one["semantic_hash"]==two["semantic_hash"]
def test_cli_json(tmp_path):
    st=tmp_path/"st.json"; ao=tmp_path/"ao.json"; st.write_text(json.dumps(session())); ao.write_text(json.dumps(agent([], [{"key":"alpha","lifecycle_state":"building"}]))); script=Path(__file__).parents[1]/"scripts/project_recovery_assessment.py"; p=subprocess.run([sys.executable,str(script),"--session-truth",str(st),"--agentos-state",str(ao),"--as-of","2026-09-14","--observed-at","2026-09-14T12:00:00Z","--json"],capture_output=True,text=True); assert p.returncode==0,p.stderr; assert json.loads(p.stdout)["schema"]=="mastermind.project_recovery_assessment.v1"

def test_program_registry_unavailable_is_unknown_not_orphan():
    out=detect_recovery_findings(session(),agent([],[],available=False),as_of="2026-09-14")
    assert [(x["code"],x["disposition"]) for x in out]==[("RUNTIME_OWNERSHIP_UNKNOWN","UNKNOWN_RECONCILE")]

def test_similar_program_title_never_binds():
    row=ws(program="alpha-v2",title="Alpha")
    out=detect_recovery_findings(session(),agent([row],[{"key":"alpha","name":"Alpha","lifecycle_state":"building"},{"key":"alpha-v2","name":"Alpha","lifecycle_state":"operating"}]),as_of="2026-09-14")
    assert any(x["code"]=="ORPHAN_BUILDING_PROGRAM" and x["program"]=="alpha" for x in out)

def test_open_exact_pr_is_active_frontier():
    st=session(); st["observations"]["github"]["pull_requests"]=[{"repository":"o/r","number":1,"state":"open","workstream":"WS:ALPHA"}]
    out=detect_recovery_findings(st,agent([ws()],[{"key":"alpha","lifecycle_state":"building"}]),as_of="2026-09-14")
    assert not any(x["code"] in {"ACTIVE_WITHOUT_CARRIER","RUNTIME_OWNERSHIP_UNKNOWN"} for x in out)

def test_unavailable_runtime_never_resurrects_quiet_work():
    st=session(); st["observations"]["executive"]={"available":False,"reason":"auth unavailable"}
    out=detect_recovery_findings(st,agent([ws()],[{"key":"alpha","lifecycle_state":"building"}]),as_of="2026-09-14")
    assert any(x["code"]=="RUNTIME_OWNERSHIP_UNKNOWN" and x["disposition"]=="UNKNOWN_RECONCILE" for x in out)
    assert not any(x["code"]=="ACTIVE_WITHOUT_CARRIER" for x in out)

def test_advisory_claim_does_not_prove_runtime():
    out=detect_recovery_findings(session(),agent([ws(claim={"by":"old-session","at":"2026-09-01","expires":"2026-09-02"})],[{"key":"alpha","lifecycle_state":"building"}]),as_of="2026-09-14")
    assert any(x["code"]=="ACTIVE_WITHOUT_CARRIER" for x in out)

def test_unclaimed_commission_requires_typed_session_truth_evidence():
    base=detect_recovery_findings(session(),agent([ws()],[{"key":"alpha","lifecycle_state":"building"}]),as_of="2026-09-14")
    assert not any(x["code"]=="UNCLAIMED_COMMISSION" for x in base)
    st=session([{"code":"SLACK_TRANSPORT_WITHOUT_RECEIVER","subject":"WS:ALPHA"}])
    typed=detect_recovery_findings(st,agent([ws()],[{"key":"alpha","lifecycle_state":"building"}]),as_of="2026-09-14")
    assert any(x["code"]=="UNCLAIMED_COMMISSION" for x in typed)

def test_multiple_terminal_bindings_are_disagreement():
    rows=[ws("WS:ALPHA-A",status="done",program="alpha"),ws("WS:ALPHA-B",status="killed",program="alpha")]
    out=detect_recovery_findings(session(),agent(rows,[{"key":"alpha","lifecycle_state":"building"}]),as_of="2026-09-14")
    assert [x["code"] for x in out]==["PROGRAM_LIFECYCLE_DISAGREEMENT"]


def test_malformed_wait_fails_closed():
    bad=agent([ws(wait={"review_after":"2026-09-25"})],[{"key":"alpha","lifecycle_state":"building"}])
    with pytest.raises(ProjectRecoveryContractError, match="wait"):
        validate_inputs(session(),bad,as_of="2026-09-14")

def test_overdue_wait_is_attention_not_resurrection():
    row=ws(wait={"kind":"natural_evidence","review_after":"2026-09-01","condition":"sample review"})
    out=detect_recovery_findings(session(),agent([row],[{"key":"alpha","lifecycle_state":"building"}]),as_of="2026-09-14")
    assert any(x["code"]=="MISSED_REVIEW_GATE" and x["disposition"]=="CEO_ATTENTION" for x in out)
    assert not any(x["code"]=="ACTIVE_WITHOUT_CARRIER" for x in out)

def test_overdue_wave_wait_is_attention_not_resurrection():
    row=ws(waves=[{"id":"W1","status":"in_progress","wait":{"kind":"calendar_window","review_after":"2026-09-01","condition":"review after window"}}])
    out=detect_recovery_findings(session(),agent([row],[{"key":"alpha","lifecycle_state":"building"}]),as_of="2026-09-14")
    assert any(x["code"]=="MISSED_REVIEW_GATE" and x.get("wave")=="W1" for x in out)
    assert not any(x["code"]=="ACTIVE_WITHOUT_CARRIER" for x in out)

def test_valid_wave_wait_projects_valid_intentional_wait():
    row=ws(waves=[{"id":"W1","status":"in_progress","wait":{"kind":"calendar_window","review_after":"2026-09-25","condition":"review after window"}}])
    a=assess_recovery(session(),agent([row],[{"key":"alpha","lifecycle_state":"building"}]),as_of="2026-09-14",observed_at="2026-09-14T12:00:00Z")
    assert a["summary"]["VALID_INTENTIONAL_WAIT"]==1

def test_active_but_complete_does_not_resurrect():
    row=ws(waves=[{"id":"W1","status":"done"},{"id":"W2","status":"dropped"}])
    out=detect_recovery_findings(session(),agent([row],[{"key":"alpha","lifecycle_state":"building"}]),as_of="2026-09-14")
    assert any(x["code"]=="ACTIVE_BUT_COMPLETE" for x in out)
    assert not any(x["code"]=="ACTIVE_WITHOUT_CARRIER" for x in out)

def test_proof_debt_does_not_resurrect_build():
    st=session([{"code":"GITHUB_MERGE_WITH_PROOF_OPEN","subject":"WS:ALPHA"}])
    out=detect_recovery_findings(st,agent([ws()],[{"key":"alpha","lifecycle_state":"building"}]),as_of="2026-09-14")
    assert any(x["code"]=="MERGED_PROOF_DEBT" for x in out)
    assert not any(x["code"]=="ACTIVE_WITHOUT_CARRIER" for x in out)

def test_unbound_executive_activity_is_unknown_not_false_healthy():
    st=session(); st["observations"]["executive"]["operations"]=[{"operation_key":"other-op","status":"RUNNING"}]
    out=detect_recovery_findings(st,agent([ws()],[{"key":"alpha","lifecycle_state":"building"}]),as_of="2026-09-14")
    assert any(x["code"]=="RUNTIME_OWNERSHIP_UNKNOWN" for x in out)
    assert not any(x["code"]=="ACTIVE_WITHOUT_CARRIER" for x in out)

def test_unavailable_github_is_unknown_not_false_healthy():
    st=session(); st["observations"]["github"]={"available":False,"reason":"quota"}
    out=detect_recovery_findings(st,agent([ws()],[{"key":"alpha","lifecycle_state":"building"}]),as_of="2026-09-14")
    assert any(x["code"]=="RUNTIME_OWNERSHIP_UNKNOWN" for x in out)

def test_partial_session_truth_scope_is_unknown():
    st=session(workstreams=["WS:OTHER"])
    out=detect_recovery_findings(st,agent([ws()],[{"key":"alpha","lifecycle_state":"building"}]),as_of="2026-09-14")
    assert any(x["code"]=="RUNTIME_OWNERSHIP_UNKNOWN" for x in out)
    assert not any(x["code"]=="ACTIVE_WITHOUT_CARRIER" for x in out)

def test_registry_unavailable_finding_counts_in_summary():
    a=assess_recovery(session(),agent([],[],available=False),as_of="2026-09-14",observed_at="2026-09-14T12:00:00Z")
    assert a["summary"]["UNKNOWN_RECONCILE"]==1
    assert any(s["subject"]=="PROGRAM_REGISTRY" for s in a["subjects"])


def test_unbound_open_pr_blocks_false_resurrection():
    st=session()
    st["observations"]["github"]["pull_requests"]=[{"repository":"o/r","number":99,"state":"open","workstream":None}]
    out=detect_recovery_findings(st,agent([ws()],[{"key":"alpha","lifecycle_state":"building"}]),as_of="2026-09-14")
    row=next(x for x in out if x["code"]=="RUNTIME_OWNERSHIP_UNKNOWN")
    assert row["evidence"]==[{"unbound_open_prs":1}]
    assert not any(x["code"]=="ACTIVE_WITHOUT_CARRIER" for x in out)

def test_canonical_agentos_wave_detail_drives_wave_wait_classification():
    row = ws(
        waves={"awaiting_ci": 0, "done": 0, "dropped": 0, "in_progress": 1, "todo": 0},
        wave_detail=[
            {
                "id": "W1",
                "status": "in_progress",
                "wait": {
                    "kind": "calendar_window",
                    "review_after": "2026-09-01",
                    "condition": "review after window",
                },
            }
        ],
    )
    assessment = assess_recovery(
        session(),
        agent([row], [{"key": "alpha", "lifecycle_state": "building"}]),
        as_of="2026-09-14",
        observed_at="2026-09-14T12:00:00Z",
    )
    assert any(
        finding["code"] == "MISSED_REVIEW_GATE" and finding.get("wave") == "W1"
        for finding in assessment["findings"]
    )
    assert not any(
        finding["code"] == "ACTIVE_WITHOUT_CARRIER"
        for finding in assessment["findings"]
    )
