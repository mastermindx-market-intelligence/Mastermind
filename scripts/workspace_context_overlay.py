#!/usr/bin/env python3
"""Observe one exact managed Mastermind workspace for context retrieval.

This adapter does not discover arbitrary filesystem state. The caller supplies one
managed workspace path/root and expected operation/lane; the adapter proves that exact
path is a currently locked Git worktree before projecting a derived local overlay.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
from typing import Any

_ROOT = Path(__file__).resolve().parents[1]
if os.fspath(_ROOT) not in sys.path:
    sys.path.insert(0, os.fspath(_ROOT))

from control_plane.project_atlas import is_sensitive_path  # noqa: E402
from control_plane.session_truth_contract import canonical_json  # noqa: E402
from control_plane.workspace_context_overlay import (  # noqa: E402
    WorkspaceContextOverlayError,
    build_workspace_overlay,
)

_GIT_TIMEOUT = 15
_MAX_GIT_OUTPUT = 8 * 1024 * 1024
_MAX_WORKING_FILE_BYTES = 4 * 1024 * 1024
_LOCK_RE = re.compile(
    r"^mastermind-linked-worktree:v1 "
    r"operation=([A-Za-z0-9][A-Za-z0-9._-]{0,95}) "
    r"lane=([a-z][a-z0-9-]{0,31}) "
    r"base=([0-9a-f]{40})$"
)
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-repo", required=True)
    parser.add_argument("--workspace-root", required=True)
    parser.add_argument("--workspace-path", required=True)
    parser.add_argument("--operation-id", required=True)
    parser.add_argument("--lane", required=True)
    parser.add_argument("--json", action="store_true", dest="emit_json")
    return parser


def _git_env() -> dict[str, str]:
    env = dict(os.environ)
    env["GIT_OPTIONAL_LOCKS"] = "0"
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GCM_INTERACTIVE"] = "never"
    return env


def _git(
    root: Path,
    *args: str,
    binary: bool = False,
) -> bytes | str:
    try:
        proc = subprocess.run(
            ["git", "-C", os.fspath(root), *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=not binary,
            env=_git_env(),
            timeout=_GIT_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise WorkspaceContextOverlayError("Git observation failed") from exc
    if proc.returncode != 0:
        raise WorkspaceContextOverlayError("Git observation failed")
    output = proc.stdout
    if len(output) > _MAX_GIT_OUTPUT:
        raise WorkspaceContextOverlayError("Git observation exceeds byte bound")
    return output


def _root(value: str, label: str) -> Path:
    path = Path(value).expanduser().resolve()
    if not path.is_dir():
        raise WorkspaceContextOverlayError(f"{label} is unavailable")
    return path


def _validate_workspace_path(root: Path, workspace: Path) -> None:
    try:
        workspace.relative_to(root)
    except ValueError as exc:
        raise WorkspaceContextOverlayError(
            "workspace is outside the managed root"
        ) from exc
    if workspace == root:
        raise WorkspaceContextOverlayError("workspace cannot equal the managed root")
    try:
        info = workspace.lstat()
    except OSError as exc:
        raise WorkspaceContextOverlayError("workspace is unavailable") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise WorkspaceContextOverlayError("workspace must be a real directory")


def _worktree_records(source: Path) -> list[dict[str, str]]:
    value = _git(source, "worktree", "list", "--porcelain")
    if not isinstance(value, str):
        raise WorkspaceContextOverlayError("worktree registry output is invalid")
    records: list[dict[str, str]] = []
    current: dict[str, str] = {}
    for line in [*value.splitlines(), ""]:
        if not line:
            if current:
                records.append(current)
                current = {}
            continue
        key, separator, item = line.partition(" ")
        if key in current:
            raise WorkspaceContextOverlayError(
                "worktree registry contains duplicate fields"
            )
        current[key] = item if separator else ""
    return records


def _registered_identity(
    *,
    source: Path,
    workspace: Path,
    expected_operation: str,
    expected_lane: str,
) -> dict[str, str]:
    matching: list[dict[str, str]] = []
    for record in _worktree_records(source):
        raw_path = record.get("worktree")
        if not raw_path:
            continue
        try:
            observed = Path(raw_path).resolve()
        except OSError:
            continue
        if observed == workspace:
            matching.append(record)
    if len(matching) != 1:
        raise WorkspaceContextOverlayError("workspace is not exactly registered once")
    record = matching[0]
    lock_reason = record.get("locked", "")
    match = _LOCK_RE.fullmatch(lock_reason)
    if match is None:
        raise WorkspaceContextOverlayError("workspace custody lock is invalid")
    operation_id, lane, base_sha = match.groups()
    if operation_id != expected_operation or lane != expected_lane:
        raise WorkspaceContextOverlayError(
            "workspace operation identity does not match"
        )

    head_sha = record.get("HEAD", "")
    branch_ref = record.get("branch", "")
    branch = branch_ref.removeprefix("refs/heads/") if branch_ref else ""
    if _SHA_RE.fullmatch(head_sha) is None or not branch:
        raise WorkspaceContextOverlayError("workspace Git identity is incomplete")
    actual_head = _git(workspace, "rev-parse", "--verify", "HEAD")
    actual_branch = _git(workspace, "symbolic-ref", "--quiet", "--short", "HEAD")
    if not isinstance(actual_head, str) or not isinstance(actual_branch, str):
        raise WorkspaceContextOverlayError("workspace Git identity is unavailable")
    if actual_head.strip() != head_sha or actual_branch.strip() != branch:
        raise WorkspaceContextOverlayError(
            "workspace Git identity changed during observation"
        )
    _git(source, "cat-file", "-e", f"{base_sha}^{{commit}}")
    return {
        "operation_id": operation_id,
        "lane": lane,
        "base_sha": base_sha,
        "head_sha": head_sha,
        "branch": branch,
    }


def _opaque_path(path: str) -> str:
    return hashlib.sha256(path.encode("utf-8")).hexdigest()


def _committed_changes(
    workspace: Path,
    *,
    base_sha: str,
    head_sha: str,
) -> list[dict[str, Any]]:
    raw = _git(
        workspace,
        "diff",
        "--name-status",
        "-z",
        "--no-renames",
        base_sha,
        head_sha,
        "--",
        binary=True,
    )
    if not isinstance(raw, bytes):
        raise WorkspaceContextOverlayError("committed diff output is invalid")
    fields = raw.split(b"\0")
    if fields and fields[-1] == b"":
        fields.pop()
    if len(fields) % 2:
        raise WorkspaceContextOverlayError("committed diff output is malformed")
    rows: list[dict[str, Any]] = []
    for index in range(0, len(fields), 2):
        try:
            status = fields[index].decode("ascii", errors="strict")
            path = fields[index + 1].decode("utf-8", errors="strict")
        except UnicodeError as exc:
            raise WorkspaceContextOverlayError(
                "committed diff path is unsupported"
            ) from exc
        if is_sensitive_path(path):
            rows.append(
                {
                    "status": status,
                    "path": None,
                    "path_digest": _opaque_path(path),
                    "content_sha256": None,
                    "content_state": "SENSITIVE_PATH",
                }
            )
        else:
            rows.append(
                {
                    "status": status,
                    "path": path,
                    "path_digest": None,
                    "content_sha256": None,
                    "content_state": "COMMITTED_REF",
                }
            )
    return rows


def _status_rows(workspace: Path) -> list[tuple[str, str]]:
    raw = _git(
        workspace,
        "status",
        "--porcelain=v1",
        "-z",
        "--untracked-files=all",
        "--no-renames",
        "--",
        binary=True,
    )
    if not isinstance(raw, bytes):
        raise WorkspaceContextOverlayError("working-tree status output is invalid")
    rows: list[tuple[str, str]] = []
    for record in raw.split(b"\0"):
        if not record:
            continue
        if len(record) < 4 or record[2:3] != b" ":
            raise WorkspaceContextOverlayError(
                "working-tree status output is malformed"
            )
        try:
            status = record[:2].decode("ascii", errors="strict")
            path = record[3:].decode("utf-8", errors="strict")
        except UnicodeError as exc:
            raise WorkspaceContextOverlayError(
                "working-tree path is unsupported"
            ) from exc
        rows.append((status, path))
    return rows


def _stable_content_digest(workspace: Path, path: str) -> tuple[str | None, str]:
    full = workspace / path
    try:
        info = full.lstat()
    except FileNotFoundError:
        return None, "DELETED"
    except OSError:
        return None, "UNAVAILABLE"
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        return None, "NON_REGULAR"
    if info.st_size > _MAX_WORKING_FILE_BYTES:
        return None, "TOO_LARGE"

    descriptor = -1
    try:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
        descriptor = os.open(full, flags)
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_size > _MAX_WORKING_FILE_BYTES
            or before.st_dev != info.st_dev
            or before.st_ino != info.st_ino
        ):
            return None, "UNAVAILABLE"
        digest = hashlib.sha256()
        remaining = _MAX_WORKING_FILE_BYTES + 1
        while remaining:
            chunk = os.read(descriptor, min(1024 * 1024, remaining))
            if not chunk:
                break
            digest.update(chunk)
            remaining -= len(chunk)
        after = os.fstat(descriptor)
        stable = (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        ) == (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        )
        if not stable or remaining <= 0:
            return None, "UNAVAILABLE"
        return digest.hexdigest(), "HASHED"
    except OSError:
        return None, "UNAVAILABLE"
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _working_changes(workspace: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for status, path in _status_rows(workspace):
        if is_sensitive_path(path):
            rows.append(
                {
                    "status": status,
                    "path": None,
                    "path_digest": _opaque_path(path),
                    "content_sha256": None,
                    "content_state": "SENSITIVE_PATH",
                }
            )
            continue
        digest, state = _stable_content_digest(workspace, path)
        rows.append(
            {
                "status": status,
                "path": path,
                "path_digest": None,
                "content_sha256": digest,
                "content_state": state,
            }
        )
    return rows


def observe_workspace_overlay(
    *,
    source_repo: Path,
    workspace_root: Path,
    workspace_path: Path,
    operation_id: str,
    lane: str,
) -> dict[str, Any]:
    _validate_workspace_path(workspace_root, workspace_path)
    identity = _registered_identity(
        source=source_repo,
        workspace=workspace_path,
        expected_operation=operation_id,
        expected_lane=lane,
    )
    committed = _committed_changes(
        workspace_path,
        base_sha=identity["base_sha"],
        head_sha=identity["head_sha"],
    )
    working = _working_changes(workspace_path)
    return build_workspace_overlay(
        **identity,
        committed_changes=committed,
        working_changes=working,
    )


def _render(value: dict[str, Any]) -> str:
    return (
        "Mastermind Workspace Context Overlay\n"
        f"operation_id: {value['operation_id']}\n"
        f"lane: {value['lane']}\n"
        f"base_sha: {value['base_sha']}\n"
        f"head_sha: {value['head_sha']}\n"
        f"dirty: {'true' if value['dirty'] else 'false'}\n"
        f"overlay_generation: {value['overlay_generation']}\n"
        f"safe_changed_paths: {len(value['safe_changed_paths'])}\n"
        f"sensitive_change_count: {value['sensitive_change_count']}\n"
    )


def _error(message: str) -> int:
    safe = " ".join(str(message).replace("\r", " ").replace("\n", " ").split())
    sys.stderr.write(
        f"workspace-context-overlay error: {safe[:220] or 'invalid input'}\n"
    )
    return 2


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        source = _root(args.source_repo, "source-repo")
        root = _root(args.workspace_root, "workspace-root")
        workspace = _root(args.workspace_path, "workspace-path")
        value = observe_workspace_overlay(
            source_repo=source,
            workspace_root=root,
            workspace_path=workspace,
            operation_id=args.operation_id,
            lane=args.lane,
        )
        rendered = canonical_json(value) + "\n" if args.emit_json else _render(value)
    except WorkspaceContextOverlayError as exc:
        return _error(str(exc))
    sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
