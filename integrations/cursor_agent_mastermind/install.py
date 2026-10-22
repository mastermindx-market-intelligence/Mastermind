#!/usr/bin/env python3
"""Project-local Cursor role projection; never grants Fabric or provider authority.

Installs only reviewed, hash-pinned agent/skill files into one exact Git root.
It never edits user MCP, credentials, Claude hooks, provider settings, or runtime.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
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
    "rules/00-mastermind-core.mdc": "e119f4f071ca76a72df1dec1b67dcfb02eace65652e62e42a4ca5e428e7b8b43",
    "rules/10-long-horizon.mdc": "5257acd028fe2db2541906c459e3283dbf0643204a4339608cc842158db7e64b",
    "rules/20-model-and-delegation.mdc": "8aaa63625d19006dfad3353261b77403576309ad788942c4d77c21cd1a9cda14",
    "rules/30-proof-and-review.mdc": "b80d30df880e57e1a35c55cd3476ae82083cfc34276951f5257fa45c3d04cb43",
    "skills/mastermind-long-horizon/SKILL.md": "166b0e664f8f8a5f4fc1c452c097d1e2031683bf6dbc00c4264d14e6ea0cddc9",
    "skills/mastermind-model-routing/SKILL.md": "dbbf3b43d4321c81ae08cfd8749b165c635cc9bdc32ca8206ab8d123d6f126dd",
    "skills/mastermind-verify-and-close/SKILL.md": "15007d0e1c27db211674c6972a21ac9880b5c161b41c7bb11db6f3445610368c",
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


@contextmanager
def anchored_parent_dir(root: Path, parts: tuple[str, ...]):
    """Open/create only the reviewed .cursor subtree via non-following dirfds.

    Each directory is validated at the instant it is opened; a symlink swap
    after preflight must not redirect source projection outside its Git root.
    All components come from fixed FILES keys, not caller input.
    """
    if not {os.open, os.mkdir}.issubset(os.supports_dir_fd):
        raise ProjectionRefused("directory-fd-safe projection unavailable")
    root_fd = os.open(str(root), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    fd = root_fd
    try:
        for part in parts:
            if part in ("", ".", "..") or "/" in part:
                raise ProjectionRefused("unsafe source manifest path")
            try:
                os.mkdir(part, mode=0o755, dir_fd=fd)
            except FileExistsError:
                pass
            try:
                child = os.open(
                    part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                    dir_fd=fd,
                )
            except OSError as exc:
                raise ProjectionRefused("unsafe project directory changed during apply") from exc
            os.close(fd)
            fd = child
        yield fd
    finally:
        os.close(fd)


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
            rel_parts = Path(".cursor", rel).parts
            try:
                with anchored_parent_dir(target, rel_parts[:-1]) as dir_fd:
                    leaf_fd = os.open(
                        rel_parts[-1],
                        os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW,
                        0o644, dir_fd=dir_fd,
                    )
                    with os.fdopen(leaf_fd, "wb") as output:
                        output.write(data)
                        output.flush()
                        os.fsync(output.fileno())
                    os.fsync(dir_fd)
            except (OSError, ProjectionRefused) as exc:
                # A lost/interrupted write may already have an effect. Never
                # remove, blindly replay or overwrite an uncertain destination.
                raise ProjectionRefused(
                    "project projection interrupted; reconcile exact destination: " + rel
                ) from exc
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
