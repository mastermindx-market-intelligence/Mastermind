"""Immutable Project Recovery assessment assembly and bounded rendering."""
from __future__ import annotations
import copy
from collections.abc import Mapping
from datetime import datetime
from typing import Any
from control_plane.project_recovery_contract import ASSESSMENT_SCHEMA, DISPOSITIONS, assessment_semantic_hash, validate_inputs
from control_plane.project_recovery_rules import build_recovery_indexes, detect_recovery_findings, has_valid_wait

PRECEDENCE={"NO_RECOVERY_ACTION":0,"VALID_INTENTIONAL_WAIT":1,"CEO_ATTENTION":2,"RECOVERY_REQUIRED":3,"UNKNOWN_RECONCILE":4}

def _ts(value:str)->str:
    text=value[:-1]+"+00:00" if value.endswith("Z") else value
    parsed=datetime.fromisoformat(text)
    if parsed.tzinfo is None or parsed.utcoffset() is None: raise ValueError("observed_at must be timezone-aware ISO-8601")
    return value

def semantic_projection(assessment: Mapping[str,Any]) -> dict[str,Any]:
    return {k:copy.deepcopy(v) for k,v in assessment.items() if k not in {"observed_at","semantic_hash"}}

def assess_recovery(session_truth:Mapping[str,Any], agentos_state:Mapping[str,Any], *, as_of:str, observed_at:str) -> dict[str,Any]:
    st,ao,day=validate_inputs(session_truth,agentos_state,as_of=as_of); _ts(observed_at)
    findings=detect_recovery_findings(st,ao,as_of=day); idx=build_recovery_indexes(st,ao)
    grouped={}
    for finding in findings: grouped.setdefault(finding["subject"],[]).append(finding)
    subjects=[]
    for ws,row in sorted(idx["workstreams"].items()):
        rows=grouped.get(ws,[])
        if rows: disp=max((f["disposition"] for f in rows),key=lambda d:PRECEDENCE[d])
        elif has_valid_wait(row, as_of=day): disp="VALID_INTENTIONAL_WAIT"
        else: disp="NO_RECOVERY_ACTION"
        subjects.append({"subject":ws,"workstream":ws,"program":row.get("program") or row.get("program_key"),"disposition":disp})
    for pkey in sorted(idx["programs"]):
        sid=f"PROGRAM:{pkey}"
        if not any(s["subject"]==sid for s in subjects):
            rows=grouped.get(sid,[]); disp=max((f["disposition"] for f in rows),key=lambda d:PRECEDENCE[d]) if rows else "NO_RECOVERY_ACTION"
            subjects.append({"subject":sid,"workstream":None,"program":pkey,"disposition":disp})
    represented={s["subject"] for s in subjects}
    for sid, rows in sorted(grouped.items()):
        if sid in represented: continue
        disp=max((f["disposition"] for f in rows),key=lambda d:PRECEDENCE[d])
        first=rows[0]
        subjects.append({"subject":sid,"workstream":first.get("workstream"),"program":first.get("program"),"disposition":disp})
    summary={d:0 for d in sorted(DISPOSITIONS)}
    for s in subjects: summary[s["disposition"]]+=1
    observations=st.get("observations") or {}; agentobs=observations.get("agentos") or {}
    receipt={"schema":ASSESSMENT_SCHEMA,"as_of":day,"observed_at":observed_at,"sources":{"session_truth_semantic_hash":st["semantic_hash"],"agentos_source_sha":agentobs.get("source_sha") or ao.get("source_sha"),"program_registry_available":idx["program_registry_available"]},"summary":summary,"subjects":sorted(subjects,key=lambda s:s["subject"]),"findings":findings}
    receipt["semantic_hash"]=assessment_semantic_hash(semantic_projection(receipt)); return receipt

def render_assessment(assessment:Mapping[str,Any])->str:
    lines=[f"schema: {assessment.get('schema')}",f"as_of: {assessment.get('as_of')}",f"semantic_hash: {assessment.get('semantic_hash')}"]
    for f in assessment.get("findings") or []:
        if f.get("disposition") in {"RECOVERY_REQUIRED","UNKNOWN_RECONCILE","CEO_ATTENTION"}: lines.append(f"{f.get('disposition')} {f.get('subject')} {f.get('code')} -> {f.get('next_ceo_action')}")
    return "\n".join(lines)+"\n"
