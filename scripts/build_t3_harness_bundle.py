#!/usr/bin/env python3
"""Build one inert, exact-source T3 tool bundle; never alter native profiles.

Source must match an existing commit. Native installation, trust, source release,
MCP enrollment and running-agent reload remain explicit separate operations.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from integrations.t3_harness.runtime import SOURCE_FILES, SCHEMA, encode
from integrations.t3_harness.native_launch import executable_digest

REQUIREMENTS = "mcp==2.3.0\n"


def build(output: Path, release_commit: str, *, source_root: Path = ROOT) -> dict:
    if not re.fullmatch(r"[0-9a-f]{40}", release_commit):
        raise ValueError("Exact source commit required")
    if not output.is_absolute() or output.exists() or output.is_symlink():
        raise ValueError("New absolute build destination required")
    if source_root.resolve() in output.parents or output.resolve() == source_root.resolve():
        raise ValueError("Build outside the source workspace")
    skill_root = source_root / "skills/mastermind-long-horizon"
    paths = set(SOURCE_FILES)
    for path in skill_root.rglob("*"):
        if path.is_symlink():
            raise ValueError("Skill symlinks cannot enter a release")
        if path.is_file():
            paths.add(path.relative_to(source_root).as_posix())
    paths.update({"integrations/session_bridge/t3_orchestration.py",
                  "integrations/session_bridge/t3_native_client.py",
                  "integrations/session_bridge/t3_mission_brief.py"})
    # Read every immutable Git blob before creating output, then compare against
    # inspected source. Do not let an uncommitted edit claim a release commit.
    content = {}
    for relative in sorted(paths):
        local = source_root / relative
        if not local.is_file() or local.is_symlink():
            raise ValueError("Source file missing or unsafe: " + relative)
        blob = subprocess.run(["git", "show", release_commit + ":" + relative], cwd=source_root,
                              capture_output=True, check=True).stdout
        if local.read_bytes() != blob:
            raise ValueError("Uncommitted source differs: " + relative)
        content[relative] = blob
    output.mkdir(parents=True, exist_ok=False)
    for relative, raw in content.items():
        target = output / relative;target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as stream:
            stream.write(raw)
    (output / "requirements.txt").write_text(REQUIREMENTS, encoding="utf-8")
    manifest = {"schema": "mastermind.t3_harness.bundle/v1", "release_commit": release_commit,
                "source_sha256": {name: hashlib.sha256(raw).hexdigest() for name, raw in content.items()},
                "requirements_sha256": hashlib.sha256(REQUIREMENTS.encode()).hexdigest(),
                "native_configuration_changed": False, "installation_performed": False}
    (output / "MANIFEST.json").write_bytes(encode(manifest) + b"\n")
    return manifest


def configuration(bundle: Path, browser_descriptor: Path, namespace: str, *, peekaboo: Path | None = None,
                  bridge_socket: Path | None = None, session_bindings: dict | None = None) -> dict:
    """Prepare operator configuration only; native thread attribution is not a grant."""
    if not bundle.is_absolute() or not browser_descriptor.is_absolute() or not namespace.startswith("t3:"):
        raise ValueError("Exact absolute installed sources and native namespace required")
    manifest = json.loads((bundle / "MANIFEST.json").read_text())
    if manifest.get("schema") != "mastermind.t3_harness.bundle/v1":
        raise ValueError("Exact built bundle required")
    files = manifest.get("source_sha256")
    if type(files) is not dict or not SOURCE_FILES <= files.keys() or len(files) > 64:
        raise ValueError("Closed bounded bundle inventory required")
    for relative, digest in files.items():
        if (type(relative) is not str or PurePosixPath(relative).is_absolute()
                or str(PurePosixPath(relative)) != relative
                or any(part in {"..", ".git"} for part in PurePosixPath(relative).parts)
                or "\\" in relative or type(digest) is not str or not re.fullmatch(r"[0-9a-f]{64}", digest)):
            raise ValueError("Unsafe bundle inventory")
        path = bundle / relative
        if any(parent.is_symlink() for parent in path.parents if parent != bundle.parent):
            raise ValueError("Bundle symlink")
        if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError("Bundle drift")
    value = {"schema": SCHEMA, "source_root": str(bundle), "source_files": {
        p: manifest["source_sha256"][p] for p in SOURCE_FILES},
        "browser_descriptor": str(browser_descriptor),
        "browser_descriptor_sha256": hashlib.sha256(browser_descriptor.read_bytes()).hexdigest(),
        "namespace": namespace, "local_browser_only": True,
        "session_bindings": {} if session_bindings is None else session_bindings}
    if peekaboo is not None or bridge_socket is not None:
        if peekaboo is None or bridge_socket is None or not bridge_socket.is_absolute():
            raise ValueError("Both exact native Peekaboo executable and original Bridge required")
        resolved = peekaboo.resolve(strict=True)
        value["peekaboo"] = {"executable": str(resolved), "executable_sha256": executable_digest(resolved),
                             "bridge_socket": str(bridge_socket)}
    return value


def mcp_entries(bundle: Path, python_executable: Path, config_path: Path, config_sha256: str,
                *, include_peekaboo: bool) -> dict:
    """Return the existing provider's native stdio shape without writing settings."""
    if (not all(p.is_absolute() for p in (bundle, python_executable, config_path))
            or not re.fullmatch(r"[0-9a-f]{64}", config_sha256) or type(include_peekaboo) is not bool):
        raise ValueError("Exact native installation coordinates required")
    modes = {"mastermind-browser": "browser"}
    if include_peekaboo:
        modes["mastermind-peekaboo"] = "peekaboo"
    return {name: {"type": "stdio", "command": str(python_executable), "args": ["-I", "-B",
        str(bundle / "integrations/t3_harness/native_launch.py"), mode, "--config", str(config_path),
        "--expected-config-sha256", config_sha256], "env": {}}
        for name, mode in modes.items()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--release-commit", required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.output, args.release_commit), sort_keys=True))


if __name__ == "__main__":
    main()
