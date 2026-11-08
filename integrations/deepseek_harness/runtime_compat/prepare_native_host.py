"""Prepare the exact native host-admission patch in an owned test/build copy."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
PIN = "687f282e8625c6b8d11ff58211a90524be2e4317"
PACKAGES = ("packages/core/agent", "packages/core/agent-loop", "apps/cli",
            "packages/typert/protocol", "packages/api/remote-access",
            "packages/api/gateway", "packages/client/connection",
            "packages/llm/llm", "packages/llm/llm-deepseek",
            "packages/credentials/deepseek-account", "packages/credentials/deepseek-account-platform",
            "packages/llm/llm-deepseek-account",
            'packages/core/tools', 'packages/sandbox/sandbox-policy', 'packages/interaction/user-approval', 'packages/skill/skill', 'packages/boot/app-boot', 'vendor/loader')
CHANGED = frozenset((PACKAGES[0] + "/src/index.ts", PACKAGES[1] + "/src/index.ts",
                    PACKAGES[2] + "/src/profile-boot.ts", PACKAGES[3] + "/src/index.ts",
                    PACKAGES[4] + "/src/index.ts", PACKAGES[5] + "/src/index.ts",
                    PACKAGES[6] + "/src/rpc-host.ts", PACKAGES[1] + "/src/agent.ts",
                    PACKAGES[1] + "/src/inbox.ts", PACKAGES[7] + "/src/index.ts",
                    PACKAGES[8] + "/src/adapter.ts", PACKAGES[8] + "/src/host.ts",
                    PACKAGES[8] + "/src/types.ts", PACKAGES[9] + "/src/index.ts",
                    PACKAGES[10] + "/src/index.ts", PACKAGES[11] + "/src/index.ts",
                    PACKAGES[11] + "/src/catalog.ts", PACKAGES[11] + "/src/listing.ts",
                    PACKAGES[12] + "/src/index.ts", PACKAGES[13] + "/src/index.ts", PACKAGES[14] + "/src/index.ts", PACKAGES[15] + "/src/index.ts", PACKAGES[16] + "/src/profile-context.ts",
                    PACKAGES[17] + "/src/index.ts", PACKAGES[17] + "/src/config/tree.ts", PACKAGES[17] + "/src/config/entry.ts"))

def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def source_path_allowed(name: str) -> bool:
    """One closed path scope for preparation and complete-package qualification."""
    path = PurePosixPath(name)
    return (not path.is_absolute() and ".." not in path.parts
            and ((any(name.startswith(package + "/src/") for package in PACKAGES)
                  and path.suffix in (".ts", ".tsx"))
                 or name in ("packages/llm/llm/package.json", "packages/boot/app-boot/package.json")))

def manifest() -> dict:
    value = json.loads((ROOT / "native-host-source.json").read_bytes())
    patch = (ROOT / "native-host-admission.patch").read_bytes()
    if (type(value) is not dict or value.get("schema") != "mastermind.dsh_native_host_source.v1"
            or value.get("donor_sha") != PIN or value.get("production_armed") is not False
            or type(value.get("source_sha256")) is not dict
            or type(value.get("output_sha256")) is not dict
            or set(value["output_sha256"]) != CHANGED
            or not CHANGED <= set(value["source_sha256"])
            or not 3 <= len(value["source_sha256"]) <= 256
            or hashlib.sha256(patch).hexdigest() != value.get("patch_sha256")):
        raise ValueError("native host source manifest refused")
    for name, digest in {**value["source_sha256"], **value["output_sha256"]}.items():
        if (not source_path_allowed(name)
                or type(digest) is not str or len(digest) != 64
                or any(c not in "0123456789abcdef" for c in digest)):
            raise ValueError("native host source path or digest refused")
    lines = patch.decode().splitlines()
    if ({line[6:] for line in lines if line.startswith("+++ b/")} != CHANGED
            or {line[6:] for line in lines if line.startswith("--- a/")} != CHANGED):
        raise ValueError("native host patch scope refused")
    return value

def donor_source(supplied: str | Path, expected: dict) -> Path:
    donor = Path(supplied)
    if not donor.is_absolute() or donor.resolve(strict=True) != donor:
        raise ValueError("canonical native donor required")
    git = ["git", "--no-optional-locks", "-C", str(donor), "-c", "core.fsmonitor=false",
           "-c", "core.hooksPath=/dev/null"]
    if (subprocess.check_output(git + ["rev-parse", "HEAD"], text=True).strip() != PIN
            or subprocess.check_output(git + ["status", "--porcelain"], text=True).strip()
            or sha(donor / "pnpm-lock.yaml") != expected["donor_lock_sha256"]):
        raise ValueError("native host donor identity changed")
    for name, digest in expected["source_sha256"].items():
        if sha(donor / name) != digest:
            raise ValueError("native host donor source changed: " + name)
    return donor

def apply_to_owned_tree(tree: Path, donor: Path) -> dict:
    expected = manifest()
    donor = donor_source(donor, expected)
    tree = Path(tree)
    if (not tree.is_absolute() or tree.resolve(strict=True) != tree
            or tree == donor or tree.is_relative_to(donor) or donor.is_relative_to(tree)
            or (tree / ".git").exists()):
        raise ValueError("separate owned native host tree required")
    states = []
    for name, before in expected["source_sha256"].items():
        path = tree / name
        if path.resolve(strict=True) != path or not path.is_file():
            raise ValueError("owned native host path refused")
        observed = sha(path)
        after = expected["output_sha256"].get(name, before)
        if observed not in {before, after}:
            raise ValueError("owned native host source differs: " + name)
        if name in CHANGED:
            states.append(observed == after)
    if any(states) and not all(states):
        raise ValueError("partial native host patch requires original-effect reconciliation")
    if not all(states):
        patch = str(ROOT / "native-host-admission.patch")
        # This owned tree may be ignored inside the original source worktree.
        # Prevent Git from treating its paths as filters relative to that parent.
        env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
        env["GIT_CEILING_DIRECTORIES"] = str(tree.parent)
        subprocess.run(["git", "-c", "gc.auto=0", "apply", "--check", patch], cwd=tree, env=env, check=True, timeout=15)
        subprocess.run(["git", "-c", "gc.auto=0", "apply", patch], cwd=tree, env=env, check=True, timeout=15)
    for name, digest in expected["output_sha256"].items():
        if sha(tree / name) != digest:
            raise ValueError("native host patched output differs")
    return {"schema": "mastermind.dsh_native_host_prepared.v1", "donor_sha": PIN,
            "patch_sha256": expected["patch_sha256"], "source_files": len(expected["source_sha256"]),
            "output_sha256": expected["output_sha256"], "installed": False, "provider_calls": 0}

def prepare(supplied: str) -> dict:
    expected = manifest()
    donor = donor_source(supplied, expected)
    tree = ROOT / (".cache/native-host-" + expected["patch_sha256"])
    if tree.resolve(strict=False) != tree:
        raise ValueError("native host artifact directory redirected")
    tree.mkdir(parents=True, exist_ok=True)
    for name, digest in expected["source_sha256"].items():
        target = tree / name
        if target.is_symlink() or target.parent.resolve(strict=False) != target.parent:
            raise ValueError("native host artifact path redirected")
        if target.exists():
            if sha(target) not in {digest, expected["output_sha256"].get(name, digest)}:
                raise ValueError("native host artifact differs: " + name)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as stream:
            stream.write((donor / name).read_bytes())
    receipt = apply_to_owned_tree(tree, donor)
    for package in PACKAGES:
        installed = donor / package / "node_modules"
        link = tree / package / "node_modules"
        if link.is_symlink():
            if link.resolve(strict=True) != installed.resolve(strict=True):
                raise ValueError("native host dependency link differs")
        elif link.exists():
            raise ValueError("native host dependency directory differs")
        elif installed.is_dir():
            link.symlink_to(installed, target_is_directory=True)
    receipt_path = tree / "preparation-receipt.json"
    if receipt_path.is_symlink() or (receipt_path.exists() and not receipt_path.is_file()):
        raise ValueError("native host receipt path refused")
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt

if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: prepare_native_host.py /absolute/pinned/donor")
    print(json.dumps(prepare(sys.argv[1]), sort_keys=True))
