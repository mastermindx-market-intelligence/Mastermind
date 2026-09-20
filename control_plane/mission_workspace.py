"""Pure, held mission-workspace reduction over already composed snapshots."""
from __future__ import annotations
from collections.abc import Mapping, Sequence
from typing import Any
from control_plane.chairman_control_room_remote import _project_agent_os_freeform

SCHEMA = "mastermind.mission_workspace.v1"
_CONTROL = "mastermind.chairman_control_room.v1"
_FABRIC = "mastermind.fabric_job_view.v1"
_MISSING = {"MISSING_PRODUCER", "NULL_BY_DESIGN", "EXCLUDED", "OMITTED", "DEGRADED"}
_ARM = ("ceo_submit_armed", "coo_autonomy_armed", "ceo_ingress_app_armed", "dialogue_bridge_armed", "terminal_return_armed")
_EXEC = {"NOT_STARTED", "IN_PROGRESS", "ACCEPTED", "CANCELLED", "FAILED", "LOST", "RATE_LIMITED"}
_DISPATCH = {"WAITING_CAPACITY", "RECEIVER_SELECTED", "DELIVERY_SENT", "PICKUP_ACKNOWLEDGED", "STARTED", "RETURNED", "DELIVERY_UNCONSUMED", "WATCH_UNPROVEN", "RUNTIME_BINDING_RECONCILIATION_REQUIRED", "EFFECT_UNKNOWN", "UNKNOWN"}

def _map(v: object) -> Mapping[str, Any]: return v if isinstance(v, Mapping) else {}
def _rows(v: object) -> list[Mapping[str, Any]]: return [_map(x) for x in v] if isinstance(v, Sequence) and not isinstance(v, (str, bytes)) else []
def _scalar(v: object) -> str | int | bool | None: return v if type(v) in (str, int, bool) else None
def _text(v: object) -> str | None: return _project_agent_os_freeform(v) if isinstance(v, str) and v else None
def _safe_items(value: object) -> tuple[list[str], bool]:
    """Keep bounded owner strings only; sensitive values become missingness."""
    kept: list[str] = []
    excluded = False
    for item in _rows(value) if not isinstance(value, (list, tuple)) else [{"v": x} for x in value]:
        raw = item.get("v") if "v" in item else None
        clean = _text(raw)
        if clean is None or clean == "agent_os_detail_redacted" or clean.startswith(("http://", "https://", "/", "~")):
            excluded = True
        else:
            kept.append(clean)
    return kept[:16], excluded
def _evidence(owner: str, ref: str | None, field: str) -> list[dict[str, Any]]:
    """No provenance is better than provenance manufactured from generation time."""
    return []
def _fact(kind: str, field: str, owner: str | None, reason: str) -> dict[str, Any]: return {"missingness_class": kind, "target_field": field, "producer_owner": owner, "reason": reason}
def _facts(values: object) -> list[dict[str, Any]]:
    found: dict[tuple[str,str,str|None,str],dict[str,Any]] = {}
    for row in _rows(values):
        k,f,o,r = row.get("missingness_class"),row.get("target_field"),row.get("producer_owner"),row.get("reason")
        if isinstance(k, str) and k in _MISSING and isinstance(f,str) and (o is None or isinstance(o,str)):
            found[(k,f,o,"source detail withheld")] = _fact(k,f,o,"source detail withheld")
    return [found[k] for k in sorted(found, key=repr)]
def _section(state: str, coverage: str, reasons: list[str], total: int | None, items: list[dict[str,Any]], overflow: int | None) -> dict[str,Any]:
    if state in {"INCOMPLETE","UNAVAILABLE","NOT_PROJECTED"}: total=overflow=None
    if state == "EMPTY": total=overflow=0
    return {"state":state,"coverage":coverage,"reason_codes":sorted(set(reasons)),"total_count":total,"items":items,"overflow_count":overflow}
def _project(v: object, keys: tuple[str,...]) -> dict[str,Any] | None:
    row=_map(v)
    return {k:_scalar(row.get(k)) for k in keys} if row else None
def _child(v: object) -> dict[str, Any]:
    row = _map(v)
    result = _project(row, ("job_id", "status", "parent_job_id", "depth", "orchestration_role", "plan_step_id", "attempt_count", "attempt_limit", "current_attempt_id")) or {}
    attempt = _map(row.get("latest_attempt"))
    result["latest_attempt"] = ({"attempt_id": _scalar(attempt.get("attempt_id")), "attempt_number": _scalar(attempt.get("attempt_number")), "status": _scalar(attempt.get("status")), "started_at": _scalar(attempt.get("started_at")), "finished_at": _scalar(attempt.get("finished_at")), "exit_code": _scalar(attempt.get("exit_code")), "has_result": attempt.get("has_result") is True, "error_present": attempt.get("error") is not None} if attempt else None)
    result["worker_id"] = None
    return result
def _valid_now(validity: Mapping[str,Any], cache: Mapping[str,Any], ref: object, root: object) -> bool:
    """Consume the server's paired B5 validity envelope, never an invented enum."""
    if cache.get("state") != "fresh" or validity.get("schema") != "mastermind.control_room_source_validity.v1" or validity.get("profile") != "b5.darwin-chrome-paired-v1" or not isinstance(ref,str) or not isinstance(root,str): return False
    if cache.get("publication_seq") != validity.get("publication_seq") or cache.get("qualification_generation") != validity.get("qualification_generation") or type(validity.get("publication_seq")) is not int: return False
    cards=[x for x in _rows(validity.get("cards")) if x.get("responsibility_ref")==ref and x.get("root_job_id")==root]
    if len(cards)!=1: return False
    c=_map(cards[0].get("components"))
    return all(type(_map(c.get(x)).get("remaining_ms")) is int and _map(c.get(x))["remaining_ms"]>0 and _map(c.get(x)).get("state") == "current" and isinstance(_map(c.get(x)).get("proof_ref"), str) for x in ("card","dispatch","owed_open_age"))
def _posture(*, execution:str, dispatch:str, current:bool, conflict:bool, blocker:bool, acceptance:Mapping[str,Any], review:str) -> tuple[str,str]:
    if dispatch=="EFFECT_UNKNOWN": return "EFFECT_UNKNOWN","A1"
    if dispatch=="RUNTIME_BINDING_RECONCILIATION_REQUIRED": return "RECONCILIATION_REQUIRED","B1"
    if conflict: return "RECONCILIATION_REQUIRED","B2"
    terminal={"FAILED":("EXECUTION_FAILED","C1"),"CANCELLED":("EXECUTION_CANCELLED","C2"),"LOST":("EXECUTION_LOST","C3"),"RATE_LIMITED":("EXECUTION_RATE_LIMITED","C4")}
    if execution in terminal: return terminal[execution]
    if blocker:return "BLOCKED","D1"
    if dispatch=="DELIVERY_UNCONSUMED":return "DELIVERED_UNCONSUMED","E1"
    if dispatch=="WATCH_UNPROVEN":return "CONSUMPTION_UNKNOWN","E2"
    if dispatch=="RETURNED" and not current:return "CONSUMPTION_UNKNOWN","E3"
    if dispatch=="RETURNED" and current:
        if execution!="ACCEPTED":return "RETURN_EXECUTION_MISMATCH","F0"
        if acceptance.get("state")=="ACCEPTED" and review=="reject":return "ACCEPTANCE_REVIEW_CONFLICT","F1"
        if acceptance.get("state")=="ACCEPTED" and acceptance.get("artifact_revision") and acceptance.get("ruling"):return "ACCEPTED_PRODUCT","F2"
        if review=="reject":return "REVIEW_REJECTED","F3"
        if review=="NOT_YET":return "RETURNED_UNREVIEWED","F4"
        if review=="approve":return "REVIEWED_NOT_ACCEPTED","F5"
    if dispatch=="STARTED":return ("RUNNING","G1") if current else ("HISTORICAL_OBSERVATION","G1h")
    if dispatch in {"WAITING_CAPACITY","RECEIVER_SELECTED","DELIVERY_SENT","PICKUP_ACKNOWLEDGED"}:return ("WAITING","G2") if current else ("HISTORICAL_OBSERVATION","G2h")
    if execution=="NOT_STARTED" and dispatch=="UNKNOWN":return "NOT_STARTED","H1"
    return "UNKNOWN","I1"

def compose_mission_workspace(*, control_room: Mapping[str,Any]|None, fabric_view: Mapping[str,Any]|None, work_ref:str, root_job_id:str|None, source_validity:Mapping[str,Any]|None, cache_currentness:Mapping[str,Any]|None, source_generation:Mapping[str,Any]|None) -> dict[str,Any]:
    control,fabric,validity,cache=_map(control_room),_map(fabric_view),_map(source_validity),_map(cache_currentness)
    cok,fok=control.get("schema")==_CONTROL,fabric.get("schema")==_FABRIC
    work=next((x for x in _rows(control.get("work")) if x.get("work_ref")==work_ref),{}) if cok else {}
    ref=work_ref if work else None; auto=next((x for x in _rows(_map(control.get("autonomy")).get("responsibilities")) if x.get("responsibility_ref")==ref and x.get("root_job_id")==root_job_id),{}) if isinstance(ref,str) else {}
    candidates=sorted({x for x in auto.get("root_job_candidates",()) if isinstance(x,str)}) if isinstance(auto.get("root_job_candidates"),Sequence) else []
    conflict=auto.get("runtime_root_state")=="CONFLICT" or len(candidates)!=1
    resolved=root_job_id if isinstance(root_job_id,str) and root_job_id in candidates and not conflict else None
    root=_map(fabric.get("root")) if fok and resolved else {}
    if root.get("job_id")!=resolved or root.get("parent_job_id") not in (None,""): resolved,root=None,{}
    dispatch=_map(auto.get("dispatch")); ds=dispatch.get("dispatch_state") if dispatch.get("dispatch_state") in _DISPATCH else "UNKNOWN"
    current=_valid_now(validity,cache,ref,resolved) and dispatch.get("historical") is False
    result,review=_map(root.get("result")),_map(root.get("review")); execution=result.get("state") if result.get("state") in _EXEC else "NOT_STARTED"; verdict=review.get("verdict") if review.get("verdict") in {"approve","reject","NOT_YET"} else "NOT_YET"
    artifacts, artifacts_excluded = _safe_items(result.get("artifacts"))
    next_actions, actions_excluded = _safe_items(result.get("next_actions"))
    acceptance={"state":"NOT_PROJECTED","reason_codes":["ACCEPTANCE_OWNER_NOT_PROJECTED"],"owner":None,"artifact_revision":None,"ruling":None,"evidence":[]}
    posture,rule=_posture(execution=execution,dispatch=ds,current=current,conflict=conflict or bool(_map(source_generation).get("conflict")),blocker=bool(auto.get("blocker") or auto.get("declared_blocker")),acceptance=acceptance,review=verdict)
    arms=_map(fabric.get("armed")); armed={k:arms.get(k) if type(arms.get(k)) is bool else None for k in _ARM}; armed["source"]=arms.get("source") if isinstance(arms.get("source"),str) else "absent"
    raw=[x for x in _rows(fabric.get("children")) if x.get("root_job_id",resolved)==resolved] if fok and resolved else []
    children=[_child(x) for x in raw]
    unjoined=fabric.get("unjoined_job_count") if type(fabric.get("unjoined_job_count")) is int and fabric.get("unjoined_job_count")>=0 else None
    if not fok: child=_section("UNAVAILABLE","UNAVAILABLE",["FABRIC_VIEW_UNAVAILABLE"],None,[],None)
    elif not resolved and unjoined is not None: child=_section("INCOMPLETE","KNOWN_SUBSET",["ROOT_NOT_JOINED","UNJOINED_JOBS_PRESENT"],None,[],None)
    elif not resolved: child=_section("UNAVAILABLE","UNAVAILABLE",["ROOT_NOT_JOINED"],None,[],None)
    elif unjoined is None: child=_section("INCOMPLETE","KNOWN_SUBSET",["UNJOINED_COUNT_UNKNOWN"],None,children,None)
    elif unjoined: child=_section("INCOMPLETE","KNOWN_SUBSET",["UNJOINED_JOBS_PRESENT"],None,children,None)
    elif not children: child=_section("EMPTY","COMPLETE",[],0,[],0)
    else: child=_section("COMPLETE","COMPLETE",[],len(children),children,0)
    read="CURRENT" if cok and fok and current else "PARTIAL" if cok or fok else "UNAVAILABLE"
    extra_facts=[_fact("MISSING_PRODUCER","acceptance",None,"acceptance owner is not projected"),_fact("MISSING_PRODUCER","children.worker_id","executive_os","worker identity is not projected"),_fact("MISSING_PRODUCER","conversation.continuation","executive_os","continuation is not projected")]
    if artifacts_excluded: extra_facts.append(_fact("EXCLUDED","execution.artifacts","executive_os","unsafe artifact detail excluded"))
    if actions_excluded: extra_facts.append(_fact("EXCLUDED","execution.next_actions","executive_os","unsafe next action detail excluded"))
    missing=_facts([*_rows(fabric.get("missingness")),*extra_facts])
    degraded=sorted({"source detail withheld" for x in [*(_rows(control.get("degraded"))),*(_rows(fabric.get("degraded")))] if x} )
    generation = {key: _scalar(_map(source_generation).get(key)) for key in ("state", "version", "generation")}
    program = {"work_ref": work_ref, "title": _text(_map(work.get("agent_os")).get("title") or work.get("title")), "state": _scalar(_map(work.get("agent_os")).get("state") or _map(work.get("agent_os")).get("status")), "next_action": _text(_map(work.get("agent_os")).get("next_action")), "github_prs": [{k: _scalar(_map(pr).get(k)) for k in ("number", "state", "head_sha", "merge_sha")} for pr in _rows(_map(work.get("github")).get("prs"))][:16], "attention_ids": [_scalar(x) for x in work.get("attention_ids", ()) if isinstance(x, str)][:16], "disagreements": [_text(_map(x).get("reason")) for x in _rows(work.get("disagreements"))][:16], "evidence": []}
    source = {"control_room_schema": control.get("schema"), "control_room_generated_at": control.get("generated_at"), "fabric_view_schema": fabric.get("schema"), "fabric_view_generated_at": fabric.get("generated_at"), "source_generation": generation, "source_coverage": [x for x,ok in (("control_room",cok),("fabric_view",fok)) if ok]}
    return {"schema":SCHEMA,"generated_at":control.get("generated_at") if isinstance(control.get("generated_at"),str) else fabric.get("generated_at"),"source":source,"read_state":{"state":read,"reason_codes":[] if read=="CURRENT" else ["SOURCE_OR_VALIDITY_INCOMPLETE"],"usable_sections":["program"] if work else []},"program":program,"mission":{"root_job_id":resolved,"root_job_candidates":candidates,"root_job_ambiguous":conflict,"runtime_root_state":"CONFLICT" if conflict else "RESOLVED" if resolved else "UNKNOWN","title":None,"status":_scalar(root.get("status")),"orchestration_role":_scalar(root.get("orchestration_role")),"plan_step_id":_scalar(root.get("plan_step_id")),"depth":_scalar(root.get("depth")),"armed":armed,"submission_availability":"UNAVAILABLE_NEW_SUBMISSION" if armed["ceo_submit_armed"] is False else "UNKNOWN","capability":{k:_scalar(_map(fabric.get("capability")).get(k)) for k in ("state","installed","version")},"evidence":[]},"principal":{"accountable_seat":_scalar(auto.get("accountable_seat")),"current_worker":_project(auto.get("current_worker"),("seat","state","effect_state","job_id","attempt_id","reason")),"current_sol_target":_project(auto.get("current_sol_target"),("seat","state","effect_state","job_id","attempt_id","reason")),"owed_turn":_project(auto.get("owed_turn"),("seat","state","effect_state","job_id","attempt_id","reason")),"evidence":[]},"children":child,"execution":{"state":execution,"summary_present":isinstance(result.get("summary"),str),"artifacts":artifacts,"errors_present":bool(result.get("errors")),"next_actions":next_actions,"evidence":[]},"review":{"required":review.get("required") if type(review.get("required")) is bool else None,"reviews_job_id":_scalar(review.get("reviews_job_id")),"verdict":verdict,"evidence":[]},"transport":{"dispatch_state":ds,"reason":_text(dispatch.get("reason")),"actionable":dispatch.get("actionable") is True,"historical":dispatch.get("historical") if type(dispatch.get("historical")) is bool else None,"watch_proven":dispatch.get("watch_proven") if type(dispatch.get("watch_proven")) is bool else None,"carrier":_project(dispatch.get("carrier"),("state","reason","historical","actionable")),"w3c":_project(dispatch.get("w3c"),("state","reason","terminal_state","wake_state","terminal_applied")),"evidence":[]},"acceptance":acceptance,"posture":{"value":posture,"rule":rule,"evidence":[]},"conversation":_section("UNAVAILABLE","NOT_PROJECTED",["MISSION_TREE_SUBSLICE_EXCLUDES_CONTENT"],None,[],None),"missingness":missing,"degraded":degraded,"budget":{},"feature_gates":{"conversation":"UNAVAILABLE","actions":"READ_ONLY","advanced":"AVAILABLE"}}
