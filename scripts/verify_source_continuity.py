#!/usr/bin/env python3
"""Read-only live Git/GitHub probe for source-continuity receipts."""
from __future__ import annotations
import argparse, base64, hashlib, json, os, re, subprocess, sys, urllib.parse, urllib.request
from pathlib import Path
from typing import Any, Mapping, Sequence
from integrations.slack_agent_dialogue.source_continuity import verify_source_continuity

MAX_INPUT=1_048_576; MAX_BLOB=1_048_576
_SECRET=re.compile(rb"(?i)(?:github_pat_|gh[pousr]_|xox[a-z]-|xapp-|sk-(?:ant-)?|sb_(?:secret|publishable)_)[A-Za-z0-9_-]{8,}")
class ProbeFailure(RuntimeError): pass

def _pairs(pairs):
    out={}
    for k,v in pairs:
        if k in out: raise ProbeFailure()
        out[k]=v
    return out

def _load(path):
    try:
        raw=sys.stdin.buffer.read(MAX_INPUT+1) if path=="-" else Path(path).read_bytes()
        if len(raw)>MAX_INPUT: raise ProbeFailure()
        return json.loads(raw,object_pairs_hook=_pairs,parse_constant=lambda _:(_ for _ in ()).throw(ProbeFailure()))
    except Exception: raise ProbeFailure() from None

def _run(args,cwd):
    try:return subprocess.run(args,cwd=cwd,check=True,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=20).stdout
    except Exception:raise ProbeFailure() from None

def _gh(repo,path):
    token=os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
    if not token: raise ProbeFailure()
    req=urllib.request.Request("https://api.github.com"+path,headers={"Accept":"application/vnd.github+json","Authorization":"Bearer "+token,"X-GitHub-Api-Version":"2022-11-28"})
    try:
        with urllib.request.urlopen(req,timeout=20) as r:return json.load(r)
    except Exception:raise ProbeFailure() from None

def _paths(raw):return sorted(x.decode() for x in raw.split(b"\0") if x)
def _probe(name,value):return {"name":name,"ok":True,"result_sha256":hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":")).encode()).hexdigest()}
def _unsafe(path):return path.startswith(("/","~",".git/")) or "\\" in path or any(p in {"",".",".."} for p in path.split("/")) or path in {".env",".git"}

def collect_observation(config: Mapping[str,Any],command_runner=_run,github_get=None,now=None):
    repo=config["repository"]; root=str(config["repo_root"]); branch=config["branch"]; number=int(config["pr_number"]); gh=github_get or (lambda p:_gh(repo,p)); now=now or (lambda:__import__("datetime").datetime.now(__import__("datetime").timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    def cmd(*a):return command_runner(list(a),root).decode().strip()
    top=cmd("git","rev-parse","--show-toplevel"); local_branch=cmd("git","branch","--show-current"); local_head=cmd("git","rev-parse","HEAD"); local_tree=cmd("git","rev-parse","HEAD^{tree}")
    unstaged=_paths(command_runner(["git","diff","--name-only","-z"],root)); staged=_paths(command_runner(["git","diff","--cached","--name-only","-z"],root)); untracked=_paths(command_runner(["git","ls-files","--others","--exclude-standard","-z"],root)); lock=bool(cmd("git","rev-parse","--git-path","index.lock") and Path(root,".git","index.lock").exists())
    remote_line=cmd("git","ls-remote","--heads",str(config.get("remote_name","origin")),"refs/heads/"+branch); remote_head=remote_line.split()[0]
    pr=gh(f"/repos/{repo}/pulls/{number}"); commit=gh(f"/repos/{repo}/git/commits/{remote_head}"); compare=gh(f"/repos/{repo}/compare/{config['pinned_base_sha']}...{remote_head}"); main=gh(f"/repos/{repo}/branches/{config.get('base_branch','master')}")["commit"]["sha"]
    changed=sorted(f["filename"] for f in compare["files"]); unsafe=[p for p in changed if _unsafe(p)]; blob_rows=[]
    for path in changed:
        row=gh(f"/repos/{repo}/contents/{urllib.parse.quote(path)}?ref={remote_head}")
        if row.get("type")!="file" or row.get("encoding")!="base64" or int(row.get("size",MAX_BLOB+1))>MAX_BLOB: unsafe.append(path);continue
        try:data=base64.b64decode(row["content"],validate=False)
        except Exception:unsafe.append(path);continue
        if b"\0" in data or _SECRET.search(data):unsafe.append(path)
        blob_rows.append((path,hashlib.sha256(data).hexdigest()))
    owned=sorted(config["owned_paths"]); dirty=sorted(set(unstaged+staged)); unowned=sorted(p for p in dirty+untracked if p not in owned); unpushed=0 if local_head==remote_head else int(cmd("git","rev-list","--count",remote_head+".."+local_head))
    probes={"LOCAL_BRANCH":local_branch,"LOCAL_HEAD":local_head,"LOCAL_TREE":local_tree,"LOCAL_STATUS":[dirty,untracked,lock],"REMOTE_BRANCH":remote_head,"REMOTE_PR":[pr["state"],pr["draft"],pr["head"]["sha"],pr["head"]["ref"]],"REMOTE_TREE":commit["tree"]["sha"],"REMOTE_MERGE_BASE":compare["merge_base_commit"]["sha"],"REMOTE_CHANGED_PATHS":changed,"CURRENT_MAIN":main}
    return {"operation_key":config["operation_key"],"carrier":config["carrier"],"repository":repo,"pr_number":number,"branch":branch,"pinned_base_sha":config["pinned_base_sha"],"expected_remote_head_sha":config["expected_remote_head_sha"],"remote_head_sha":remote_head,"remote_tree_sha":commit["tree"]["sha"],"remote_merge_base_sha":compare["merge_base_commit"]["sha"],"remote_changed_paths":changed,"owned_paths":owned,"sealed_changed_paths":sorted(config["sealed_changed_paths"]),"local_branch":local_branch,"local_head_sha":local_head,"local_tree_sha":local_tree,"unpushed_commit_count":unpushed,"uncommitted_in_scope_paths":sorted(p for p in dirty if p in owned),"untracked_in_scope_paths":sorted(p for p in untracked if p in owned),"unowned_dirty_paths":unowned,"unsafe_paths":sorted(set(unsafe)),"external_effect_state":config["external_effect_state"],"external_effect_evidence_ref":config["external_effect_evidence_ref"],"local_only_effect":config["local_only_effect"],"index_lock":lock,"collision_state":config["collision_state"],"current_main_sha":main,"pr_open":pr["state"]=="open","pr_draft":pr["draft"] is True,"verified_at":now(),"probe_results":sorted([_probe(k,v) for k,v in probes.items()]+[_probe("REMOTE_BLOB_SAFETY",blob_rows)],key=lambda r:r["name"]),"last_completed_task":config.get("last_completed_task",""),"remaining_tasks":sorted(config.get("remaining_tasks",[])),"checks_started_or_pending":sorted(config.get("checks_started_or_pending",[])),"ended_because":config.get("ended_because","ONGOING"),"exact_next_action":config.get("exact_next_action","")}

def main(argv:Sequence[str]|None=None)->int:
    p=argparse.ArgumentParser();p.add_argument("--config",required=True);a=p.parse_args(argv)
    try: result=verify_source_continuity(collect_observation(_load(a.config)))
    except Exception:
        print(json.dumps({"schema":"mastermind.source_continuity_error.v1","error":"INVALID_INPUT","message":"input is invalid"},sort_keys=True),file=sys.stderr);return 2
    print(json.dumps(result,sort_keys=True,separators=(",",":")))
    return 0 if result["ok"] else 1
if __name__=="__main__":raise SystemExit(main())
