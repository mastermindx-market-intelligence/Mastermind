#!/usr/bin/env python3
"""Prepare the pinned native session cancellation patch in an owned copy only."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
PIN = "687f282e8625c6b8d11ff58211a90524be2e4317"
PREFIX = "packages/api/session-controller/src/"
CHANGED = frozenset(PREFIX + name for name in ("index.ts", "commands.ts", "agent.ts", "history.ts"))

def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def validate_manifest(value: dict, patch: bytes) -> dict:
    if (type(value) is not dict or type(value.get("source_sha256")) is not dict
            or type(value.get("output_sha256")) is not dict):
        raise ValueError("native session source manifest refused")
    if (value["schema"] != "mastermind.dsh_native_session_source.v1" or value["donor_sha"] != PIN
            or value["production_armed"] is not False or set(value["output_sha256"]) != CHANGED
            or not CHANGED <= set(value["source_sha256"])
            or not 4 <= len(value["source_sha256"]) <= 128):
        raise ValueError("native session source manifest refused")
    for name, digest in {**value["source_sha256"], **value["output_sha256"]}.items():
        path = PurePosixPath(name)
        if (path.is_absolute() or ".." in path.parts or not name.startswith(PREFIX)
                or path.suffix != ".ts" or len(digest) != 64
                or any(c not in "0123456789abcdef" for c in digest)):
            raise ValueError("native session source path or digest refused")
    if hashlib.sha256(patch).hexdigest() != value["patch_sha256"]:
        raise ValueError("native session patch changed")
    headers = patch.decode().splitlines()
    if ({line[6:] for line in headers if line.startswith("+++ b/")} != CHANGED
            or {line[6:] for line in headers if line.startswith("--- a/")} != CHANGED):
        raise ValueError("native session patch scope changed")
    return value

def manifest() -> dict:
    return validate_manifest(json.loads((ROOT / "native-session-source.json").read_bytes()),
                             (ROOT / "native-session-generation.patch").read_bytes())

def prepared_receipt(expected: dict) -> dict:
    return {"schema": "mastermind.dsh_native_session_prepared.v1", "donor_sha": PIN,
            "patch_sha256": expected["patch_sha256"], "source_files": len(expected["source_sha256"]),
            "output_sha256": expected["output_sha256"], "installed": False, "provider_calls": 0}

def donor_source(supplied: str | Path, expected: dict) -> Path:
    donor = Path(supplied)
    if not donor.is_absolute() or donor.resolve(strict=True) != donor:
        raise ValueError("absolute clean pinned native donor required")
    git = ["git", "--no-optional-locks", "-C", str(donor), "-c", "core.fsmonitor=false",
           "-c", "core.hooksPath=/dev/null"]
    if (subprocess.check_output(git + ["rev-parse", "HEAD"], text=True).strip() != PIN
            or subprocess.check_output(git + ["status", "--porcelain"], text=True).strip()
            or sha(donor / "pnpm-lock.yaml") != expected["donor_lock_sha256"]):
        raise ValueError("native donor identity changed")
    for name, digest in expected["source_sha256"].items():
        if sha(donor / name) != digest:
            raise ValueError("native donor source changed: " + name)
    return donor

def apply_to_owned_tree(tree: Path, donor: Path) -> dict:
    """Called after the existing packager copies the donor, before its native build."""
    expected = manifest()
    donor = donor_source(donor, expected)
    tree = Path(tree)
    if (not tree.is_absolute() or tree.resolve(strict=True) != tree
            or tree == donor or tree.is_relative_to(donor) or donor.is_relative_to(tree)
            or (tree / ".git").exists()):
        raise ValueError("separate owned native build tree required")
    states = []
    for name, before in expected["source_sha256"].items():
        path = tree / name
        if path.resolve(strict=True) != path or not path.is_file():
            raise ValueError("owned native source path refused")
        observed = sha(path)
        after = expected["output_sha256"].get(name, before)
        if observed not in {before, after}:
            raise ValueError("owned native source differs: " + name)
        if name in CHANGED:
            states.append(observed == after)
    if any(states) and not all(states):
        raise ValueError("partial native patch requires original-effect reconciliation")
    if not all(states):
        patch = ROOT / "native-session-generation.patch"
        subprocess.run(["git", "apply", "--check", str(patch)], cwd=tree, check=True, timeout=15)
        subprocess.run(["git", "apply", str(patch)], cwd=tree, check=True, timeout=15)
    for name, digest in expected["output_sha256"].items():
        if sha(tree / name) != digest:
            raise ValueError("native patched output differs")
    return prepared_receipt(expected)

def prepare(supplied: str) -> dict:
    expected = manifest()
    donor = donor_source(supplied, expected)
    cache = ROOT / ".cache" / "native-session"
    if cache.resolve(strict=False) != cache:
        raise ValueError("native artifact directory may not be symlinked")
    cache.mkdir(parents=True, exist_ok=True)
    for name, digest in expected["source_sha256"].items():
        target = cache / name
        if target.is_symlink():
            raise ValueError("native artifact may not be symlinked")
        if target.exists():
            if sha(target) not in {digest, expected["output_sha256"].get(name, digest)}:
                raise ValueError("existing native artifact differs: " + name)
            continue
        if target.parent.resolve(strict=False) != target.parent:
            raise ValueError("native artifact parent may not be symlinked")
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as stream:
            stream.write((donor / name).read_bytes())
    receipt = apply_to_owned_tree(cache, donor)
    # Reuse exactly the donor package's already-installed development dependencies.
    package = Path("packages/api/session-controller")
    modules = cache / package / "node_modules"
    installed = donor / package / "node_modules"
    if modules.is_symlink():
        if modules.resolve(strict=True) != installed.resolve(strict=True):
            raise ValueError("native package dependency link differs")
    elif modules.exists():
        raise ValueError("native package dependency directory differs")
    elif installed.is_dir():
        modules.symlink_to(installed, target_is_directory=True)
    receipt_path = cache / "preparation-receipt.json"
    if receipt_path.is_symlink() or (receipt_path.exists() and not receipt_path.is_file()):
        raise ValueError("native preparation receipt path refused")
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt

if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: prepare_native_session.py /absolute/pinned/donor")
    print(json.dumps(prepare(sys.argv[1]), sort_keys=True))
