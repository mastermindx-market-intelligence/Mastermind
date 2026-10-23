"""Source-bound reconciliation candidate for the original Terminal #1127 review-03.

No provider request, lease release, retry, cancellation, source mutation, or
approval is performed. This fixed original-owner candidate is NOT wired into
the installed Fabric status projection until separately reviewed and released.
The original request, log and remote result remain immutable.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shlex
import sqlite3
import stat
import subprocess
import time

RUN = "terminal-colw-pr1127-independent-review-03"
ROOT = "terminal-colw-20261022-pr1127"
LEASE = "037d4f680550"
HOST = "ubuntu1"
MODEL = "qwen3.8-max"
SCHEMA = "mastermind.fabric.original-review03-reconciliation.v1"
HERE = Path(__file__).resolve().parent
EXPECTED = {
    ".log": "c222d04564dafbc6885d6feb71d6326b636e69c1fc26562c049334204a76c610",
    ".request.json": "ead83381c3824aa3a34a6bc67e6bf639847fed034afeef6a6ab489e397b0e1e6",
    ".request-return.json": "12d0363a0cab313e28d2da038e47c3c5bab9981ff44250b2969deedf67bbdd2f",
    ".request-launch.json": "d046d24d9ea73f0bde25260d61667aa59cbb4bc23ca08cf899b0fd7789aa8c6f",
    ".transport-verified.json": "1f73622270058eaae45306d2cd09e50a31f775b6dd576e4f7aefc88ccf150ca8",
    ".continuation-finished.json": "3dfcd719d14909d88eb19f9ffe934a2f86de5ba36759b0a09f7e5fd6f240d55a",
    ".controller-process.jsonl": "66b4bfa1e4cb89293c781f3f09a5846934952602904d4649857d3d9125cc99c6",
    ".routing-process.jsonl": "87917429ca019084adc42c1a63aa20714b44191fc6e5699b26eb9da505bfeddb",
}
PACKET_SHA = "72c8e60626d4147b265dfa0f2efb25e283d98c11e537c2818c0dfa490a734970"
HOST_EXPECTED = {
    "stderr": "049bf2b971fd0aadd0677340830bcb89701b309f8a96e3b59e8036dd5470f45e",
    "rc": "4355a46b19d348dc2f57c046f8ef63d4538ebb936000f3c9ee954a27460dd865",
    "process": "7faa43fc03794a122c6dec9b24eaccc863b1fa3f3dead2f7902795709c3c9a3e",
    "packet": PACKET_SHA,
}

class NotQualified(ValueError):
    pass

def require(ok, why):
    if not ok:
        raise NotQualified(why)

def digest(data):
    return hashlib.sha256(data).hexdigest()

def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(",",":"),allow_nan=False).encode()

def strict_json(data):
    def pairs(seq):
        out={}
        for k,v in seq:
            require(k not in out,"duplicate_json_key")
            out[k]=v
        return out
    def finite_fail(text):
        raise NotQualified("nonfinite_json")
    return json.loads(data,object_pairs_hook=pairs,parse_constant=finite_fail)

def read_owned(path,limit=1048576):
    # Reuse the installed artifact owner's existing descriptor-held directory
    # chain, not a second file custody implementation. Every directory edge
    # (including state/remote_sub) must remain non-symlinked and unchanged.
    import artifact_delivery as delivery

    path=Path(path)
    with delivery.DirectoryChain(path.parent) as chain:
        chain.verify()
        fd=os.open(path.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=chain.fd)
        try:
            before=os.fstat(fd)
            require(stat.S_ISREG(before.st_mode) and before.st_uid==os.getuid()
                    and not before.st_mode & 0o022 and before.st_nlink==1
                    and 0<=before.st_size<=limit,"source_custody")
            data=os.read(fd,limit+1)
            after=os.fstat(fd)
            visible=os.stat(path.name,dir_fd=chain.fd,follow_symlinks=False)
            ident=lambda x:(x.st_dev,x.st_ino,x.st_size,x.st_mtime_ns,x.st_ctime_ns)
            require(ident(before)==ident(after)==ident(visible)
                    and len(data)==before.st_size,"source_changed")
            chain.verify()
            return data
        finally:
            os.close(fd)

def read_bound(path,expected,limit=1048576):
    data=read_owned(path,limit)
    require(digest(data)==expected,"source_digest_changed")
    return data

def source_snapshot():
    base=HERE/"state/remote_sub"
    data={s:read_bound(base/(RUN+s),v) for s,v in EXPECTED.items()}
    request=strict_json(data[".request.json"])
    launch=strict_json(data[".request-launch.json"])
    returned=strict_json(data[".request-return.json"])
    verified=strict_json(data[".transport-verified.json"])
    ended=strict_json(data[".continuation-finished.json"])
    for obj in (request,launch,returned,ended):
        require(obj.get("run_id",obj.get("origin_run_id"))==RUN
                and obj.get("root_id")==ROOT
                and obj.get("parent_run_id")==ROOT,"original_binding")
    require(request.get("task_class")=="review"
            and request.get("packet_sha256")==PACKET_SHA
            and request.get("packet_bytes")==2971,"original_packet")
    require(launch.get("packet_sha256")==PACKET_SHA
            and launch.get("request_sha256")==EXPECTED[".request.json"]
            and launch.get("state")=="LAUNCH_ATTEMPT_RESERVED"
            and launch.get("route")=={
                "HOST":"ubuntu1","KEY":"-","MODE":"qwen",
                "MODEL":MODEL,"POOL":"bailian","REASON":"execute_order_bailian"
            },"original_launch")
    require(returned.get("controller_rc")==124
            and returned.get("log_sha256")==EXPECTED[".log"]
            and returned.get("launch_sha256")==EXPECTED[".request-launch.json"]
            and returned.get("state")=="NATIVE_CONTROLLER_RETURNED","controller_return")
    require(ended.get("controller_rc")==124
            and ended.get("effective_run_id")==RUN
            and ended.get("background_execution") is False
            and ended.get("reason")=="continuation_evidence_unqualified","no_continuation")
    require(verified.get("run_id")==RUN and verified.get("lease_id")==LEASE
            and verified.get("host")==HOST and verified.get("mode")=="qwen"
            and verified.get("packet_sha256")==PACKET_SHA
            and verified.get("support_digest")=="558b4875ba6dda4f0a48e23692945c4c0317389deae673e84da45296e217c580","original_transport")
    log=data[".log"].decode("utf-8")
    require(log.count("RUN_RESERVED explicit=1")==1
            and log.count("LAUNCH_ATTEMPT attempt=1")==1
            and log.count("LEASE_PRESERVED effect_unknown=1 lease="+LEASE)==1
            and log.count("DONE rc=124 signal=effect_unknown reason=transport_deadline_without_rc")==1
            and " REMOTE_DONE " not in log
            and " REMOTE_CLEANED " not in log,"controller_effect_hold")
    # The existing owner's outcome ledger corroborates (it is NOT a release grant).
    ledger=HERE.parent/"orch/fabric/ledger.jsonl"
    ledger_bytes=read_owned(ledger,33554432)
    rows=[]
    for raw in ledger_bytes.splitlines(keepends=True):
        if RUN.encode() not in raw:continue
        item=strict_json(raw)
        if item.get("run_id")==RUN:rows.append((item,raw))
    require(len(rows)==1,"controller_ledger_unique")
    row,line=rows[0]
    require(row.get("root_id")==ROOT and row.get("rc")==124
            and row.get("signal")=="effect_unknown"
            and row.get("reason")=="transport_deadline_without_rc","controller_ledger_hold")
    # Broker is the same original owner evidence as the launch artifacts.
    # Its parent chain and leaf must not resolve through a symlink. Hold an
    # O_NOFOLLOW descriptor across SQLite's read-only snapshot and verify that
    # the visible database is still the same file when SQLite finishes.
    import artifact_delivery as delivery
    db=HERE/"broker/leases.sqlite"
    with delivery.DirectoryChain(db.parent) as chain:
        chain.verify()
        fd=os.open(db.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=chain.fd)
        try:
            before=os.fstat(fd)
            visible=os.stat(db.name,dir_fd=chain.fd,follow_symlinks=False)
            identity=lambda x:(x.st_dev,x.st_ino,x.st_mode,x.st_uid,
                               x.st_size,x.st_mtime_ns,x.st_ctime_ns)
            require(stat.S_ISREG(before.st_mode) and before.st_uid==os.getuid()
                    and not before.st_mode & 0o022 and before.st_nlink==1
                    and identity(before)==identity(visible),"broker_db_custody")
            with sqlite3.connect("file:"+str(db)+"?mode=ro",uri=True,timeout=5) as conn:
                lease=conn.execute("SELECT id,orchestrator_id,pool,account,host,state,model "
                                   "FROM leases WHERE id=?",(LEASE,)).fetchone()
            after=os.fstat(fd)
            visible=os.stat(db.name,dir_fd=chain.fd,follow_symlinks=False)
            require(identity(before)==identity(after)==identity(visible),
                    "broker_db_changed")
            chain.verify()
        finally:
            os.close(fd)
    require(lease is not None and tuple(lease)==
            (LEASE,ROOT,"bailian","Ryan",HOST,"expired",MODEL),
            "original_lease_not_expired")
    return {"local_source_sha256":{k:digest(v) for k,v in data.items()},
            "ledger_row_sha256":digest(line),"broker_lease_state":"expired"}

# The host inspector is fixed source with no caller-controlled path, command, ID or PID.
# Its output carries *only* the already-pinned original process/rc/output evidence.
HOST_SOURCE = r'''
import os,stat,hashlib,json,sys
run="terminal-colw-pr1127-independent-review-03"
home="/home/longr/lanes/"
paths={
"stderr":home+"ext/lanes_"+run+".stdout",
"rc":home+"ext/lanes_"+run+".rc",
"process":home+"ext/lanes/"+run+".process.jsonl",
"packet":home+"tmp/"+run+".txt",
}
wanted={
"stderr":"049bf2b971fd0aadd0677340830bcb89701b309f8a96e3b59e8036dd5470f45e",
"rc":"4355a46b19d348dc2f57c046f8ef63d4538ebb936000f3c9ee954a27460dd865",
"process":"7faa43fc03794a122c6dec9b24eaccc863b1fa3f3dead2f7902795709c3c9a3e",
"packet":"72c8e60626d4147b265dfa0f2efb25e283d98c11e537c2818c0dfa490a734970",
}
def check(condition):
 if not condition:
  raise ValueError("original_host_proof_invalid")
def file(path):
 # Inspect every ancestor through retained directory descriptors. No symlink
 # in /home/.../lanes may substitute a valid leaf file.
 components=[x for x in path.split("/") if x]
 check(path.startswith("/") and components and "." not in components and ".." not in components)
 fds=[os.open("/",os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)]
 edges=[]
 def identity(info):
  return (info.st_dev,info.st_ino,info.st_mode,info.st_uid,info.st_gid)
 def verify():
  for i,held in enumerate(fds):
   now=os.fstat(held)
   check(stat.S_ISDIR(now.st_mode) and now.st_uid in (0,os.getuid()) and not now.st_mode & 0o022)
   if i:
    visible=os.stat(edges[i-1],dir_fd=fds[i-1],follow_symlinks=False)
    check(identity(now)==identity(visible))
 try:
  verify()
  for component in components[:-1]:
   fd=os.open(component,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fds[-1])
   fds.append(fd)
   edges.append(component)
   verify()
  name=components[-1]
  fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=fds[-1])
  try:
   verify()
   before=os.fstat(fd)
   visible=os.stat(name,dir_fd=fds[-1],follow_symlinks=False)
   check(stat.S_ISREG(before.st_mode) and before.st_uid==os.getuid()
         and not before.st_mode&0o022 and before.st_nlink==1)
   check(identity(before)==identity(visible) and before.st_size==visible.st_size
         and 0<=before.st_size<=1048576)
   data=os.read(fd,1048577)
   after=os.fstat(fd)
   check(len(data)==before.st_size and identity(after)==identity(before)
         and after.st_size==before.st_size and after.st_mtime_ns==before.st_mtime_ns)
   verify()
   return data
  finally:os.close(fd)
 finally:
  for held in reversed(fds):
   os.close(held)
raw={k:file(p) for k,p in paths.items()}
d={k:hashlib.sha256(v).hexdigest() for k,v in raw.items()}
check(d==wanted)
check(raw["rc"]==b"1\n" and len(raw["stderr"])==690)
check(b"QWEN_FINAL_RESPONSE_UNCONFIRMED" in raw["stderr"] and b"429" in raw["stderr"])
check(len(raw["process"].splitlines())==1)
r=json.loads(raw["process"]);c=r["cleanup"]
check(r["schema"]=="mastermind.local_owned_process_receipt.v1" and r["label"]==run)
check(r["pid"]==r["pgid"]==3880222 and r["returncode"]==1 and r["timed_out"] is False)
check(r["runtime_failure_code"] is None)
check(r["started_at"]=="2026-10-22T18:48:04.378Z" and r["ended_at"]=="2026-10-22T18:48:07.123Z")
check(r["stdout_bytes"]==0 and r["stderr_bytes"]==690)
check(r["stdout_truncated"] is False and r["stderr_truncated"] is False)
check(all(c.get(k) is True for k in ("census_proven","identity_verified","stderr_capture_complete","stdout_capture_complete","stdin_delivery_complete")))
check(c["residual_count"]==0 and c["reason"]=="normal_completion" and c["status"]=="not_needed")
check(not c["sigkill_sent"] and not c["sigterm_sent"])
check(r["ended_at"]>r["started_at"])
print(json.dumps({"schema":"mastermind.original-review03-host-observation.v1","run_id":run,
"host":"ubuntu1","returncode":1,"review_produced":False,"worker_cleanup_proven":True,
"files_sha256":d},sort_keys=True,separators=(",",":")))
'''

def validate_host_observation(payload):
    v=strict_json(payload)
    require(type(v) is dict and set(v)=={
        "schema","run_id","host","returncode","review_produced",
        "worker_cleanup_proven","files_sha256"},"host_report_shape")
    require(v["schema"]=="mastermind.original-review03-host-observation.v1"
            and v["run_id"]==RUN and v["host"]==HOST and v["returncode"]==1
            and v["review_produced"] is False and v["worker_cleanup_proven"] is True
            and v["files_sha256"]==HOST_EXPECTED,"host_report_identity")
    return v

def observe_original_host():
    command="python3 -I -S -c "+shlex.quote(HOST_SOURCE)
    process=subprocess.run(["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes",
                            "-o","ConnectTimeout=12",HOST,command],
                           capture_output=True,timeout=25)
    require(process.returncode==0 and 0<len(process.stdout)<4096,
            "original_host_read_unavailable")
    return validate_host_observation(process.stdout)

def qualification():
    before=source_snapshot()
    host=observe_original_host()
    after=source_snapshot()
    require(before==after,"original_evidence_changed")
    proof={"schema":SCHEMA,"run_id":RUN,"root_id":ROOT,"lease_id":LEASE,
           "local":before,"remote":host,"review_performed":False,
           "lease_released_by_this_operation":False,
           "retry_permitted":False}
    return {**proof,"proof_sha256":digest(canonical(proof))}

def receipt_path():
    return HERE/"state/remote_sub"/(RUN+".original-review03-reconciliation.json")

def _saved():
    path=receipt_path()
    try:raw=read_owned(path,65536)
    except FileNotFoundError:return None
    v=strict_json(raw)
    require(type(v) is dict and set(v)=={"schema","proof","created_at","receipt_sha256"}
            and v["schema"]==SCHEMA and type(v["created_at"]) in (int,float),
            "original_receipt_shape")
    material={k:v[k] for k in ("schema","proof","created_at")}
    require(v["receipt_sha256"]==digest(canonical(material))
            and type(v["proof"]) is dict
            and v["proof"].get("run_id")==RUN
            and v["proof"].get("root_id")==ROOT
            and v["proof"].get("lease_id")==LEASE
            and v["proof"].get("review_performed") is False
            and v["proof"].get("retry_permitted") is False,"original_receipt_hash_or_binding")
    return v

def reconcile_original(run_id,root_id,expected_proof_sha256):
    """Owner-only fixed-run write; never reset/modify original log/lease/results."""
    require((run_id,root_id)==(RUN,ROOT),"original_operation_only")
    proof=qualification()
    require(expected_proof_sha256==proof["proof_sha256"],"stale_qualification")
    existing=_saved()
    if existing is None:
        material={"schema":SCHEMA,"proof":proof,"created_at":time.time()}
        material["receipt_sha256"]=digest(canonical(material))
        raw=canonical(material)+b"\n"
        path=receipt_path()
        import artifact_delivery as delivery
        with delivery.DirectoryChain(path.parent) as chain:
            chain.verify()
            # Another already-running original owner may win O_EXCL between
            # inspection and open. That is a readback condition, NOT failure
            # and NEVER permission to overwrite/erase the other receipt.
            try:
                fd=os.open(path.name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,
                           0o600,dir_fd=chain.fd)
            except FileExistsError:
                chain.verify()
            else:
                try:
                    with os.fdopen(fd,"wb") as stream:
                        require(stream.write(raw)==len(raw),"receipt_short_write")
                        stream.flush()
                        os.fsync(stream.fileno())
                    chain.verify()
                    os.fsync(chain.fd)
                    chain.verify()
                except BaseException:
                    # An effect may exist; never unlink or attempt replacement.
                    raise
        try:
            existing=_saved()
        except (json.JSONDecodeError,UnicodeError) as exc:
            # Another O_EXCL writer may still be populating its immutable file.
            # Stop on that original effect; never unlink/recreate or poll/retry
            # an uncertain rival receipt from this path.
            raise NotQualified("original_receipt_incomplete") from exc
    require(existing is not None and existing["proof"]==proof,
            "original_reconciliation_conflict")
    return status_from_receipt()

def status_from_receipt():
    try:
        saved=_saved()
        if saved is None:return None
        require(saved["proof"]==qualification(),"reconciliation_sources_changed")
        return {"schema":"mastermind.fabric_task_status.v1","run_id":RUN,
                "root_id":ROOT,"parent_run_id":ROOT,"state":"TERMINAL_FAILURE",
                "rc":1,"signal":"other","result_available":False,"result_bytes":None,
                "accepted":None,"accepted_by":None,"acceptance_state":"UNVERIFIED",
                "acceptance_reason":"REVIEW_NOT_PERFORMED",
                "original_reconciliation":{
                    "receipt_sha256":saved["receipt_sha256"],
                    "worker_terminated":True,"broker_lease_expired":True,
                    "review_completed":False,"retry_allowed":False}}
    except (OSError,TypeError,ValueError,KeyError,sqlite3.Error,
            subprocess.SubprocessError,NotQualified):
        return None

def main(argv=None):
    import argparse
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("action",choices=["check","reconcile"])
    p.add_argument("run_id");p.add_argument("--root",required=True)
    p.add_argument("--expected-proof-sha256")
    a=p.parse_args(argv)
    try:
        require((a.run_id,a.root)==(RUN,ROOT),"original_operation_only")
        if a.action=="check":
            v=qualification()
        else:
            require(type(a.expected_proof_sha256) is str and len(a.expected_proof_sha256)==64,
                    "missing_proof_sha")
            v=reconcile_original(a.run_id,a.root,a.expected_proof_sha256)
        print(canonical(v).decode())
        return 0 if v is not None else 78
    except (OSError,ValueError,TypeError,KeyError,sqlite3.Error,
            subprocess.SubprocessError,NotQualified):
        print('{"state":"REFUSED","reason":"original_review03_evidence_unqualified"}')
        return 78

if __name__=="__main__":
    raise SystemExit(main())
