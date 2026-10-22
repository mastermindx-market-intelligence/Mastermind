#!/usr/bin/env python3
"""Project-local Cursor role projection; never grants Fabric or provider authority.

Installs only reviewed, hash-pinned agent/skill files into one exact Git root.
It never edits user MCP, credentials, Claude hooks, provider settings, or runtime.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess

FILES = {
    "agents/mmx-repo-explorer.md": "8139e10ac33c8e065b628b8e69f18ccedf95e3041db63e2f8f9d0f668287681d",
    "agents/mmx-independent-reviewer.md": "f1e9d443b37d4518252f2f983dfe359ba16242f72ee4014ad67566fa5c90cfbd",
    "agents/mmx-implementation-worker.md": "33e203eba06f3a3ec3ee397ed8b46be8d33f81711eaa6a56ac505d9694d26683",
    "agents/mmx-fabric-operator.md": "cae9255f0e8de8d439b50c547cb3efaebe1d61644e4926f3364bf0dd58f5ecd2",
    "skills/mastermind-fabric/SKILL.md": "00f3a12833c9fad654215f5af5819f3d1306e7f8b775b9bf4c7cce1fe23c6949",
}
ROOT = Path(__file__).resolve().parent


class ProjectionRefused(ValueError):
    pass


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def checked_root(workspace: Path) -> Path:
    if not workspace.is_absolute() or workspace.is_symlink() or not workspace.is_dir():
        raise ProjectionRefused("workspace must be an existing non-symlink absolute directory")
    try:
        output = subprocess.check_output(
            ["git", "-C", str(workspace), "rev-parse", "--show-toplevel"],
            stderr=subprocess.DEVNULL, timeout=5, text=True,
        ).strip()
    except (OSError, subprocess.SubprocessError) as exc:
        raise ProjectionRefused("workspace is not a readable Git root") from exc
    if Path(output).resolve() != workspace.resolve():
        raise ProjectionRefused("workspace must be the exact Git root")
    return workspace


def checked_dir(path: Path) -> None:
    if path.is_symlink():
        raise ProjectionRefused("symlink directory refused")
    if path.exists() and not path.is_dir():
        raise ProjectionRefused("non-directory destination refused")


def checked_regular(path: Path) -> bytes | None:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(info.st_mode) or info.st_size > 65536:
        raise ProjectionRefused("non-regular or oversized target refused")
    return path.read_bytes()


def project(workspace: Path, mode: str = "plan") -> dict:
    if mode not in {"plan", "apply", "verify"}:
        raise ProjectionRefused("unknown operation")
    target = checked_root(workspace)
    source = ROOT
    changes = []
    # Preflight ALL reviewed sources, parent directories, and destinations before any writes.
    for rel, expected in sorted(FILES.items()):
        data = (source / rel).read_bytes()
        if digest(data) != expected:
            raise ProjectionRefused("source digest mismatch: " + rel)
        dest = target / ".cursor" / rel
        # Check every directory component, including .cursor/skills, rather than
        # only the top and last parent; a symlinked intermediate directory must
        # never redirect a credential-free project projection outside this Git root.
        rel_parts = Path(".cursor", rel).parts[:-1]
        for depth in range(1, len(rel_parts) + 1):
            checked_dir(target.joinpath(*rel_parts[:depth]))
        existing = checked_regular(dest)
        if existing is not None and existing != data:
            raise ProjectionRefused("conflicting project-owned file: " + rel)
        changes.append((rel, dest, data, "unchanged" if existing is not None else "missing"))
    if mode == "verify" and any(state != "unchanged" for _, _, _, state in changes):
        raise ProjectionRefused("project projection incomplete")
    wrote = []
    if mode == "apply":
        for rel, dest, data, state in changes:
            if state != "missing":
                continue
            dest.parent.mkdir(parents=True, mode=0o755, exist_ok=True)
            rel_parts = Path(".cursor", rel).parts[:-1]
            for depth in range(1, len(rel_parts) + 1):
                checked_dir(target.joinpath(*rel_parts[:depth]))
            fd = os.open(str(dest), os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0), 0o644)
            try:
                with os.fdopen(fd, "wb") as output:
                    output.write(data)
                    output.flush()
                    os.fsync(output.fileno())
            except Exception:
                # A partially created file is an uncertain effect; do not remove/retry it.
                raise ProjectionRefused("file write interrupted; reconcile exact destination: " + rel)
            wrote.append(rel)
    return {
        "schema": "mastermind.cursor_project_projection.v1",
        "mode": mode,
        "workspace": str(target),
        "source_pinned": True,
        "state": "APPLIED" if wrote else ("READY" if mode == "verify" else "NOT_APPLIED"),
        "created": wrote,
        "files": [{"path": rel, "sha256": FILES[rel], "status": ("installed" if rel in wrote else state)}
                  for rel, _, _, state in changes],
        "fabric_dispatch_granted": False,
        "provider_identity_granted": False,
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--workspace", type=Path, required=True)
    p.add_argument("--mode", choices=("plan", "apply", "verify"), default="plan")
    args = p.parse_args()
    try:
        print(json.dumps(project(args.workspace, args.mode), sort_keys=True))
    except (ProjectionRefused, OSError) as exc:
        print(json.dumps({"schema": "mastermind.cursor_project_projection.v1",
                          "state": "REFUSED", "reason": str(exc)}))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
