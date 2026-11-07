"""Build an isolated full native Web/ACP qualification copy; never install it."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import prepare_native_host as host
import prepare_native_session as session
import prepare_native_acp as acp

# Reuse the original complete package inventory, including native libraries,
# ACP/Session outputs, browser assets and dependency symlinks.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from package_attended import inventory


def record_inventory(tree: Path, target: Path) -> dict:
    # The original host bundler includes AcpSession inside acp/lib/index.js.
    required = ("packages/acp/acp/lib/index.js", "packages/core/session/lib/index.js",
                "apps/web/dist/index.html")
    if not all((tree / name).is_file() for name in required):
        raise ValueError("complete native runtime outputs required")
    entries = inventory(tree)
    path = target / "runtime-inventory.json"
    path.write_text(json.dumps(entries, sort_keys=True, separators=(",", ":")) + "\n")
    return {"file": path.name, "sha256": host.sha(path), "entries": len(entries)}

def build(donor_arg: str, target_arg: str, pnpm_arg: str, *, native_acp: bool = False) -> dict:
    expected = host.manifest()
    donor = host.donor_source(donor_arg, expected)
    target, pnpm = Path(target_arg), Path(pnpm_arg)
    if (not target.is_absolute() or target.resolve(strict=False) != target or target.exists()
            or target.is_relative_to(donor) or donor.is_relative_to(target)):
        raise ValueError("fresh independent native qualification tree required")
    if (not pnpm.is_absolute() or pnpm.resolve(strict=True) != pnpm
            or json.loads((pnpm.parent.parent / "package.json").read_bytes())["version"] != "11.28.5"):
        raise ValueError("accepted pnpm 11.28.5 required")
    node = Path("/opt/homebrew/Cellar/node/26.5.0/bin/node")
    if not node.is_file() or node.resolve(strict=True) != node:
        raise ValueError("qualified native node required")
    for parent, dirs, files in os.walk(donor, followlinks=False):
        dirs[:] = [name for name in dirs if name not in (".git", ".cache", ".turbo")]
        for name in dirs + files:
            path = Path(parent) / name
            if path.is_symlink() and not path.resolve(strict=True).is_relative_to(donor):
                raise ValueError("native dependency escapes original donor")
    target.mkdir(mode=0o700, parents=True)
    tree = target / "app"
    print("NATIVE_COMPANY_FIXTURE_COPY_STARTED", flush=True)
    shutil.copytree(donor, tree, symlinks=True,
                    ignore=shutil.ignore_patterns(".git", ".cache", ".turbo"))
    session_receipt = session.apply_to_owned_tree(tree, donor)
    host_receipt = host.apply_to_owned_tree(tree, donor)
    acp_receipt = acp.apply_to_owned_tree(tree, donor) if native_acp else None
    print("NATIVE_COMPANY_FIXTURE_BUILD_STARTED", flush=True)
    build_env = {key: os.environ[key] for key in ("HOME", "PATH", "TMPDIR", "LANG", "LC_ALL", "SDKROOT", "DEVELOPER_DIR") if key in os.environ}
    build_env.update(CI="true", DSH_CLIENT_TITLE="Mastermind", DSH_CLIENT_COMMIT_HASH=host.PIN)
    subprocess.run([str(node), str(pnpm), "run", "build:artifacts"], cwd=tree,
                   env=build_env, stdin=subprocess.DEVNULL, check=True)
    package = json.loads((tree / "apps/cli/package.json").read_bytes())
    if package["exports"]["./profile-boot"]["default"] != "./lib/profile-boot.js":
        raise ValueError("original stable profile boot export changed")
    outputs = {}
    for relative in host.PACKAGES:
        for file in sorted((tree / relative / "lib").rglob("*")):
            if file.is_file() and not file.is_symlink():
                outputs[file.relative_to(tree).as_posix()] = host.sha(file)
    for path in ("apps/cli/lib/bin.js", "apps/cli/lib/profile-boot.js", "apps/web/dist/index.html",
                 ".dsh-build/client-build-environment.json"):
        outputs[path] = host.sha(tree / path)
    closure = record_inventory(tree, target)
    receipt = {"schema": "mastermind.dsh_native_company_fixture.v1", "donor_sha": host.PIN,
               "runtime_inventory": closure,
               "host_preparation": host_receipt, "session_preparation": session_receipt,
               "node": str(node), "node_sha256": host.sha(node), "pnpm_sha256": host.sha(pnpm),
               "output_sha256": outputs, "installed": False, "provider_calls": 0,
               "production_armed": False}
    if acp_receipt is not None:
        receipt["native_acp_preparation"] = acp_receipt
    (target / "build-manifest.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print("NATIVE_COMPANY_FIXTURE_BUILT " + host.sha(target / "build-manifest.json"), flush=True)
    return receipt

if __name__ == "__main__":
    if len(sys.argv) not in (4, 5) or (len(sys.argv) == 5 and sys.argv[4] != "--native-acp"):
        raise SystemExit("Usage: build-company-host-fixture.py /pinned/donor /fresh/fixture /pnpm.cjs [--native-acp]")
    build(*sys.argv[1:4], native_acp=len(sys.argv) == 5)
