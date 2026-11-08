#!/usr/bin/env python3
"""Prepare pinned full-app compatibility artifacts; never modify or install donor."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
PIN = "687f282e8625c6b8d11ff58211a90524be2e4317"
PREFIXES = ("packages/core/tools/src/", "packages/mcp/mcp-client/src/")

def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def retain(path: Path, data: bytes) -> None:
    if path.is_symlink():
        raise ValueError("artifact may not be a symlink")
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError(f"existing artifact differs: {path.name}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(data)

def prepare(supplied: str) -> dict:
    donor = Path(supplied)
    if not donor.is_absolute() or donor.resolve(strict=True) != donor:
        raise ValueError("one absolute non-symlinked pinned donor is required")
    git = ["/usr/bin/git", "--no-optional-locks", "-C", str(donor),
           "-c", "core.fsmonitor=false", "-c", "core.hooksPath=/dev/null"]
    def observe(*args):
        return subprocess.check_output(git + list(args), text=True, timeout=15).strip()
    if observe("rev-parse", "HEAD") != PIN or observe("status", "--porcelain"):
        raise ValueError("clean full-app donor pin required")
    manifest = json.loads((ROOT / "source-manifest.json").read_text())
    if (manifest["schema"] != "mastermind.dsh_fullapp_runtime_source.v1"
            or manifest["donor_sha"] != PIN or manifest["production_armed"] is not False
            or digest((donor / "pnpm-lock.yaml").read_bytes()) != manifest["donor_lock_sha256"]):
        raise ValueError("full-app source identity mismatch")
    patches = manifest["patches"]
    expected_outputs = {}
    for row in patches:
        if row["file"] not in ("strict-dispatch-binding.patch", "mcp-generation-admission.patch"):
            raise ValueError("unexpected patch")
        if digest((ROOT / row["file"]).read_bytes()) != row["sha256"]:
            raise ValueError("patch identity mismatch")
        expected_outputs.update(row["outputs"])
    cache = ROOT / ".cache"
    if cache.is_symlink():
        raise ValueError("artifact root may not be symlinked")
    cache.mkdir(mode=0o700, exist_ok=True)
    for relative, expected in manifest["source_sha256"].items():
        path = PurePosixPath(relative)
        if (path.is_absolute() or ".." in path.parts
                or not relative.startswith(PREFIXES) or path.suffix != ".ts"):
            raise ValueError("unexpected donor input path")
        data = (donor / relative).read_bytes()
        if digest(data) != expected:
            raise ValueError(f"donor input changed: {relative}")
        retain(cache / "pristine" / relative, data)
        output = cache / "patched" / relative
        if output.exists() and digest(output.read_bytes()) == expected_outputs.get(relative):
            continue
        retain(output, data)
    for row in patches:
        states = [digest((cache / "patched" / relative).read_bytes()) == expected
                  for relative, expected in row["outputs"].items()]
        if all(states):
            continue
        if any(states):
            raise ValueError("partial patch effect requires reconciliation")
        patch = ROOT / row["file"]
        subprocess.run(["/usr/bin/git", "apply", "--check", str(patch)],
                       cwd=cache / "patched", check=True, timeout=15)
        subprocess.run(["/usr/bin/git", "apply", str(patch)],
                       cwd=cache / "patched", check=True, timeout=15)
        for relative, expected in row["outputs"].items():
            if digest((cache / "patched" / relative).read_bytes()) != expected:
                raise ValueError("patched output identity mismatch")
    receipt = {"schema": "mastermind.dsh_fullapp_runtime_prepared.v1",
               "donor_sha": PIN, "source_files": len(manifest["source_sha256"]),
               "patched_sha256": expected_outputs, "installed": False, "provider_calls": 0}
    (cache / "preparation-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt

if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: prepare.py /absolute/pinned/donor")
    print(json.dumps(prepare(sys.argv[1]), sort_keys=True))
