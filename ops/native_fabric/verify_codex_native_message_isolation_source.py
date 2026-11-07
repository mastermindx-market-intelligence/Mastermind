#!/usr/bin/env python3
"""Digest-guarded replay of inert native Codex message isolation patch.

This verifier never changes the installed Macro Fabric source or makes a
provider/worker/session call. It tests only a temporary exact-source copy.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
PREFIX="codex_native_message_isolation_20261018"
PATCH=HERE/"patches"/(PREFIX+".patch")
MANIFEST=HERE/"patches"/(PREFIX+".manifest.json")
TESTS=ROOT/"tests/test_native_codex_message_isolation_source.py"
_SHA=re.compile(r"[0-9a-f]{64}")


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def run(argv: list[str], *, cwd: Path, env: dict[str,str] | None=None) -> str:
    p=subprocess.run(argv,cwd=cwd,env=env,capture_output=True,text=True,
                     check=False,timeout=75)
    if p.returncode != 0:
        stage = "TESTS" if "pytest" in argv else "PATCH"
        raise ValueError("SOURCE_REPLAY_" + stage + "_REFUSED")
    return p.stdout


def verify(source: Path) -> None:
    try:
        manifest=json.loads(MANIFEST.read_text())
    except (ValueError,OSError):
        raise ValueError("SOURCE_MANIFEST_UNAVAILABLE") from None
    exact={
        "schema","status","source_preimage_sha256","source_postimage_sha256",
        "patch_sha256","tests_sha256","runtime_modified","worker_launched",
        "provider_turn",
    }
    if (type(manifest) is not dict or set(manifest)!=exact
            or manifest["schema"]!="mastermind.codex_native_message_isolation_source/v1"
            or manifest["status"]!="candidate_not_installed"
            or any(manifest[k] is not False for k in (
                "runtime_modified","worker_launched","provider_turn"))
            or any(type(manifest[k]) is not str or _SHA.fullmatch(manifest[k]) is None
                   for k in ("source_preimage_sha256","source_postimage_sha256",
                             "patch_sha256","tests_sha256"))):
        raise ValueError("SOURCE_MANIFEST_INVALID")
    patch=PATCH.read_bytes()
    if (digest(patch)!=manifest["patch_sha256"]
            or digest(TESTS.read_bytes())!=manifest["tests_sha256"]):
        raise ValueError("SOURCE_BUNDLE_CHANGED")
    stat=source.lstat()
    if not source.is_file() or source.is_symlink() or stat.st_nlink != 1:
        raise ValueError("SOURCE_PATH_UNSAFE")
    before=source.read_bytes()
    if digest(before)!=manifest["source_preimage_sha256"]:
        raise ValueError("SOURCE_PREIMAGE_DRIFT")
    with tempfile.TemporaryDirectory(prefix="mmx-native-message-") as folder:
        work=Path(folder)
        clone=work/"native_remote.py"
        clone.write_bytes(before)
        run(["git","apply","--unidiff-zero","--check",str(PATCH)],cwd=work)
        run(["git","apply","--unidiff-zero",str(PATCH)],cwd=work)
        if digest(clone.read_bytes())!=manifest["source_postimage_sha256"]:
            raise ValueError("SOURCE_POSTIMAGE_DRIFT")
        local_env={
            k:v for k,v in os.environ.items()
            if not k.startswith(("OPENAI_","CODEX_","ANTHROPIC_"))
            and k not in {"PYTHONPATH","PYTHONHOME","HTTP_PROXY","HTTPS_PROXY"}
        }
        local_env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"]="1"
        local_env["MMX_NATIVE_CODEX_SOURCE_TEST"]=str(clone)
        output=run([
            sys.executable,"-m","pytest","-q","-p","no:cacheprovider",
            "--basetemp",str(work/"pytest-private"),str(TESTS)
        ],cwd=ROOT,env=local_env)
        print("OFFLINE_PROVIDER_FREE_TESTS="+output.strip().splitlines()[-1])
    current=source.lstat()
    if ((stat.st_dev,stat.st_ino,stat.st_mtime_ns,stat.st_size)
            !=(current.st_dev,current.st_ino,current.st_mtime_ns,current.st_size)
            or digest(source.read_bytes())!=manifest["source_preimage_sha256"]):
        raise ValueError("INSTALLED_SOURCE_DRIFT")
    print("PATCH_DIGEST_VERIFIED=true")
    print("POSTIMAGE_SHA256_VERIFIED=true")
    print("INSTALLED_SOURCE_UNCHANGED=true")
    print("WORKER_STARTED=false")
    print("MODEL_TURN=false")
    print("CAPACITY_ADMISSION_GRANTED=false")


def main() -> int:
    p=argparse.ArgumentParser()
    p.add_argument("--source",type=Path,required=True)
    args=p.parse_args()
    try:
        verify(args.source)
    except (ValueError,OSError,subprocess.TimeoutExpired) as exc:
        print("SOURCE_REPLAY_REFUSED="+str(exc).splitlines()[0][:90])
        return 2
    return 0


if __name__=="__main__":
    raise SystemExit(main())
