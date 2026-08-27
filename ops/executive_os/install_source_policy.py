"""Fail-closed source identity policy for Executive OS installation.

The ordinary installer law remains exact protected-head installation. A
separate, explicit frozen-accepted-ancestor mode exists only for production
proof or recovery already bound to an older accepted release: the source
checkout must be exactly that release, its ``origin/master`` tracking ref must
equal a separately supplied protected-master SHA, and the release must be a
strict ancestor of that protected head.

For the privileged installer path, frozen mode also binds the installer code to
one clean checkout whose HEAD and ``origin/master`` are that same protected
master SHA. This module performs no fetch and no mutation; the operator runbook
must refresh ``origin/master`` immediately before invoking the root installer.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Sequence

_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_INSTALLER_REPO = Path(__file__).resolve().parents[2]


class InstallSourcePolicyError(RuntimeError):
    """The source checkout does not satisfy the reviewed install policy."""


def _require_sha(value: str, label: str) -> str:
    if _SHA_RE.fullmatch(value or "") is None:
        raise InstallSourcePolicyError(f"{label} must be one full lowercase SHA")
    return value


def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    try:
        completed = subprocess.run(
            ["/usr/bin/git", "--no-optional-locks", "-C", str(repo), *args],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise InstallSourcePolicyError("could not inspect source checkout") from exc
    if check and completed.returncode != 0:
        raise InstallSourcePolicyError("could not inspect source checkout")
    return completed


def _require_checkout(
    repo: Path,
    *,
    label: str,
    expected_head: str,
    expected_remote: str,
) -> None:
    repo = Path(repo)
    if not repo.is_absolute() or not repo.is_dir():
        raise InstallSourcePolicyError(f"{label} must be an absolute directory")

    head = _git(repo, "rev-parse", "HEAD").stdout.strip()
    if head != expected_head:
        raise InstallSourcePolicyError(
            f"{label} HEAD is not the exact expected SHA"
        )

    dirty = _git(
        repo,
        "status",
        "--porcelain=v1",
        "--untracked-files=normal",
    ).stdout
    if dirty:
        raise InstallSourcePolicyError(f"{label} is not clean")

    remote = _git(
        repo,
        "rev-parse",
        "refs/remotes/origin/master",
        check=False,
    )
    if remote.returncode != 0:
        raise InstallSourcePolicyError(
            f"{label} has no exact protected origin/master ref"
        )
    remote_sha = _require_sha(remote.stdout.strip(), f"{label} origin/master SHA")
    if remote_sha != expected_remote:
        raise InstallSourcePolicyError(
            f"{label} origin/master differs from the attested protected master SHA"
        )


def validate_install_source(
    *,
    source_repo: Path,
    expected_sha: str,
    protected_master_sha: str | None,
    allow_frozen_accepted_ancestor: bool,
    installer_repo: Path | None = None,
) -> dict[str, str]:
    """Validate one immutable install source without mutating Git state."""

    source_repo = Path(source_repo)
    expected_sha = _require_sha(expected_sha, "expected SHA")
    if not source_repo.is_absolute() or not source_repo.is_dir():
        raise InstallSourcePolicyError("source checkout must be an absolute directory")

    head = _git(source_repo, "rev-parse", "HEAD").stdout.strip()
    if head != expected_sha:
        raise InstallSourcePolicyError("source checkout HEAD is not the exact expected SHA")

    dirty = _git(
        source_repo,
        "status",
        "--porcelain=v1",
        "--untracked-files=normal",
    ).stdout
    if dirty:
        raise InstallSourcePolicyError("source checkout is not clean")

    remote = _git(
        source_repo,
        "rev-parse",
        "refs/remotes/origin/master",
        check=False,
    )
    if remote.returncode != 0:
        raise InstallSourcePolicyError("checkout has no exact protected origin/master ref")
    remote_sha = _require_sha(remote.stdout.strip(), "origin/master SHA")

    if not allow_frozen_accepted_ancestor:
        if protected_master_sha is not None or installer_repo is not None:
            raise InstallSourcePolicyError(
                "frozen install arguments are only valid in frozen accepted ancestor mode"
            )
        if remote_sha != expected_sha:
            raise InstallSourcePolicyError(
                "expected SHA is not the checkout's exact origin/master"
            )
        return {
            "expected_sha": expected_sha,
            "mode": "exact_protected_master",
            "protected_master_sha": remote_sha,
        }

    if protected_master_sha is None:
        raise InstallSourcePolicyError(
            "frozen accepted ancestor mode requires protected master SHA"
        )
    protected_master_sha = _require_sha(
        protected_master_sha,
        "protected master SHA",
    )
    if remote_sha != protected_master_sha:
        raise InstallSourcePolicyError(
            "checkout origin/master differs from the attested protected master SHA"
        )
    if expected_sha == protected_master_sha:
        raise InstallSourcePolicyError(
            "frozen accepted release must be a strict ancestor of protected master"
        )

    ancestry = _git(
        source_repo,
        "merge-base",
        "--is-ancestor",
        expected_sha,
        protected_master_sha,
        check=False,
    )
    if ancestry.returncode != 0:
        raise InstallSourcePolicyError(
            "frozen accepted release is not an ancestor of protected master"
        )

    if installer_repo is not None:
        _require_checkout(
            Path(installer_repo),
            label="installer checkout",
            expected_head=protected_master_sha,
            expected_remote=protected_master_sha,
        )

    return {
        "expected_sha": expected_sha,
        "mode": "frozen_accepted_ancestor",
        "protected_master_sha": protected_master_sha,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate Executive install source identity")
    parser.add_argument("--source-repo", required=True)
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--protected-master-sha")
    parser.add_argument("--allow-frozen-accepted-ancestor", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        receipt = validate_install_source(
            source_repo=Path(args.source_repo),
            expected_sha=args.expected_sha,
            protected_master_sha=args.protected_master_sha,
            allow_frozen_accepted_ancestor=args.allow_frozen_accepted_ancestor,
            installer_repo=(
                _INSTALLER_REPO if args.allow_frozen_accepted_ancestor else None
            ),
        )
    except InstallSourcePolicyError as exc:
        print(str(exc), file=sys.stderr)
        return 65
    print(json.dumps(receipt, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "InstallSourcePolicyError",
    "build_parser",
    "main",
    "validate_install_source",
]
