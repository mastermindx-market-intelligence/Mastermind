"""Produce inert, exact-source Research Read candidates. Never install or start.

The selected Macro archive roots are an owner-reviewed import closure input;
this stager verifies their bytes, not production dependency sufficiency.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import tarfile

SCHEMA = "mastermind.research_read_stage.v1"
_SHA = re.compile(r"[0-9a-f]{40}\Z")
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
MAX_BYTES = 64 * 1024 * 1024
MAX_MEMBERS = 8192
UNIT_PATH = "ops/research_read_tunnel/mastermind-research-read.service"
LOCK_PATH = "requirements/research-read-linux-x86_64-py312.lock"
SERVER_PATH = "scripts/mastermind_research_read_server.py"
MASTERMIND_ROOTS = ("common", "control_plane", "integrations", SERVER_PATH, LOCK_PATH)


class StageRefused(ValueError):
    def __init__(self, code="STAGE_SOURCE_REFUSED"):
        self.code = code
        super().__init__(code)


def _git(source, *args, binary=False):
    environment = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    environment["GIT_OPTIONAL_LOCKS"] = "0"
    try:
        return subprocess.run(["git", "-C", str(source), *args], capture_output=True,
                              text=not binary, check=True, timeout=30, env=environment).stdout
    except (OSError, subprocess.SubprocessError):
        raise StageRefused() from None


def qualify_source(source: Path, commit: str, tree: str):
    try:
        if (not source.is_absolute() or not source.is_dir()
                or any(path.is_symlink() for path in (source, *source.parents))
                or type(commit) is not str or _SHA.fullmatch(commit) is None
                or type(tree) is not str or _SHA.fullmatch(tree) is None):
            raise StageRefused()
        if _git(source, "rev-parse", "HEAD").strip() != commit:
            raise StageRefused("STAGE_COMMIT_MISMATCH")
        if _git(source, "rev-parse", "HEAD^{tree}").strip() != tree:
            raise StageRefused("STAGE_TREE_MISMATCH")
        if _git(source, "status", "--porcelain", "--untracked-files=all"):
            raise StageRefused("STAGE_SOURCE_DIRTY")
    except StageRefused:
        raise
    except Exception:
        raise StageRefused() from None


def _paths(roots):
    if type(roots) not in (list, tuple) or not roots or len(roots) > 64:
        raise StageRefused("STAGE_PATH_REFUSED")
    checked = []
    for value in roots:
        if type(value) is not str or not value or len(value) > 500:
            raise StageRefused("STAGE_PATH_REFUSED")
        path = PurePosixPath(value)
        if (path.is_absolute() or str(path) != value or ".." in path.parts
                or any(part in {".git", ".lane"} or part.startswith(".env") for part in path.parts)
                or any(char in value for char in ("\\", "\x00", "*", "?", "[", "]", ":"))
                or value.startswith("-")):
            raise StageRefused("STAGE_PATH_REFUSED")
        checked.append(value)
    if len(set(checked)) != len(checked):
        raise StageRefused("STAGE_PATH_REFUSED")
    return tuple(checked)


def source_archive(source: Path, commit: str, tree: str, roots):
    qualify_source(source, commit, tree)
    paths = _paths(roots)
    count, size = 0, 0
    expected = {}
    # Bound source member sizes before retaining the archive in memory.
    listing = _git(source, "ls-tree", "-r", "-l", commit, "--", *paths)
    for row in listing.splitlines():
        header, name = row.split("\t", 1)
        mode, kind, _oid, length = header.split()
        if mode not in {"100644", "100755"} or kind != "blob" or length == "-":
            raise StageRefused("STAGE_MEMBER_REFUSED")
        _paths((name,))
        expected[name] = (int(length), _oid)
        count += 1
        size += int(length)
    if not count or count > MAX_MEMBERS or size + count * 2048 > MAX_BYTES:
        raise StageRefused("STAGE_ARCHIVE_BOUND")
    for root in paths:
        if not _git(source, "ls-tree", commit, "--", root).strip():
            raise StageRefused("STAGE_REQUIRED_SOURCE_MISSING")
    raw = _git(source, "archive", "--format=tar", commit, "--", *paths, binary=True)
    if len(raw) > MAX_BYTES:
        raise StageRefused("STAGE_ARCHIVE_BOUND")
    members = []
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:") as archive:
        rows = archive.getmembers()
        if len(rows) > MAX_MEMBERS:
            raise StageRefused("STAGE_ARCHIVE_BOUND")
        for member in rows:
            _paths((member.name.rstrip("/"),))
            if not member.isdir() and not member.isfile():
                raise StageRefused("STAGE_MEMBER_REFUSED")
            if member.isfile():
                body = archive.extractfile(member).read()
                identity = (len(body), hashlib.sha1(b"blob " + str(len(body)).encode()
                                                   + b"\x00" + body).hexdigest())
                if expected.get(member.name) != identity:
                    raise StageRefused("STAGE_ARCHIVE_IDENTITY_REFUSED")
                members.append({"path": member.name, "bytes": len(body),
                                "sha256": hashlib.sha256(body).hexdigest()})
    if {row["path"] for row in members} != set(expected):
        raise StageRefused("STAGE_ARCHIVE_IDENTITY_REFUSED")
    # Reject a source change during capture, including untracked content.
    qualify_source(source, commit, tree)
    return raw, members


def render_unit(template: str, *, commit: str, lock_sha256: str):
    if (_SHA.fullmatch(commit) is None or _DIGEST.fullmatch(lock_sha256) is None
            or template.count("@MASTERMIND_COMMIT@") != 2
            or template.count("@LOCK_SHA256@") != 1):
        raise StageRefused("STAGE_UNIT_REFUSED")
    rendered = template.replace("@MASTERMIND_COMMIT@", commit).replace("@LOCK_SHA256@", lock_sha256)
    required = {
        "User=mastermind-research", "Group=mastermind-research",
        f"WorkingDirectory=/opt/mastermind-research/releases/{commit}",
        f"ExecStart=/opt/mastermind-research/venvs/{lock_sha256}/bin/python -I -B "
        f"/opt/mastermind-research/releases/{commit}/{SERVER_PATH} "
        "--config /etc/mastermind/research-read-deployment.json",
        "EnvironmentFile=/etc/mastermind/research-read.env", "NoNewPrivileges=true",
        "ProtectSystem=strict", "ProtectHome=true", "PrivateTmp=true", "UMask=0077",
        "RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6",
        "CapabilityBoundingSet=", "AmbientCapabilities=",
    }
    allowed = required | {"[Unit]", "[Service]", "[Install]", "Type=simple",
        "Description=Mastermind Research Read MCP (pinned candidate)",
        "After=network-online.target", "Wants=network-online.target",
        "Restart=on-failure", "RestartSec=5", "WantedBy=multi-user.target"}
    lines = [line for line in rendered.splitlines() if line]
    if any(lines.count(line) != 1 for line in required) or any(line not in allowed for line in lines):
        raise StageRefused("STAGE_UNIT_REFUSED")
    return rendered


def prepare_bundle(*, mastermind_source: Path, mastermind_commit: str, mastermind_tree: str,
                   macro_source: Path, macro_commit: str, macro_tree: str,
                   macro_roots, output: Path):
    """Write a NEW candidate directory; no overwrites or install effects."""
    try:
        qualify_source(mastermind_source, mastermind_commit, mastermind_tree)
        # The launcher must exist at the exact selected commit before staging.
        lock = _git(mastermind_source, "show", f"{mastermind_commit}:{LOCK_PATH}", binary=True)
        template = _git(mastermind_source, "show", f"{mastermind_commit}:{UNIT_PATH}")
        unit = render_unit(template, commit=mastermind_commit,
                           lock_sha256=hashlib.sha256(lock).hexdigest()).encode()
        mm, mm_members = source_archive(mastermind_source, mastermind_commit,
                                        mastermind_tree, MASTERMIND_ROOTS)
        macro, macro_members = source_archive(macro_source, macro_commit, macro_tree, macro_roots)
        blobs = {"mastermind-release.tar": mm, "macro-release.tar": macro,
                 "mastermind-research-read.service": unit}
        manifest = {"schema": SCHEMA, "state": "INERT_CANDIDATE",
                    "mastermind_commit": mastermind_commit, "mastermind_tree": mastermind_tree,
                    "macro_commit": macro_commit, "macro_tree": macro_tree,
                    "dependency_lock_sha256": hashlib.sha256(lock).hexdigest(),
                    "macro_import_closure": "OWNER_QUALIFICATION_REQUIRED",
                    "files": [{"path": name, "bytes": len(raw),
                               "sha256": hashlib.sha256(raw).hexdigest()} for name, raw in blobs.items()],
                    "members": {"mastermind": mm_members, "macro": macro_members}}
        blobs["manifest.json"] = (json.dumps(manifest, sort_keys=True, indent=2) + "\n").encode()
        if (not output.is_absolute() or output.exists()
                or any(path.is_symlink() for path in output.parents)):
            raise StageRefused("STAGE_OUTPUT_REFUSED")
        output.mkdir(mode=0o700)
        for name, raw in blobs.items():
            descriptor = os.open(output / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(raw)
        return manifest
    except StageRefused:
        raise
    except Exception:
        raise StageRefused() from None
