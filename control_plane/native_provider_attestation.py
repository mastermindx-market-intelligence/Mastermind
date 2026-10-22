"""Root-produced native Claude CLI/SDK attestation, not account readiness.

The producer consumes the existing installation receipts. The startup reader
checks their sealed postimage without launching a provider, importing its SDK,
reading credentials, or manufacturing a Worker Broker readiness receipt.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from control_plane.codex_provider_realm import _native_open, ProviderRealmError
from control_plane.fs_security import has_macos_acl, FilesystemSecurityError
from control_plane.worker_execution_contract import BinaryAttestation

SCHEMA = "mastermind.native_claude_attestation/v2"
CLAUDE_TEAM = "Q6L2SF6YDW"
CLI_VERSION = "2.1.275"
SDK_VERSION = "0.2.160"
_ROOT_UID = 0
_LIMIT = 65536
_IDENTITY = ("device", "inode", "size", "mode", "uid", "gid", "mtime_ns", "ctime_ns")
_DURABLE_IDENTITY = ("inode", "size", "mode", "uid", "gid", "mtime_ns", "ctime_ns")


class NativeAttestationError(ValueError):
    """Native installation authority is absent, malformed, or stale."""


def _fail(message):
    raise NativeAttestationError(message)


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _identity(info):
    return dict(zip(_IDENTITY, (info.st_dev, info.st_ino, info.st_size,
        stat.S_IMODE(info.st_mode), info.st_uid, info.st_gid, info.st_mtime_ns, info.st_ctime_ns)))


def _durable_identity(info):
    full = _identity(info)
    return {key: full[key] for key in _DURABLE_IDENTITY}


def _runtime_identity(path):
    with _native_open(Path(path)) as (fd, info):
        _check_entry(Path(path), fd, info)
        return _identity(info)


def _check_entry(path, fd, info, directory=False):
    if (not (stat.S_ISDIR if directory else stat.S_ISREG)(info.st_mode)
            or info.st_uid != _ROOT_UID or info.st_mode & 0o022
            or (not directory and info.st_nlink != 1)
            or has_macos_acl(path, descriptor=fd, expected_identity=info)):
        _fail("native installation custody is unsafe")


def _read(fd, limit):
    data = bytearray()
    while len(data) <= limit:
        block = os.read(fd, min(65536, limit + 1 - len(data)))
        if not block:
            break
        data.extend(block)
    if len(data) > limit:
        _fail("native receipt exceeds its bound")
    return bytes(data)


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            _fail("duplicate native receipt field")
        result[key] = value
    return result


def _json_receipt(path, *, mode, gid=None, digest=None):
    with _native_open(Path(path)) as (fd, info):
        if stat.S_IMODE(info.st_mode) != mode or (gid is not None and info.st_gid != gid):
            _fail("native receipt mode/group differs from its consumer")
        if not 0 < info.st_size <= _LIMIT:
            _fail("native receipt size is invalid")
        raw = _read(fd, _LIMIT)
        if len(raw) != info.st_size or (digest is not None and hashlib.sha256(raw).hexdigest() != digest):
            _fail("native source receipt changed")
        value = json.loads(raw, object_pairs_hook=_pairs,
                           parse_constant=lambda _: _fail("non-finite receipt value"))
        if not isinstance(value, dict):
            _fail("native receipt is not an object")
        return value


def _file_observation(path, *, content=False):
    with _native_open(Path(path)) as (fd, info):
        _check_entry(Path(path), fd, info)
        result = {"path": str(path), "identity": _durable_identity(info)}
        if content:
            if not 0 < info.st_size <= 512 * 1024 * 1024:
                _fail("native executable size is invalid")
            digest = hashlib.sha256()
            while block := os.read(fd, 1024 * 1024):
                digest.update(block)
            result["sha256"] = digest.hexdigest()
        return result


def _sdk_tree(root, *, content=False):
    """Seal every SDK entry through held descriptors; no symlinks or imports."""
    identities, contents = [], []
    total_bytes = 0
    def visit(fd, path, relative):
        nonlocal total_bytes
        before = os.fstat(fd)
        _check_entry(path, fd, before, directory=True)
        identities.append([relative, "directory", _durable_identity(before)])
        with os.scandir(fd) as entries:
            names = sorted(entry.name for entry in entries)
        for name in names:
            if len(identities) >= 20000:
                _fail("native SDK tree exceeds entry bound")
            child_path, rel = path / name, f"{relative}/{name}"
            info = os.stat(name, dir_fd=fd, follow_symlinks=False)
            directory = stat.S_ISDIR(info.st_mode)
            flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK
            if directory:
                flags |= os.O_DIRECTORY
            child = os.open(name, flags, dir_fd=fd)
            try:
                current = os.fstat(child)
                if _identity(current) != _identity(info):
                    _fail("native SDK entry changed while opening")
                _check_entry(child_path, child, current, directory=directory)
                if directory:
                    visit(child, child_path, rel)
                else:
                    identities.append([rel, "file", _durable_identity(current)])
                    total_bytes += current.st_size
                    if total_bytes > 4 * 1024**3:
                        _fail("native SDK tree exceeds byte bound")
                    if content:
                        digest = hashlib.sha256()
                        while block := os.read(child, 1024 * 1024):
                            digest.update(block)
                        contents.append([rel, digest.hexdigest()])
                if _identity(os.fstat(child)) != _identity(current):
                    _fail("native SDK entry changed during observation")
            finally:
                os.close(child)
        if _identity(os.fstat(fd)) != _identity(before):
            _fail("native SDK directory changed during observation")
    with _native_open(Path(root), directory=True) as (fd, _):
        readable = os.open(".", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=fd)
        try:
            visit(readable, Path(root), ".")
        finally:
            os.close(readable)
    return {"entries": len(identities), "identity_sha256": hashlib.sha256(_canonical(identities)).hexdigest(),
            "content_sha256": hashlib.sha256(_canonical(contents)).hexdigest() if content else None}


def build_native_claude_attestation(*, binary_path: Path, sdk_python: Path,
        cli_provision_receipt: Path, cli_receipt_sha256: str,
        sdk_provision_receipt: Path, sdk_receipt_sha256: str) -> dict:
    """Root-only installation observation. Publication is the installer owner's act."""
    if os.geteuid() != _ROOT_UID:
        _fail("native attestation producer requires root")
    # The incumbent host provisioner finalized its root-only receipt at 0600.
    # Consume its pinned bytes without changing that historical artifact.
    cli_source = _json_receipt(cli_provision_receipt, mode=0o600, digest=cli_receipt_sha256)
    sdk_source = _json_receipt(sdk_provision_receipt, mode=0o400, digest=sdk_receipt_sha256)
    if (cli_source.get("schema") != "mastermind.claude_native_host_provision.v1"
            or cli_source.get("status") != "PROVISIONED_NOT_AUTHENTICATED"
            or cli_source.get("binary") != str(binary_path)
            or cli_source.get("version_under_principal") != f"{CLI_VERSION} (Claude Code)"
            or sdk_source.get("status") != "INSTALLED_IMPORT_PROVEN"
            or sdk_source.get("python_path") != str(sdk_python)
            or sdk_source.get("import_probe", {}).get("sdk") != SDK_VERSION):
        _fail("native provision evidence is not the qualified installation")
    cli = _file_observation(binary_path, content=True)
    python = _file_observation(sdk_python, content=True)
    cli_runtime = _runtime_identity(binary_path)
    python_runtime = _runtime_identity(sdk_python)
    if ({key: cli_runtime[key] for key in _DURABLE_IDENTITY} != cli["identity"]
            or {key: python_runtime[key] for key in _DURABLE_IDENTITY} != python["identity"]
            or cli["sha256"] != cli_source.get("binary_sha256")
            or python["sha256"] != sdk_source.get("python_sha256")
            or not cli["identity"]["mode"] & 0o111
            or not python["identity"]["mode"] & 0o111):
        _fail("native executable differs from its installation receipt")
    env = {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "HOME": "/var/empty", "LANG": "C"}
    subprocess.run(["/usr/bin/codesign", "--verify", "--strict", str(binary_path)],
                   check=True, capture_output=True, timeout=60, env=env)
    signing = subprocess.run(["/usr/bin/codesign", "-dv", "--verbose=4", str(binary_path)],
                   check=True, capture_output=True, timeout=30, env=env)
    if f"TeamIdentifier={CLAUDE_TEAM}" not in signing.stderr.decode().splitlines():
        _fail("native Claude signer is not qualified")
    sdk_root = sdk_python.parent.parent
    if sdk_source.get("target") != str(sdk_root):
        _fail("SDK root differs from provisioned target")
    tree = _sdk_tree(sdk_root, content=True)
    if _runtime_identity(binary_path) != cli_runtime:
        _fail("native CLI changed during attestation")
    if _runtime_identity(sdk_python) != python_runtime:
        _fail("native SDK interpreter changed during attestation")
    cli.update(version=CLI_VERSION, team_identifier=CLAUDE_TEAM)
    return {"schema_version": SCHEMA, "recorded_at": datetime.now(timezone.utc).isoformat(),
            "cli": cli, "sdk": {"python": python, "root": str(sdk_root), "version": SDK_VERSION, **tree},
            "source_receipts": {"cli": {"path": str(cli_provision_receipt), "sha256": cli_receipt_sha256},
                                "sdk": {"path": str(sdk_provision_receipt), "sha256": sdk_receipt_sha256}}}


def _require_shape(document):
    if set(document) != {"schema_version", "recorded_at", "cli", "sdk", "source_receipts"} or document["schema_version"] != SCHEMA:
        _fail("native attestation schema differs")
    cli, sdk = document["cli"], document["sdk"]
    if (not isinstance(cli, dict) or set(cli) != {"path", "identity", "sha256", "version", "team_identifier"}
            or not isinstance(sdk, dict) or set(sdk) != {"python", "root", "version", "entries", "identity_sha256", "content_sha256"}
            or not isinstance(sdk["python"], dict) or set(sdk["python"]) != {"path", "identity", "sha256"}):
        _fail("native attestation fields differ")
    for executable in (cli, sdk["python"]):
        identity = executable["identity"]
        if (not isinstance(identity, dict) or set(identity) != set(_DURABLE_IDENTITY)
                or any(type(v) is not int or v < 0 for v in identity.values())
                or identity["uid"] != _ROOT_UID or identity["mode"] & 0o022 or not identity["mode"] & 0o111):
            _fail("native executable identity is malformed")
    for digest in (cli["sha256"], sdk["python"]["sha256"], sdk["identity_sha256"], sdk["content_sha256"]):
        if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            _fail("native attestation digest is malformed")
    if type(sdk["entries"]) is not int or not 1 <= sdk["entries"] <= 20000:
        _fail("native SDK count is malformed")
    sources = document["source_receipts"]
    if not isinstance(sources, dict) or set(sources) != {"cli", "sdk"}:
        _fail("native provenance is malformed")
    for source in sources.values():
        if (not isinstance(source, dict) or set(source) != {"path", "sha256"}
                or not isinstance(source["path"], str) or not Path(source["path"]).is_absolute()
                or not isinstance(source["sha256"], str) or re.fullmatch(r"[0-9a-f]{64}", source["sha256"]) is None):
            _fail("native provenance is malformed")
    try:
        recorded = datetime.fromisoformat(document["recorded_at"])
        if recorded.utcoffset() != timezone.utc.utcoffset(recorded):
            _fail("native attestation timestamp is not UTC")
    except (TypeError, ValueError):
        _fail("native attestation timestamp is invalid")


def load_native_claude_attestation(receipt_path: Path, *, expected_binary_path: Path,
        expected_owner_gid: int, allowed_versions: frozenset[str], sdk_python: Path) -> BinaryAttestation:
    """Check current CLI/SDK postimage without provider work or credential access."""
    try:
        document = _json_receipt(receipt_path, mode=0o440, gid=expected_owner_gid)
        _require_shape(document)
        cli, sdk = document["cli"], document["sdk"]
        if (cli["path"] != str(expected_binary_path) or cli["version"] != CLI_VERSION
                or cli["version"] not in allowed_versions or cli["team_identifier"] != CLAUDE_TEAM
                or sdk["python"]["path"] != str(sdk_python) or sdk["root"] != str(sdk_python.parent.parent)
                or sdk["version"] != SDK_VERSION):
            _fail("native receipt does not match the configured installation")
        for executable in (cli, sdk["python"]):
            if _file_observation(Path(executable["path"]))["identity"] != executable["identity"]:
                _fail("native executable changed since attestation")
        tree = _sdk_tree(Path(sdk["root"]))
        if tree["entries"] != sdk["entries"] or tree["identity_sha256"] != sdk["identity_sha256"]:
            _fail("native SDK changed since attestation")
        # Re-read root authority after observing its consumers; revocation wins.
        if _json_receipt(receipt_path, mode=0o440, gid=expected_owner_gid) != document:
            _fail("native receipt changed during observation")
        for executable in (cli, sdk["python"]):
            if _file_observation(Path(executable["path"]))["identity"] != executable["identity"]:
                _fail("native executable changed during SDK observation")
        runtime_identity = _runtime_identity(Path(cli["path"]))
        if {key: runtime_identity[key] for key in _DURABLE_IDENTITY} != cli["identity"]:
            _fail("native executable changed during final attestation")
        return BinaryAttestation(path=cli["path"], real_path=cli["path"], version=cli["version"],
            sha256=cli["sha256"], team_identifier=cli["team_identifier"],
            **{key: runtime_identity[key] for key in ("size", "device", "inode", "mode", "uid", "gid", "mtime_ns")})
    except (OSError, ProviderRealmError, FilesystemSecurityError, KeyError, TypeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NativeAttestationError("native attestation is unavailable or invalid") from exc
