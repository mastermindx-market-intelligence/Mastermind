"""Run exact-source Web Fabric manual-pin patch without touching installed source."""
from pathlib import Path
import shutil
import subprocess
import pytest

ROOT=Path(__file__).resolve().parents[1]
PATCH=ROOT/"ops/native_fabric/patches/web_fabric_manual_model_20261021.patch"
SOURCE=ROOT/"integrations/studio_direct_mcp"
BLOBS={"fabric-backend.mjs":"6c828312a3de711ded1eaa388efaf4fb4fc4a149","fabric-backend.test.mjs":"555d5b89c651c47eb4ed3209063d8bacc7960463"}

def test_exact_source_web_fabric_manual_model_pin(tmp_path):
    if not shutil.which("git") or not shutil.which("node"): pytest.skip("Node/git absent")
    out=tmp_path/"integrations/studio_direct_mcp"
    out.mkdir(parents=True)
    for name,blob in BLOBS.items():
        assert subprocess.check_output(["git","hash-object",str(SOURCE/name)],text=True).strip()==blob, "incumbent changed: reconcile first"
        shutil.copy2(SOURCE/name,out/name)
    shutil.copytree(SOURCE/"fixtures",out/"fixtures")
    subprocess.run(["git","init","-q"],cwd=tmp_path,check=True)
    subprocess.run(["git","apply","--check",str(PATCH)],cwd=tmp_path,check=True)
    subprocess.run(["git","apply",str(PATCH)],cwd=tmp_path,check=True)
    run=subprocess.run(["node","--test","fabric-backend.test.mjs"],cwd=out,text=True,
                       stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=70)
    assert run.returncode==0,run.stdout[-14000:]
