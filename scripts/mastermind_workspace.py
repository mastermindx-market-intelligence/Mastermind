#!/usr/bin/env python3
"""Canonical attended-session workspace route for Mastermind hosts.

This CLI is a thin adapter over ``control_plane.executive_workspace``.  It does
not own lifecycle state.  The host owns the source repo and workspace root; the
caller supplies only an operation identity, exact base SHA, and a closed lane.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import plistlib
import shutil
import stat
import subprocess
import sys
import uuid
from pathlib import Path
from xml.parsers.expat import ExpatError

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



_STORAGE_POLICY_FIELDS = frozenset(
    {"version", "mount_point", "volume_uuid", "root", "min_free_bytes"}
)
_STORAGE_POLICY_MAX_BYTES = 16 * 1024


def _unique_policy_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate policy field")
        result[key] = value
    return result


def _read_storage_policy(path: Path) -> tuple[dict[str, object], str]:
    """Read the existing host policy without following a substituted file."""
    descriptor = -1
    try:
        if not path.is_absolute():
            raise ValueError("policy path is not absolute")
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        flags |= getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_CLOEXEC", 0)
        descriptor = os.open(path, flags)
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or before.st_uid not in {0, os.geteuid()}
            or stat.S_IMODE(before.st_mode) & 0o022
            or not 0 < before.st_size <= _STORAGE_POLICY_MAX_BYTES
        ):
            raise ValueError("policy file identity is invalid")
        chunks: list[bytes] = []
        remaining = _STORAGE_POLICY_MAX_BYTES + 1
        while remaining:
            chunk = os.read(descriptor, remaining)
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        payload = b"".join(chunks)
        after = os.fstat(descriptor)
        named = path.lstat()
        fields = ("st_dev", "st_ino", "st_mode", "st_uid", "st_gid", "st_nlink",
                  "st_size", "st_mtime_ns", "st_ctime_ns")
        if len(payload) != before.st_size or any(
            getattr(before, key) != getattr(observed, key)
            for observed in (after, named) for key in fields
        ):
            raise ValueError("policy changed while reading")
        data = json.loads(payload.decode("utf-8"), object_pairs_hook=_unique_policy_pairs)
        if not isinstance(data, dict) or set(data) != _STORAGE_POLICY_FIELDS:
            raise ValueError("policy fields are not closed")
        if type(data["version"]) is not int or data["version"] != 1:
            raise ValueError("unsupported policy version")
        minimum = data["min_free_bytes"]
        if type(minimum) is not int or not 0 < minimum < 2**63:
            raise ValueError("invalid storage floor")
        for key in ("mount_point", "root"):
            value = data[key]
            if not isinstance(value, str) or "\x00" in value or not Path(value).is_absolute():
                raise ValueError("invalid storage path")
        identity = data["volume_uuid"]
        if not isinstance(identity, str) or str(uuid.UUID(identity)).lower() != identity.lower():
            raise ValueError("invalid volume identity")
        return data, hashlib.sha256(payload).hexdigest()
    except (OSError, ValueError, TypeError, UnicodeError) as exc:
        raise WorkspaceError("STORAGE_POLICY_INVALID: enrolled host policy cannot be trusted") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _volume_identity(mount: Path) -> dict[str, object]:
    """Observe macOS volume identity; do not infer UUIDs on other platforms."""
    if sys.platform != "darwin":
        raise WorkspaceError("STORAGE_IDENTITY_UNSUPPORTED: configured volume requires a qualified host probe")
    try:
        result = subprocess.run(
            ["/usr/sbin/diskutil", "info", "-plist", str(mount)],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LC_ALL": "C"},
            timeout=5, check=False,
        )
        if result.returncode != 0 or len(result.stdout) > 1024 * 1024:
            raise ValueError("volume probe failed")
        value = plistlib.loads(result.stdout)
        if not isinstance(value, dict):
            raise ValueError("volume probe is not an object")
        return value
    except (OSError, ValueError, plistlib.InvalidFileException, ExpatError, subprocess.SubprocessError) as exc:
        raise WorkspaceError("STORAGE_OBSERVATION_FAILED: volume identity unavailable") from exc


def _storage_free_bytes(mount: Path) -> int:
    return shutil.disk_usage(mount).free


def _storage_status(root: Path) -> dict[str, object]:
    """One current admission observation, never a disk reservation or lease."""
    policy_path = os.environ.get("MASTERMIND_WORKSPACE_STORAGE_POLICY", "")
    observation: dict[str, object] = {
        "schema_version": "mastermind.workspace_storage/v1",
        "observed_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "admission_check_only": True,
        "state": "NOT_CONFIGURED", "admission_allowed": True,
        "free_bytes": None, "min_free_bytes": None, "policy_sha256": None,
    }
    if not policy_path:
        return observation
    policy, digest = _read_storage_policy(Path(policy_path))
    try:
        mount = Path(str(policy["mount_point"]))
        if mount.is_symlink() or not mount.is_dir() or not mount.is_mount():
            raise WorkspaceError("STORAGE_MOUNT_UNAVAILABLE: enrolled volume is not mounted")
        mount = mount.resolve()
        configured_root = Path(str(policy["root"])).resolve()
        if configured_root != root or root == mount or not root.is_relative_to(mount):
            raise WorkspaceError("STORAGE_ROOT_MISMATCH: host policy does not name the selected workspace root")
        before = mount.stat()
        anchor = root
        while not anchor.exists() and anchor != mount:
            anchor = anchor.parent
        if not anchor.is_dir() or anchor.stat().st_dev != before.st_dev:
            raise WorkspaceError("STORAGE_ROOT_MISMATCH: workspace root is on another filesystem")
        observed = _volume_identity(mount)
        observed_uuid = observed.get("VolumeUUID")
        if (
            # APFS diskutil output omits Mounted; is_mount() and the exact
            # MountPoint/UUID above and below supply the positive witness.
            observed.get("Mounted", True) is not True
            or observed.get("MountPoint") != str(mount)
            or not isinstance(observed_uuid, str)
            or observed_uuid.lower() != str(policy["volume_uuid"]).lower()
        ):
            raise WorkspaceError("STORAGE_VOLUME_IDENTITY_MISMATCH: mounted volume is not the enrolled volume")
        if observed.get("Writable") is not True:
            raise WorkspaceError("STORAGE_VOLUME_READ_ONLY: writable volume is not proven")
        free = _storage_free_bytes(mount)
        after = mount.stat()
        if type(free) is not int or free < 0 or (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
            raise WorkspaceError("STORAGE_OBSERVATION_FAILED: storage observation is not stable")
        minimum = int(policy["min_free_bytes"])
        observation.update({
            "state": "READY" if free >= minimum else "LOW_SPACE",
            "admission_allowed": free >= minimum,
            "free_bytes": free, "min_free_bytes": minimum,
            "policy_sha256": digest,
            "mount_point": str(mount), "workspace_root": str(root),
            "volume_uuid": observed_uuid,
        })
        return observation
    except WorkspaceError:
        raise
    except (OSError, ValueError, RuntimeError) as exc:
        raise WorkspaceError("STORAGE_OBSERVATION_FAILED: storage readiness unavailable") from exc


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
    sub.add_parser("storage", help="read-only enrolled volume and free-space admission check")
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
        if args.action == "storage":
            return _emit("storage", _storage_status(root), effect="NOT_APPLIED")
        if args.action == "census":
            return _emit("census", _census(source, root), effect="NOT_APPLIED")
        if args.action == "prune-missing":
            receipt = _prune_missing(source, apply=args.apply)
            return _emit("prune-missing", receipt, effect="APPLIED" if args.apply and receipt["lines"] else "NOT_APPLIED")
        if args.action == "acquire":
            if not _storage_status(root)["admission_allowed"]:
                raise WorkspaceError("STORAGE_LOW_SPACE: available storage is below the host reserve")
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


def installation_storage_profile(
    home: Path, *, external_mount: Path = Path("/Volumes/Mastermind")
) -> dict[str, str]:
    """Choose host-owned launcher inputs, not runtime admission or a reservation."""
    home = home.expanduser().resolve()
    policy_path = home / ".config/mastermind/worktree-storage.json"
    if policy_path.exists() or policy_path.is_symlink():
        policy, _digest = _read_storage_policy(policy_path)
        volume = Path(str(policy["mount_point"]))
        root = Path(str(policy["root"])).resolve()
        if volume.is_symlink():
            raise WorkspaceError("STORAGE_ROOT_MISMATCH: enrolled volume is indirect")
        volume = volume.resolve()
        if root == volume or not root.is_relative_to(volume):
            raise WorkspaceError("STORAGE_ROOT_MISMATCH: enrolled root escapes its volume")
        # Keep an explicitly required mount pinned even while disconnected.
        # The installed launcher and existing storage owner refuse use until ready.
        return {
            "root": str(root),
            "mount_point": str(volume),
            "policy_path": str(policy_path),
        }

    selected = {
        "root": str((home / ".mastermind/agent-workspaces").resolve()),
        "mount_point": "",
        "policy_path": "",
    }
    if (
        external_mount.is_symlink()
        or not external_mount.is_dir()
        or not external_mount.is_mount()
    ):
        return selected

    volume = external_mount.resolve()
    try:
        observed = _volume_identity(volume)
    except WorkspaceError:
        return selected
    filesystem = observed.get("FilesystemType")
    if (
        observed.get("MountPoint") != str(volume)
        or observed.get("Writable") is not True
        or not isinstance(filesystem, str)
        or filesystem.lower() not in {"apfs", "hfs", "hfsx"}
    ):
        return selected
    return {
        "root": str((volume / "agent-workspaces").resolve()),
        "mount_point": str(volume),
        "policy_path": "",
    }
