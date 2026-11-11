"""Build an exact local-commit manifest; no remote repository or hosted CI."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[2]


def build(destination):
    commit=subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip()
    names=subprocess.check_output(["git","ls-tree","-r","--name-only",commit],cwd=ROOT,text=True).splitlines()
    if not 1<=len(names)<=300:raise RuntimeError("invalid source closure")
    files={}
    for name in names:
        raw=subprocess.check_output(["git","show",commit+":"+name],cwd=ROOT)
        if (ROOT/name).is_symlink() or (ROOT/name).read_bytes()!=raw:raise RuntimeError("source differs from local commit: "+name)
        files[name]=hashlib.sha256(raw).hexdigest()
    document=dict(schema="mastermind.browser_direct_build.v1",source_commit=commit,files=files)
    payload=(json.dumps(document,indent=2,sort_keys=True)+"\n").encode()
    destination.write_bytes(payload)
    return {"source_commit":commit,"manifest_sha256":hashlib.sha256(payload).hexdigest(),"files":len(files)}


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--output",type=Path,required=True)
    print(json.dumps(build(parser.parse_args().output)))
