#!/usr/bin/env python3
"""Canonical attended-session workspace route for Mastermind hosts.

This CLI is a thin adapter over ``control_plane.executive_workspace``.  It does
not own lifecycle state.  The host owns the source repo and workspace root; the
caller supplies only an operation identity, exact base SHA, and a closed lane.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from control_plane.executive_workspace import (  # noqa: E402
    WorkspaceError,
    inspect_linked_worktree,
    prepare_linked_worktree,
    release_linked_worktree,
)

SCHEMA = "mastermind.workspace_cli/v1"
ALLOWED_LANES = {"web", "sol", "manual", "review"}


def _source_repo() -> Path:
    configured = os.environ.get("MASTERMIND_SOURCE_REPO")
    return Path(configured).expanduser().resolve() if configured else REPO_ROOT


def _workspace_root() -> Path:
    configured = os.environ.get("MASTERMIND_AGENT_WORKSPACE_ROOT")
    if configured:
        return Path(configured).expanduser().resolve()
    external = Path("/Volumes/Mastermind/agent-workspaces")
    if external.parent.is_dir():
        return external.resolve()
    return (Path.home() / ".mastermind" / "agent-workspaces").resolve()


def _branch(operation_id: str, lane: str) -> str:
    operation = operation_id.strip().lower()
    if lane == "sol":
        return f"sol/{operation}"
    return f"sol/{lane}-{operation}"


def _workspace_path(root: Path, lane: str, operation_id: str) -> Path:
    return root / lane / operation_id.strip().lower()


def _emit(action: str, receipt: object, *, effect: str) -> int:
    body = receipt.to_dict() if hasattr(receipt, "to_dict") else receipt
    print(
        json.dumps(
            {
                "schema_version": SCHEMA,
                "action": action,
                "effect": effect,
                "receipt": body,
            },
            sort_keys=True,
        )
    )
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)

    acquire = sub.add_parser("acquire", help="acquire or reuse one linked workspace")
    acquire.add_argument("--operation-id", required=True)
    acquire.add_argument("--base-sha", required=True)
    acquire.add_argument("--lane", choices=sorted(ALLOWED_LANES), default="web")

    sub.add_parser("census", help="read-only census of registered source worktrees")
    prune = sub.add_parser("prune-missing", help="prune only registrations whose paths Git proves missing")
    prune.add_argument("--apply", action="store_true", help="apply; default is dry-run")

    for name in ("status", "release"):
        command = sub.add_parser(name, help=f"{name} one managed linked workspace")
        command.add_argument("--operation-id", required=True)
        command.add_argument("--lane", choices=sorted(ALLOWED_LANES), default="web")
    return parser



def _git_text(source: Path, *args: str) -> tuple[int, str, str]:
    env = dict(os.environ)
    env["GIT_OPTIONAL_LOCKS"] = "0"
    completed = subprocess.run(
        ["git", "-C", str(source), *args],
        env=env,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return completed.returncode, completed.stdout.strip(), completed.stderr.strip()


def _porcelain_records(source: Path) -> list[dict[str, str]]:
    code, output, error = _git_text(source, "worktree", "list", "--porcelain")
    if code != 0:
        raise WorkspaceError(f"worktree census failed: {error or output}")
    records: list[dict[str, str]] = []
    current: dict[str, str] = {}
    for line in [*output.splitlines(), ""]:
        if not line:
            if current:
                records.append(current)
                current = {}
            continue
        key, sep, value = line.partition(" ")
        current[key] = value if sep else ""
    return records


def _census(source: Path, root: Path) -> dict[str, object]:
    source = source.resolve()
    root = root.resolve()
    entries: list[dict[str, object]] = []
    for record in _porcelain_records(source):
        path = Path(record["worktree"]).resolve()
        exists = path.is_dir()
        locked_reason = record.get("locked", "")
        managed = locked_reason.startswith("mastermind-linked-worktree:v1")
        try:
            path.relative_to(root)
            under_managed_root = True
        except ValueError:
            under_managed_root = False
        branch_ref = record.get("branch", "")
        branch = branch_ref.removeprefix("refs/heads/") if branch_ref else ""
        head = record.get("HEAD", "")
        dirty: bool | None = None
        recoverability = "UNKNOWN"
        if path == source:
            state = "SOURCE_CHECKOUT"
        elif not exists:
            state = "MISSING_LOCKED" if locked_reason else "MISSING_PRUNABLE"
        else:
            code, status, _ = _git_text(path, "status", "--porcelain=v1", "--untracked-files=all")
            dirty = None if code != 0 else bool(status)
            if dirty is True:
                state = "DIRTY_PRESERVE"
                recoverability = "WORKSPACE_ONLY_CHANGES_PRESENT"
            elif dirty is None:
                state = "UNAVAILABLE_PRESERVE"
            elif managed and locked_reason:
                state = "MANAGED_ACTIVE"
            else:
                ancestor_code, _, _ = _git_text(
                    source, "merge-base", "--is-ancestor", head, "refs/remotes/origin/master"
                )
                remote_head = ""
                if branch:
                    remote_code, remote_value, _ = _git_text(
                        source, "rev-parse", "--verify", "--quiet", f"refs/remotes/origin/{branch}"
                    )
                    if remote_code == 0:
                        remote_head = remote_value
                if ancestor_code == 0:
                    state = "CLEAN_RECOVERABLE"
                    recoverability = "HEAD_REACHABLE_FROM_ORIGIN_MASTER"
                elif remote_head == head and head:
                    state = "CLEAN_RECOVERABLE"
                    recoverability = "HEAD_PUBLISHED_TO_ORIGIN_BRANCH"
                else:
                    state = "CLEAN_UNPUBLISHED_PRESERVE"
                    recoverability = "HEAD_NOT_OBSERVED_ON_ORIGIN_REFS"
        entries.append(
            {
                "path": str(path),
                "head_sha": head,
                "branch": branch,
                "exists": exists,
                "locked": bool(locked_reason),
                "lock_reason": locked_reason,
                "managed": managed,
                "under_managed_root": under_managed_root,
                "dirty": dirty,
                "recoverability": recoverability,
                "state": state,
            }
        )
    counts: dict[str, int] = {}
    for entry in entries:
        state = str(entry["state"])
        counts[state] = counts.get(state, 0) + 1
    return {"counts": counts, "worktrees": entries}


def _prune_missing(source: Path, *, apply: bool) -> dict[str, object]:
    args = ["worktree", "prune", "--verbose", "--expire", "now"]
    if not apply:
        args.insert(2, "--dry-run")
    code, output, error = _git_text(source, *args)
    if code != 0:
        raise WorkspaceError(f"worktree prune failed: {error or output}")
    detail = "\n".join(part for part in (output, error) if part)
    return {
        "applied": apply,
        "lines": [line for line in detail.splitlines() if line],
    }


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    source = _source_repo()
    root = _workspace_root()
    destination = (
        _workspace_path(root, args.lane, args.operation_id)
        if args.action in {"status", "release"}
        else None
    )
    try:
        if args.action == "census":
            return _emit("census", _census(source, root), effect="NOT_APPLIED")
        if args.action == "prune-missing":
            receipt = _prune_missing(source, apply=args.apply)
            return _emit("prune-missing", receipt, effect="APPLIED" if args.apply and receipt["lines"] else "NOT_APPLIED")
        if args.action == "acquire":
            receipt = prepare_linked_worktree(
                source,
                root,
                operation_id=args.operation_id,
                lane=args.lane,
                base_sha=args.base_sha,
                branch=_branch(args.operation_id, args.lane),
            )
            return _emit(
                "acquire",
                receipt,
                effect="NOT_APPLIED" if receipt.reused else "APPLIED",
            )
        if args.action == "status":
            receipt = inspect_linked_worktree(
                source,
                root,
                destination,
                expected_operation_id=args.operation_id,
            )
            return _emit("status", receipt, effect="NOT_APPLIED")
        receipt = release_linked_worktree(
            source,
            root,
            destination,
            expected_operation_id=args.operation_id,
        )
        return _emit(
            "release",
            receipt,
            effect="APPLIED" if receipt.removed else "NOT_APPLIED",
        )
    except WorkspaceError as exc:
        print(
            json.dumps(
                {
                    "schema_version": SCHEMA,
                    "action": args.action,
                    "effect": "NOT_APPLIED",
                    "error": str(exc),
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
