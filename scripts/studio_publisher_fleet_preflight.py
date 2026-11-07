#!/usr/bin/env python3
"""Read-only Studio Direct publisher census; never substitutes for live app proof.

Installed accounts use one existing owner. This tool reads only bounded sealed
metadata and returns capability *expectations*, not credentials, admission,
a new registry, an installer, or a Git publication authority.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
from pathlib import Path

SCHEMA = "mastermind.studio_publisher_fleet_preflight.v1"
ACCOUNTS = (
    "chatgpt1", "chatgpt2-business", "chatgpt2-personal", "chatgpt3", "chatgpt4",
)
CLOSED_REPOSITORIES = frozenset(("mastermind", "macro", "terminal"))
REPOSITORY_GATEWAY = "17157fa5f8739dbe17aae767a335e97dd713a978dde9b192feb1b41a7b036b30"
PUBLISHER_GENERATIONS = {
    "d8f7f7712129094ce0ffac2eaeb66d15dd3f063a3ade9fa354de7af0d412477a": "INDEX_SYNC",
    "badd8a554ae8230808d18a1943aa49edb7ced51391ed2cbadb358cd015d62c3a": "MERGE_CAPABLE",
    "f67119198a0e63c34ae148633402a7ec3ab351ecf7f40a24bdc355b9890f8a2c": "MERGE_DIAGNOSTICS",
    "9d50cd828e51d0c08a7be0ca7b18c89bfd8fb767a548bb1e4deaddaf185225ae": "C4_LEGACY",
}
WORKSPACE_GENERATIONS = frozenset((
    "9c4c20dd4edbc426c8561801708ee205e19bb47b48134ec8f5654a10f1cb7cf3",
    "e4f74c201d177e6af1c3e113cc180430542cfd08a25591b81fb6d04c8a575db5",
))


class UnsafeRead(ValueError):
    """Conservative diagnostic refusal; never serialize exception internals."""


def bounded_bytes(path: Path, max_bytes: int = 2_000_000) -> bytes:
    # Reject special files after opening without waiting for a FIFO writer.
    # O_NONBLOCK has no effect on the regular files accepted below.
    flags = (os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
             | getattr(os, "O_NONBLOCK", 0))
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise UnsafeRead("FILE_UNAVAILABLE") from exc
    try:
        mode = os.fstat(fd).st_mode
        size = os.fstat(fd).st_size
        if not stat.S_ISREG(mode) or size > max_bytes:
            raise UnsafeRead("FILE_UNSAFE")
        data = os.read(fd, max_bytes + 1)
        if len(data) > max_bytes:
            raise UnsafeRead("FILE_OVERSIZE")
        return data
    finally:
        os.close(fd)


def digest(path: Path) -> str:
    return hashlib.sha256(bounded_bytes(path)).hexdigest()


def parse_object(path: Path) -> dict:
    try:
        value = json.loads(bounded_bytes(path))
    except UnsafeRead:
        raise
    except (ValueError, UnicodeError) as exc:
        raise UnsafeRead("JSON_INVALID") from exc
    if not isinstance(value, dict):
        raise UnsafeRead("JSON_INVALID")
    return value


def audit(root: Path, account: str) -> dict:
    if account not in ACCOUNTS:
        raise ValueError("ACCOUNT_NOT_ALLOWLISTED")
    base = root / account
    result = {
        "account": account,
        "effect_state": "NOT_APPLIED",
        "live_client_schema": "NOT_OBSERVED",
        "installation_proof": "NOT_OBSERVED",
    }
    try:
        if base.is_symlink() or not base.is_dir():
            raise UnsafeRead("ACCOUNT_UNAVAILABLE")
        config = parse_object(base / "config.json")
        manifest = parse_object(base / "manifest.json")
        if manifest.get("account") != account:
            raise UnsafeRead("MANIFEST_IDENTITY_MISMATCH")
        if config.get("accountLabel") != account:
            raise UnsafeRead("CONFIG_IDENTITY_MISMATCH")
        git_config = config.get("gitPublish")
        if not isinstance(git_config, dict) or git_config.get("enabled") is not True:
            raise UnsafeRead("PUBLISHER_NOT_CONFIGURED")
        routes = config.get("repositoryWorkspaces")
        repositories = []
        if routes is not None:
            if not isinstance(routes, dict) or routes.get("enabled") is not True:
                raise UnsafeRead("WORKSPACE_CONFIGURATION_INVALID")
            allowed = routes.get("allowedRepositories")
            if not isinstance(allowed, list) or not allowed or (
                any(not isinstance(x, str) or x not in CLOSED_REPOSITORIES for x in allowed)
            ) or len(set(allowed)) != len(allowed):
                raise UnsafeRead("WORKSPACE_CONFIGURATION_INVALID")
            repositories = sorted(allowed)

        gateway_sha = digest(base / "gateway.mjs")
        publisher_sha = digest(base / "git-publish.mjs")
        workspace_file = base / "workspace-access.mjs"
        workspace_sha = digest(workspace_file) if workspace_file.is_file() else None
        manifest_sha = digest(base / "manifest.json")
        pin = base / "state/native-pool-pin"
        # This is an existence observation, not a native-pin validity proof.
        if pin.is_symlink():
            raise UnsafeRead("PIN_PATH_UNSAFE")

        publisher_generation = PUBLISHER_GENERATIONS.get(publisher_sha, "UNRECOGNIZED")
        repository_schema_expected = bool(
            repositories and gateway_sha == REPOSITORY_GATEWAY
            and workspace_sha in WORKSPACE_GENERATIONS
        )
        result.update({
            "status": "OBSERVED",
            "configured_repositories": repositories or ["mastermind"],
            "repository_schema_expected": "YES" if repository_schema_expected else (
                "NO" if not repositories else "UNKNOWN"
            ),
            "merge_schema_expected": "YES" if publisher_generation in (
                "MERGE_CAPABLE", "MERGE_DIAGNOSTICS"
            ) and repository_schema_expected else (
                "NO" if publisher_generation in ("INDEX_SYNC", "C4_LEGACY") else "UNKNOWN"
            ),
            "publisher_generation": publisher_generation,
            "native_pin_owner_required": pin.exists(),
            "manifest_sha256": manifest_sha,
            "gateway_sha256": gateway_sha,
            "publisher_sha256": publisher_sha,
            "workspace_sha256": workspace_sha,
        })
    except UnsafeRead as exc:
        result.update({"status": "REFUSED", "reason": str(exc)})
    except (OSError, TypeError, KeyError):
        result.update({"status": "REFUSED", "reason": "INSPECTION_UNQUALIFIED"})
    return result


def scan(root: Path, accounts: tuple[str, ...] = ACCOUNTS) -> dict:
    return {
        "schema": SCHEMA,
        "effect_state": "NOT_APPLIED",
        "scope": "READ_ONLY_INSTALLED_FILES",
        "live_app_catalog_proven": False,
        "accounts": [audit(root, account) for account in accounts],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account", choices=ACCOUNTS, action="append")
    args = parser.parse_args()
    root = Path.home() / ".local/share/studio-direct-mcp/private"
    report = scan(root, tuple(dict.fromkeys(args.account)) if args.account else ACCOUNTS)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if all(row["status"] == "OBSERVED" for row in report["accounts"]) else 2


if __name__ == "__main__":
    raise SystemExit(main())
