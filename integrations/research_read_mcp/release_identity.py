"""Verify installed archive bytes against an independently pinned stage manifest.

The expected digest must come from secure owner configuration. This verifier
does not qualify dependency completeness, install files or create that trust.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import threading
import time
from dataclasses import asdict

from .runtime import (DEPLOYMENT_SCHEMA, READ_PORT_CONTRACT, RuntimeRefused,
                      _absolute, _identity, _json, parse_deployment, read_secure_json)
from . import CONTRACT

_SHA = re.compile(r"[0-9a-f]{40}\Z")
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_MANIFEST_FIELDS = frozenset({
    "schema", "state", "mastermind_commit", "mastermind_tree", "macro_commit", "macro_tree",
    "dependency_lock_sha256", "macro_import_closure", "files", "members",
})
_MAX_BYTES = 64 * 1024 * 1024
_MAX_MEMBERS = 8192
ARCHIVE_OWNER_SCHEMA = "mastermind.research_read_archive_owner.v1"
# v2 adds exactly one selected_read object to the SAME owner file. It is an
# explicit trusted local release-owner declaration, never independent evidence
# that writers have settled; actual issuance stays with real writer
# qualification. No default-true or default-selected behavior exists: a v1
# owner file admits no selected options at all.
SELECTED_ARCHIVE_OWNER_SCHEMA = "mastermind.research_read_archive_owner.v2"
MAX_SELECTED_OWNER_VALIDITY_SECONDS = 24 * 60 * 60
_OWNER_MANIFEST_FIELDS = frozenset({"schema", "manifest_path", "manifest_sha256"})
_SELECTED_OWNER_FIELDS = _OWNER_MANIFEST_FIELDS | {"selected_read"}
_SELECTED_READ_FIELDS = frozenset({
    "expected_producer_commit", "max_age_seconds", "max_reuse_seconds",
    "corpus_byte_budget", "image_admission_bytes", "refresh_interval_seconds",
    "writer_protocol_qualified", "valid_until",
})


def _refuse():
    raise RuntimeRefused("ARCHIVE_IDENTITY_REFUSED")


def _safe_path(value):
    if type(value) is not str or not value or len(value) > 500:
        _refuse()
    path = PurePosixPath(value)
    if (value == "." or path.is_absolute() or str(path) != value or ".." in path.parts
            or any(part in {".git", ".lane"} or part.startswith(".env") for part in path.parts)
            or "\\" in value or "\x00" in value):
        _refuse()
    return path


def _file_digest(path, expected_size, expected_uid):
    descriptor = None
    try:
        before = path.stat(follow_symlinks=False)
        if (not stat.S_ISREG(before.st_mode) or before.st_uid != expected_uid
                or before.st_mode & 0o022 or before.st_nlink != 1
                or before.st_size != expected_size):
            _refuse()
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        if _identity(before) != _identity(os.fstat(descriptor)):
            _refuse()
        digest, count = hashlib.sha256(), 0
        while True:
            chunk = os.read(descriptor, min(65536, expected_size - count + 1))
            if not chunk:
                break
            count += len(chunk)
            if count > expected_size:
                _refuse()
            digest.update(chunk)
        if (count != expected_size or _identity(before) != _identity(os.fstat(descriptor))
                or _identity(before) != _identity(path.stat(follow_symlinks=False))):
            _refuse()
        return digest.hexdigest(), _identity(before)
    except Exception:
        _refuse()

    finally:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                raise RuntimeRefused("ARCHIVE_CLOSE_UNCERTAIN") from None


def _walk(root, expected_uid):
    files, directories = set(), {}
    stack = [root]
    while stack:
        directory = stack.pop()
        info = directory.stat(follow_symlinks=False)
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != expected_uid
                or info.st_mode & 0o022):
            _refuse()
        directories[directory] = _identity(info)
        if len(directories) > _MAX_MEMBERS:
            _refuse()
        with os.scandir(directory) as entries:
            for entry in entries:
                path = Path(entry.path)
                relative = path.relative_to(root).as_posix()
                _safe_path(relative)
                if entry.is_symlink():
                    _refuse()
                if entry.is_dir(follow_symlinks=False):
                    stack.append(path)
                elif entry.is_file(follow_symlinks=False):
                    files.add(relative)
                else:
                    _refuse()
                if len(files) + len(directories) + len(stack) > _MAX_MEMBERS:
                    _refuse()
    return files, directories


def verify_archive_release(path: str, commit: str, tree: str, *, project: str,
                           manifest_path: str, expected_manifest_sha256: str,
                           manifest_owner_uid: int, release_owner_uid: int = 0):
    """Return a byte-integrity receipt; no deployment/readiness claim is made."""
    try:
        if (project not in {"mastermind", "macro"} or type(project) is not str
                or any(type(value) is not str or _SHA.fullmatch(value) is None
                       for value in (commit, tree))
                or type(expected_manifest_sha256) is not str
                or _DIGEST.fullmatch(expected_manifest_sha256) is None
                or type(release_owner_uid) is not int or release_owner_uid < 0):
            _refuse()
        root = Path(path)
        if (not root.is_absolute() or str(root) != path or root.name != commit
                or any(ancestor.is_symlink() for ancestor in (root, *root.parents))):
            _refuse()
        raw = read_secure_json(manifest_path, expected_owner_uid=manifest_owner_uid,
                               maximum=4 * 1024 * 1024)
        if hashlib.sha256(raw).hexdigest() != expected_manifest_sha256:
            _refuse()
        manifest = _json(raw, 4 * 1024 * 1024)
        if (type(manifest) is not dict or set(manifest) != _MANIFEST_FIELDS
                or manifest["schema"] != "mastermind.research_read_stage.v1"
                or manifest["state"] != "INERT_CANDIDATE"
                or manifest[project + "_commit"] != commit
                or manifest[project + "_tree"] != tree
                or type(manifest["members"]) is not dict
                or set(manifest["members"]) != {"mastermind", "macro"}):
            _refuse()
        rows = manifest["members"][project]
        if type(rows) is not list or not 0 < len(rows) <= _MAX_MEMBERS:
            _refuse()
        expected, total = {}, 0
        for row in rows:
            if type(row) is not dict or set(row) != {"path", "bytes", "sha256"}:
                _refuse()
            name = _safe_path(row["path"]).as_posix()
            size, digest = row["bytes"], row["sha256"]
            if (name in expected or type(size) is not int or not 0 <= size <= _MAX_BYTES
                    or type(digest) is not str or _DIGEST.fullmatch(digest) is None):
                _refuse()
            expected[name] = size, digest
            total += size
        if total > _MAX_BYTES:
            _refuse()
        files, directories = _walk(root, release_owner_uid)
        if files != set(expected):
            _refuse()
        expected_directories = {PurePosixPath(".")}
        for name in expected:
            expected_directories.update(PurePosixPath(name).parents)
        if {PurePosixPath(directory.relative_to(root).as_posix()) for directory in directories} != expected_directories:
            _refuse()
        identities = {}
        for name, (size, digest) in expected.items():
            actual, identity = _file_digest(root / name, size, release_owner_uid)
            if actual != digest:
                _refuse()
            identities[name] = identity
        # A later change cannot be hidden by checking only each file in isolation.
        final_files, final_directories = _walk(root, release_owner_uid)
        if final_files != files or final_directories != directories:
            _refuse()
        for name, identity in identities.items():
            if _identity((root / name).stat(follow_symlinks=False)) != identity:
                _refuse()
        if any(ancestor.is_symlink() for ancestor in (root, *root.parents)):
            _refuse()
        return {"state": "ARCHIVE_BYTES_VERIFIED", "project": project,
                "commit": commit, "tree": tree, "manifest_sha256": expected_manifest_sha256,
                "member_count": len(expected), "bytes": total,
                "dependency_closure": "OWNER_QUALIFICATION_REQUIRED"}
    except RuntimeRefused:
        raise
    except Exception:
        _refuse()


def _wall_now():
    """Injected wall-clock seam; tests may patch it, the contract never changes."""
    return time.time()


class _SelectedWriterPolicy:
    """Freshly reread the SAME admitted owner file bytes on every use.

    The callable returns False for an absent, unreadable, changed or expired
    owner file and keeps returning False for the rest of the process once any
    invalidation has actually been observed, even if the file is restored
    afterwards. The latch records only observed invalidation; it is not proof
    that a transient unobserved change could never have occurred. No network,
    source sweep or store access happens in this policy.
    """

    def __init__(self, path, owner_uid, admitted, valid_until):
        self._path = path
        self._owner_uid = owner_uid
        self._admitted = admitted
        self._valid_until = valid_until
        self._lock = threading.Lock()
        self._withdrawn = False

    def __call__(self):
        with self._lock:
            if self._withdrawn:
                return False
            try:
                raw = read_secure_json(self._path, expected_owner_uid=self._owner_uid,
                                       maximum=32768)
                if raw != self._admitted or int(_wall_now()) >= self._valid_until:
                    self._withdrawn = True
                    return False
            except Exception:
                self._withdrawn = True
                return False
            return True


def _selected_owner_options(selected, *, path, owner_uid, admitted):
    """Validate one explicit closed selected_read object into SelectedReadOptions.

    Every field must be present, no extra field may exist, the owner must have
    declared a currently qualified writer protocol and a future int
    valid_until no more than 24 hours away, and the numeric bounds are the existing SelectedReadOptions
    bounds. The producer commit is independent of the reader release commit.
    """
    try:
        if type(selected) is not dict or set(selected) != _SELECTED_READ_FIELDS:
            _refuse()
        valid_until = selected["valid_until"]
        now = int(_wall_now())
        # A finite horizon also rejects milliseconds mistaken for epoch seconds.
        # ``is True`` rejects JSON 1/1.0; a past or non-int valid_until never binds.
        if (selected["writer_protocol_qualified"] is not True
                or type(valid_until) is not int
                or not now < valid_until <= now + MAX_SELECTED_OWNER_VALIDITY_SECONDS):
            _refuse()
        from .selected_factory import SelectedReadOptions
        options = SelectedReadOptions(
            expected_producer_commit=selected["expected_producer_commit"],
            writer_policy=_SelectedWriterPolicy(path, owner_uid, admitted, valid_until),
            max_age_seconds=selected["max_age_seconds"],
            max_reuse_seconds=selected["max_reuse_seconds"],
            corpus_byte_budget=selected["corpus_byte_budget"],
            image_admission_bytes=selected["image_admission_bytes"],
            refresh_interval_seconds=selected["refresh_interval_seconds"])
        options.validate()
        return options
    except RuntimeRefused:
        raise
    except Exception:
        _refuse()


def load_archive_verifier(config_path, deployment, *, owner_uid, release_owner_uid=0):
    """Bind the runtime callback to separately secured owner-selected manifest trust.

    The callable re-verifies bytes on every invocation. Its receipts are evidence
    only, never a cached release admission. Reading configuration is explicit.
    A v1 owner file exposes ``selected_options is None``; a v2 owner file adds
    exactly one selected_read object and exposes validated SelectedReadOptions
    whose writer policy rereads this same owner file. Binding is not a serving
    or production-readiness claim.
    """
    try:
        # A manually constructed Deployment must pass the same closed parser.
        data = asdict(deployment)
        data.update(schema=DEPLOYMENT_SCHEMA, mode="production", server_contract=CONTRACT,
                    read_port_contract=READ_PORT_CONTRACT,
                    allowed_hosts=list(deployment.allowed_hosts),
                    allowed_origins=list(deployment.allowed_origins))
        qualified = parse_deployment(json.dumps(data).encode())
        raw = read_secure_json(config_path, expected_owner_uid=owner_uid, maximum=32768)
        config = _json(raw, 32768)
        if (type(config) is not dict
                or set(config) not in (_OWNER_MANIFEST_FIELDS, _SELECTED_OWNER_FIELDS)
                or config["schema"] not in (ARCHIVE_OWNER_SCHEMA, SELECTED_ARCHIVE_OWNER_SCHEMA)
                or type(config["manifest_sha256"]) is not str
                or _DIGEST.fullmatch(config["manifest_sha256"]) is None
                or type(release_owner_uid) is not int or release_owner_uid < 0):
            _refuse()
        # Schema and field set are bound together: a v1 file can never carry a
        # selected_read object and a v2 file must carry exactly one.
        if ((config["schema"] == ARCHIVE_OWNER_SCHEMA)
                != (set(config) == _OWNER_MANIFEST_FIELDS)):
            _refuse()
        _absolute(config["manifest_path"])
        selected_options = None
        if config["schema"] == SELECTED_ARCHIVE_OWNER_SCHEMA:
            selected_options = _selected_owner_options(config["selected_read"],
                                                       path=config_path, owner_uid=owner_uid,
                                                       admitted=raw)
        bindings = {
            (qualified.mastermind_release, qualified.mastermind_commit,
             qualified.mastermind_tree): "mastermind",
            (qualified.macro_release, qualified.macro_commit, qualified.macro_tree): "macro",
        }
    except RuntimeRefused:
        raise
    except Exception:
        _refuse()

    class BoundArchiveVerifier:
        def __init__(self):
            self._receipts = {}
            # v1 owner: None. v2 owner: validated SelectedReadOptions whose
            # writer policy is the current callback above; the launcher passes
            # this to the selected composition, never to a legacy fallback.
            self.selected_options = selected_options

        @property
        def receipts(self):
            return tuple(dict(receipt) for receipt in self._receipts.values())

        def __call__(self, path, commit, tree):
            try:
                project = bindings.get((path, commit, tree))
                if project is None:
                    _refuse()
                receipt = verify_archive_release(
                    path, commit, tree, project=project,
                    manifest_path=config["manifest_path"],
                    expected_manifest_sha256=config["manifest_sha256"],
                    manifest_owner_uid=owner_uid, release_owner_uid=release_owner_uid)
                self._receipts[project] = receipt
            except RuntimeRefused:
                raise
            except Exception:
                _refuse()
            return None

    return BoundArchiveVerifier()
