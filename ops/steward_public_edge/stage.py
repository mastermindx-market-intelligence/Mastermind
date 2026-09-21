#!/usr/bin/env python3
"""Stage one immutable, inert Steward public-edge release bundle.

This command verifies an exact clean Git source identity and emits a bounded
release archive plus rendered systemd/Caddy candidates. It performs no service,
proxy, DNS, OAuth, Workspace, provider, or production effect.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path
from typing import Any

SCHEMA = "mastermind.steward_public_edge_stage.v1"
PUBLIC_HOST = "mcp.mastermind-x.com"
RESOURCE_PATH = "/mcp/steward/v1"
METADATA_PATH = "/.well-known/oauth-protected-resource/mcp/steward/v1"
RESOURCE_URL = f"https://{PUBLIC_HOST}{RESOURCE_PATH}"
METADATA_URL = f"https://{PUBLIC_HOST}{METADATA_PATH}"
UNIT_TEMPLATE = "ops/steward_public_edge/mastermind-steward.service"
CADDY_TEMPLATE = "ops/steward_public_edge/mastermind-steward.caddy"
CADDY_TEMPLATE_SHA256 = "bde4f3a14d6289bdca12ee593220837ff2e02a08f405a687991102190b6ed7b3"
ARCHIVE_NAME = "steward-release.tar"
UNIT_NAME = "mastermind-steward.service"
CADDY_NAME = "mastermind-steward.caddy"
MANIFEST_NAME = "manifest.json"
RELEASE_ROOTS = (
    "common",
    "control_plane",
    "integrations",
    "scripts/mastermind_steward_app.py",
)
MAX_ARCHIVE_BYTES = 64 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 8192
OUTPUT_DIR_MODE = 0o700
OUTPUT_FILE_MODE = 0o600

_SHA40 = re.compile(r"\A[0-9a-f]{40}\Z")
_SAFE_HOST = re.compile(r"\A[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?\Z")


class StageError(ValueError):
    """Fixed-code staging refusal; caller content never crosses this boundary."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _refuse(code: str) -> None:
    raise StageError(code)


def _run_git(source: Path, *args: str, text: bool = True) -> str | bytes:
    try:
        result = subprocess.run(
            ["git", "-C", os.fspath(source), *args],
            check=True,
            capture_output=True,
            text=text,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        _refuse("SOURCE_UNAVAILABLE")
    return result.stdout


def _source_identity(source: Path, commit: str, tree: str) -> tuple[str, str]:
    if (
        not source.is_absolute()
        or not source.is_dir()
        or source.is_symlink()
        or _SHA40.fullmatch(commit) is None
        or _SHA40.fullmatch(tree) is None
    ):
        _refuse("SOURCE_UNAVAILABLE")
    status = _run_git(source, "status", "--porcelain", "--untracked-files=all")
    if status:
        _refuse("SOURCE_DIRTY")
    observed_commit = str(_run_git(source, "rev-parse", "HEAD")).strip()
    observed_tree = str(_run_git(source, "rev-parse", "HEAD^{tree}")).strip()
    if observed_commit != commit:
        _refuse("SOURCE_COMMIT_MISMATCH")
    if observed_tree != tree:
        _refuse("SOURCE_TREE_MISMATCH")
    return observed_commit, observed_tree


def _git_text(source: Path, commit: str, path: str) -> str:
    raw = _run_git(source, "show", f"{commit}:{path}", text=False)
    assert isinstance(raw, bytes)
    try:
        return raw.decode("utf-8", errors="strict")
    except UnicodeError:
        _refuse("TEMPLATE_INVALID")


def _render_unit(template: str, commit: str) -> str:
    if template.count("@EXPECTED_COMMIT@") != 2:
        _refuse("UNIT_TEMPLATE_INVALID")
    rendered = template.replace("@EXPECTED_COMMIT@", commit)
    required = (
        "User=mastermind-steward",
        "Group=mastermind-steward",
        f"WorkingDirectory=/opt/mastermind-steward/releases/{commit}",
        (
            "ExecStart=/opt/mastermind/.venv/bin/python -I -B "
            f"/opt/mastermind-steward/releases/{commit}/scripts/mastermind_steward_app.py "
            "--transport http --repo-root /opt/mastermind --macro-root /opt/macro "
            "--policy-file /etc/mastermind/steward-policy.json "
            "--host 127.0.0.1 --port 8766"
        ),
        "NoNewPrivileges=true",
        "ProtectSystem=strict",
        "ProtectHome=true",
        "RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6",
        "CapabilityBoundingSet=",
        "AmbientCapabilities=",
    )
    lines = rendered.splitlines()
    if any(lines.count(item) != 1 for item in required):
        _refuse("UNIT_TEMPLATE_INVALID")
    forbidden = (
        "User=root",
        "Group=root",
        "EnvironmentFile=",
        "0.0.0.0",
        " --host ::",
        "CAP_NET_BIND_SERVICE",
        "ExecStartPre=",
        "ExecStartPost=",
        "ExecReload=",
    )
    if any(item in rendered for item in forbidden):
        _refuse("UNIT_TEMPLATE_INVALID")
    return rendered


def _render_caddy(template: str) -> str:
    if (
        _SAFE_HOST.fullmatch(PUBLIC_HOST) is None
        or hashlib.sha256(template.encode("utf-8")).hexdigest() != CADDY_TEMPLATE_SHA256
        or template.count("@PUBLIC_HOST@") != 3
    ):
        _refuse("CADDY_TEMPLATE_INVALID")
    rendered = template.replace("@PUBLIC_HOST@", PUBLIC_HOST)
    required = (
        f"{PUBLIC_HOST} {{",
        f"path {METADATA_PATH}",
        f"path {RESOURCE_PATH}",
        "method GET POST DELETE",
        "reverse_proxy 127.0.0.1:8766",
        f"header_up Host {PUBLIC_HOST}",
        "header_up X-Forwarded-Proto https",
        "max_size 64KB",
        "abort",
    )
    if any(item not in rendered for item in required):
        _refuse("CADDY_TEMPLATE_INVALID")
    if rendered.count("reverse_proxy 127.0.0.1:8766") != 2:
        _refuse("CADDY_TEMPLATE_INVALID")
    forbidden = (
        "control.mastermind-x.com",
        "0.0.0.0",
        "reverse_proxy *",
        "forward_auth",
        "handle /mcp/*",
        "path /mcp/*",
        "log {",
        "debug",
    )
    if any(item in rendered for item in forbidden):
        _refuse("CADDY_TEMPLATE_INVALID")
    return rendered


def _reject_symlink_components(path: Path) -> None:
    if not path.is_absolute():
        _refuse("OUTPUT_PATH_REFUSED")
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current = current / part
        try:
            info = current.lstat()
        except OSError:
            _refuse("OUTPUT_PATH_REFUSED")
        if stat.S_ISLNK(info.st_mode):
            _refuse("OUTPUT_PATH_REFUSED")


def _safe_output(source: Path, output: Path) -> Path:
    if not output.is_absolute():
        _refuse("OUTPUT_PATH_REFUSED")
    _reject_symlink_components(output.parent)
    try:
        source_real = source.resolve(strict=True)
        output_real = output.resolve(strict=False)
        parent = output.parent.resolve(strict=True)
        parent_info = parent.lstat()
    except OSError:
        _refuse("OUTPUT_PATH_REFUSED")
    if (
        output_real == source_real
        or source_real in output_real.parents
        or output_real in source_real.parents
        or stat.S_ISLNK(parent_info.st_mode)
        or parent_info.st_uid != os.getuid()
        or os.path.lexists(output)
    ):
        _refuse("OUTPUT_PATH_REFUSED")
    return parent


def _archive_member_allowed(name: str, *, is_directory: bool) -> bool:
    """Admit release roots plus only the directory ancestors needed to reach them."""
    if any(name == root or name.startswith(root + "/") for root in RELEASE_ROOTS):
        return True
    ancestors = {
        "/".join(Path(root).parts[:index])
        for root in RELEASE_ROOTS
        for index in range(1, len(Path(root).parts))
    }
    return is_directory and name in ancestors


def _archive(source: Path, commit: str, target: Path) -> tuple[str, int, int, int]:
    try:
        with target.open("xb") as stream:
            subprocess.run(
                [
                    "git", "-C", os.fspath(source), "archive", "--format=tar",
                    commit, "--", *RELEASE_ROOTS,
                ],
                check=True,
                stdout=stream,
                stderr=subprocess.PIPE,
                timeout=60,
            )
            stream.flush()
            os.fsync(stream.fileno())
    except (OSError, subprocess.SubprocessError):
        _refuse("ARCHIVE_FAILED")
    try:
        size = target.stat().st_size
    except OSError:
        _refuse("ARCHIVE_FAILED")
    if not 0 < size <= MAX_ARCHIVE_BYTES:
        _refuse("ARCHIVE_FAILED")
    count = 0
    expanded = 0
    try:
        with tarfile.open(target, mode="r:") as archive:
            for member in archive.getmembers():
                count += 1
                if count > MAX_ARCHIVE_MEMBERS:
                    _refuse("ARCHIVE_FAILED")
                path = Path(member.name)
                if (
                    path.is_absolute()
                    or not path.parts
                    or any(part in {"", ".", ".."} for part in path.parts)
                    or not (member.isfile() or member.isdir())
                ):
                    _refuse("ARCHIVE_FAILED")
                if not _archive_member_allowed(
                    member.name, is_directory=member.isdir(),
                ):
                    _refuse("ARCHIVE_FAILED")
                if member.isfile():
                    expanded += member.size
                    if expanded > MAX_ARCHIVE_BYTES:
                        _refuse("ARCHIVE_FAILED")
    except (OSError, tarfile.TarError):
        _refuse("ARCHIVE_FAILED")
    return _sha256_file(target), count, expanded, size


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            while True:
                block = stream.read(1024 * 1024)
                if not block:
                    break
                digest.update(block)
    except OSError:
        _refuse("READBACK_FAILED")
    return digest.hexdigest()


def _write(path: Path, content: bytes) -> str:
    try:
        with path.open("xb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(path, OUTPUT_FILE_MODE)
    except OSError:
        _refuse("WRITE_FAILED")
    return _sha256_file(path)


def _sha256_fd_exact(fd: int, expected_size: int) -> str | None:
    """Hash exactly the admitted size plus one bounded overflow observation."""
    if not 0 <= expected_size <= MAX_ARCHIVE_BYTES:
        return None
    digest = hashlib.sha256()
    remaining = expected_size
    while remaining:
        block = os.read(fd, min(remaining, 1024 * 1024))
        if not block:
            return None
        digest.update(block)
        remaining -= len(block)
    if os.read(fd, 1):
        return None
    return digest.hexdigest()


def _published_bundle_matches(
    output: Path, expected: dict[str, tuple[str, int]],
) -> bool:
    """Bounded, read-only verification of a possibly published release directory."""
    directory_fd = -1
    try:
        directory_flags = os.O_RDONLY
        directory_flags |= getattr(os, "O_DIRECTORY", 0)
        directory_flags |= getattr(os, "O_NOFOLLOW", 0)
        directory_fd = os.open(output, directory_flags)
        output_info = os.fstat(directory_fd)
        if (
            not stat.S_ISDIR(output_info.st_mode)
            or output_info.st_uid != os.getuid()
            or stat.S_IMODE(output_info.st_mode) != OUTPUT_DIR_MODE
        ):
            return False
        names: list[str] = []
        with os.scandir(directory_fd) as entries:
            for entry in entries:
                names.append(entry.name)
                if len(names) > len(expected):
                    return False
        if set(names) != set(expected):
            return False
        file_flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        for name in names:
            expected_digest, expected_size = expected[name]
            file_fd = os.open(name, file_flags, dir_fd=directory_fd)
            try:
                before = os.fstat(file_fd)
                if (
                    not stat.S_ISREG(before.st_mode)
                    or before.st_uid != os.getuid()
                    or stat.S_IMODE(before.st_mode) != OUTPUT_FILE_MODE
                    or before.st_size != expected_size
                    or _sha256_fd_exact(file_fd, expected_size) != expected_digest
                ):
                    return False
                after = os.fstat(file_fd)
                if (
                    after.st_dev != before.st_dev
                    or after.st_ino != before.st_ino
                    or after.st_uid != os.getuid()
                    or after.st_size != expected_size
                    or stat.S_IMODE(after.st_mode) != OUTPUT_FILE_MODE
                ):
                    return False
            finally:
                os.close(file_fd)
    except (OSError, TypeError, ValueError):
        return False
    finally:
        if directory_fd >= 0:
            try:
                os.close(directory_fd)
            except OSError:
                pass
    return True


def _canonical_json(value: Any) -> bytes:
    try:
        return (
            json.dumps(
                value,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
                allow_nan=False,
            )
            + "\n"
        ).encode("ascii")
    except (TypeError, ValueError, UnicodeError, RecursionError):
        _refuse("INTERNAL_ERROR")


def stage(
    *,
    source_repo: Path,
    accepted_commit: str,
    accepted_tree: str,
    output_dir: Path,
) -> dict[str, Any]:
    source = source_repo.expanduser()
    output = output_dir.expanduser()
    _source_identity(source, accepted_commit, accepted_tree)
    parent = _safe_output(source, output)

    unit = _render_unit(_git_text(source, accepted_commit, UNIT_TEMPLATE), accepted_commit)
    caddy = _render_caddy(_git_text(source, accepted_commit, CADDY_TEMPLATE))

    temporary = Path(
        tempfile.mkdtemp(prefix=f".steward-stage-{accepted_commit[:12]}-", dir=parent)
    )
    os.chmod(temporary, OUTPUT_DIR_MODE)
    published = False
    try:
        archive_path = temporary / ARCHIVE_NAME
        archive_digest, member_count, expanded_bytes, archive_size = _archive(
            source, accepted_commit, archive_path
        )
        os.chmod(archive_path, OUTPUT_FILE_MODE)
        unit_bytes = unit.encode("utf-8")
        caddy_bytes = caddy.encode("utf-8")
        unit_digest = _write(temporary / UNIT_NAME, unit_bytes)
        caddy_digest = _write(temporary / CADDY_NAME, caddy_bytes)
        manifest = {
            "schema": SCHEMA,
            "status": "STAGED_INERT",
            "source_commit": accepted_commit,
            "source_tree": accepted_tree,
            "public_host": PUBLIC_HOST,
            "resource_url": RESOURCE_URL,
            "resource_metadata_url": METADATA_URL,
            "release_roots": list(RELEASE_ROOTS),
            "archive": {
                "name": ARCHIVE_NAME,
                "sha256": archive_digest,
                "member_count": member_count,
                "expanded_bytes": expanded_bytes,
            },
            "unit": {"name": UNIT_NAME, "sha256": unit_digest},
            "caddy": {"name": CADDY_NAME, "sha256": caddy_digest},
            "service_effect_applied": False,
            "proxy_effect_applied": False,
            "dns_effect_applied": False,
            "oauth_effect_applied": False,
            "workspace_effect_applied": False,
            "provider_effect_applied": False,
            "production_acceptance_granted": False,
        }
        manifest_bytes = _canonical_json(manifest)
        manifest_digest = _write(temporary / MANIFEST_NAME, manifest_bytes)
        manifest["manifest_sha256"] = manifest_digest

        try:
            directory_fd = os.open(temporary, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except OSError:
            _refuse("WRITE_FAILED")

        expected = {
            ARCHIVE_NAME: (archive_digest, archive_size),
            UNIT_NAME: (unit_digest, len(unit_bytes)),
            CADDY_NAME: (caddy_digest, len(caddy_bytes)),
            MANIFEST_NAME: (manifest_digest, len(manifest_bytes)),
        }
        try:
            os.replace(temporary, output)
        except OSError:
            # Rename acknowledgement can fail after the directory moved. Inspect only
            # to bound the observation; never delete or claim a determinate outcome.
            _published_bundle_matches(output, expected)
            _refuse("PUBLISH_EFFECT_UNKNOWN")
        published = True
        try:
            parent_fd = os.open(parent, os.O_RDONLY)
            try:
                os.fsync(parent_fd)
            finally:
                os.close(parent_fd)
        except OSError:
            # The output may already be visible. Preserve it for same-carrier
            # reconciliation and return only the fixed uncertainty classification.
            _published_bundle_matches(output, expected)
            _refuse("PUBLISH_EFFECT_UNKNOWN")
        if not _published_bundle_matches(output, expected):
            _refuse("PUBLISH_EFFECT_UNKNOWN")
        return manifest
    finally:
        if not published and temporary.exists() and not temporary.is_symlink():
            for child in temporary.iterdir():
                if child.is_file() and not child.is_symlink():
                    child.unlink()
            temporary.rmdir()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-repo", required=True, type=Path)
    parser.add_argument("--accepted-commit", required=True)
    parser.add_argument("--accepted-tree", required=True)
    parser.add_argument("--output-dir", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(sys.argv[1:] if argv is None else argv)
    try:
        result = stage(
            source_repo=args.source_repo,
            accepted_commit=args.accepted_commit,
            accepted_tree=args.accepted_tree,
            output_dir=args.output_dir,
        )
    except StageError as exc:
        print(
            json.dumps(
                {"schema": SCHEMA, "ok": False, "error": exc.code},
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 2
    print(json.dumps({"ok": True, **result}, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
