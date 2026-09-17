"""Pure exact-key recovery classification for R8-A.

The classifier never treats quietness, advisory claims, or missing prose as evidence of
abandonment. A recoverable missing frontier requires positive source coverage: current
GitHub observations plus fresh Executive observations that establish no scoped runtime
operation, or an already-typed Session Truth disagreement.
"""
from __future__ import annotations
from collections import defaultdict
from collections.abc import Mapping
from datetime import date
from typing import Any
from control_plane.project_recovery_contract import TERMINAL_WAVE, TERMINAL_WORKSTREAM, workstream_wave_rows

RUNTIME_UNKNOWN={"RUNTIME_STATE_UNAVAILABLE","RUNTIME_STATE_STALE"}
PROOF_DEBT={"GITHUB_MERGE_WITH_PROOF_OPEN"}
UNCLAIMED={"SLACK_TRANSPORT_WITHOUT_RECEIVER","SLACK_TRANSPORT_WITHOUT_ACK"}
BLOCKING_COLLISION={"MULTIPLE_ACTIVE_CARRIERS"}
ACTIVE_PR_STATES={"open"}
ACTIVE_EXEC_STATES={"QUEUED","CLAIMED","RUNNING","STARTED","BLOCKED","AWAITING_REVIEW"}

def _ws_id(key: str) -> str:
    return key if key.startswith("WS:") else f"WS:{key}"

def build_recovery_indexes(session_truth: Mapping[str,Any], agentos_state: Mapping[str,Any]) -> dict[str,Any]:
    workstreams={}
    waves={}
    by_program=defaultdict(list)
    for row in agentos_state.get("workstreams",[]):
        if not isinstance(row,Mapping) or not isinstance(row.get("key"),str): continue
        wid=_ws_id(row["key"]); workstreams[wid]=row
        program=row.get("program")
        if isinstance(program,str) and program: by_program[program].append(wid)
        for wave in workstream_wave_rows(row, label=f"workstream[{row.get('key') or 'unknown'}]"):
            if isinstance(wave,Mapping) and isinstance(wave.get("id"),str): waves[(wid,wave["id"])]=wave
    reg=agentos_state.get("program_registry") or {}
    programs={r["key"]:r for r in reg.get("programs",[]) if isinstance(r,Mapping) and isinstance(r.get("key"),str)} if reg.get("available") is True else {}
    sf=defaultdict(list)
    for finding in session_truth.get("findings",[]):
        if isinstance(finding,Mapping) and isinstance(finding.get("subject"),str): sf[finding["subject"]].append(finding)
    scope=session_truth.get("scope") or {}
    covered_workstreams={item for item in scope.get("workstreams") or [] if isinstance(item,str)} if isinstance(scope,Mapping) else set()
    scoped_repositories={item for item in scope.get("repositories") or [] if isinstance(item,str)} if isinstance(scope,Mapping) else set()
    obs=session_truth.get("observations") or {}
    gh=obs.get("github") if isinstance(obs,Mapping) else None
    github_available=isinstance(gh,Mapping) and gh.get("available") is True and bool(scoped_repositories)
    active_prs=defaultdict(list)
    unbound_open_prs=[]
    if github_available:
        for pr in gh.get("pull_requests") or []:
            if not isinstance(pr,Mapping) or pr.get("repository") not in scoped_repositories: continue
            if str(pr.get("state") or "").lower() not in ACTIVE_PR_STATES: continue
            wid=pr.get("workstream")
            if isinstance(wid,str) and wid:
                active_prs[_ws_id(wid)].append(pr)
            else:
                unbound_open_prs.append(pr)
    ex=obs.get("executive") if isinstance(obs,Mapping) else None
    executive_available=isinstance(ex,Mapping) and ex.get("available") is True and ex.get("fresh") is True
    executive_active=[]
    if executive_available:
        executive_active=[op for op in ex.get("operations") or [] if isinstance(op,Mapping) and str(op.get("status") or "").upper() in ACTIVE_EXEC_STATES]
    return {"workstreams":workstreams,"waves":waves,"programs":programs,"workstreams_by_program":{k:sorted(v) for k,v in by_program.items()},"session_findings":dict(sf),"program_registry_available":reg.get("available") is True,"covered_workstreams":covered_workstreams,"scoped_repositories":scoped_repositories,"github_available":github_available,"active_prs":dict(active_prs),"unbound_open_prs":unbound_open_prs,"executive_available":executive_available,"executive_active":executive_active}

def wait_state(wait: Mapping[str,Any]|None, *, as_of: str) -> str:
    if not wait: return "NONE"
    review_after=wait.get("review_after")
    if not isinstance(review_after,str): return "NONE"
    try: due=date.fromisoformat(review_after); today=date.fromisoformat(as_of)
    except ValueError: return "NONE"
    return "OVERDUE" if due < today else "VALID"

def _finding(code:str, subject:str, disposition:str, *, workstream:str|None=None, program:str|None=None, wave:str|None=None, owner:str="Agent OS", evidence:list[dict[str,Any]]|None=None, action:str) -> dict[str,Any]:
    return {"code":code,"subject":subject,"program":program,"workstream":workstream,"wave":wave,"disposition":disposition,"canonical_owner":owner,"evidence":evidence or [],"next_ceo_action":action}

def _ws_status(row:Mapping[str,Any])->str: return str(row.get("status") or "").lower()
def _nonterminal(row:Mapping[str,Any])->bool: return _ws_status(row) not in TERMINAL_WORKSTREAM

def has_valid_wait(row: Mapping[str, Any], *, as_of: str) -> bool:
    if wait_state(row.get("wait") if isinstance(row.get("wait"), Mapping) else None, as_of=as_of) == "VALID":
        return True
    for wave in workstream_wave_rows(row, label=f"workstream[{row.get('key') or 'unknown'}]"):
        if isinstance(wave, Mapping) and wait_state(wave.get("wait") if isinstance(wave.get("wait"), Mapping) else None, as_of=as_of) == "VALID":
            return True
    return False

def _typed_gate(row:Mapping[str,Any], *, as_of:str) -> bool:
    # Both current and overdue authored waits explain why the frontier is quiet.
    # Overdue waits become CEO attention; they must not be laundered into resurrection.
    if wait_state(row.get("wait") if isinstance(row.get("wait"),Mapping) else None,as_of=as_of) in {"VALID", "OVERDUE"}: return True
    if _ws_status(row)=="blocked" or bool(row.get("blocked_by")) or isinstance(row.get("needs_ceo"),Mapping): return True
    waves=workstream_wave_rows(row, label=f"workstream[{row.get('key') or 'unknown'}]")
    for wave in waves:
        if not isinstance(wave,Mapping): continue
        if wait_state(wave.get("wait") if isinstance(wave.get("wait"),Mapping) else None,as_of=as_of) in {"VALID", "OVERDUE"}: return True
    return False

def detect_recovery_findings(session_truth: Mapping[str,Any], agentos_state: Mapping[str,Any], *, as_of: str) -> list[dict[str,Any]]:
    idx=build_recovery_indexes(session_truth,agentos_state); out=[]
    if not idx["program_registry_available"]:
        out.append(_finding("RUNTIME_OWNERSHIP_UNKNOWN","PROGRAM_REGISTRY","UNKNOWN_RECONCILE",owner="Agent OS / semantic program registry",action="Restore/reconcile the canonical program-registry projection before asserting orphan programs."))
    else:
        for pkey,program in sorted(idx["programs"].items()):
            if str(program.get("lifecycle_state") or "").lower() != "building": continue
            bindings=idx["workstreams_by_program"].get(pkey,[])
            if not bindings:
                out.append(_finding("ORPHAN_BUILDING_PROGRAM",f"PROGRAM:{pkey}","RECOVERY_REQUIRED",program=pkey,action="Admit a fresh Sol recovery review; do not fabricate worker execution."))
            elif all(not _nonterminal(idx["workstreams"][w]) for w in bindings):
                out.append(_finding("PROGRAM_LIFECYCLE_DISAGREEMENT",f"PROGRAM:{pkey}","UNKNOWN_RECONCILE",program=pkey,evidence=[{"terminal_workstreams":bindings}],action="Reconcile semantic lifecycle against terminal workstreams before any successor commission."))
    for ws,row in sorted(idx["workstreams"].items()):
        if not _nonterminal(row): continue
        program=row.get("program"); typed=idx["session_findings"].get(ws,[]); codes={f.get("code") for f in typed}
        if codes & (RUNTIME_UNKNOWN|BLOCKING_COLLISION):
            code="MULTIPLE_ACTIVE_CARRIERS" if "MULTIPLE_ACTIVE_CARRIERS" in codes else "RUNTIME_OWNERSHIP_UNKNOWN"
            out.append(_finding(code,ws,"UNKNOWN_RECONCILE",workstream=ws,program=program,owner="Executive OS / RuntimeBinding",evidence=[{"session_truth_codes":sorted(c for c in codes if isinstance(c,str))}],action="Reconcile exact runtime/carrier ownership; preserve the current operation and do not fail over.")); continue
        wait=row.get("wait") if isinstance(row.get("wait"),Mapping) else None
        state=wait_state(wait,as_of=as_of)
        if state=="OVERDUE": out.append(_finding("MISSED_REVIEW_GATE",ws,"CEO_ATTENTION",workstream=ws,program=program,evidence=[{"review_after":wait.get("review_after")}],action="Sol reviews the overdue gate and explicitly continues, parks, or closes the workstream."))
        needs=row.get("needs_ceo")
        if isinstance(needs,Mapping) and isinstance(needs.get("by_when"),str):
            try:
                if date.fromisoformat(needs["by_when"]) < date.fromisoformat(as_of): out.append(_finding("CEO_DECISION_OVERDUE",ws,"CEO_ATTENTION",workstream=ws,program=program,evidence=[{"by_when":needs["by_when"]}],action="Surface the bounded Chairman/Sol decision; do not dispatch worker work from prose."))
            except ValueError: pass
        waves=workstream_wave_rows(row, label=f"workstream[{row.get('key') or 'unknown'}]")
        for wave in waves:
            if not isinstance(wave, Mapping): continue
            wwait = wave.get("wait") if isinstance(wave.get("wait"), Mapping) else None
            if wait_state(wwait, as_of=as_of) == "OVERDUE":
                out.append(_finding("MISSED_REVIEW_GATE",ws,"CEO_ATTENTION",workstream=ws,program=program,wave=str(wave.get("id") or "") or None,evidence=[{"review_after":wwait.get("review_after")}],action="Sol reviews the overdue wave gate and explicitly continues, parks, or closes it."))
        all_waves_terminal=bool(waves) and all(isinstance(w,Mapping) and str(w.get("status") or "").lower() in TERMINAL_WAVE for w in waves)
        if all_waves_terminal: out.append(_finding("ACTIVE_BUT_COMPLETE",ws,"CEO_ATTENTION",workstream=ws,program=program,action="Repair Agent OS organizational status; do not create a new build."))
        proof_debt=bool(codes & PROOF_DEBT)
        stale_next="SUPERSEDED_NEXT_ACTION" in codes
        if proof_debt: out.append(_finding("MERGED_PROOF_DEBT",ws,"CEO_ATTENTION",workstream=ws,program=program,owner="GitHub / proof owner",action="Complete the declared production-proof gate before closing the parent."))
        if stale_next: out.append(_finding("SUPERSEDED_NEXT_ACTION",ws,"CEO_ATTENTION",workstream=ws,program=program,action="Repair the durable next_action from newer canonical evidence."))
        if codes & UNCLAIMED:
            out.append(_finding("UNCLAIMED_COMMISSION",ws,"RECOVERY_REQUIRED",workstream=ws,program=program,action="Rebind pre-START capacity or admit a fresh receiver; delivery alone is not START."))
            continue
        # Positive or explicit non-runtime frontier evidence suppresses resurrection.
        if idx["active_prs"].get(ws) or _typed_gate(row,as_of=as_of) or all_waves_terminal or proof_debt or stale_next: continue
        if ws not in idx["covered_workstreams"]:
            out.append(_finding("RUNTIME_OWNERSHIP_UNKNOWN",ws,"UNKNOWN_RECONCILE",workstream=ws,program=program,owner="Session Truth + Agent OS",action="Expand the accepted Session Truth scope to this exact workstream before recovery classification."))
            continue
        if not idx["github_available"] or not idx["executive_available"]:
            if not any(f.get("workstream")==ws and f["disposition"]=="UNKNOWN_RECONCILE" for f in out):
                out.append(_finding("RUNTIME_OWNERSHIP_UNKNOWN",ws,"UNKNOWN_RECONCILE",workstream=ws,program=program,owner="GitHub + Executive OS / RuntimeBinding",action="Restore current carrier/runtime visibility before deciding whether the frontier is abandoned."))
            continue
        # An open PR inside the scoped repositories but without exact Workstream identity
        # can still be this frontier's carrier.  Never declare abandonment until that
        # carrier debt is resolved; titles/branches are forbidden substitute joins.
        if idx["unbound_open_prs"]:
            out.append(_finding("RUNTIME_OWNERSHIP_UNKNOWN",ws,"UNKNOWN_RECONCILE",workstream=ws,program=program,owner="GitHub / carrier metadata",evidence=[{"unbound_open_prs":len(idx["unbound_open_prs"])}],action="Bind or rule out open GitHub carriers by exact workstream identity before recovery; never infer from PR title or branch name."))
            continue
        # R1 executive rows currently expose operation identity but no workstream binding.
        # Zero active operations globally is conclusive negative runtime evidence; any active
        # operation makes this workstream ambiguous rather than falsely healthy.
        if idx["executive_active"]:
            out.append(_finding("RUNTIME_OWNERSHIP_UNKNOWN",ws,"UNKNOWN_RECONCILE",workstream=ws,program=program,owner="Executive OS / RuntimeBinding",evidence=[{"unbound_active_operations":len(idx["executive_active"])}],action="Bind current Executive operation evidence to the exact workstream before recovery; do not infer ownership from unrelated activity."))
            continue
        if not any(f.get("workstream")==ws and f["disposition"] in {"RECOVERY_REQUIRED","UNKNOWN_RECONCILE"} for f in out):
            out.append(_finding("ACTIVE_WITHOUT_CARRIER",ws,"RECOVERY_REQUIRED",workstream=ws,program=program,owner="Agent OS + GitHub + Executive OS",evidence=[{"github_active_carriers":0,"executive_active_operations":0}],action="Assign Sol attention and reconcile/admit the exact next child; do not resurrect the old browser tab."))
    out.sort(key=lambda f:(f["subject"],f["code"])); return out
