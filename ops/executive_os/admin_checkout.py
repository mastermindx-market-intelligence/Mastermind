#!/usr/bin/env python3
"""Normalize one complete Executive administrative checkout without network access.

The installer owns this checkout. This helper proves the exact local Git closure
is complete with lazy fetching disabled before removing only safe, empty
``*.promisor`` sidecars inherited from a complete partial-clone source.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import stat
import subprocess
import time
from pathlib import Path
from typing import Sequence

_GIT = "/usr/bin/git"
_SHA = re.compile(r"^[0-9a-f]{40}$")
_PROMISOR = re.compile(r"^pack-[0-9a-f]{40}\.promisor$")
_MAX_GIT_OUTPUT = 4 * 1024 * 1024
_GIT_TIMEOUT_SECONDS = 10.0


class AdminCheckoutError(RuntimeError):
    """The installer-owned checkout is not safe to normalize."""


def _git_env() -> dict[str, str]:
    return {
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        "HOME": os.environ.get("HOME", "/var/empty"),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_NO_LAZY_FETCH": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_NO_REPLACE_OBJECTS": "1",
    }


def _run_git(
    checkout: Path, *args: str, maximum: int = _MAX_GIT_OUTPUT,
    input_bytes: bytes | None = None, deadline: float | None = None,
) -> bytes:
    timeout = _GIT_TIMEOUT_SECONDS
    if deadline is not None:
        timeout = min(timeout, deadline - time.monotonic())
    if timeout <= 0 or (input_bytes is not None and len(input_bytes) > maximum):
        raise AdminCheckoutError("Git observation exceeded its bound")
    try:
        result = subprocess.run(
            [_GIT, "-C", os.fspath(checkout), *args],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            input=input_bytes,
            env=_git_env(),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise AdminCheckoutError("Git observation failed") from exc
    if result.returncode != 0:
        raise AdminCheckoutError("Git observation failed")
    if len(result.stdout) > maximum or len(result.stderr) > maximum:
        raise AdminCheckoutError("Git observation exceeded its bound")
    return result.stdout


def _require_direct_object_store(git_dir: Path) -> None:
    objects_root = git_dir / "objects"
    try:
        objects_stat = objects_root.lstat()
    except OSError as exc:
        raise AdminCheckoutError("administrative checkout object store is unsafe") from exc
    if not stat.S_ISDIR(objects_stat.st_mode) or stat.S_ISLNK(objects_stat.st_mode):
        raise AdminCheckoutError("administrative checkout object store is unsafe")
    markers = (
        git_dir / "commondir",
        git_dir / "shallow",
        git_dir / "info" / "grafts",
        objects_root / "info" / "alternates",
        objects_root / "info" / "http-alternates",
    )
    try:
        if any(marker.exists() or marker.is_symlink() for marker in markers):
            raise AdminCheckoutError("administrative checkout object store is unsafe")
    except AdminCheckoutError:
        raise
    except OSError as exc:
        raise AdminCheckoutError("administrative checkout object store is unsafe") from exc


def _direct_checkout(checkout: Path) -> tuple[Path, os.stat_result]:
    try:
        root_stat = checkout.lstat()
        git_dir = checkout / ".git"
        git_stat = git_dir.lstat()
    except OSError as exc:
        raise AdminCheckoutError("administrative checkout is unavailable") from exc
    if not stat.S_ISDIR(root_stat.st_mode) or stat.S_ISLNK(root_stat.st_mode):
        raise AdminCheckoutError("administrative checkout root is unsafe")
    if not stat.S_ISDIR(git_stat.st_mode) or stat.S_ISLNK(git_stat.st_mode):
        raise AdminCheckoutError("administrative checkout Git directory is unsafe")
    if root_stat.st_uid != os.geteuid():
        raise AdminCheckoutError("administrative checkout ownership differs")
    _require_direct_object_store(git_dir)
    return git_dir, root_stat


def _local_config(checkout: Path) -> list[tuple[str, str]]:
    raw = _run_git(checkout, "config", "--local", "--null", "--list")
    fields = [field for field in raw.split(b"\0") if field]
    rows: list[tuple[str, str]] = []
    for field in fields:
        if b"\n" in field:
            key, value = field.split(b"\n", 1)
        elif b"=" in field:
            key, value = field.split(b"=", 1)
        else:
            key, value = field, b""
        try:
            rows.append((key.decode("utf-8").lower(), value.decode("utf-8")))
        except UnicodeDecodeError as exc:
            raise AdminCheckoutError("local Git configuration is invalid") from exc
    return rows


def _require_no_partial_config(checkout: Path) -> None:
    for key, _value in _local_config(checkout):
        if (
            key == "extensions.partialclone"
            or (key.startswith("remote.") and key.endswith(".promisor"))
            or (key.startswith("remote.") and key.endswith(".partialclonefilter"))
        ):
            raise AdminCheckoutError("partial clone configuration remains")
    if _run_git(checkout, "remote").strip():
        raise AdminCheckoutError("administrative checkout still has a remote")


def _require_complete_closure(checkout: Path, expected_commit: str) -> int:
    _require_direct_object_store(checkout / ".git")
    # Enumeration and every existence batch share the old ten-second bound.
    deadline = time.monotonic() + _GIT_TIMEOUT_SECONDS
    raw = _run_git(
        checkout,
        "rev-list",
        "--objects",
        "--missing=print",
        "--no-object-names",
        expected_commit,
        deadline=deadline,
    )
    objects: set[str] = set()
    for line in raw.splitlines():
        try:
            value = line.decode("ascii")
        except UnicodeDecodeError as exc:
            raise AdminCheckoutError("reachable object closure is incomplete") from exc
        if not _SHA.fullmatch(value) or value in objects:
            raise AdminCheckoutError("reachable object closure is incomplete")
        objects.add(value)
    if expected_commit not in objects:
        raise AdminCheckoutError("reachable object closure is incomplete")
    # A commit graph may enumerate a missing commit as an ordinary SHA. Every
    # enumerated object must cross the no-lazy-fetch object database boundary,
    # both on initial admission and on the caller's immediately pre-unlink pass.
    ordered = sorted(objects)
    for start in range(0, len(ordered), 4096):
        batch = ordered[start:start + 4096]
        observed = _run_git(
            checkout, "cat-file", "--buffer", "--batch-check=%(objectname) %(objecttype)",
            input_bytes=("\n".join(batch) + "\n").encode("ascii"), deadline=deadline,
        ).splitlines()
        if len(observed) != len(batch):
            raise AdminCheckoutError("reachable object closure is incomplete")
        for oid, line in zip(batch, observed):
            parts = line.split()
            if (
                len(parts) != 2
                or parts[0] != oid.encode("ascii")
                or parts[1] not in {b"blob", b"tree", b"commit"}
                or (oid == expected_commit and parts[1] != b"commit")
            ):
                raise AdminCheckoutError("reachable object closure is incomplete")
    return len(objects)


def _pack_directory(git_dir: Path) -> tuple[int, int, int, list[str]]:
    pack_dir = git_dir / "objects" / "pack"
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(pack_dir, flags)
    except OSError as exc:
        raise AdminCheckoutError("Git pack directory is unavailable") from exc
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISDIR(info.st_mode):
            raise AdminCheckoutError("Git pack directory is unsafe")
        names = sorted(os.listdir(descriptor))
        return descriptor, info.st_uid, info.st_gid, names
    except Exception:
        os.close(descriptor)
        raise


def _validated_markers(git_dir: Path, expected_uid: int, expected_gid: int) -> tuple[int, list[tuple[str, tuple[int, int, int, int, int]]]]:
    descriptor, pack_uid, pack_gid, names = _pack_directory(git_dir)
    try:
        pack_info = os.fstat(descriptor)
        if (
            pack_uid != expected_uid
            or pack_gid != expected_gid
            or stat.S_IMODE(pack_info.st_mode) & 0o022
        ):
            raise AdminCheckoutError("Git pack directory ownership differs")
        markers: list[tuple[str, tuple[int, int, int, int, int]]] = []
        for name in names:
            if not name.endswith(".promisor"):
                continue
            if _PROMISOR.fullmatch(name) is None:
                raise AdminCheckoutError("promisor marker is unsafe")
            try:
                info = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
            except OSError as exc:
                raise AdminCheckoutError("promisor marker is unsafe") from exc
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_nlink != 1
                or info.st_size != 0
                or info.st_uid != expected_uid
                or info.st_gid != expected_gid
                or stat.S_IMODE(info.st_mode) & 0o022
            ):
                raise AdminCheckoutError("promisor marker is unsafe")
            markers.append(
                (name, (info.st_dev, info.st_ino, info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode)))
            )
        return descriptor, markers
    except Exception:
        os.close(descriptor)
        raise


def normalize_admin_checkout(checkout: Path, *, expected_commit: str) -> dict[str, object]:
    """Normalize inherited empty promisor sidecars after complete local proof."""
    if _SHA.fullmatch(expected_commit) is None:
        raise AdminCheckoutError("expected commit is invalid")
    checkout = Path(checkout)
    git_dir, root_stat = _direct_checkout(checkout)
    head = _run_git(checkout, "rev-parse", "--verify", "HEAD^{commit}").decode("ascii").strip()
    if head != expected_commit:
        raise AdminCheckoutError("administrative checkout HEAD differs")
    _require_no_partial_config(checkout)
    object_count = _require_complete_closure(checkout, expected_commit)

    descriptor, markers = _validated_markers(git_dir, root_stat.st_uid, root_stat.st_gid)
    try:
        if markers:
            # Recheck all preconditions immediately before the first mutation. If any
            # evidence drifted, leave every marker untouched.
            head_now = _run_git(checkout, "rev-parse", "--verify", "HEAD^{commit}").decode("ascii").strip()
            if head_now != expected_commit:
                raise AdminCheckoutError("administrative checkout HEAD changed")
            _require_no_partial_config(checkout)
            _require_complete_closure(checkout, expected_commit)
            for name, identity in markers:
                info = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
                observed = (
                    info.st_dev,
                    info.st_ino,
                    info.st_uid,
                    info.st_gid,
                    stat.S_IMODE(info.st_mode),
                )
                if observed != identity or info.st_nlink != 1 or info.st_size != 0:
                    raise AdminCheckoutError("promisor marker is unsafe")
            for name, _identity in markers:
                os.unlink(name, dir_fd=descriptor)
        remaining = [name for name in os.listdir(descriptor) if name.endswith(".promisor")]
        if remaining:
            raise AdminCheckoutError("promisor marker normalization is incomplete")
    finally:
        os.close(descriptor)

    return {
        "schema": "mastermind.executive_admin_checkout_normalization.v1",
        "commit": expected_commit,
        "reachable_object_count": object_count,
        "normalized_promisor_markers": len(markers),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Normalize one complete Executive admin checkout")
    sub = parser.add_subparsers(dest="command", required=True)
    normalize = sub.add_parser("normalize")
    normalize.add_argument("--checkout", required=True)
    normalize.add_argument("--expected-commit", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = normalize_admin_checkout(
            Path(args.checkout), expected_commit=args.expected_commit
        )
    except (AdminCheckoutError, OSError, UnicodeError) as exc:
        print(json.dumps({"ok": False, "code": "ADMIN_CHECKOUT_NORMALIZATION_REFUSED"}))
        return 65
    print(json.dumps({"ok": True, **result}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
