"""Pure, content-addressed source continuity and same-PR release decisions."""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from datetime import datetime
from typing import Any

RECEIPT_SCHEMA = "mastermind.agent_dialogue.source_continuity.v1"
RELEASE_SCHEMA = "mastermind.agent_dialogue.source_release_transfer.v1"
_KINDS = {"CHECKPOINT_VERIFIED", "REMOTE_COMPLETE_VERIFIED"}
_EFFECTS = {"NONE", "RECONCILED_NO_OPEN_EFFECT", "OPEN_KNOWN_EFFECT", "EFFECT_UNKNOWN"}
_ENDS = {"ONGOING", "COMPLETED", "BLOCKED", "CONTEXT_BUDGET"}
_ACTIONS = {"CURRENT_MAIN_JOIN", "CHECKS", "REVIEW", "READY", "MERGE_ADJUDICATION"}
_PROBES = {"LOCAL_BRANCH", "LOCAL_HEAD", "LOCAL_TREE", "LOCAL_STATUS", "REMOTE_BRANCH", "REMOTE_PR", "REMOTE_TREE", "REMOTE_MERGE_BASE", "REMOTE_CHANGED_PATHS", "CURRENT_MAIN"}
_SHA = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_REPO = re.compile(r"^[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}$")
_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{2,255}$")
_BRANCH = re.compile(r"^(?!/)(?!.*(?:\.\.|//|@\{|\\))[A-Za-z0-9._/-]{1,240}(?<!/)$")
_UTC = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_SECRET = re.compile(r"(?i)(?:github_pat_|gh[pousr]_|xox[a-z]-|xapp-|sk-(?:ant-)?|sb_(?:secret|publishable)_)[A-Za-z0-9_-]{8,}")

class ContinuityContractError(ValueError):
    def __init__(self, code: str):
        super().__init__(code); self.code = code

def _fail(code="INPUT_INVALID"):
    raise ContinuityContractError(code)

def _closed(value: Any, keys: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys: _fail()
    return value

def _text(value: Any, limit=480, empty=False) -> str:
    if not isinstance(value, str) or len(value) > limit or value != value.strip() or (not empty and not value) or any(ord(c)<32 or ord(c)==127 for c in value) or _SECRET.search(value): _fail()
    return value

def _sha(value: Any) -> str:
    if not isinstance(value, str) or not _SHA.fullmatch(value): _fail()
    return value

def _integer(value: Any, low=0, high=10_000_000) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high: _fail()
    return value

def _boolean(value: Any) -> bool:
    if not isinstance(value, bool): _fail()
    return value

def _enum(value: Any, allowed: set[str]) -> str:
    value = _text(value, 80)
    if value not in allowed: _fail()
    return value

def _utc(value: Any) -> str:
    value = _text(value, 20)
    if not _UTC.fullmatch(value): _fail()
    try: datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError: _fail()
    return value

def _path(value: Any) -> str:
    value = _text(value, 300)
    if value.startswith(("/", "~", ".git/")) or "\\" in value or any(p in {"", ".", ".."} for p in value.split("/")) or value in {".env", ".git"}: _fail()
    return value

def _list(value: Any, item, *, limit=256, empty=True):
    if not isinstance(value, list) or len(value)>limit or (not empty and not value): _fail()
    out=[item(v) for v in value]
    if out != sorted(set(out)): _fail()
    return out

def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        out={}
        for k,v in value.items():
            if not isinstance(k,str): _fail()
            out[k]=_jsonable(v)
        return out
    if isinstance(value,(list,tuple)): return [_jsonable(v) for v in value]
    if isinstance(value,(set,frozenset,float)): _fail()
    if isinstance(value,(str,int,bool)) or value is None: return value
    _fail()

def canonical_json(value: Any) -> bytes:
    try: return json.dumps(_jsonable(value),sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode()
    except ContinuityContractError: raise
    except Exception: _fail()

def _refusal(*codes):
    return {"schema":RECEIPT_SCHEMA,"ok":False,"decision":"REFUSED","reason_codes":sorted(set(codes)) or ["INPUT_INVALID"],"receipt":None,"grants_merge_authority":False,"grants_reassignment_authority":False}

_OBS = {"operation_key","carrier","repository","pr_number","branch","pinned_base_sha","expected_remote_head_sha","remote_head_sha","remote_tree_sha","remote_merge_base_sha","remote_changed_paths","owned_paths","sealed_changed_paths","local_branch","local_head_sha","local_tree_sha","unpushed_commit_count","uncommitted_in_scope_paths","untracked_in_scope_paths","unowned_dirty_paths","unsafe_paths","external_effect_state","external_effect_evidence_ref","local_only_effect","index_lock","collision_state","current_main_sha","pr_open","pr_draft","verified_at","probe_results","last_completed_task","remaining_tasks","checks_started_or_pending","ended_because","exact_next_action"}

def verify_source_continuity(raw: Any) -> dict[str, object]:
    try:
        v=_closed(raw,_OBS)
        op=_text(v["operation_key"],256); carrier=_text(v["carrier"],320); repo=_text(v["repository"],201); branch=_text(v["branch"],240)
        if not _TOKEN.fullmatch(op) or not carrier.startswith("github:") or not _REPO.fullmatch(repo) or not _BRANCH.fullmatch(branch): _fail()
        number=_integer(v["pr_number"],1); base=_sha(v["pinned_base_sha"]); expected=_sha(v["expected_remote_head_sha"]); head=_sha(v["remote_head_sha"]); tree=_sha(v["remote_tree_sha"]); merge_base=_sha(v["remote_merge_base_sha"]); main=_sha(v["current_main_sha"])
        changed=_list(v["remote_changed_paths"],_path,empty=False); owned=_list(v["owned_paths"],_path,empty=False); sealed=_list(v["sealed_changed_paths"],_path,empty=False)
        local_branch=_text(v["local_branch"],240); local_head=_sha(v["local_head_sha"]); local_tree=_sha(v["local_tree_sha"]); unpushed=_integer(v["unpushed_commit_count"])
        uncommitted=_list(v["uncommitted_in_scope_paths"],_path); untracked=_list(v["untracked_in_scope_paths"],_path); unowned=_list(v["unowned_dirty_paths"],_path); unsafe=_list(v["unsafe_paths"],_path)
        effect=_enum(v["external_effect_state"],_EFFECTS); effect_ref=_text(v["external_effect_evidence_ref"],320); local_effect=_boolean(v["local_only_effect"]); lock=_boolean(v["index_lock"]); collision=_enum(v["collision_state"],{"CLEAR","CONFLICT","UNKNOWN"})
        open_=_boolean(v["pr_open"]); draft=_boolean(v["pr_draft"]); verified=_utc(v["verified_at"]); end=_enum(v["ended_because"],_ENDS)
        probes=v["probe_results"]
        if not isinstance(probes,list) or not probes or len(probes)>32: _fail()
        names=[]; normalized=[]
        for row in probes:
            row=_closed(row,{"name","ok","result_sha256"}); name=_text(row["name"],80); ok=_boolean(row["ok"]); digest=_text(row["result_sha256"],64)
            if not _SHA256.fullmatch(digest): _fail()
            names.append(name); normalized.append({"name":name,"ok":ok,"result_sha256":digest})
        if names != sorted(set(names)) or not _PROBES.issubset(names) or not all(r["ok"] for r in normalized): _fail()
        last=_text(v["last_completed_task"],empty=True); remaining=_list(v["remaining_tasks"],lambda x:_text(x),limit=64); checks=_list(v["checks_started_or_pending"],lambda x:_text(x),limit=64); next_=_text(v["exact_next_action"],empty=True)
    except ContinuityContractError: return _refusal("INPUT_INVALID")
    reasons=[]
    if expected!=head: reasons.append("EXPECTED_REMOTE_HEAD_MISMATCH")
    if merge_base!=base: reasons.append("MERGE_BASE_MISMATCH")
    if changed!=sealed: reasons.append("SEALED_PATH_SET_MISMATCH")
    if not set(changed)<=set(owned): reasons.append("REMOTE_PATH_OUTSIDE_OWNERSHIP")
    if unsafe: reasons.append("UNSAFE_SOURCE_PRESENT")
    if collision!="CLEAR": reasons.append("COLLISION_UNRESOLVED")
    if not open_: reasons.append("PR_NOT_OPEN")
    if not draft: reasons.append("PR_NOT_DRAFT")
    if local_branch!=branch: reasons.append("LOCAL_BRANCH_MISMATCH")
    if end=="CONTEXT_BUDGET" and (not remaining or not next_): reasons.append("CONTEXT_BUDGET_HANDOFF_INCOMPLETE")
    if reasons: return _refusal(*reasons)
    sticky=[]
    if local_head!=head: sticky.append("LOCAL_HEAD_DIFFERS")
    if local_tree!=tree: sticky.append("LOCAL_TREE_DIFFERS")
    if unpushed: sticky.append("UNPUSHED_COMMITS")
    if uncommitted: sticky.append("UNCOMMITTED_IN_SCOPE")
    if untracked: sticky.append("UNTRACKED_IN_SCOPE")
    if unowned: sticky.append("UNOWNED_DIRTY_PATHS")
    if local_effect: sticky.append("LOCAL_ONLY_EFFECT")
    if lock: sticky.append("INDEX_LOCK_PRESENT")
    if effect=="OPEN_KNOWN_EFFECT": sticky.append("EXTERNAL_EFFECT_OPEN")
    if effect=="EFFECT_UNKNOWN": sticky.append("EXTERNAL_EFFECT_UNKNOWN")
    kind="REMOTE_COMPLETE_VERIFIED" if not sticky else "CHECKPOINT_VERIFIED"
    receipt={"schema":RECEIPT_SCHEMA,"receipt_kind":kind,"operation_key":op,"carrier":carrier,"repository":repo,"pr_number":number,"branch":branch,"pinned_base_sha":base,"remote_head_sha":head,"remote_tree_sha":tree,"remote_merge_base_sha":merge_base,"changed_paths":changed,"owned_paths_sha256":hashlib.sha256(canonical_json(owned)).hexdigest(),"local_head_sha":local_head,"local_tree_sha":local_tree,"local_equals_remote":local_head==head and local_tree==tree,"unpushed_commit_count":unpushed,"uncommitted_in_scope_paths":uncommitted,"untracked_in_scope_paths":untracked,"unowned_dirty_paths":unowned,"external_effect_state":effect,"external_effect_evidence_ref":effect_ref,"collision_state":collision,"current_main_sha":main,"probe_results":normalized,"sticky_reasons":sorted(sticky),"handoff":{"last_completed_task":last,"remaining_tasks":remaining,"checks_started_or_pending":checks,"ended_because":end,"exact_next_action":next_},"verified_at":verified,"transfer_safe":False,"grants_merge_authority":False,"grants_reassignment_authority":False}
    receipt["receipt_sha256"]=hashlib.sha256(canonical_json(receipt)).hexdigest()
    return {"schema":RECEIPT_SCHEMA,"ok":True,"decision":kind,"reason_codes":[],"receipt":validate_receipt(receipt),"grants_merge_authority":False,"grants_reassignment_authority":False}

def validate_receipt(value: Any) -> dict[str, object]:
    try:
        if not isinstance(value,dict) or value.get("schema")!=RECEIPT_SCHEMA or value.get("receipt_kind") not in _KINDS: _fail("RECEIPT_INVALID")
        digest=value.get("receipt_sha256"); unsigned=dict(value); unsigned.pop("receipt_sha256",None)
        if not isinstance(digest,str) or not _SHA256.fullmatch(digest) or hashlib.sha256(canonical_json(unsigned)).hexdigest()!=digest: _fail("RECEIPT_INVALID")
        if value.get("transfer_safe") is not False or value.get("grants_merge_authority") is not False or value.get("grants_reassignment_authority") is not False: _fail("RECEIPT_INVALID")
        _sha(value["remote_head_sha"]); _sha(value["remote_tree_sha"]); _sha(value["remote_merge_base_sha"]); _utc(value["verified_at"])
        return _jsonable(value)
    except (ContinuityContractError,KeyError): raise ContinuityContractError("RECEIPT_INVALID") from None

def evaluate_release_transfer(raw: Any) -> dict[str, object]:
    deny=lambda *c:{"schema":RELEASE_SCHEMA,"ok":False,"decision":"REFUSED","reason_codes":sorted(set(c)) or ["INPUT_INVALID"],"source_receipt_sha256":None,"grants_release_authority":False,"grants_merge_authority":False,"grants_implementation_authority":False}
    try:
        receipt=validate_receipt(raw["source_receipt"]); actions=_list(raw["requested_actions"],lambda x:_text(x,80),limit=8,empty=False); _utc(raw["verified_at"])
    except Exception: return deny("INPUT_INVALID")
    reasons=[]
    if receipt["receipt_kind"]!="REMOTE_COMPLETE_VERIFIED": reasons.append("REMOTE_COMPLETE_REQUIRED")
    if raw.get("builder_result_state")!="SOL_ACCEPTED_BUILDER_RESULT": reasons.append("BUILDER_RESULT_NOT_ACCEPTED")
    if raw.get("terminal_stop_verified") is not True: reasons.append("TERMINAL_STOP_REQUIRED")
    if raw.get("stop_operation_key")!=receipt["operation_key"] or raw.get("stop_carrier")!=receipt["carrier"]: reasons.append("STOP_IDENTITY_MISMATCH")
    if raw.get("child_source_state")=="WATCH_STOP_FAILED" and raw.get("stale_child_source_suppressed") is not True: reasons.append("CHILD_SOURCE_NOT_SUPPRESSED")
    if raw.get("child_source_state") not in {"REMOVED","WATCH_STOP_FAILED"}: reasons.append("CHILD_SOURCE_STATE_INVALID")
    if raw.get("branch_writer_state")!="BRANCH_WRITER_RELEASED": reasons.append("BRANCH_WRITER_NOT_RELEASED")
    if raw.get("release_operation_key")==receipt["operation_key"]: reasons.append("FRESH_RELEASE_OPERATION_REQUIRED")
    for k in ("repository","pr_number","branch"):
        if raw.get(k)!=receipt[k]: reasons.append("SOURCE_CARRIER_MISMATCH")
    pairs=(("current_remote_head_sha","remote_head_sha"),("current_remote_tree_sha","remote_tree_sha"),("current_remote_merge_base_sha","remote_merge_base_sha"),("current_changed_paths","changed_paths"),("current_main_sha","current_main_sha"))
    if any(raw.get(a)!=receipt[b] for a,b in pairs): reasons.append("RECEIPT_STALE")
    if not set(actions)<=_ACTIONS: reasons.append("RELEASE_SCOPE_VIOLATION")
    if reasons:return deny(*reasons)
    result={"schema":RELEASE_SCHEMA,"ok":True,"decision":"RELEASE_RESPONSIBILITY_ELIGIBLE","reason_codes":[],"source_receipt_sha256":receipt["receipt_sha256"],"release_operation_key":raw["release_operation_key"],"repository":receipt["repository"],"pr_number":receipt["pr_number"],"branch":receipt["branch"],"allowed_actions":actions,"verified_at":raw["verified_at"],"grants_release_authority":False,"grants_merge_authority":False,"grants_implementation_authority":False}
    result["evidence_sha256"]=hashlib.sha256(canonical_json(result)).hexdigest(); return result

__all__=["ContinuityContractError","RECEIPT_SCHEMA","RELEASE_SCHEMA","canonical_json","verify_source_continuity","validate_receipt","evaluate_release_transfer"]
