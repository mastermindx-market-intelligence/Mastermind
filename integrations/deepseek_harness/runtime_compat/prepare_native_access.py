#!/usr/bin/env python3
"""Compose scoped owner access with the exact original native host admission."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess
import sys

if __package__:
    from . import prepare_native_host as native_host
    from . import prepare_native_session as native_session
else:
    import prepare_native_host as native_host
    import prepare_native_session as native_session

ROOT = Path(__file__).resolve().parent
PIN = "687f282e8625c6b8d11ff58211a90524be2e4317"
LEGACY_PACKAGES = ("packages/api/remote-access", "packages/api/gateway", "packages/api/remotes")
PACKAGES = (*LEGACY_PACKAGES, "packages/api/session-controller", "packages/client/connection", "packages/client/file-upload", "packages/client/ui-deliverables")
PREFIXES = tuple(package + "/src/" for package in PACKAGES)
CHANGED_V1 = frozenset((PREFIXES[0] + "index.ts", PREFIXES[0] + "types.ts",
                        PREFIXES[1] + "index.ts", PREFIXES[1] + "types.ts", PREFIXES[2] + "index.ts"))
CHANGED_V2 = CHANGED_V1 | {PREFIXES[3] + "index.ts", PREFIXES[3] + "list.ts", PREFIXES[3] + "commands.ts"}
CHANGED_V3 = CHANGED_V2 | {PREFIXES[4] + "index.ts", PREFIXES[4] + "rpc.ts", PREFIXES[4] + "rpc-host.ts",
                           PREFIXES[5] + "index.ts", PREFIXES[5] + "http-route.ts"}
CHANGED = CHANGED_V3 | {PREFIXES[6] + "present-open.ts"}

def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def validate_manifest(value: dict, patch: bytes) -> dict:
    if (type(value) is not dict or type(value.get("source_sha256")) is not dict
            or type(value.get("base_sha256")) is not dict
            or type(value.get("output_sha256")) is not dict):
        raise ValueError("native access source manifest refused")
    version = value.get("schema")
    current = version != "mastermind.dsh_native_access_source.v1"
    changed = CHANGED if version == "mastermind.dsh_native_access_source.v4" else CHANGED_V3 if version == "mastermind.dsh_native_access_source.v3" else CHANGED_V2 if current else CHANGED_V1
    prefixes = PREFIXES if version == "mastermind.dsh_native_access_source.v4" else PREFIXES[:6] if version == "mastermind.dsh_native_access_source.v3" else PREFIXES[:4] if current else PREFIXES[:3]
    if (version not in {"mastermind.dsh_native_access_source.v1", "mastermind.dsh_native_access_source.v2", "mastermind.dsh_native_access_source.v3", "mastermind.dsh_native_access_source.v4"}
            or value.get("donor_sha") != PIN or value.get("production_armed") is not False
            or set(value["output_sha256"]) != changed
            or set(value["base_sha256"]) != set(value["source_sha256"])
            or not changed <= set(value["source_sha256"])
            or not 5 <= len(value["source_sha256"]) <= 128):
        raise ValueError("native access source manifest refused")
    for mapping in ("source_sha256", "base_sha256", "output_sha256"):
        for name, digest in value[mapping].items():
            path = PurePosixPath(name)
            if (path.is_absolute() or ".." in path.parts or not name.startswith(prefixes)
                    or path.suffix != ".ts" or type(digest) is not str or len(digest) != 64
                    or any(c not in "0123456789abcdef" for c in digest)):
                raise ValueError("native access source path or digest refused")
    for key in ("host_patch_sha256", "host_manifest_sha256", "donor_lock_sha256",
                *(("session_patch_sha256", "session_manifest_sha256") if current else ())):
        digest = value.get(key)
        if type(digest) is not str or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise ValueError("native access host identity refused")
    if hashlib.sha256(patch).hexdigest() != value.get("patch_sha256"):
        raise ValueError("native access patch changed")
    headers = patch.decode().splitlines()
    if ({line[6:] for line in headers if line.startswith("+++ b/")} != changed
            or {line[6:] for line in headers if line.startswith("--- a/")} != changed):
        raise ValueError("native access patch scope changed")
    return value

def manifest() -> dict:
    return validate_manifest(json.loads((ROOT / "native-access-source.json").read_bytes()),
                             (ROOT / "native-owner-access.patch").read_bytes())

def session_source(expected: dict) -> dict | None:
    if expected["schema"] == "mastermind.dsh_native_access_source.v1":
        return None
    if sha(ROOT / "native-session-source.json") != expected["session_manifest_sha256"]:
        raise ValueError("native access requires its exact session source composition")
    session = native_session.manifest()
    if (session["patch_sha256"] != expected["session_patch_sha256"]
            or any(expected["source_sha256"].get(name) != digest
                   for name, digest in session["source_sha256"].items())):
        raise ValueError("native access session source changed")
    return session

def host_source(expected: dict):
    if sha(ROOT / "native-host-source.json") != expected["host_manifest_sha256"]:
        raise ValueError("native access requires its exact host source composition")
    module = native_host
    host = module.manifest()
    if host["patch_sha256"] != expected["host_patch_sha256"]:
        raise ValueError("native access host patch changed")
    session = session_source(expected)
    outputs = {**host["output_sha256"], **(session["output_sha256"] if session else {})}
    if expected["base_sha256"] != {
        name: outputs.get(name, digest)
        for name, digest in expected["source_sha256"].items()
    }:
        raise ValueError("native access base is not the original host postimage")
    return module, host

def prepared_receipt(expected: dict) -> dict:
    current = expected["schema"] != "mastermind.dsh_native_access_source.v1"
    version = expected["schema"].rsplit(".", 1)[1]
    return {"schema": "mastermind.dsh_native_access_prepared." + version, "donor_sha": PIN,
            **({"session_patch_sha256": expected["session_patch_sha256"]} if current else {}),
            "patch_sha256": expected["patch_sha256"], "host_patch_sha256": expected["host_patch_sha256"],
            "source_files": len(expected["source_sha256"]),
            "output_sha256": expected["output_sha256"], "installed": False, "provider_calls": 0}

def donor_source(supplied: str | Path, expected: dict) -> Path:
    donor = Path(supplied)
    if not donor.is_absolute() or donor.resolve(strict=True) != donor:
        raise ValueError("absolute clean pinned native donor required")
    git = ["git", "-c", "gc.auto=0", "--no-optional-locks", "-C", str(donor),
           "-c", "core.fsmonitor=false", "-c", "core.hooksPath=/dev/null"]
    if (subprocess.check_output(git + ["rev-parse", "HEAD"], text=True).strip() != PIN
            or subprocess.check_output(git + ["status", "--porcelain"], text=True).strip()
            or sha(donor / "pnpm-lock.yaml") != expected["donor_lock_sha256"]):
        raise ValueError("native donor identity changed")
    _, host = host_source(expected)
    for name, digest in {**host["source_sha256"], **expected["source_sha256"]}.items():
        if sha(donor / name) != digest:
            raise ValueError("native donor source changed: " + name)
    return donor

def apply_to_owned_tree(tree: Path, donor: Path) -> dict:
    expected = manifest()
    donor = donor_source(donor, expected)
    _, host = host_source(expected)
    tree = Path(tree)
    if (not tree.is_absolute() or tree.resolve(strict=True) != tree
            or tree == donor or tree.is_relative_to(donor) or donor.is_relative_to(tree)
            or (tree / ".git").exists()):
        raise ValueError("separate owned native build tree required")
    states = []
    session = session_source(expected)
    base = {**host["source_sha256"], **host["output_sha256"],
            **(session["source_sha256"] if session else {}), **(session["output_sha256"] if session else {}),
            **expected["base_sha256"]}
    for name, before in base.items():
        path = tree / name
        if path.resolve(strict=True) != path or not path.is_file():
            raise ValueError("owned native source path refused")
        observed = sha(path)
        after = expected["output_sha256"].get(name, before)
        if observed not in {before, after}:
            raise ValueError("owned native access source differs: " + name)
        if name in expected["output_sha256"]:
            states.append(observed == after)
    if any(states) and not all(states):
        raise ValueError("partial native access patch requires original-effect reconciliation")
    if not all(states):
        patch = ROOT / "native-owner-access.patch"
        for args in (["--check"], []):
            subprocess.run(["git", "-c", "gc.auto=0", "apply", *args, str(patch)],
                           cwd=tree, check=True, timeout=15)
    for name, digest in expected["output_sha256"].items():
        if sha(tree / name) != digest:
            raise ValueError("native access patched output differs")
    return prepared_receipt(expected)

def prepare(supplied: str) -> dict:
    expected = manifest()
    donor = donor_source(supplied, expected)
    host_module, host = host_source(expected)
    cache = ROOT / ".cache" / "native-access" / expected["patch_sha256"]
    if cache.resolve(strict=False) != cache:
        raise ValueError("native access artifact directory may not be symlinked")
    cache.mkdir(parents=True, exist_ok=True)
    for name, digest in {**host["source_sha256"], **expected["source_sha256"]}.items():
        target = cache / name
        if target.is_symlink() or target.parent.resolve(strict=False) != target.parent:
            raise ValueError("native access artifact path redirected")
        if target.exists():
            allowed = {digest, host["output_sha256"].get(name, digest),
                       expected["base_sha256"].get(name, digest), expected["output_sha256"].get(name, digest)}
            if sha(target) not in allowed:
                raise ValueError("existing native access artifact differs: " + name)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as stream:
            stream.write((donor / name).read_bytes())
    complete = all(sha(cache / name) == digest for name, digest in expected["output_sha256"].items())
    if not complete:
        if any(sha(cache / name) == digest for name, digest in expected["output_sha256"].items()):
            raise ValueError("partial native access patch requires original-effect reconciliation")
        if session_source(expected) is not None:
            native_session.apply_to_owned_tree(cache, donor)
        host_module.apply_to_owned_tree(cache, donor)
    receipt = apply_to_owned_tree(cache, donor)
    packages = PACKAGES if expected["schema"] == "mastermind.dsh_native_access_source.v4" else PACKAGES[:6] if expected["schema"] == "mastermind.dsh_native_access_source.v3" else PACKAGES[:4] if session_source(expected) is not None else LEGACY_PACKAGES
    for package in set(packages) | set(host_module.PACKAGES):
        modules, installed = cache / package / "node_modules", donor / package / "node_modules"
        if modules.is_symlink():
            if modules.resolve(strict=True) != installed.resolve(strict=True):
                raise ValueError("native access dependency link differs")
        elif modules.exists():
            raise ValueError("native access dependency directory differs")
        elif installed.is_dir():
            modules.symlink_to(installed, target_is_directory=True)
    target = cache / "preparation-receipt.json"
    if target.is_symlink() or (target.exists() and not target.is_file()):
        raise ValueError("native access receipt path refused")
    target.write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt

if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: prepare_native_access.py /absolute/pinned/donor")
    print(json.dumps(prepare(sys.argv[1]), sort_keys=True))
